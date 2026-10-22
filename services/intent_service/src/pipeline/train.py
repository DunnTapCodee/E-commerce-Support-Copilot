from pathlib import Path
import sys
from typing import Any, Dict
import joblib

try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline

from services.intent_service.src.pipeline.dataset import (
    TARGET_INTENTS,
    generate_bitext_dataframe,
    get_train_test_splits,
)
from services.intent_service.src.pipeline.evaluate import evaluate_model, print_detailed_report


def build_pipeline() -> Pipeline:
    """Build scikit-learn Pipeline with word and char n-grams."""
    return Pipeline([
        ("tfidf", TfidfVectorizer(ngram_range=(1, 3), sublinear_tf=True, max_features=5000)),
        ("clf", LogisticRegression(C=10.0, max_iter=1000, class_weight="balanced", random_state=42)),
    ])


def train_and_persist(output_path: Path) -> Dict[str, Any]:
    """Train pipeline, evaluate Macro-F1, and persist to output_path."""
    print("[Intent Pipeline] Generating dataset and splitting...")
    X_train, X_test, y_train, y_test = get_train_test_splits()

    pipeline = build_pipeline()
    print("[Intent Pipeline] Cross-validating model...")
    cv_metrics = evaluate_model(pipeline, X_train, y_train)
    print(f"[Intent Pipeline] Cross-validation Macro-F1: {cv_metrics['macro_f1_mean']:.4f} (>= 0.85: {cv_metrics['meets_target_criterion']})")

    print("[Intent Pipeline] Fitting final model on full train dataset...")
    pipeline.fit(X_train, y_train)

    report = print_detailed_report(pipeline, X_test, y_test)
    print("[Intent Pipeline] Holdout Classification Report:\n" + report)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(pipeline, output_path)
    print(f"[Intent Pipeline] Successfully saved model artifact to {output_path}")

    return {
        "model_path": str(output_path),
        "cv_metrics": cv_metrics,
        "classes": list(pipeline.classes_),
    }


if __name__ == "__main__":
    default_artifact_path = Path(__file__).resolve().parent.parent.parent.parent.parent / "artifacts" / "models" / "intent_model.pkl"
    train_and_persist(default_artifact_path)
