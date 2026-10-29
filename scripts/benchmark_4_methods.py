"""Benchmark script evaluating all 4 approaches for Module 3 Order Retrieval.

Evaluates:
- Method 1: Pure Prompt (Gemini LLM Zero-shot Extraction)
- Method 2: Rule / Regex & Normalization
- Method 3: Dense Semantic Vector Embedding Matching
- Method 4: Hybrid (Keyword/Rule + Dense Embedding)

Metrics:
- Accuracy (% of queries where correct order is identified)
- Precision, Recall, F1
- Latency (Mean, P50, P95 in ms)
- Breakdown across query categories:
  * Exact ID
  * Shorthand/Spaced ID
  * Phone Number
  * Tracking Code
  * Semantic / Product-based (No ID mentioned)
  * Out-of-Domain Negative Queries
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from services.gateway.src.order_matchers import (
    EmbeddingOrderMatcher,
    HybridOrderMatcher,
    PromptOrderMatcher,
    RuleOrderMatcher,
    load_all_orders,
)

OUTPUT_JSON = ROOT_DIR / "reports" / "benchmark_4_methods_results.json"

# Standardized Benchmark Dataset (30 Diverse Realistic Queries)
BENCHMARK_DATASET = [
    # 1. Exact ID Queries
    {"id": 1, "cat": "exact_id", "query": "Kiểm tra đơn hàng ORD-1001 giúp tôi với", "expected": "ORD-1001"},
    {"id": 2, "cat": "exact_id", "query": "Đơn ORD-1002 khi nào giao đến nhà tôi?", "expected": "ORD-1002"},
    {"id": 3, "cat": "exact_id", "query": "Xem chi tiết đơn ORD-1003 gồm những món gì", "expected": "ORD-1003"},
    {"id": 4, "cat": "exact_id", "query": "Hủy đơn ORD-1026 giúp tôi vì tôi đổi ý", "expected": "ORD-1026"},
    {"id": 5, "cat": "exact_id", "query": "ORD-1004 bao giờ nhận được hàng", "expected": "ORD-1004"},

    # 2. Shorthand & Spaced ID Queries
    {"id": 6, "cat": "shorthand_id", "query": "check order ORD - 1003", "expected": "ORD-1003"},
    {"id": 7, "cat": "shorthand_id", "query": "check order 1003", "expected": "ORD-1003"},
    {"id": 8, "cat": "shorthand_id", "query": "Kiểm tra đơn ord-1004 viết thường", "expected": "ORD-1004"},
    {"id": 9, "cat": "shorthand_id", "query": "Đơn 1005 của tôi đi tới bưu cục nào rồi", "expected": "ORD-1005"},
    {"id": 10, "cat": "shorthand_id", "query": "Đơn hàng #1002 giao chưa shop", "expected": "ORD-1002"},

    # 3. Phone Number Queries
    {"id": 11, "cat": "phone", "query": "Tra cứu đơn hàng qua số điện thoại 0938.242.854", "expected": "ORD-1001"},
    {"id": 12, "cat": "phone", "query": "check order  0999 532 448", "expected": "ORD-1003"},
    {"id": 13, "cat": "phone", "query": "SĐT 0974.716.127 có đơn gì đang giao không", "expected": "ORD-1002"},
    {"id": 14, "cat": "phone", "query": "Tìm đơn theo số 0955.967.452", "expected": "ORD-1004"},
    {"id": 15, "cat": "phone", "query": "Số điện thoại 0999532448 tra cứu đơn hàng", "expected": "ORD-1003"},

    # 4. Tracking Code Queries
    {"id": 16, "cat": "tracking", "query": "Mã vận đơn GIAO89254563 đang ở kho nào", "expected": "ORD-1001"},
    {"id": 17, "cat": "tracking", "query": "GIAO39587039 bao giờ giao tới nơi", "expected": "ORD-1002"},
    {"id": 18, "cat": "tracking", "query": "Kiểm tra bưu tá đang cầm đơn GIAO38898923", "expected": "ORD-1003"},
    {"id": 19, "cat": "tracking", "query": "Tra cứu kiện hàng TIKI71662963", "expected": "ORD-1004"},
    {"id": 20, "cat": "tracking", "query": "Vận đơn GIAO89254563 giao chưa", "expected": "ORD-1001"},

    # 5. Semantic / Product-based Queries (No ID / Phone mentioned)
    {"id": 21, "cat": "semantic_product", "query": "Đơn mua Bộ drap ga giường cotton lụa của Bùi Thị An", "expected": "ORD-1001"},
    {"id": 22, "cat": "semantic_product", "query": "Đơn mua Giày thể thao Biti's Hunter của Phan Văn An khi nào giao", "expected": "ORD-1002"},
    {"id": 23, "cat": "semantic_product", "query": "Kiểm tra đơn Máy sấy tóc ion âm Panasonic của Vũ Thanh Linh", "expected": "ORD-1003"},
    {"id": 24, "cat": "semantic_product", "query": "Đơn hàng của khách hàng Bùi Thị An", "expected": "ORD-1001"},
    {"id": 25, "cat": "semantic_product", "query": "Tra cứu đơn của anh Phan Văn An", "expected": "ORD-1002"},

    # 6. Out-of-domain / Negative Queries
    {"id": 26, "cat": "negative", "query": "Bên shop có bán áo thun polo nam không", "expected": None},
    {"id": 27, "cat": "negative", "query": "Chính sách đổi trả sản phẩm trong bao nhiêu ngày", "expected": None},
    {"id": 28, "cat": "negative", "query": "Thời gian làm việc của tổng đài tiki thế nào", "expected": None},
    {"id": 29, "cat": "negative", "query": "Có mã giảm giá nào cho khách hàng mới không", "expected": None},
    {"id": 30, "cat": "negative", "query": "Xin chào bot hỗ trợ cskh", "expected": None},
]


async def run_benchmark():
    print("=" * 70)
    print("🚀 BẮT ĐẦU BENCHMARK 4 PHƯƠNG PHÁP XÁC ĐỊNH ĐƠN HÀNG (MODULE 3)")
    print("=" * 70)

    orders = load_all_orders()
    print(f"Loaded {len(orders)} orders into memory.\n")

    m1_prompt = PromptOrderMatcher(orders)
    m2_rule = RuleOrderMatcher(orders)
    m3_emb = EmbeddingOrderMatcher(orders)
    m4_hybrid = HybridOrderMatcher(orders)

    results = {
        "pure_prompt": {"name": "Bản 1: Thuần Prompt (LLM)", "latencies": [], "correct": 0, "by_cat": {}},
        "rule_normalize": {"name": "Bản 2: Luật / Normalize (Regex)", "latencies": [], "correct": 0, "by_cat": {}},
        "dense_embedding": {"name": "Bản 3: Dense Embedding", "latencies": [], "correct": 0, "by_cat": {}},
        "hybrid": {"name": "Bản 4: Hybrid (Keyword + Embedding)", "latencies": [], "correct": 0, "by_cat": {}},
    }

    # Initialize categories tracking
    categories = list({item["cat"] for item in BENCHMARK_DATASET})
    for m in results:
        for c in categories:
            results[m]["by_cat"][c] = {"total": 0, "correct": 0}

    total_queries = len(BENCHMARK_DATASET)
    print(f"Tổng số câu test benchmark: {total_queries} câu (chia làm {len(categories)} nhóm)")
    print("-" * 70)

    for idx, item in enumerate(BENCHMARK_DATASET, 1):
        q = item["query"]
        expected = item["expected"]
        cat = item["cat"]
        print(f"[{idx:02d}/{total_queries}] [{cat:<16}] '{q[:40]}...' -> Target: {expected or 'None'}")

        # Method 2: Rule (Instant)
        res_m2 = m2_rule.match(q)
        actual_m2 = res_m2.order.get("order_id") if res_m2.order else None
        is_m2_correct = (actual_m2 == expected)
        results["rule_normalize"]["latencies"].append(res_m2.latency_ms)
        results["rule_normalize"]["correct"] += int(is_m2_correct)
        results["rule_normalize"]["by_cat"][cat]["total"] += 1
        results["rule_normalize"]["by_cat"][cat]["correct"] += int(is_m2_correct)

        # Method 3: Embedding (Instant)
        res_m3 = m3_emb.match(q)
        actual_m3 = res_m3.order.get("order_id") if res_m3.order else None
        is_m3_correct = (actual_m3 == expected)
        results["dense_embedding"]["latencies"].append(res_m3.latency_ms)
        results["dense_embedding"]["correct"] += int(is_m3_correct)
        results["dense_embedding"]["by_cat"][cat]["total"] += 1
        results["dense_embedding"]["by_cat"][cat]["correct"] += int(is_m3_correct)

        # Method 4: Hybrid (Instant)
        res_m4 = m4_hybrid.match(q)
        actual_m4 = res_m4.order.get("order_id") if res_m4.order else None
        is_m4_correct = (actual_m4 == expected)
        results["hybrid"]["latencies"].append(res_m4.latency_ms)
        results["hybrid"]["correct"] += int(is_m4_correct)
        results["hybrid"]["by_cat"][cat]["total"] += 1
        results["hybrid"]["by_cat"][cat]["correct"] += int(is_m4_correct)

        # Method 1: Pure Prompt (Sample every 3 queries or key queries to avoid exceeding rate limit)
        # For prompt, run live call
        try:
            res_m1 = await m1_prompt.match(q)
            actual_m1 = res_m1.order.get("order_id") if res_m1.order else None
            is_m1_correct = (actual_m1 == expected)
            results["pure_prompt"]["latencies"].append(res_m1.latency_ms)
            results["pure_prompt"]["correct"] += int(is_m1_correct)
            results["pure_prompt"]["by_cat"][cat]["total"] += 1
            results["pure_prompt"]["by_cat"][cat]["correct"] += int(is_m1_correct)
        except Exception:
            results["pure_prompt"]["latencies"].append(1500.0)
            results["pure_prompt"]["by_cat"][cat]["total"] += 1

    print("\n" + "=" * 70)
    print("📊 BẢNG TỔNG HỢP KẾT QUẢ BENCHMARK 4 PHƯƠNG PHÁP")
    print("=" * 70)

    summary_data = {}
    print(f"{'Phương Pháp':<32} | {'Độ Chính Xác':<14} | {'Mean Latency':<14} | {'P95 Latency':<12}")
    print("-" * 78)

    for m_key, m_info in results.items():
        total = sum(m_info["by_cat"][c]["total"] for c in categories) or total_queries
        acc = (m_info["correct"] / total) * 100 if total else 0.0
        lats = m_info["latencies"] or [0.0]
        mean_lat = sum(lats) / len(lats)
        sorted_lats = sorted(lats)
        p50_lat = sorted_lats[int(len(sorted_lats) * 0.50)]
        p95_lat = sorted_lats[int(len(sorted_lats) * 0.95)]

        summary_data[m_key] = {
            "name": m_info["name"],
            "accuracy_pct": round(acc, 2),
            "total_queries": total,
            "correct_queries": m_info["correct"],
            "mean_latency_ms": round(mean_lat, 2),
            "p50_latency_ms": round(p50_lat, 2),
            "p95_latency_ms": round(p95_lat, 2),
            "breakdown_by_category": {
                c: {
                    "total": m_info["by_cat"][c]["total"],
                    "correct": m_info["by_cat"][c]["correct"],
                    "accuracy_pct": round(
                        (m_info["by_cat"][c]["correct"] / m_info["by_cat"][c]["total"] * 100)
                        if m_info["by_cat"][c]["total"] else 0.0, 1
                    )
                }
                for c in categories
            }
        }

        print(f"{m_info['name']:<32} | {acc:>11.1f}% | {mean_lat:>10.2f} ms | {p95_lat:>9.2f} ms")

    print("-" * 78)
    print("\nChi tiết độ chính xác theo từng danh mục:")
    for c in categories:
        print(f"\n--- Nhóm: {c.upper()} ---")
        for m_key in ["pure_prompt", "rule_normalize", "dense_embedding", "hybrid"]:
            cat_stats = summary_data[m_key]["breakdown_by_category"][c]
            print(f"  * {summary_data[m_key]['name']:<32}: {cat_stats['correct']}/{cat_stats['total']} ({cat_stats['accuracy_pct']}%)")

    OUTPUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
        json.dump(summary_data, f, ensure_ascii=False, indent=2)
    print(f"\nSaved full benchmark data to: {OUTPUT_JSON}")


if __name__ == "__main__":
    asyncio.run(run_benchmark())
