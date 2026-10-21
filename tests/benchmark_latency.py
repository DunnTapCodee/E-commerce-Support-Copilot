"""Benchmark p50 and p95 inference and orchestration latency."""
import time
from src.core.schemas import QueryRequest
from src.orchestrator import CopilotOrchestrator


def run_benchmark(n_iterations: int = 50):
    orchestrator = CopilotOrchestrator()
    queries = [
        "Cho tôi hỏi phí ship nội thành là bao nhiêu?",
        "Tôi muốn kiểm tra chính sách đổi trả hàng",
        "Bao lâu thì đơn hàng của tôi được giao?",
        "Tôi muốn hoàn tiền đơn hàng này",
    ]
    latencies = []
    print(f"Running latency benchmark with {n_iterations} iterations...")
    for i in range(n_iterations):
        q = queries[i % len(queries)]
        start = time.perf_counter()
        orchestrator.handle(QueryRequest(query=q, session_id=f"bench-{i}"))
        latencies.append((time.perf_counter() - start) * 1000)

    latencies.sort()
    p50 = latencies[int(len(latencies) * 0.50)]
    p95 = latencies[int(len(latencies) * 0.95)]
    mean_lat = sum(latencies) / len(latencies)
    print(f"Latency Results (ms):\n- Mean: {mean_lat:.2f} ms\n- P50:  {p50:.2f} ms\n- P95:  {p95:.2f} ms")


if __name__ == '__main__':
    run_benchmark(30)
