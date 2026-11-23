"""Run the Module 2 policy retrieval benchmark.

Example:
    python scripts/benchmark_retrieval.py --methods tfidf,bm25,dense,hybrid,reranked
"""
from __future__ import annotations

import argparse
import gc
import json
import os
import platform
import statistics
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.rag_service.src.search_experiments import (  # noqa: E402
    BM25Searcher,
    DenseSearcher,
    HybridSearcher,
    RerankedHybridSearcher,
    TfidfSearcher,
    load_policy_documents,
)


METHODS = ("tfidf", "bm25", "dense", "hybrid", "reranked")


def _percentile(values: list[float], percentile: float) -> float:
    return float(np.percentile(np.asarray(values, dtype=np.float64), percentile))


def evaluate_searcher(
    searcher: Any,
    cases: list[dict[str, Any]],
    top_k: int,
    latency_repeats: int,
) -> dict[str, Any]:
    answerable = [case for case in cases if case.get("answerable", True)]
    no_answer = [case for case in cases if not case.get("answerable", True)]
    if not answerable:
        raise ValueError("The evaluation set has no answerable queries")

    # Warm up the model/runtime. The cold model load and corpus indexing are
    # reported separately in build_ms; query latency below includes encoding,
    # search, RRF and reranking performed for each request.
    for case in answerable[: min(3, len(answerable))]:
        searcher.search(case["query"], top_k=top_k)

    hit_values: list[float] = []
    recall_values: list[float] = []
    reciprocal_ranks: list[float] = []
    latencies: list[float] = []
    inactive_hits = 0
    no_answer_with_result = 0

    for case in cases:
        best_hits = None
        case_latencies = []
        for _ in range(max(1, latency_repeats)):
            started = time.perf_counter()
            hits = searcher.search(case["query"], top_k=top_k)
            case_latencies.append((time.perf_counter() - started) * 1000)
            best_hits = hits
        latencies.extend(case_latencies)
        ids = [hit.document.doc_id for hit in (best_hits or [])]
        inactive_hits += sum(not hit.document.is_active for hit in (best_hits or []))

        if not case.get("answerable", True):
            no_answer_with_result += bool(ids)
            continue

        relevant = set(case["relevant_doc_ids"])
        found = [doc_id for doc_id in ids if doc_id in relevant]
        hit_values.append(float(bool(found)))
        recall_values.append(len(set(found)) / len(relevant) if relevant else 0.0)
        first_rank = next(
            (rank for rank, doc_id in enumerate(ids, start=1) if doc_id in relevant),
            None,
        )
        reciprocal_ranks.append(1.0 / first_rank if first_rank else 0.0)

    dense_searcher = (
        getattr(searcher, "dense_searcher", None)
        or getattr(getattr(searcher, "hybrid_searcher", None), "dense_searcher", None)
        or (searcher if hasattr(searcher, "backend") else None)
    )

    return {
        "method": searcher.name,
        "model": getattr(searcher, "model_name", None),
        "dense_backend": getattr(dense_searcher, "backend", None),
        "build_ms": round(float(getattr(searcher, "build_ms", 0.0)), 3),
        "answerable_queries": len(answerable),
        "unanswerable_queries": len(no_answer),
        f"hit_rate_at_{top_k}": round(statistics.mean(hit_values), 4),
        f"recall_at_{top_k}": round(statistics.mean(recall_values), 4),
        f"mrr_at_{top_k}": round(statistics.mean(reciprocal_ranks), 4),
        "query_latency_ms": {
            "median": round(_percentile(latencies, 50), 3),
            "p95": round(_percentile(latencies, 95), 3),
            "threshold_ms": 15.0,
            "p95_under_15ms": _percentile(latencies, 95) < 15.0,
        },
        "unanswerable_queries_with_any_result": no_answer_with_result,
        "inactive_documents_returned": inactive_hits,
    }


def load_cases(path: Path) -> list[dict[str, Any]]:
    cases = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(cases, list):
        raise ValueError("The retrieval evaluation set must be a JSON array")
    for case in cases:
        if not isinstance(case.get("relevant_doc_ids"), list):
            raise ValueError(f"{case.get('query_id')} is missing relevant_doc_ids")
        if case.get("answerable", True) and not case["relevant_doc_ids"]:
            raise ValueError(f"Answerable query {case.get('query_id')} has no gold IDs")
        if not case.get("answerable", True) and case["relevant_doc_ids"]:
            raise ValueError(f"Unanswerable query {case.get('query_id')} has gold IDs")
    return cases


def build_searchers(
    methods: list[str],
    documents,
    dense_model: str,
    reranker_model: str,
    device: str,
    include_tags: bool,
) -> dict[str, Any]:
    built: dict[str, Any] = {}
    bm25 = None
    dense = None

    if "tfidf" in methods:
        built["tfidf"] = TfidfSearcher(documents, include_tags=include_tags)
    if "bm25" in methods or "hybrid" in methods or "reranked" in methods:
        bm25 = BM25Searcher(documents, include_tags=include_tags)
        if "bm25" in methods:
            built["bm25"] = bm25
    if "dense" in methods or "hybrid" in methods or "reranked" in methods:
        dense = DenseSearcher(
            documents,
            model_name=dense_model,
            include_tags=include_tags,
            device=device,
        )
        if "dense" in methods:
            built["dense"] = dense
    if "hybrid" in methods or "reranked" in methods:
        hybrid = HybridSearcher(bm25, dense, candidate_k=10, rrf_constant=60)
        if "hybrid" in methods:
            built["hybrid"] = hybrid
        if "reranked" in methods:
            built["reranked"] = RerankedHybridSearcher(
                hybrid,
                model_name=reranker_model,
                candidate_k=10,
                device=device,
            )
    return built


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--methods",
        default=",".join(METHODS),
        help=f"Comma-separated methods: {','.join(METHODS)}",
    )
    parser.add_argument("--top-k", type=int, default=3)
    parser.add_argument("--latency-repeats", type=int, default=3)
    parser.add_argument("--dense-model", default="keepitreal/vietnamese-sbert")
    parser.add_argument("--reranker-model", default="BAAI/bge-reranker-base")
    parser.add_argument("--device", default="cpu")
    parser.add_argument(
        "--include-tags",
        action="store_true",
        help="Include curated policy tags in all methods for a controlled ablation.",
    )
    parser.add_argument("--policy-file", type=Path, default=ROOT / "data" / "knowledge_base" / "policies.json")
    parser.add_argument("--eval-file", type=Path, default=ROOT / "data" / "retrieval_eval.json")
    parser.add_argument("--output", type=Path, default=ROOT / "reports" / "module2_retrieval_benchmark.json")
    parser.add_argument(
        "--model-cache",
        type=Path,
        default=Path(tempfile.gettempdir()) / "ecommerce-support-copilot-hf-cache",
    )
    args = parser.parse_args()

    methods = [item.strip() for item in args.methods.split(",") if item.strip()]
    invalid = sorted(set(methods) - set(METHODS))
    if invalid:
        parser.error(f"Unknown methods: {', '.join(invalid)}")
    if not methods:
        parser.error("Select at least one method")

    # Keep model downloads in the task temp folder instead of the user's home.
    os.environ.setdefault("HF_HOME", str(args.model_cache))
    args.model_cache.mkdir(parents=True, exist_ok=True)

    documents = load_policy_documents(args.policy_file, active_only=True)
    cases = load_cases(args.eval_file)
    covered_ids = {doc_id for case in cases for doc_id in case["relevant_doc_ids"]}
    missing_ids = sorted({doc.doc_id for doc in documents} - covered_ids)
    if missing_ids:
        raise ValueError(f"Evaluation set does not cover active policies: {', '.join(missing_ids)}")

    report: dict[str, Any] = {
        "corpus": {
            "policy_file": str(args.policy_file.relative_to(ROOT)),
            "total_active_documents": len(documents),
            "total_evaluation_queries": len(cases),
            "active_policy_ids_covered": len(covered_ids),
            "query_text_fields": "title + content",
            "inactive_documents_filtered_before_ranking": True,
        },
        "settings": {
            "top_k": args.top_k,
            "latency_repeats": args.latency_repeats,
            "dense_model": args.dense_model,
            "reranker_model": args.reranker_model,
            "device": args.device,
            "rrf_constant": 60,
            "hybrid_candidate_k": 10,
            "reranker_candidate_k": 10,
            "latency_includes_query_encoding_and_reranking": True,
            "include_tags": args.include_tags,
        },
        "environment": {
            "python": sys.version.split()[0],
            "platform": platform.platform(),
            "numpy": np.__version__,
        },
        "results": [],
    }

    searchers = build_searchers(
        methods,
        documents,
        args.dense_model,
        args.reranker_model,
        args.device,
        args.include_tags,
    )
    for method in methods:
        searcher = searchers[method]
        print(f"Benchmarking {method}...")
        report["results"].append(
            evaluate_searcher(searcher, cases, args.top_k, args.latency_repeats)
        )
        if method == "reranked":
            report["results"][-1]["model"] = args.reranker_model
        print(json.dumps(report["results"][-1], ensure_ascii=False))

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Saved report: {args.output.resolve().relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
