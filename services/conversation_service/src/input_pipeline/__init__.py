"""Input pipeline package."""
from .fact_extractor import extract_facts
from .input_classifier import InputClassifier

__all__ = ["extract_facts", "InputClassifier"]
