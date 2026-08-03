"""WebhookConnector — receives telemetry via HTTP POST.

Validates HMAC signatures, enforces rate limits, and converts
incoming JSON payloads to Canonical Telemetry Events.
"""

import hashlib
import hmac
import time
import threading
from datetime import datetime, timezone
from typing import Optional

from ingestion.connectors.base import BaseConnector
from ingestion.models import CanonicalTelemetryEvent
from ingestion.staging import compute_event_id


class TokenBucketRateLimiter:
    """Simple thread-safe token bucket rate limiter."""

    def __init__(self, rate: float = 100.0, capacity: float = 200.0):
        """
        Args:
            rate: Tokens added per second.
            capacity: Maximum bucket size.
        """
        self._rate = rate
        self._capacity = capacity
        self._tokens = capacity
        self._last_refill = time.monotonic()
        self._lock = threading.Lock()

    def allow(self) -> bool:
        """Return True if a request is allowed, consuming one token."""
        with self._lock:
            now = time.monotonic()
            elapsed = now - self._last_refill
            self._tokens = min(self._capacity, self._tokens + elapsed * self._rate)
            self._last_refill = now

            if self._tokens >= 1.0:
                self._tokens -= 1.0
                return True
            return False


class WebhookConnector(BaseConnector):
    """Connector that receives telemetry via HTTP POST webhook."""

    def __init__(self, connector_config: dict):
        """Initialize from config dict.

        Expected config keys:
            id: Unique connector ID
            secret_env_var: Name of env var holding the HMAC secret
            secret: Direct HMAC secret (alternative to env var; for testing)
            path: URL path for the webhook endpoint (default: /api/ingest/webhook)
            rate_limit: Requests per second (default: 100)
            rate_capacity: Burst capacity (default: 200)
            max_payload_bytes: Maximum request body size (default: 1048576 = 1MB)
        """
        self._id = connector_config["id"]
        self._path = connector_config.get("path", "/api/ingest/webhook")
        self._max_payload_bytes = connector_config.get("max_payload_bytes", 1_048_576)

        # HMAC secret
        import os
        secret_env = connector_config.get("secret_env_var", "WEBHOOK_SECRET")
        self._secret = connector_config.get("secret") or os.environ.get(secret_env, "")

        # Rate limiter
        rate = connector_config.get("rate_limit", 100)
        capacity = connector_config.get("rate_capacity", 200)
        self._rate_limiter = TokenBucketRateLimiter(rate=rate, capacity=capacity)

        # Track idempotency keys (in-memory; sufficient for single-process)
        self._seen_idempotency_keys: dict[str, str] = {}  # key → event_id
        self._idem_lock = threading.Lock()

    def connector_id(self) -> str:
        return self._id

    def connector_type(self) -> str:
        return "webhook"

    def poll(self) -> list[CanonicalTelemetryEvent]:
        """Webhook is push-based; poll is a no-op."""
        return []

    def health_check(self) -> bool:
        """Webhook is always healthy if the app is running."""
        return True

    def verify_signature(self, body: bytes, signature_header: Optional[str]) -> bool:
        """Verify the HMAC-SHA256 signature of a request body.

        Args:
            body: Raw request body bytes.
            signature_header: Value of X-Webhook-Signature header (e.g., "sha256=abc123").

        Returns:
            True if signature is valid.
        """
        if not self._secret:
            # No secret configured — accept all (dev mode)
            return True

        if not signature_header:
            return False

        if not signature_header.startswith("sha256="):
            return False

        provided_sig = signature_header[7:]  # Strip "sha256=" prefix
        expected_sig = hmac.new(
            self._secret.encode("utf-8"),
            body,
            hashlib.sha256,
        ).hexdigest()

        return hmac.compare_digest(provided_sig, expected_sig)

    def check_rate_limit(self) -> bool:
        """Return True if request is within rate limit."""
        return self._rate_limiter.allow()

    def check_idempotency(self, idempotency_key: Optional[str]) -> tuple[bool, Optional[str]]:
        """Check if an idempotency key has been seen before.

        Args:
            idempotency_key: Client-provided key (from X-Idempotency-Key header).

        Returns:
            (is_duplicate, existing_event_id). If not duplicate, event_id is None.
        """
        if not idempotency_key:
            return False, None

        with self._idem_lock:
            if idempotency_key in self._seen_idempotency_keys:
                return True, self._seen_idempotency_keys[idempotency_key]
            return False, None

    def record_idempotency(self, idempotency_key: str, event_id: str) -> None:
        """Record a processed idempotency key."""
        if idempotency_key:
            with self._idem_lock:
                self._seen_idempotency_keys[idempotency_key] = event_id

    def validate_payload(self, data: dict) -> tuple[bool, Optional[str]]:
        """Validate the webhook JSON payload.

        Required fields: source_entity_ref, event_type, timestamp, payload.

        Returns:
            (is_valid, error_message).
        """
        required = ["source_entity_ref", "event_type", "timestamp", "payload"]
        for field in required:
            if field not in data or data[field] is None:
                return False, f"Missing required field: {field}"

        if not isinstance(data["payload"], dict):
            return False, "Field 'payload' must be a JSON object"

        valid_types = {"metric", "prediction", "drift", "trace", "alert", "lifecycle"}
        if data["event_type"] not in valid_types:
            return False, f"Invalid event_type: {data['event_type']}. Must be one of: {', '.join(sorted(valid_types))}"

        return True, None

    def create_cte(self, data: dict) -> CanonicalTelemetryEvent:
        """Create a CTE from a validated webhook payload.

        Args:
            data: Validated JSON payload dict.

        Returns:
            A CanonicalTelemetryEvent ready for staging insertion.
        """
        now = datetime.now(timezone.utc).isoformat()
        metric_name = data["payload"].get("metric_name")

        event_id = compute_event_id(
            self._id,
            data["source_entity_ref"],
            data["event_type"],
            data["timestamp"],
            metric_name,
        )

        return CanonicalTelemetryEvent(
            event_id=event_id,
            source_connector=self._id,
            source_entity_ref=data["source_entity_ref"],
            event_type=data["event_type"],
            timestamp=data["timestamp"],
            received_at=now,
            mapping_version="v1",
            payload=data["payload"],
        )
