"""Comprehensive Benchmark for Module 3: Dynamic Data Integration, Caching, and Tool Calling.

Evaluates:
1. Database Lookup Latency (Target < 2ms):
   - Baseline: Sequential JSON File Scan
   - SQLite Unindexed Table Scan
   - SQLite with Dedicated Indexes (order_id, phone, customer_id)
   - SQLite + In-Memory LRU Cache
2. Entity Extraction Performance (Precision, Recall, F1):
   - Baseline Regex (\bORD-[A-Z0-9-]+\b)
   - Advanced Multi-Entity ReAct Extractor (Shorthand ORD, Phones, Colloquial)
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import sqlite3
import sys
import time
from typing import Any, Dict, List

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from services.gateway.src.agent import extract_entities_advanced, extract_entities_baseline
from services.telemetry_service.src.cache import OrderLRUCache, normalize_phone
from services.telemetry_service.src.database import get_db_connection, init_db, migrate_mock_orders
from services.telemetry_service.src.repository import TelemetryRepository

DB_PATH = ROOT_DIR / "copilot_telemetry.sqlite3"
ORDERS_JSON_PATH = ROOT_DIR / "data" / "mock_orders.json"
EVAL_DATASET_PATH = ROOT_DIR / "data" / "module3_eval_dataset.json"
OUTPUT_REPORT_PATH = ROOT_DIR / "reports" / "module3_benchmark.json"


# -------------------------------------------------------------------
# 1. Latency Benchmark Methods
# -------------------------------------------------------------------
def raw_json_lookup(mock_orders_path: Path, identifier: str) -> Dict[str, Any] | None:
    """Baseline: Re-read JSON from disk and linearly scan orders list."""
    with open(mock_orders_path, "r", encoding="utf-8") as f:
        orders = json.load(f)
    clean = identifier.lower()
    for o in orders:
        if str(o.get("order_id", "")).lower() == clean:
            return o
        if str(o.get("customer_id", "")).lower() == clean:
            return o
        if str(o.get("phone", "")).lower() == clean:
            return o
    return None


def run_latency_benchmark(num_trials: int = 400) -> Dict[str, Any]:
    """Benchmark sequential JSON scan, unindexed SQLite, indexed SQLite, and LRU Cache."""
    # Ensure database is initialized with orders table
    init_db(DB_PATH)
    migrate_mock_orders(DB_PATH, ORDERS_JSON_PATH, force=False)

    with open(ORDERS_JSON_PATH, "r", encoding="utf-8") as f:
        orders = json.load(f)

    # Build test queries from existing orders (orders, phones, customer IDs)
    test_keys = []
    for o in orders:
        test_keys.append(o["order_id"])
        if o.get("phone"):
            test_keys.append(o["phone"])
        test_keys.append(o["customer_id"])

    # Setup unindexed table for comparison
    with get_db_connection(DB_PATH) as conn:
        conn.execute("DROP TABLE IF EXISTS orders_unindexed;")
        conn.execute("CREATE TABLE orders_unindexed AS SELECT * FROM orders;")
        conn.commit()

    repo = TelemetryRepository(DB_PATH, ORDERS_JSON_PATH)

    latencies: Dict[str, List[float]] = {
        "json_sequential_scan": [],
        "sqlite_unindexed": [],
        "sqlite_indexed": [],
        "sqlite_lru_cache": [],
    }

    # Warm up LRU Cache with half of keys to simulate realistic production cache hits
    warm_keys = test_keys[: len(test_keys) // 2]
    for k in warm_keys:
        repo.get_order(k)

    # Run trials
    keys_len = len(test_keys)
    for i in range(num_trials):
        key = test_keys[i % keys_len]

        # 1. Baseline: Sequential JSON scan
        t0 = time.perf_counter()
        raw_json_lookup(ORDERS_JSON_PATH, key)
        t_json = (time.perf_counter() - t0) * 1000
        latencies["json_sequential_scan"].append(t_json)

        # 2. SQLite Unindexed Query
        t0 = time.perf_counter()
        with get_db_connection(DB_PATH) as conn:
            conn.execute(
                "SELECT * FROM orders_unindexed WHERE order_id = ? OR customer_id = ? LIMIT 1;",
                (key, key),
            ).fetchone()
        t_unindexed = (time.perf_counter() - t0) * 1000
        latencies["sqlite_unindexed"].append(t_unindexed)

        # 3. SQLite Indexed Query (Bypassing cache directly to measure DB engine)
        t0 = time.perf_counter()
        with get_db_connection(DB_PATH) as conn:
            conn.execute(
                "SELECT * FROM orders WHERE order_id = ? COLLATE NOCASE OR customer_id = ? COLLATE NOCASE LIMIT 1;",
                (key, key),
            ).fetchone()
        t_indexed = (time.perf_counter() - t0) * 1000
        latencies["sqlite_indexed"].append(t_indexed)

        # 4. SQLite + In-Memory LRU Cache
        t0 = time.perf_counter()
        repo.get_order(key)
        t_cache = (time.perf_counter() - t0) * 1000
        latencies["sqlite_lru_cache"].append(t_cache)

    # Calculate metrics
    results = {}
    for name, lat_list in latencies.items():
        sorted_lats = sorted(lat_list)
        n = len(sorted_lats)
        p50 = sorted_lats[int(n * 0.50)]
        p90 = sorted_lats[int(n * 0.90)]
        p95 = sorted_lats[int(n * 0.95)]
        p99 = sorted_lats[int(n * 0.99)]
        avg = sum(sorted_lats) / n
        qps = round(1000.0 / avg, 1) if avg > 0 else 0.0

        results[name] = {
            "p50_ms": round(p50, 4),
            "p90_ms": round(p90, 4),
            "p95_ms": round(p95, 4),
            "p99_ms": round(p99, 4),
            "mean_ms": round(avg, 4),
            "qps": qps,
            "target_under_2ms": p95 < 2.0,
        }

    return results


# -------------------------------------------------------------------
# 2. Entity Extraction & Action Evaluation
# -------------------------------------------------------------------
def run_extraction_benchmark() -> Dict[str, Any]:
    """Evaluate entity extraction precision, recall, and action detection on test scenarios."""
    with open(EVAL_DATASET_PATH, "r", encoding="utf-8") as f:
        dataset = json.load(f)

    # Metrics containers
    # Order ID metrics
    b_order_tp = b_order_fp = b_order_fn = 0
    a_order_tp = a_order_fp = a_order_fn = 0

    # Phone metrics
    b_phone_tp = b_phone_fp = b_phone_fn = 0
    a_phone_tp = a_phone_fp = a_phone_fn = 0

    # Action detection metrics
    a_action_correct = 0

    for item in dataset:
        query = item["query"]
        expected_order = item.get("expected_order_id")
        expected_phone = item.get("expected_phone")
        expected_action = item.get("expected_action")

        # 1. Baseline Regex
        b_res = extract_entities_baseline(query)
        b_order = b_res.get("order_id")
        b_phone = b_res.get("phone")

        # Baseline Order Evaluation
        if expected_order:
            if b_order == expected_order:
                b_order_tp += 1
            else:
                b_order_fn += 1
                if b_order:
                    b_order_fp += 1
        else:
            if b_order:
                b_order_fp += 1

        # Baseline Phone Evaluation
        if expected_phone:
            b_phone_fn += 1

        # 2. Advanced Multi-Entity ReAct Extractor
        a_res = extract_entities_advanced(query)
        a_order = a_res.get("order_id")
        a_phone = a_res.get("phone")
        a_action = a_res.get("action")

        # Advanced Order Evaluation
        if expected_order:
            if a_order == expected_order:
                a_order_tp += 1
            else:
                a_order_fn += 1
                if a_order:
                    a_order_fp += 1
        else:
            if a_order:
                a_order_fp += 1

        # Advanced Phone Evaluation
        if expected_phone:
            if a_phone and normalize_phone(a_phone) == normalize_phone(expected_phone):
                a_phone_tp += 1
            else:
                a_phone_fn += 1
                if a_phone:
                    a_phone_fp += 1
        else:
            if a_phone:
                a_phone_fp += 1

        # Action Accuracy Evaluation
        if expected_action:
            if a_action == expected_action or (expected_action == "lookup" and a_action in ("lookup", "details")):
                a_action_correct += 1

    def calc_prf(tp: int, fp: int, fn: int) -> Dict[str, float]:
        precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1 = (2 * precision * recall) / (precision + recall) if (precision + recall) > 0 else 0.0
        return {
            "precision": round(precision, 4),
            "recall": round(recall, 4),
            "f1_score": round(f1, 4),
            "tp": tp,
            "fp": fp,
            "fn": fn,
        }

    total_queries = len(dataset)
    return {
        "total_test_scenarios": total_queries,
        "baseline_regex": {
            "order_extraction": calc_prf(b_order_tp, b_order_fp, b_order_fn),
            "phone_extraction": calc_prf(b_phone_tp, b_phone_fp, b_phone_fn),
        },
        "advanced_react_extractor": {
            "order_extraction": calc_prf(a_order_tp, a_order_fp, a_order_fn),
            "phone_extraction": calc_prf(a_phone_tp, a_phone_fp, a_phone_fn),
            "action_intent_accuracy": round((a_action_correct / total_queries) * 100, 2),
        },
    }


# -------------------------------------------------------------------
# 3. Main Runner & Reporter
# -------------------------------------------------------------------
def main():
    print("=" * 75)
    print("🚀 MODULE 3 BENCHMARK: DYNAMIC DATA INTEGRATION & TOOL CALLING")
    print("=" * 75)

    print("\n[1/2] Đang đo lường độ trễ truy xuất dữ liệu (Database Lookup Latency)...")
    latency_results = run_latency_benchmark(num_trials=400)

    print("\n[2/2] Đang đánh giá độ chính xác trích xuất Entity (Precision & Recall)...")
    extraction_results = run_extraction_benchmark()

    # Save to JSON
    report = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "latency_metrics": latency_results,
        "extraction_metrics": extraction_results,
    }

    OUTPUT_REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_REPORT_PATH, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    # Print Visual Summary
    print("\n" + "=" * 75)
    print("📊 KẾT QUẢ ĐO LƯỜNG ĐỘ TRỄ DATABASE (DATABASE LOOKUP LATENCY)")
    print("=" * 75)
    print(f"{'Phương pháp':<26} | {'p50 (ms)':<9} | {'p95 (ms)':<9} | {'QPS':<8} | {'Đạt < 2ms?':<10}")
    print("-" * 75)
    for name, m in latency_results.items():
        status_str = "✅ ĐẠT" if m["target_under_2ms"] else "❌ VƯỢT"
        display_name = {
            "json_sequential_scan": "1. Baseline JSON Scan",
            "sqlite_unindexed": "2. SQLite Unindexed",
            "sqlite_indexed": "3. SQLite Indexed",
            "sqlite_lru_cache": "4. SQLite + LRU Cache",
        }.get(name, name)
        print(f"{display_name:<26} | {m['p50_ms']:<9.4f} | {m['p95_ms']:<9.4f} | {m['qps']:<8.0f} | {status_str:<10}")

    print("\n" + "=" * 75)
    print("🎯 KẾT QUẢ TRÍCH XUẤT THỰC THỂ (ENTITY EXTRACTION PRECISION & RECALL)")
    print("=" * 75)
    b_ord = extraction_results["baseline_regex"]["order_extraction"]
    a_ord = extraction_results["advanced_react_extractor"]["order_extraction"]
    b_ph = extraction_results["baseline_regex"]["phone_extraction"]
    a_ph = extraction_results["advanced_react_extractor"]["phone_extraction"]
    act_acc = extraction_results["advanced_react_extractor"]["action_intent_accuracy"]

    print(f"{'Thành phần':<28} | {'Precision':<10} | {'Recall':<10} | {'F1-Score':<10}")
    print("-" * 75)
    print(f"{'Baseline Regex (Order ID)':<28} | {b_ord['precision']:<10.2%} | {b_ord['recall']:<10.2%} | {b_ord['f1_score']:<10.2%}")
    print(f"{'Advanced ReAct (Order ID)':<28} | {a_ord['precision']:<10.2%} | {a_ord['recall']:<10.2%} | {a_ord['f1_score']:<10.2%}")
    print("-" * 75)
    print(f"{'Baseline Regex (Phone)':<28} | {b_ph['precision']:<10.2%} | {b_ph['recall']:<10.2%} | {b_ph['f1_score']:<10.2%}")
    print(f"{'Advanced ReAct (Phone)':<28} | {a_ph['precision']:<10.2%} | {a_ph['recall']:<10.2%} | {a_ph['f1_score']:<10.2%}")
    print("-" * 75)
    print(f"🎯 Độ chính xác nhận diện Tool Action Intent (ReAct): {act_acc}%\n")
    print(f"📁 Báo cáo chi tiết đã được lưu tại: {OUTPUT_REPORT_PATH.relative_to(ROOT_DIR)}")
    print("=" * 75)


if __name__ == "__main__":
    main()
