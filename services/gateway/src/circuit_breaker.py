"""Circuit Breaker & Graceful Degradation pattern for API Gateway.
Protects against cascading failures when downstream services (LLM, RAG, DB) slow down or fail.
Aligns with CMU MLIP Chapter 18: System Quality (Non-functional attributes, Fail-closed envelopes).
"""
import logging
import os
import time
from enum import Enum
from typing import Any, Callable, Dict, Optional

logger = logging.getLogger("circuit_breaker")


class CircuitState(str, Enum):
    CLOSED = "CLOSED"        # Normal operation
    OPEN = "OPEN"            # Tripped, immediately returns fallback
    HALF_OPEN = "HALF_OPEN"  # Testing recovery with limited traffic


class CircuitBreaker:
    """In-memory circuit breaker with timeout and failure count tracking."""

    def __init__(
        self,
        name: str,
        failure_threshold: Optional[int] = None,
        recovery_timeout_sec: Optional[float] = None,
        expected_latency_budget_ms: Optional[float] = None,
    ):
        self.name = name
        self.failure_threshold = failure_threshold or int(os.getenv("CIRCUIT_BREAKER_FAIL_MAX", "3"))
        self.recovery_timeout_sec = recovery_timeout_sec or float(os.getenv("CIRCUIT_BREAKER_RESET_TIMEOUT", "30.0"))
        self.expected_latency_budget_ms = expected_latency_budget_ms or float(os.getenv("CIRCUIT_BREAKER_LATENCY_BUDGET_MS", "5000.0"))

        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.last_failure_time = 0.0
        self.total_trips = 0

    def can_execute(self) -> bool:
        """Check if request can pass through circuit."""
        now = time.time()
        if self.state == CircuitState.OPEN:
            if now - self.last_failure_time > self.recovery_timeout_sec:
                logger.info("[CircuitBreaker:%s] Half-open probe allowed after cool-down.", self.name)
                self.state = CircuitState.HALF_OPEN
                return True
            return False
        return True

    def record_success(self):
        """Record a successful execution."""
        if self.state == CircuitState.HALF_OPEN:
            logger.info("[CircuitBreaker:%s] Probe successful. Transitioning to CLOSED.", self.name)
            self.state = CircuitState.CLOSED
            self.failure_count = 0
        elif self.state == CircuitState.CLOSED:
            self.failure_count = max(0, self.failure_count - 1)

    def record_failure(self, reason: str = ""):
        """Record a failed execution or timeout."""
        self.failure_count += 1
        self.last_failure_time = time.time()
        if self.failure_count >= self.failure_threshold:
            if self.state != CircuitState.OPEN:
                logger.warning(
                    "[CircuitBreaker:%s] TRIP TO OPEN! Failures (%d/%d): %s",
                    self.name, self.failure_count, self.failure_threshold, reason
                )
            self.state = CircuitState.OPEN
            self.total_trips += 1

    def get_status(self) -> Dict[str, Any]:
        """Return circuit telemetry."""
        return {
            "name": self.name,
            "state": self.state.value,
            "failure_count": self.failure_count,
            "total_trips": self.total_trips,
            "is_available": self.can_execute(),
        }
