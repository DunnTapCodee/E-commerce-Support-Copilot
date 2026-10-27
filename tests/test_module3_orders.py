"""Unit and integration tests for Module 3: Dynamic Data Integration, Caching, and Tool Calling."""
import json
from pathlib import Path
import unittest

from contracts.schemas import OrderCancelRequest
from services.gateway.src.agent import extract_entities_advanced, extract_entities_baseline
from services.telemetry_service.src.cache import OrderLRUCache, normalize_phone
from services.telemetry_service.src.database import get_db_connection, init_db, migrate_mock_orders
from services.telemetry_service.src.repository import TelemetryRepository

ROOT_DIR = Path(__file__).resolve().parent.parent
DB_PATH = ROOT_DIR / "copilot_telemetry.sqlite3"
ORDERS_JSON = ROOT_DIR / "data" / "mock_orders.json"


class TestModule3OrdersAndTools(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_db(DB_PATH)
        migrate_mock_orders(DB_PATH, ORDERS_JSON, force=True)
        cls.repo = TelemetryRepository(DB_PATH, ORDERS_JSON)

    def test_database_migration_count(self):
        """Verify that all 100 Tiki mock orders are migrated into SQLite."""
        with get_db_connection(DB_PATH) as conn:
            count = conn.execute("SELECT COUNT(*) FROM orders;").fetchone()[0]
        self.assertEqual(count, 100)

    def test_indexed_lookup_by_order_id(self):
        """Lookup order by order_id returns correct details."""
        order = self.repo.get_order("ORD-1001")
        self.assertIsNotNone(order)
        self.assertEqual(order["order_id"], "ORD-1001")
        self.assertEqual(order["customer_id"], "demo-customer")
        self.assertIn("items", order)
        self.assertIsInstance(order["items"], list)

    def test_indexed_lookup_by_phone(self):
        """Lookup order by phone number (formatted or digits) works."""
        order = self.repo.get_order("0938.242.854")
        self.assertIsNotNone(order)
        self.assertEqual(order["order_id"], "ORD-1001")

        # Test normalized digits
        order_digits = self.repo.get_order("0938242854")
        self.assertIsNotNone(order_digits)
        self.assertEqual(order_digits["order_id"], "ORD-1001")

    def test_lru_cache_operations(self):
        """Test LRU cache hit, miss, and capacity eviction."""
        cache = OrderLRUCache(max_size=3)
        cache.put({"order_id": "ORD-1", "customer_id": "c1", "phone": "0911"})
        cache.put({"order_id": "ORD-2", "customer_id": "c2", "phone": "0922"})
        cache.put({"order_id": "ORD-3", "customer_id": "c3", "phone": "0933"})

        self.assertIsNotNone(cache.get("ORD-1"))
        self.assertEqual(cache.hits, 1)

        # Evict oldest (ORD-2 should be evicted since ORD-1 was recently accessed)
        cache.put({"order_id": "ORD-4", "customer_id": "c4", "phone": "0944"})
        self.assertIsNone(cache.get("ORD-2"))
        self.assertEqual(cache.misses, 1)

    def test_order_cancellation(self):
        """Test cancellation logic, status change, and idempotency."""
        # ORD-1026 is a pending order that can be cancelled
        res = self.repo.cancel_order("ORD-1026", reason="Test reason")
        self.assertTrue(res["success"])
        self.assertEqual(res["updated_status"], "Cancelled")

        # Second cancel should fail as already cancelled
        res2 = self.repo.cancel_order("ORD-1026", reason="Test again")
        self.assertFalse(res2["success"])

    def test_entity_extraction_advanced_comparison(self):
        """Verify advanced extractor handles colloquial forms missed by baseline regex."""
        # Query with shorthand number without ORD- prefix
        q1 = "hủy đơn 1030 giùm tôi vì giao lâu"
        b1 = extract_entities_baseline(q1)
        a1 = extract_entities_advanced(q1)

        self.assertIsNone(b1["order_id"])  # Baseline missed it
        self.assertEqual(a1["order_id"], "ORD-1030")  # Advanced resolved it
        self.assertEqual(a1["action"], "cancel")

        # Query with phone number
        q2 = "Kiểm tra đơn hàng của số điện thoại 0938.242.854"
        b2 = extract_entities_baseline(q2)
        a2 = extract_entities_advanced(q2)

        self.assertIsNone(b2["phone"])
        self.assertEqual(a2["phone"], "0938.242.854")
        self.assertEqual(a2["action"], "status")

        # Queries with spaces around hyphen or English syntax: "check order ORD - 1003", "check order 1003"
        q3 = "check order ORD - 1003"
        a3 = extract_entities_advanced(q3)
        self.assertEqual(a3["order_id"], "ORD-1003")
        self.assertEqual(a3["action"], "status")

        q4 = "check order 1003"
        a4 = extract_entities_advanced(q4)
        self.assertEqual(a4["order_id"], "ORD-1003")
        self.assertEqual(a4["action"], "status")

        # Lookup by shorthand order_id in repository
        order_shorthand = self.repo.get_order("1003")
        self.assertIsNotNone(order_shorthand)
        self.assertEqual(order_shorthand["order_id"], "ORD-1003")

        order_spaced = self.repo.get_order("ORD - 1003")
        self.assertIsNotNone(order_spaced)
        self.assertEqual(order_spaced["order_id"], "ORD-1003")

        # Query with spaced phone number: "check order  0999 532 448"
        q5 = "check order  0999 532 448"
        a5 = extract_entities_advanced(q5)
        self.assertIsNone(a5["order_id"])  # Phone digits should not be falsely captured as order_id
        self.assertEqual(a5["phone"], "0999 532 448")
        self.assertEqual(a5["action"], "status")

        # Multi-order lookup by phone number
        orders_by_phone = self.repo.get_orders_by_phone("0999 532 448")
        self.assertEqual(len(orders_by_phone), 2)
        order_ids_found = [o["order_id"] for o in orders_by_phone]
        self.assertIn("ORD-1003", order_ids_found)
        self.assertIn("ORD-1088", order_ids_found)


if __name__ == "__main__":
    unittest.main()
