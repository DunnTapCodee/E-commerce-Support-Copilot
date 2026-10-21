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
    def __init__(self, model_source=None, routing_mode=None):
        self.model_dir = Path(model_source or os.getenv('INTENT_MODEL_DIR', str(ROOT / 'artifacts/models/intent')))
        self.routing_mode = routing_mode or os.getenv('INTENT_ROUTING_MODE', 'router')
        if self.routing_mode not in {'router', 'multilingual'}:
            raise ValueError('INTENT_ROUTING_MODE must be router or multilingual')
        self.router = LanguageRouter.load(self.model_dir / 'router')
        self.backends, self.metadata = {}, {}
        for lang in (('multi',) if self.routing_mode == 'multilingual' else ('vi', 'en')):
            path = self.model_dir / lang
            meta = json.loads((path / 'meta.json').read_text())
            if len(set(meta['classes'])) != len(meta['classes']):
                raise ValueError(f'Duplicate classes in {path}')
            if meta.get('threshold') is None or not 0 <= float(meta['threshold']) <= 1:
                raise ValueError(f'Invalid threshold in {path}')
            self.backends[lang] = BACKENDS[meta['backend']](path, meta)
            self.metadata[lang] = meta

    @property
    def models(self):
        return {lang: meta['method'] for lang, meta in self.metadata.items()}

    @property
    def is_loaded(self):
        return bool(self.backends)

    def predict(self, query):
        start = time.perf_counter()
        text = preprocess(query)
        language = self.router.detect(text)
        key = 'multi' if self.routing_mode == 'multilingual' else language
        meta = self.metadata[key]
        probs = np.asarray(self.backends[key].predict_proba(text), dtype=float)
        if probs.shape != (len(meta['classes']),) or not np.isfinite(probs).all() or (probs < 0).any() or not np.isclose(probs.sum(), 1, atol=1e-4):
            raise ValueError('Backend returned invalid probabilities')
        best = int(probs.argmax()); intent = meta['classes'][best]
        return IntentPredictionResponse(
            intent=intent, confidence=float(probs[best]),
            is_in_scope=intent in TARGET_INTENTS and intent != OOS_LABEL,
            all_probabilities={meta['classes'][i]: round(float(probs[i]), 4) for i in np.argsort(probs)[::-1][:5]},
            language=language, model_name=meta['method'], latency_ms=(time.perf_counter() - start) * 1000,
        )
