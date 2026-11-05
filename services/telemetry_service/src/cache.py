"""Thread-safe LRU Cache Layer for Order Lookups."""
from collections import OrderedDict
import re
import threading
from typing import Any, Dict, List, Optional


def normalize_phone(phone: str) -> str:
    """Normalize phone numbers to digits only, e.g. '0938.242.854' -> '0938242854'."""
    if not phone:
        return ""
    digits = re.sub(r"\D", "", phone)
    if digits.startswith("84") and len(digits) == 11:
        digits = "0" + digits[2:]
    return digits


class OrderLRUCache:
    """High-performance in-memory LRU Cache with secondary index lookups."""

    def __init__(self, max_size: int = 256):
        self.max_size = max_size
        self._lock = threading.RLock()
        self._cache: OrderedDict[str, Dict[str, Any]] = OrderedDict()
        self._phone_map: Dict[str, str] = {}
        self._customer_map: Dict[str, str] = {}
        self._tracking_map: Dict[str, str] = {}

        self.hits: int = 0
        self.misses: int = 0
        self.evictions: int = 0

    def get(self, key: str) -> Optional[Dict[str, Any]]:
        """Look up order by order_id, phone, customer_id, or tracking_code."""
        if not key:
            return None

        clean_key = key.strip().lower()
        clean_key = re.sub(r"\bord\s*[-_:]\s*", "ord-", clean_key)
        if clean_key.isdigit() and len(clean_key) >= 4:
            clean_key = f"ord-{clean_key}"
        phone_key = normalize_phone(clean_key)

        with self._lock:
            # 1. Direct order_id hit
            if clean_key in self._cache:
                self.hits += 1
                self._cache.move_to_end(clean_key)
                return self._cache[clean_key].copy()

            # 2. Phone index hit
            if phone_key and phone_key in self._phone_map:
                order_ids = self._phone_map[phone_key]
                if isinstance(order_ids, list) and order_ids:
                    latest_id = order_ids[-1]
                    if latest_id in self._cache:
                        self.hits += 1
                        self._cache.move_to_end(latest_id)
                        return self._cache[latest_id].copy()
                elif isinstance(order_ids, str) and order_ids in self._cache:
                    self.hits += 1
                    self._cache.move_to_end(order_ids)
                    return self._cache[order_ids].copy()

            # 3. Tracking code hit
            if clean_key.upper() in self._tracking_map:
                order_id = self._tracking_map[clean_key.upper()]
                if order_id in self._cache:
                    self.hits += 1
                    self._cache.move_to_end(order_id)
                    return self._cache[order_id].copy()

            # 4. Customer ID hit
            if clean_key in self._customer_map:
                order_id = self._customer_map[clean_key]
                if order_id in self._cache:
                    self.hits += 1
                    self._cache.move_to_end(order_id)
                    return self._cache[order_id].copy()

            self.misses += 1
            return None

    def put(self, order: Dict[str, Any]) -> None:
        """Insert or refresh order in LRU cache and update index maps."""
        if not order or "order_id" not in order:
            return

        order_id = str(order["order_id"]).strip().lower()
        customer_id = str(order.get("customer_id", "")).strip().lower()
        phone = normalize_phone(str(order.get("phone", "")))
        tracking = str(order.get("tracking_code", "")).strip().upper()

        with self._lock:
            if order_id in self._cache:
                self._cache.move_to_end(order_id)
            self._cache[order_id] = order.copy()

            # Update secondary indices
            if customer_id:
                self._customer_map[customer_id] = order_id
            if phone:
                if phone not in self._phone_map or isinstance(self._phone_map[phone], str):
                    existing = [self._phone_map[phone]] if isinstance(self._phone_map.get(phone), str) else []
                    self._phone_map[phone] = existing
                if order_id not in self._phone_map[phone]:
                    self._phone_map[phone].append(order_id)
            if tracking:
                self._tracking_map[tracking] = order_id

            # Evict oldest entry if over capacity
            while len(self._cache) > self.max_size:
                evicted_id, evicted_order = self._cache.popitem(last=False)
                self.evictions += 1
                self._cleanup_indices(evicted_id, evicted_order)

    def get_all_by_phone(self, phone: str) -> List[Dict[str, Any]]:
        """Retrieve all cached orders for a given phone."""
        phone_key = normalize_phone(phone)
        with self._lock:
            if phone_key in self._phone_map:
                order_ids = self._phone_map[phone_key]
                if isinstance(order_ids, list):
                    return [self._cache[oid].copy() for oid in order_ids if oid in self._cache]
                elif isinstance(order_ids, str) and order_ids in self._cache:
                    return [self._cache[order_ids].copy()]
        return []

    def _cleanup_indices(self, order_id: str, order: Dict[str, Any]) -> None:
        """Clean up secondary mapping when an item is evicted."""
        cust_id = str(order.get("customer_id", "")).strip().lower()
        phone = normalize_phone(str(order.get("phone", "")))
        tracking = str(order.get("tracking_code", "")).strip().upper()

        if cust_id in self._customer_map and self._customer_map[cust_id] == order_id:
            del self._customer_map[cust_id]
        if phone in self._phone_map:
            if isinstance(self._phone_map[phone], list):
                if order_id in self._phone_map[phone]:
                    self._phone_map[phone].remove(order_id)
                if not self._phone_map[phone]:
                    del self._phone_map[phone]
            elif self._phone_map[phone] == order_id:
                del self._phone_map[phone]
        if tracking in self._tracking_map and self._tracking_map[tracking] == order_id:
            del self._tracking_map[tracking]

    def invalidate(self, order_id: str) -> bool:
        """Remove order from cache on mutation (e.g. cancellation)."""
        clean_id = order_id.strip().lower()
        with self._lock:
            if clean_id in self._cache:
                order = self._cache.pop(clean_id)
                self._cleanup_indices(clean_id, order)
                return True
            return False

    def clear(self) -> None:
        """Clear all cached entries and reset statistics."""
        with self._lock:
            self._cache.clear()
            self._phone_map.clear()
            self._customer_map.clear()
            self._tracking_map.clear()
            self.hits = 0
            self.misses = 0
            self.evictions = 0

    def stats(self) -> Dict[str, Any]:
        """Return cache health and performance statistics."""
        with self._lock:
            total_lookups = self.hits + self.misses
            hit_ratio = round((self.hits / total_lookups) * 100, 2) if total_lookups > 0 else 0.0
            return {
                "size": len(self._cache),
                "max_size": self.max_size,
                "hits": self.hits,
                "misses": self.misses,
                "total_lookups": total_lookups,
                "hit_ratio_percent": hit_ratio,
                "evictions": self.evictions,
            }
