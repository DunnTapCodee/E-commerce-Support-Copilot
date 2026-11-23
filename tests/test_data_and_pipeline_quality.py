"""Layer 7 & Layer 4: Data Quality, Schema Validation & RAG Pipeline Regression Tests.

Validates policies.json, mock_orders.json, and both default `bm25` and legacy `tfidf`
active-only retrieval & expired/superseded trap rejection in an isolated temporary directory.
"""
from datetime import datetime
import gc
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

from contracts.schemas import RetrievedDocument
from services.rag_service.src.indexer import PolicyVectorIndexer
from services.rag_service.src.retriever import PolicyRetriever

ROOT_DIR = Path(__file__).resolve().parent.parent
POLICIES_PATH = ROOT_DIR / "data" / "knowledge_base" / "policies.json"
ORDERS_PATH = ROOT_DIR / "data" / "mock_orders.json"


class TestDataAndPipelineQuality(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp_dir = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        with open(POLICIES_PATH, "r", encoding="utf-8") as f:
            cls.raw_policies = json.load(f)
        with open(ORDERS_PATH, "r", encoding="utf-8") as f:
            cls.raw_orders = json.load(f)

        cls.documents = [RetrievedDocument(**doc) for doc in cls.raw_policies]
        cls.indexer = PolicyVectorIndexer()
        cls.indexer.fit_and_save(cls.documents, Path(cls.tmp_dir.name) / "test_policy_index.pkl")
        cls.retrievers = [("tfidf", PolicyRetriever(cls.indexer, method="tfidf"))]
        if importlib.util.find_spec("rank_bm25") is not None:
            cls.retrievers.insert(0, ("bm25", PolicyRetriever(cls.indexer, method="bm25")))

    @classmethod
    def tearDownClass(cls):
        cls.retrievers = []
        cls.indexer = None
        gc.collect()
        cls.tmp_dir.cleanup()

    def test_policies_json_schema_and_uniqueness(self):
        """All policy documents must have unique doc_ids, non-empty content, and valid policy_type."""
        self.assertGreater(len(self.raw_policies), 5, "Knowledge base should contain sufficient policies")
        seen_ids = set()
        valid_policy_types = {"permanent", "temporary", "superseded"}

        for item in self.raw_policies:
            doc_id = item.get("doc_id", "").strip()
            self.assertTrue(doc_id.startswith("POL-"), f"Invalid doc_id prefix: {doc_id}")
            self.assertNotIn(doc_id, seen_ids, f"Duplicate doc_id detected in policies.json: {doc_id}")
            seen_ids.add(doc_id)

            self.assertTrue(len(item.get("title", "").strip()) >= 10, f"Policy {doc_id} title too short")
            self.assertTrue(len(item.get("content", "").strip()) >= 30, f"Policy {doc_id} content too short")
            self.assertIn(
                item.get("policy_type"),
                valid_policy_types,
                f"Policy {doc_id} has invalid policy_type: {item.get('policy_type')}",
            )

            if item.get("policy_type") == "superseded":
                self.assertFalse(item.get("is_active"), f"Superseded policy {doc_id} must have is_active=False")

            for date_field in ("effective_date", "expiration_date"):
                val = item.get(date_field)
                if val:
                    datetime.strptime(val[:10], "%Y-%m-%d")

    def test_mock_orders_schema_and_financial_integrity(self):
        """All order records must have unique order_ids, positive total_amount, and valid items list."""
        self.assertGreater(len(self.raw_orders), 0, "mock_orders.json must not be empty")
        seen_order_ids = set()

        for order in self.raw_orders:
            oid = order.get("order_id", "").strip()
            self.assertTrue(oid.startswith("ORD-"), f"Invalid order_id format: {oid}")
            self.assertNotIn(oid, seen_order_ids, f"Duplicate order_id in mock_orders.json: {oid}")
            seen_order_ids.add(oid)

            amount = order.get("total_amount", 0)
            self.assertIsInstance(amount, (int, float))
            self.assertGreater(amount, 0, f"Order {oid} must have positive total_amount")
            self.assertTrue(order.get("customer_id"), f"Order {oid} missing customer_id")
            self.assertTrue(isinstance(order.get("items"), list) and len(order["items"]) > 0)

    def test_rag_index_regression_top3_recall(self):
        """Both runtime default BM25 and TF-IDF return canonical policies within Top-3 for core queries."""
        golden_queries = [
            ("Chính sách đổi trả sản phẩm trong bao nhiêu ngày?", "return_policy", "POL-RET-001"),
            ("Hướng dẫn các bước tạo yêu cầu trả hàng trên app", "return_product", "POL-RET-002"),
            ("Thời gian giao hàng tiêu chuẩn mất bao lâu?", "delivery_time", "POL-SHIP-001"),
            ("Phí vận chuyển freeship tính như thế nào?", "shipping_costs", "POL-SHIP-002"),
            ("Làm sao để hủy đơn hàng đã đặt?", "cancel_order", "POL-ORD-002"),
            ("Bao lâu thì tiền hoàn về tài khoản ngân hàng?", "refund_status", "POL-REFUND-002"),
        ]

        for name, retriever in self.retrievers:
            hits = 0
            for query, intent, expected_doc_id in golden_queries:
                results = retriever.retrieve(query, intent=intent, top_k=3, filter_active_only=True)
                if expected_doc_id in [r.doc_id for r in results]:
                    hits += 1
            recall_at_3 = hits / len(golden_queries)
            self.assertGreaterEqual(
                recall_at_3,
                0.85,
                f"RAG Top-3 Recall ({name}) regression detected: {recall_at_3:.1%} (expected >= 85%)",
            )

    def test_rag_pipeline_blocks_expired_policies_on_normal_queries(self):
        """Normal queries with filter_active_only=True must NEVER return inactive or OLD policies."""
        queries = [
            "Chính sách bảo hành sản phẩm điện tử",
            "Khuyến mãi hoàn xu hiện tại",
            "Quy định đổi trả hàng hóa",
        ]
        for _, retriever in self.retrievers:
            for q in queries:
                docs = retriever.retrieve(q, top_k=5, filter_active_only=True)
                for d in docs:
                    self.assertTrue(d.is_active, f"Inactive policy {d.doc_id} leaked into active retrieval!")
                    self.assertNotIn("OLD", d.doc_id, f"Historical trap policy {d.doc_id} leaked into normal query!")


if __name__ == "__main__":
    unittest.main()
