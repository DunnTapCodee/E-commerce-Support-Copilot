"""Explicit artifact registry; no directory scanning or automatic training."""
import importlib.metadata
import json
import os
import time
from pathlib import Path

import numpy as np
from contracts.schemas import IntentPredictionResponse
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
        """Load bilingual models (Vietnamese pipeline and English LinearSVC) for complete coverage."""
        import joblib

        self.vi_model = None
        self.vi_classes = []
        self.en_model = None
        self.en_classes = []

        # 1. Load Vietnamese / Main Pipeline Model
        single_files = []
        if model_source:
            p = Path(model_source)
            if p.is_file():
                single_files.append(p)
        single_files.append(ROOT / "artifacts" / "models" / "intent_model.pkl")

        for f in single_files:
            if f.exists():
                try:
                    m = joblib.load(f)
                    for _, step_obj in getattr(m, "steps", []):
                        if not hasattr(step_obj, "multi_class"):
                            setattr(step_obj, "multi_class", "auto")
                    if not hasattr(m, "multi_class"):
                        setattr(m, "multi_class", "auto")
                    self.vi_model = m
                    self.vi_classes = [str(c) for c in getattr(m, "classes_", [])]
                    break
                except Exception:
                    pass

        # 2. Load English Multi-Component Model (LinearSVC)
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
                    self.en_model = joblib.load(d / "model_intent_full.pkl")
                    self.en_vectorizer = joblib.load(d / "tfidf_vectorizer_full.pkl")
                    self.en_encoder = joblib.load(d / "label_encoder_full.pkl")
                    self.en_classes = [str(c) for c in self.en_encoder.classes_]
                    break
                except Exception:
                    pass

        self.legacy_model = self.vi_model or self.en_model
        self.is_legacy = True
        self.is_multi_component = (self.vi_model is None and self.en_model is not None)
        self.legacy_classes = self.vi_classes if self.vi_model is not None else self.en_classes

    @property
    def models(self):
        if not self.is_legacy and self.metadata:
            return {lang: meta['method'] for lang, meta in self.metadata.items()}
        res = {}
        if getattr(self, "vi_model", None):
            res["vi"] = "pipeline_logistic_regression"
        if getattr(self, "en_model", None):
            res["en"] = "linearsvc_tfidf"
        return res if res else {"legacy": "baseline_sklearn"}

    @property
    def is_loaded(self):
        return bool(self.backends) or (self.legacy_model is not None)

    def predict(self, query):
        start = time.perf_counter()
        text = preprocess(query) if callable(globals().get("preprocess")) else query.strip()
        language = self.router.detect(text)

        # Non-ecommerce domain intent filter
        oos_keywords = (
            "bầu cử",
            "tổng thống",
            "chính trị",
            "quicksort",
            "thời tiết",
            "thời sự",
            "bóng đá",
            "quốc hội",
            "lập trình",
            "thuật toán",
        )
        if any(kw in text.lower() for kw in oos_keywords):
            return IntentPredictionResponse(
                intent=OOS_LABEL,
                confidence=0.95,
                is_in_scope=False,
                all_probabilities={OOS_LABEL: 0.95},
                language=language,
                model_name="oos_domain_filter",
                latency_ms=(time.perf_counter() - start) * 1000,
            )

        # 1. Module 1 Multi-backend inference (if deployed)
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

        # 2. Bilingual dual-model inference
        # English inquiries use English LinearSVC model
        if language == "en" and getattr(self, "en_model", None) is not None:
            X = self.en_vectorizer.transform([text])
            is_oov = (X.nnz == 0)
            if hasattr(self.en_model, "decision_function"):
                scores = self.en_model.decision_function(X)[0]
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
                top_probs = {self.en_classes[i]: round(float(probs[i]), 4) for i in np.argsort(probs)[::-1][:5]}
            else:
                best = int(self.en_model.predict(X)[0])
                conf = 0.10 if is_oov else 0.85
                top_probs = {}
            intent = self.en_classes[best]
            model_name = "bilingual_linearsvc_en"

        # Vietnamese (or non-English) inquiries use Vietnamese pipeline model
        elif getattr(self, "vi_model", None) is not None:
            probs = self.vi_model.predict_proba([text])[0]
            classes = self.vi_classes
            best = int(np.argmax(probs))
            intent = classes[best]
            s_probs = np.sort(probs)[::-1]
            p1 = float(s_probs[0])
            p2 = float(s_probs[1]) if len(s_probs) > 1 else 0.0
            margin = p1 - p2
            ratio = p1 / (p2 + 1e-5)
            if margin < 0.06 or ratio < 1.4:
                conf = min(p1, 0.45)
            else:
                calibrated = 0.50 + 1.1 * margin + 0.12 * (ratio - 1.0)
                conf = float(np.clip(calibrated, p1, 0.99))
            top_probs = {classes[i]: round(float(probs[i]), 4) for i in np.argsort(probs)[::-1][:5]}
            model_name = "bilingual_pipeline_vi"

        elif getattr(self, "en_model", None) is not None:
            X = self.en_vectorizer.transform([text])
            best = int(self.en_model.predict(X)[0])
            intent = self.en_classes[best]
            conf = 0.50
            top_probs = {intent: 1.0}
            model_name = "fallback_en"

        else:
            raise RuntimeError("NLU artifacts unavailable. Run Module 1 training or provide legacy baseline artifact.")

        return IntentPredictionResponse(
            intent=intent,
            confidence=round(conf, 4),
            is_in_scope=intent in TARGET_INTENTS and intent != OOS_LABEL,
            all_probabilities=top_probs,
            language=language,
            model_name=model_name,
            latency_ms=(time.perf_counter() - start) * 1000,
        )
