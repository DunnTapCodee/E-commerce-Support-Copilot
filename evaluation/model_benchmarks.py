"""Model Benchmark Suite aligning with CMU MLIP Slicing & Quality Attribute Analysis.
Evaluates accuracy, macro F1, per-intent metrics, slice breakdowns, and latency percentiles.
"""
import time
from typing import Any, Dict, List, Optional
import numpy as np
from sklearn.metrics import accuracy_score, f1_score, precision_recall_fscore_support

from evaluation.dataset_loader import BENCHMARK_DATASET, EvaluationTestCase
from services.intent_service.src.predictor import IntentPredictor


class ModelBenchmarkRunner:
    """Runs sliced statistical evaluation and latency profiling for Intent Classifiers."""

    def __init__(self, predictor: Optional[IntentPredictor] = None):
        self.predictor = predictor or IntentPredictor()

    def run_benchmark(self, dataset: Optional[List[EvaluationTestCase]] = None) -> Dict[str, Any]:
        cases = dataset or BENCHMARK_DATASET
        y_true = []
        y_pred = []
        latencies_ms = []
        slice_records: Dict[str, Dict[str, List[Any]]] = {}

        for case in cases:
            t0 = time.perf_counter()
            resp = self.predictor.predict(case.query)
            lat_ms = (time.perf_counter() - t0) * 1000

            y_true.append(case.ground_truth_intent)
            y_pred.append(resp.intent)
            latencies_ms.append(lat_ms)

            s_type = case.slice_type
            if s_type not in slice_records:
                slice_records[s_type] = {"y_true": [], "y_pred": [], "latencies": []}
            slice_records[s_type]["y_true"].append(case.ground_truth_intent)
            slice_records[s_type]["y_pred"].append(resp.intent)
            slice_records[s_type]["latencies"].append(lat_ms)

        # Global metrics
        labels = sorted(list(set(y_true + y_pred)))
        acc = accuracy_score(y_true, y_pred)
        macro_f1 = f1_score(y_true, y_pred, average="macro", zero_division=0)
        p, r, f1, sup = precision_recall_fscore_support(y_true, y_pred, labels=labels, zero_division=0)

        per_intent_metrics = []
        for i, label in enumerate(labels):
            per_intent_metrics.append({
                "intent": label,
                "precision": round(float(p[i]), 4),
                "recall": round(float(r[i]), 4),
                "f1": round(float(f1[i]), 4),
                "support": int(sup[i]),
            })

        # Slice-based analysis
        slice_metrics = []
        for s_type, data in slice_records.items():
            s_acc = accuracy_score(data["y_true"], data["y_pred"])
            s_f1 = f1_score(data["y_true"], data["y_pred"], average="macro", zero_division=0)
            slice_metrics.append({
                "slice": s_type,
                "sample_count": len(data["y_true"]),
                "accuracy": round(float(s_acc), 4),
                "macro_f1": round(float(s_f1), 4),
                "mean_latency_ms": round(float(np.mean(data["latencies"])), 2),
            })

        # Latency statistics
        lat_arr = np.array(latencies_ms)
        latency_stats = {
            "mean_ms": round(float(np.mean(lat_arr)), 2),
            "median_ms": round(float(np.median(lat_arr)), 2),
            "p90_ms": round(float(np.percentile(lat_arr, 90)), 2),
            "p99_ms": round(float(np.percentile(lat_arr, 99)), 2),
            "min_ms": round(float(np.min(lat_arr)), 2),
            "max_ms": round(float(np.max(lat_arr)), 2),
        }

        # Confusion Matrix
        from sklearn.metrics import confusion_matrix
        cm = confusion_matrix(y_true, y_pred, labels=labels)

        return {
            "total_samples": len(cases),
            "accuracy": round(float(acc), 4),
            "macro_f1": round(float(macro_f1), 4),
            "latency_stats": latency_stats,
            "per_intent_metrics": per_intent_metrics,
            "slice_metrics": slice_metrics,
            "labels": labels,
            "confusion_matrix": cm.tolist(),
        }
