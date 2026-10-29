"""Explicit artifact registry; no directory scanning or automatic training."""
import importlib.metadata
import json
import os
import time
from pathlib import Path

import numpy as np
from contracts.schemas import IntentPredictionResponse
from services.intent_service.src.llm_classifier import LLMIntentClassifier
from services.intent_service.src.pipeline.dataset import TARGET_INTENTS, OOS_LABEL
from services.intent_service.src.preprocessing import preprocess, segment_vi
from services.intent_service.src.router import LanguageRouter

ROOT = Path(__file__).resolve().parents[3]


def softmax(logits):
    values = np.asarray(logits, dtype=np.float64)
    values -= values.max(axis=-1, keepdims=True)
    exp = np.exp(values)
    return exp / exp.sum(axis=-1, keepdims=True)


class SklearnBackend:
    """Load a local-version sklearn pipeline with calibrated predict_proba."""
    def __init__(self, path, meta):
        import joblib
        actual = importlib.metadata.version('scikit-learn')
        expected = meta['library_versions']['scikit-learn']
        if actual != expected:
            raise RuntimeError(f'scikit-learn mismatch: artifact={expected}, runtime={actual}. Retrain locally.')
        self.model = joblib.load(path / meta.get('model_file', 'model.joblib'))
        if not hasattr(self.model, 'predict_proba'):
            raise ValueError('Serving requires calibrated predict_proba')
        if list(map(str, self.model.classes_)) != meta['classes']:
            raise ValueError('Artifact class order differs from meta.json')

    def predict_proba(self, text):
        return self.model.predict_proba([text])[0]


class OnnxTransformerBackend:
    """CPU ONNX transformer with optional PhoBERT word segmentation."""
    def __init__(self, path, meta):
        import onnxruntime as ort
        from transformers import AutoTokenizer
        self.meta = meta
        self.tokenizer = AutoTokenizer.from_pretrained(str(path), local_files_only=True)
        options = ort.SessionOptions()
        if os.getenv('INTENT_NUM_THREADS'):
            options.intra_op_num_threads = int(os.environ['INTENT_NUM_THREADS'])
            options.inter_op_num_threads = 1
        self.session = ort.InferenceSession(str(path / meta.get('model_file', 'model_int8.onnx')), sess_options=options, providers=['CPUExecutionProvider'])
        self.input_names = {i.name for i in self.session.get_inputs()}

    def encode(self, text):
        if self.meta.get('needs_word_segmentation'):
            text = segment_vi(text)
        encoded = self.tokenizer(text, return_tensors='np', truncation=True, max_length=self.meta.get('max_length', 64))
        return {name: np.asarray(encoded[name], dtype=np.int64) for name in self.input_names}

    def predict_proba(self, text):
        logits = self.session.run(None, self.encode(text))[0][0]
        return softmax(logits / float(self.meta.get('temperature', 1.0)))


class MiniLMLRBackend(OnnxTransformerBackend):
    """ONNX MiniLM mean pooling + normalization + locally fitted LR."""
    def __init__(self, path, meta):
        super().__init__(path, meta)
        import joblib
        expected = meta['library_versions']['scikit-learn']
        if expected != importlib.metadata.version('scikit-learn'):
            raise RuntimeError('MiniLM LR must be retrained with the serving sklearn version')
        self.lr = joblib.load(path / 'lr.joblib')
        if list(map(str, self.lr.classes_)) != meta['classes']:
            raise ValueError('LR class order differs from metadata')

    def predict_proba(self, text):
        inputs = self.encode(text)
        hidden = self.session.run(None, inputs)[0]
        mask = inputs['attention_mask'][..., None]
        pooled = (hidden * mask).sum(axis=1) / np.clip(mask.sum(axis=1), 1, None)
        pooled /= np.clip(np.linalg.norm(pooled, axis=1, keepdims=True), 1e-12, None)
        return self.lr.predict_proba(pooled)[0]


BACKENDS = {'sklearn': SklearnBackend, 'onnx_transformer': OnnxTransformerBackend, 'minilm_lr': MiniLMLRBackend}


class IntentPredictor:
    """Bilingual runtime inference engine supporting Module 1 router and legacy baselines."""

    def __init__(self, model_source=None, routing_mode=None):
        raw_source = model_source or os.getenv('INTENT_MODEL_DIR', str(ROOT / 'artifacts/models/intent'))
        self.model_dir = Path(raw_source)
        self.routing_mode = routing_mode or os.getenv('INTENT_ROUTING_MODE', 'router')
        if self.routing_mode not in {'router', 'multilingual'}:
            raise ValueError('INTENT_ROUTING_MODE must be router or multilingual')

        self.intent_backend = os.getenv("INTENT_BACKEND", "llm").lower()
        self.llm_classifier = LLMIntentClassifier()

        self.backends = {}
        self.metadata = {}
        self.legacy_model = None
        self.is_legacy = False

        router_dir = self.model_dir / 'router'
        if router_dir.exists() and (router_dir / 'meta.json').exists():
            self.router = LanguageRouter.load(router_dir)
            for lang in (('multi',) if self.routing_mode == 'multilingual' else ('vi', 'en')):
                path = self.model_dir / lang
                if (path / 'meta.json').exists():
                    meta = json.loads((path / 'meta.json').read_text())
                    if meta.get('backend') in BACKENDS:
                        self.backends[lang] = BACKENDS[meta['backend']](path, meta)
                        self.metadata[lang] = meta
            if not self.backends:
                self._load_legacy_model(raw_source)
        else:
            self.router = LanguageRouter()
            self._load_legacy_model(raw_source)

    def _load_legacy_model(self, model_source):
        """Fallback to local model (3-component or single-pipeline) if Module 1 artifacts are not yet deployed."""
        import joblib
        multi_dirs = [
            ROOT / "ML-model",
            ROOT / "artifacts" / "models" / "legacy_linearsvc_en",
            ROOT / "ML-modeel",
        ]
        if model_source:
            p = Path(model_source)
            if p.is_dir():
                multi_dirs.insert(0, p)

        for d in multi_dirs:
            if d.exists() and (d / "model_intent_full.pkl").exists() and (d / "tfidf_vectorizer_full.pkl").exists() and (d / "label_encoder_full.pkl").exists():
                try:
                    self.legacy_model = joblib.load(d / "model_intent_full.pkl")
                    self.legacy_vectorizer = joblib.load(d / "tfidf_vectorizer_full.pkl")
                    self.legacy_encoder = joblib.load(d / "label_encoder_full.pkl")
                    self.legacy_classes = [str(c) for c in self.legacy_encoder.classes_]
                    self.is_multi_component = True
                    self.is_legacy = True
                    return
                except Exception:
                    pass

        # Single pipeline fallback
        single_files = [
            ROOT / "artifacts" / "models" / "intent_model.pkl",
        ]
        if model_source and Path(model_source).is_file():
            single_files.insert(0, Path(model_source))

        for f in single_files:
            if f.exists():
                try:
                    self.legacy_model = joblib.load(f)
                    self.legacy_classes = [str(c) for c in getattr(self.legacy_model, "classes_", [])]
                    self.is_multi_component = False
                    self.is_legacy = True
                    return
                except Exception:
                    pass

    @property
    def models(self):
        if self.intent_backend == "llm":
            return {"llm": "gemini-2.5-flash"}
        if self.intent_backend == "hybrid":
            base = {lang: meta['method'] for lang, meta in self.metadata.items()} if (not self.is_legacy and self.metadata) else {"legacy": "baseline_sklearn"}
            base["fallback"] = "llm_gemini"
            return base
        if not self.is_legacy and self.metadata:
            return {lang: meta['method'] for lang, meta in self.metadata.items()}
        return {"legacy": "baseline_sklearn"} if self.legacy_model else {}

    @property
    def is_loaded(self):
        return (self.intent_backend in {"llm", "hybrid"}) or bool(self.backends) or (self.legacy_model is not None)

    def _predict_ml(self, query: str) -> IntentPredictionResponse:
        """Execute legacy/module 1 ML model pipeline."""
        start = time.perf_counter()
        text = preprocess(query) if callable(globals().get("preprocess")) else query.strip()
        language = self.router.detect(text)

        # 1. Module 1 Multi-backend inference
        if not self.is_legacy and self.backends:
            key = 'multi' if self.routing_mode == 'multilingual' else language
            meta = self.metadata.get(key)
            if meta:
                probs = np.asarray(self.backends[key].predict_proba(text), dtype=float)
                if probs.shape != (len(meta['classes']),) or not np.isfinite(probs).all() or (probs < 0).any():
                    raise ValueError('Backend returned invalid probabilities')
                best = int(probs.argmax())
                intent = meta['classes'][best]
                conf = float(probs[best])
                top_probs = {meta['classes'][i]: round(float(probs[i]), 4) for i in np.argsort(probs)[::-1][:5]}
                return IntentPredictionResponse(
                    intent=intent,
                    confidence=conf,
                    is_in_scope=intent in TARGET_INTENTS and intent != OOS_LABEL,
                    all_probabilities=top_probs,
                    language=language,
                    model_name=meta.get('method', 'module1_model'),
                    latency_ms=(time.perf_counter() - start) * 1000,
                )

        # 2. Legacy baseline inference
        if self.legacy_model is not None:
            if getattr(self, "is_multi_component", False):
                X = self.legacy_vectorizer.transform([text])
                is_oov = (X.nnz == 0)
                if hasattr(self.legacy_model, "decision_function"):
                    scores = self.legacy_model.decision_function(X)[0]
                    best = int(np.argmax(scores))
                    top_score = float(scores[best])
                    
                    sorted_scores = np.sort(scores)[::-1]
                    runner_up = float(sorted_scores[1]) if len(sorted_scores) > 1 else -1.0
                    margin_gap = max(0.0, top_score - runner_up)

                    if is_oov or top_score <= 0:
                        conf = 0.10 if is_oov else float(1.0 / (1.0 + np.exp(-1.5 * top_score)))
                        conf = min(conf, 0.45)
                    else:
                        effective_score = top_score + 0.35 * margin_gap
                        conf = float(1.0 / (1.0 + np.exp(-2.0 * effective_score)))

                    probs = softmax(scores)
                    top_probs = {self.legacy_classes[i]: round(float(probs[i]), 4) for i in np.argsort(probs)[::-1][:5]}
                else:
                    best = int(self.legacy_model.predict(X)[0])
                    conf = 0.10 if is_oov else 0.85
                    top_probs = {}
                intent = self.legacy_classes[best]
            elif hasattr(self.legacy_model, "predict_proba"):
                probs = self.legacy_model.predict_proba([text])[0]
                classes = self.legacy_classes
                best = int(np.argmax(probs))
                intent = classes[best]
                conf = float(probs[best])
                top_probs = {classes[i]: round(float(probs[i]), 4) for i in np.argsort(probs)[::-1][:5]}
            else:
                intent = str(self.legacy_model.predict([text])[0])
                conf = 0.85
                top_probs = {intent: 1.0}

            return IntentPredictionResponse(
                intent=intent,
                confidence=round(conf, 4),
                is_in_scope=intent in TARGET_INTENTS and intent != OOS_LABEL,
                all_probabilities=top_probs,
                language=language,
                model_name="legacy_baseline",
                latency_ms=(time.perf_counter() - start) * 1000,
            )

        return self.llm_classifier.predict(query)

    def predict(self, query: str) -> IntentPredictionResponse:
        # Pure LLM Intent Classifier
        if self.intent_backend == "llm":
            return self.llm_classifier.predict(query)

        # Pure ML model
        if self.intent_backend == "ml":
            return self._predict_ml(query)

        # Hybrid: run ML first; if low confidence or out-of-scope, fallback to LLM
        ml_resp = self._predict_ml(query)
        if ml_resp.is_in_scope and ml_resp.confidence >= 0.75:
            return ml_resp
        return self.llm_classifier.predict(query)
