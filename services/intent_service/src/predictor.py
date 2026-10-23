"""Inference engine wrapper loading serialized model artifacts.
Supports both single-file pipeline and 3-component LinearSVC (Model, Vectorizer, LabelEncoder).
"""
import warnings
from pathlib import Path
from typing import Dict, List, Optional, Union
import joblib
import numpy as np
from scipy.special import softmax

try:
    from sklearn.exceptions import InconsistentVersionWarning
    warnings.filterwarnings("ignore", category=InconsistentVersionWarning)
except ImportError:
    pass

from contracts.schemas import IntentPredictionResponse
from services.intent_service.src.pipeline.dataset import TARGET_INTENTS


class IntentPredictor:
    """Production runtime inference engine for intent classification."""

    def __init__(self, model_source: Optional[Union[str, Path]] = None):
        # Auto-detect model directory or file, defaulting to production artifact
        if not model_source:
            root = Path(__file__).resolve().parent.parent.parent.parent
            default_path = root / "artifacts" / "models" / "intent_model.pkl"
            if default_path.exists():
                model_source = default_path

        self.model_source = Path(model_source) if model_source else None
        self.is_multi_component = False
        self.model = None
        self.vectorizer = None
        self.label_encoder = None
        self.classes: List[str] = []

        self.load_model()

    def _find_multi_component_dir(self) -> Optional[Path]:
        """Check known directories for the 3-component model artifacts."""
        candidates = []
        if self.model_source:
            if self.model_source.is_dir():
                candidates.append(self.model_source)
            else:
                candidates.append(self.model_source.parent)

        # Check standard project roots
        root = Path(__file__).resolve().parent.parent.parent.parent
        candidates.extend([
            root / "ML-model",
            root / "ML-modeel",
            root / "artifacts" / "models",
        ])

        for c in candidates:
            if c.exists() and (c / "model_intent_full.pkl").exists() and (c / "tfidf_vectorizer_full.pkl").exists() and (c / "label_encoder_full.pkl").exists():
                return c
        return None

    def load_model(self) -> None:
        """Load either the single pipeline .pkl or 3-component LinearSVC."""
        # 1. Prioritize explicit model file if provided
        if self.model_source and self.model_source.is_file() and self.model_source.exists():
            self.model = joblib.load(self.model_source)
            self.classes = [str(c) for c in getattr(self.model, "classes_", [])]
            self.is_multi_component = False
            return

        # 2. Check for multi-component directory (ML-model/)
        multi_dir = self._find_multi_component_dir()
        if multi_dir:
            self.model = joblib.load(multi_dir / "model_intent_full.pkl")
            self.vectorizer = joblib.load(multi_dir / "tfidf_vectorizer_full.pkl")
            self.label_encoder = joblib.load(multi_dir / "label_encoder_full.pkl")
            self.classes = [str(c) for c in self.label_encoder.classes_]
            self.is_multi_component = True
            return

        raise FileNotFoundError("No valid intent model artifact found in ML-model/ or artifacts/models/")

    @property
    def is_loaded(self) -> bool:
        return self.model is not None

    def predict(self, query: str) -> IntentPredictionResponse:
        """Predict intent, calibrated confidence score, and candidate probabilities."""
        if not self.model:
            raise RuntimeError("Model is not loaded.")

        clean_query = query.strip()

        if self.is_multi_component:
            return self._predict_multi_component(clean_query)
        else:
            return self._predict_single_pipeline(clean_query)

    def _predict_multi_component(self, query: str) -> IntentPredictionResponse:
        """Predict using TfidfVectorizer -> LinearSVC -> LabelEncoder with margin calibration."""
        X = self.vectorizer.transform([query])
        is_oov = (X.nnz == 0)

        # Check raw decision function margins
        if hasattr(self.model, "decision_function"):
            scores = self.model.decision_function(X)[0]
            max_idx = int(np.argmax(scores))
            top_score = float(scores[max_idx])

            # Calibrate confidence using sigmoid on top margin
            # High margin (>1.0) -> conf > 73%
            # If completely OOV (no matching words) -> conf = 0.10 (triggers abstention)
            if is_oov:
                confidence = 0.10
            else:
                confidence = float(1.0 / (1.0 + np.exp(-top_score)))

            # Softmax distribution across candidate classes for observability
            probs = softmax(scores)
            prob_dict = {
                self.classes[idx]: float(round(probs[idx], 4))
                for idx in range(len(self.classes))
            }
        else:
            max_idx = int(self.model.predict(X)[0])
            confidence = 0.10 if is_oov else 0.85
            prob_dict = {}

        predicted_intent = self.classes[max_idx]
        is_in_scope = predicted_intent in TARGET_INTENTS

        return IntentPredictionResponse(
            intent=predicted_intent,
            confidence=round(confidence, 4),
            is_in_scope=is_in_scope,
            all_probabilities=prob_dict,
        )

    def _predict_single_pipeline(self, query: str) -> IntentPredictionResponse:
        """Predict using standard scikit-learn Pipeline with predict_proba."""
        if hasattr(self.model, "predict_proba"):
            probs = self.model.predict_proba([query])[0]
            max_idx = int(np.argmax(probs))
            predicted_intent = str(self.classes[max_idx])
            confidence = float(probs[max_idx])
            prob_dict = {
                str(c): float(round(p, 4)) for c, p in zip(self.classes, probs)
            }
        elif hasattr(self.model, "decision_function"):
            scores = self.model.decision_function([query])[0]
            max_idx = int(np.argmax(scores))
            top_score = float(scores[max_idx])
            confidence = float(1.0 / (1.0 + np.exp(-top_score)))
            probs = softmax(scores)
            predicted_intent = str(self.classes[max_idx])
            prob_dict = {
                str(c): float(round(p, 4)) for c, p in zip(self.classes, probs)
            }
        else:
            predicted_intent = str(self.model.predict([query])[0])
            confidence = 1.0
            prob_dict = {predicted_intent: 1.0}

        is_in_scope = predicted_intent in TARGET_INTENTS

        return IntentPredictionResponse(
            intent=predicted_intent,
            confidence=round(confidence, 4),
            is_in_scope=is_in_scope,
            all_probabilities=prob_dict,
        )
