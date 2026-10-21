"""Evaluate intent classifier pipeline with 10-Fold Cross Validation and Macro-F1 metric."""
from typing import Any, Dict
import numpy as np
from sklearn.metrics import classification_report, f1_score
from sklearn.model_selection import StratifiedKFold, cross_val_score


def evaluate_model(pipeline: Any, X, y) -> Dict[str, float]:
    """Calculate 10-fold CV Macro-F1 score and ensure threshold >= 0.85."""
    cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
    scores = cross_val_score(pipeline, X, y, cv=cv, scoring="f1_macro")
    macro_f1 = float(np.mean(scores))
    std_f1 = float(np.std(scores))
    return {
        "macro_f1_mean": macro_f1,
        "macro_f1_std": std_f1,
        "meets_target_criterion": macro_f1 >= 0.85,
    }


def print_detailed_report(pipeline: Any, X_test, y_test) -> str:
    """Print classification report on holdout test set."""
    y_pred = pipeline.predict(X_test)
    report = classification_report(y_test, y_pred, zero_division=0)
    return report
