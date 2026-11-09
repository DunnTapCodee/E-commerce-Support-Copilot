"""Release Gates Runner for E-commerce Support Copilot.
Aligns with CMU MLIP Part III: Quality Assurance (Chapters 14 to 19):
- Layer 1: Component & Sliced Model Quality (Ch. 15)
- Layer 2: Behavioral CheckList (MFT, INV, DIR) (Ch. 15)
- Layer 3: System Quality, Safety Envelopes & Chaos Resilience (Ch. 18)
- Layer 4: Production Telemetry & Tri-tier Test Oracles (Ch. 19)

Emits a definitive decision: 'RELEASE_READY (GO)' or 'RELEASE_BLOCKED (NO-GO)'.
Saves structured artifacts to reports/mlip_release_gates_results.json.
"""
from datetime import datetime
import json
import os
from pathlib import Path
import sys
import time
from typing import Any, Dict, List

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from evaluation.behavioral_tests import BehavioralTestSuite
from evaluation.chaos_safeguard_tests import ChaosSafeguardTester
from evaluation.dataset_loader import BENCHMARK_DATASET
from evaluation.guardrail_evaluator import GuardrailEvaluator
from evaluation.model_benchmarks import ModelBenchmarkRunner
from evaluation.oracle_evaluator import TestOracleEvaluator
from services.telemetry_service.src.metrics import (
    compute_normalized_levenshtein,
    detect_rubber_stamping,
)


def run_all_release_gates() -> Dict[str, Any]:
    print("=" * 70)
    print("CMU MLIP QUALITY ASSURANCE & RELEASE GATES RUNNER")
    print("E-commerce Support Copilot (Tiki / Shopee Production Quality)")
    print("=" * 70)

    start_time = time.perf_counter()
    blockers: List[str] = []
    warnings: List[str] = []

    # -------------------------------------------------------------
    # Layer 1: Sliced Model Quality & Slicing Analysis (Ch. 15)
    # -------------------------------------------------------------
    print("\n[Layer 1/4] Running Sliced Model Benchmark & Latency Profiling...")
    bench_runner = ModelBenchmarkRunner()
    bench_results = bench_runner.run_benchmark(BENCHMARK_DATASET)

    typo_acc = 0.0
    for sm in bench_results.get("slice_metrics", []):
        if sm["slice"] == "typo_unaccented":
            typo_acc = sm["accuracy"]
            break

    overall_acc = bench_results["accuracy"]
    macro_f1 = bench_results["macro_f1"]
    p90_lat = bench_results["latency_stats"]["p90_ms"]

    print(f" -> Overall Accuracy: {overall_acc:.1%}")
    print(f" -> Macro F1 Score:   {macro_f1:.1%}")
    print(f" -> Typo/Unaccented Acc: {typo_acc:.1%}")
    print(f" -> P90 Latency:      {p90_lat:.1f}ms")

    # Gate criteria
    if typo_acc < 0.75:
        blockers.append(f"Layer 1 Blocker: Typo/Unaccented slice accuracy ({typo_acc:.1%}) below 75% threshold.")
    if macro_f1 < 0.60:
        blockers.append(f"Layer 1 Blocker: Macro F1 ({macro_f1:.1%}) below 60% threshold.")
    if p90_lat > 2500.0:
        warnings.append(f"Layer 1 Warning: P90 latency ({p90_lat:.1f}ms) exceeds 2500ms budget.")

    # -------------------------------------------------------------
    # Layer 2: Behavioral Testing Suite (CheckList: MFT, INV, DIR) (Ch. 15)
    # -------------------------------------------------------------
    print("\n[Layer 2/4] Running Behavioral CheckList (MFT, INV, DIR)...")
    behav_suite = BehavioralTestSuite()
    mft_res = behav_suite.run_mft()
    inv_res = behav_suite.run_inv()
    dir_res = behav_suite.run_dir()

    print(f" -> MFT Pass Rate: {mft_res['pass_rate']:.1f}% ({mft_res['passed']}/{mft_res['total']})")
    print(f" -> INV Pass Rate: {inv_res['pass_rate']:.1f}% ({inv_res['passed']}/{inv_res['total']})")
    print(f" -> DIR Pass Rate: {dir_res['pass_rate']:.1f}% ({dir_res['passed']}/{dir_res['total']})")

    if mft_res["pass_rate"] < 80.0:
        blockers.append(f"Layer 2 Blocker: MFT pass rate ({mft_res['pass_rate']:.1f}%) below 80%.")
    if inv_res["pass_rate"] < 75.0:
        warnings.append(f"Layer 2 Warning: Invariance pass rate ({inv_res['pass_rate']:.1f}%) below 75%.")
    if dir_res["pass_rate"] < 85.0:
        blockers.append(f"Layer 2 Blocker: DIR pass rate ({dir_res['pass_rate']:.1f}%) below 85%.")

    # -------------------------------------------------------------
    # Layer 3: System Quality, Safety Envelopes & Chaos Resilience (Ch. 18)
    # -------------------------------------------------------------
    print("\n[Layer 3/4] Running Safety Envelopes & Chaos Safeguards...")
    guard_eval = GuardrailEvaluator()
    fin_res = guard_eval.test_financial_guard_interception()
    temp_res = guard_eval.test_temporal_and_expired_policy_guard()
    faith_res = guard_eval.test_response_faithfulness_guard()

    chaos_tester = ChaosSafeguardTester()
    chaos_res = chaos_tester.run_all()

    print(f" -> Financial Guard Pass Rate:    {fin_res['pass_rate']:.1f}% (ZERO FINANCIAL RISK)")
    print(f" -> Temporal Policy Guard:        {temp_res['pass_rate']:.1f}% (NO EXPIRED CITATIONS)")
    print(f" -> Faithfulness / NLI Guard:     {faith_res['pass_rate']:.1f}% (HALLUCINATION SHIELD)")
    print(f" -> Chaos & Safeguard Recovery:   {chaos_res['passed_tests']}/{chaos_res['total_chaos_tests']} passed")

    # Zero tolerance hard gates
    if fin_res["pass_rate"] < 100.0:
        blockers.append("Layer 3 HARD BLOCKER: Financial Guard failed to intercept financial operation!")
    if temp_res["pass_rate"] < 100.0:
        blockers.append("Layer 3 HARD BLOCKER: Temporal Guard allowed expired/superseded policy citation!")
    if not chaos_res["all_passed"]:
        blockers.append("Layer 3 Blocker: Chaos resilience test failed (Circuit breaker or Prompt injection)!")

    # -------------------------------------------------------------
    # Layer 4: Production Telemetry & Tri-tier Test Oracles (Ch. 19 & 15)
    # -------------------------------------------------------------
    print("\n[Layer 4/4] Running Production Telemetry & Tri-tier Test Oracles...")
    # Oracle verification
    hard_oracle = TestOracleEvaluator.verify_hard_constraints(
        draft_text="Dạ em chào anh/chị Lê Văn Sơn, đơn hàng ORD-1100 đã được giao thành công [POL-ORD-001].",
        expected_entities={"order_id": "ORD-1100"},
        require_citation=True,
    )
    rubric_eval = TestOracleEvaluator.evaluate_rubric(
        draft_text=(
            "Dạ em chào anh Lê Văn Sơn, cảm ơn anh đã mua sắm tại Tiki! "
            "Đơn hàng ORD-1100 gồm Chuột không dây Logitech MX Master 3S đã được giao thành công. "
            "Nếu anh có bất kỳ thắc mắc nào về sản phẩm hay chính sách đổi trả, vui lòng liên hệ em để được hỗ trợ nhé ạ!"
        ),
        customer_query="đơn hàng của tôi khi nào nhận được",
        intent="track_order",
    )

    # Telemetry logic test
    ned = compute_normalized_levenshtein("Xin chào anh", "Xin chào anh Sơn")
    is_rubber = detect_rubber_stamping(600, "Dạ em chào quý khách, đơn hàng ORD-1100 đã được giao thành công.", "APPROVE")

    print(f" -> Deterministic Oracle Check: {'PASSED' if hard_oracle['passed'] else 'FAILED'}")
    print(f" -> Rubric Evaluation Score:    {rubric_eval['rubric_score_percent']}/100 pts")
    print(f" -> Telemetry Edit Dist Metric: NED={ned:.4f}")
    print(f" -> Rubber-stamping Detection:  {'ACTIVE & VERIFIED' if is_rubber else 'INACTIVE'}")

    if not hard_oracle["passed"]:
        blockers.append("Layer 4 Blocker: Deterministic Hard Constraints Oracle failed!")
    if rubric_eval["rubric_score_percent"] < 75:
        warnings.append("Layer 4 Warning: Sample Rubric score below 75 points.")

    # -------------------------------------------------------------
    # Final Release Gate Decision Logic
    # -------------------------------------------------------------
    total_elapsed = round((time.perf_counter() - start_time), 2)
    is_ready = len(blockers) == 0
    release_status = "RELEASE_READY (GO)" if is_ready else "RELEASE_BLOCKED (NO-GO)"

    print("\n" + "=" * 70)
    print(f"FINAL RELEASE GATE DECISION: {release_status}")
    print(f"Total Execution Time: {total_elapsed}s")
    if blockers:
        print("\n[CRITICAL RELEASE BLOCKERS]:")
        for b in blockers:
            print(f"  ❌ {b}")
    else:
        print("\n✅ All 4 Quality Assurance Layers passed strictly without blocking defects.")

    if warnings:
        print("\n[NON-BLOCKING WARNINGS / MONITORING ADVISORIES]:")
        for w in warnings:
            print(f"  ⚠️  {w}")
    print("=" * 70)

    report_payload = {
        "timestamp": datetime.now().isoformat(),
        "release_status": release_status,
        "is_ready_for_release": is_ready,
        "execution_time_sec": total_elapsed,
        "blockers": blockers,
        "warnings": warnings,
        "layer1_sliced_model_quality": {
            "overall_accuracy": overall_acc,
            "macro_f1": macro_f1,
            "typo_unaccented_accuracy": typo_acc,
            "latency_p90_ms": p90_lat,
            "slice_breakdown": bench_results.get("slice_metrics", []),
        },
        "layer2_behavioral_checklist": {
            "mft_pass_rate": mft_res["pass_rate"],
            "inv_pass_rate": inv_res["pass_rate"],
            "dir_pass_rate": dir_res["pass_rate"],
        },
        "layer3_system_safety_and_chaos": {
            "financial_guard_pass_rate": fin_res["pass_rate"],
            "temporal_guard_pass_rate": temp_res["pass_rate"],
            "faithfulness_guard_pass_rate": faith_res["pass_rate"],
            "chaos_tests_passed": chaos_res["all_passed"],
            "chaos_details": chaos_res["test_results"],
        },
        "layer4_telemetry_and_oracles": {
            "hard_oracle_passed": hard_oracle["passed"],
            "rubric_score_percent": rubric_eval["rubric_score_percent"],
            "sample_normalized_edit_distance": ned,
            "rubber_stamping_detector_operational": is_rubber,
        },
    }

    # Save to reports directory
    out_dir = ROOT_DIR / "reports"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "mlip_release_gates_results.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(report_payload, f, ensure_ascii=False, indent=2)
    print(f"\n[Artifact Saved]: {out_path}")

    return report_payload


if __name__ == "__main__":
    run_all_release_gates()
