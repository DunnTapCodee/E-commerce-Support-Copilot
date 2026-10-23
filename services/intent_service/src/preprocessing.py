"""Shared, serialization-safe preprocessing for training and inference."""
import re
import unicodedata


def normalize_text(text: str) -> str:
    """Normalize NFC and spaces; preserve order IDs and diacritics."""
    return re.sub(r"\s+", " ", unicodedata.normalize("NFC", text)).strip()


def preprocess(text: str) -> str:
    """Case normalization used by all classifiers and tokenizers."""
    return normalize_text(text).lower()


def segment_vi(text: str) -> str:
    """Use exactly the same PhoBERT segmentation in training and serving."""
    from pyvi import ViTokenizer
    return ViTokenizer.tokenize(preprocess(text))
