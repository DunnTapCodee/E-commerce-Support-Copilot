"""Benchmark p50, p90, and p95 inference, retrieval, and pipeline latency."""
from pathlib import Path
import sys
import time
import requests

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

from services.intent_service.src.predictor import IntentPredictor
from services.rag_service.src.indexer import PolicyVectorIndexer
from services.rag_service.src.retriever import PolicyRetriever
from services.gateway.src.guardrails import (
    evaluate_financial_guard,
    evaluate_intent_guard,
    evaluate_policy_guard,
)


def run_benchmark(n_iterations: int = 50, gateway_url: str = "http://127.0.0.1:8000"):
    print("=" * 65)
    print(f"Running Latency Benchmark ({n_iterations} iterations per component)...")
    print("=" * 65)

    model_path = ROOT_DIR / "artifacts" / "models" / "intent"
    predictor = IntentPredictor(model_path)

    index_path = ROOT_DIR / "artifacts" / "vector_store" / "policy_index.pkl"
    indexer = PolicyVectorIndexer()
    indexer.load(index_path)
    retriever = PolicyRetriever(indexer)

    queries = [
        "Cho tôi hỏi phí ship nội thành là bao nhiêu?",
        "Tôi muốn kiểm tra chính sách đổi trả hàng trong mấy ngày?",
        "Bao lâu thì đơn hàng của tôi được giao tới nơi?",
        "Tôi muốn hoàn tiền đơn hàng này về thẻ tín dụng",
        "Làm thế nào để hủy đơn hàng vừa đặt?",
    ]

    # 1. Benchmark Intent Predictor
    intent_lats = []
    for i in range(n_iterations):
        q = queries[i % len(queries)]
        t0 = time.perf_counter()
        _ = predictor.predict(q)
        intent_lats.append((time.perf_counter() - t0) * 1000)

    intent_lats.sort()
    p50_intent = intent_lats[int(len(intent_lats) * 0.50)]
    p95_intent = intent_lats[int(len(intent_lats) * 0.95)]
    print(f"\n[1] Intent Predictor (CPU):\n  - Mean: {sum(intent_lats)/len(intent_lats):.2f} ms\n  - P50:  {p50_intent:.2f} ms\n  - P95:  {p95_intent:.2f} ms")

    # 2. Benchmark Vector Retrieval
    rag_lats = []
    for i in range(n_iterations):
        q = queries[i % len(queries)]
        t0 = time.perf_counter()
        _ = retriever.retrieve(q, top_k=3)
        rag_lats.append((time.perf_counter() - t0) * 1000)

    rag_lats.sort()
    p50_rag = rag_lats[int(len(rag_lats) * 0.50)]
    p95_rag = rag_lats[int(len(rag_lats) * 0.95)]
    print(f"\n[2] Policy Retriever (Top-3 Cosine Similarity):\n  - Mean: {sum(rag_lats)/len(rag_lats):.2f} ms\n  - P50:  {p50_rag:.2f} ms\n  - P95:  {p95_rag:.2f} ms")

    # 3. Benchmark Local Pipeline (Intent -> Guardrails -> Retrieval -> Policy Guard)
    pipe_lats = []
    for i in range(n_iterations):
        q = queries[i % len(queries)]
        t0 = time.perf_counter()
        pred = predictor.predict(q)
        intent_guard = evaluate_intent_guard(pred)
        if intent_guard.allow_llm:
            fin_guard = evaluate_financial_guard(pred.intent)
            if not fin_guard:
                docs = retriever.retrieve(q, intent=pred.intent, top_k=3)
                _ = evaluate_policy_guard(docs)
        pipe_lats.append((time.perf_counter() - t0) * 1000)

    pipe_lats.sort()
    p50_pipe = pipe_lats[int(len(pipe_lats) * 0.50)]
    p95_pipe = pipe_lats[int(len(pipe_lats) * 0.95)]
    print(f"\n[3] Orchestration State Machine Pipeline (Local):\n  - Mean: {sum(pipe_lats)/len(pipe_lats):.2f} ms\n  - P50:  {p50_pipe:.2f} ms\n  - P95:  {p95_pipe:.2f} ms")
    print(f"  - Target Requirement (P95 <= 12000 ms): {'PASS' if p95_pipe <= 12000 else 'FAIL'}")

    # 4. Optional Live Gateway Test
    try:
        res = requests.get(f"{gateway_url}/health", timeout=1.0)
        if res.status_code == 200:
            print(f"\n[4] Live Gateway ({gateway_url}) is UP. Testing HTTP E2E Latency...")
            gw_lats = []
            for i in range(min(15, n_iterations)):
                q = queries[i % len(queries)]
                t0 = time.perf_counter()
                requests.post(
                    f"{gateway_url}/api/v1/copilot/query",
                    json={"query": q, "session_id": f"bench-{i}"},
                    timeout=5.0,
                )
                gw_lats.append((time.perf_counter() - t0) * 1000)
            gw_lats.sort()
            print(f"  - Gateway E2E P50: {gw_lats[int(len(gw_lats)*0.5)]:.2f} ms | P95: {gw_lats[int(len(gw_lats)*0.95)]:.2f} ms")
    except Exception:
        print(f"\n[4] Live Gateway ({gateway_url}) is not running right now (skipping HTTP network bench).")

    print("\n" + "=" * 65)


if __name__ == "__main__":
    run_benchmark(50)
