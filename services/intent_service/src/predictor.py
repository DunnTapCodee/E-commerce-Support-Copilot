"""Inference engine wrapper loading serialized .pkl model."""
from pathlib import Path
from typing import Dict, Optional, Union
import joblib
import numpy as np

from contracts.schemas import IntentPredictionResponse
from services.intent_service.src.pipeline.dataset import TARGET_INTENTS


class IntentPredictor:
    """Production runtime inference engine for intent classification."""

    def __init__(self, model_path: Union[str, Path]):
        self.model_path = Path(model_path)
        self.model = None
        self.load_model()

    def load_model(self) -> None:
        """Load pickled scikit-learn pipeline from disk."""
        if not self.model_path.exists():
            raise FileNotFoundError(f"Model file not found at {self.model_path}")
        self.model = joblib.load(self.model_path)

    @property
    def is_loaded(self) -> bool:
        return self.model is not None

    def predict(self, query: str) -> IntentPredictionResponse:
        """Predict intent, confidence score, and candidate probabilities."""
        if not self.model:
            raise RuntimeError("Model is not loaded.")

        clean_query = query.strip()
        classes = list(self.model.classes_)

        # Predict probability distribution
        if hasattr(self.model, "predict_proba"):
            probs = self.model.predict_proba([clean_query])[0]
            max_idx = int(np.argmax(probs))
            predicted_intent = str(classes[max_idx])
            confidence = float(probs[max_idx])
            prob_dict: Dict[str, float] = {
                str(c): float(round(p, 4)) for c, p in zip(classes, probs)
            }
        else:
            predicted_intent = str(self.model.predict([clean_query])[0])
            confidence = 1.0
            prob_dict = {predicted_intent: 1.0}

        # Check if predicted intent is within the 12 supported operational intents
        is_in_scope = predicted_intent in TARGET_INTENTS

        return IntentPredictionResponse(
            intent=predicted_intent,
            confidence=confidence,
            is_in_scope=is_in_scope,
            all_probabilities=prob_dict,
        )
