"""Tests for Session 7: WebhookConnector and Ingestion API."""

import hashlib
import hmac
import json
import os
import sqlite3
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from ingestion.connectors.webhook import WebhookConnector, TokenBucketRateLimiter


# ── Fixtures ────────────────────────────────────────────────────────────────

WEBHOOK_SECRET = "test-secret-key-12345"


@pytest.fixture
def webhook():
    """Create a WebhookConnector with a known secret."""
    return WebhookConnector({
        "id": "test-webhook",
        "type": "webhook",
        "secret": WEBHOOK_SECRET,
        "rate_limit": 10,
        "rate_capacity": 20,
        "max_payload_bytes": 1024,
    })


@pytest.fixture
def webhook_client(tmp_path):
    """Flask test client with webhook connector and full schema."""
    db_path = str(tmp_path / "webhook_test.db")
    import app as app_module
    import data_source as ds_module
    orig_app_db = app_module.DB_PATH
    orig_ds_db = ds_module.DB_PATH
    app_module.DB_PATH = db_path
    ds_module.DB_PATH = db_path
    app_module.init_db()

    # Reset the global webhook connector so it picks up test config
    app_module._webhook_connector = WebhookConnector({
        "id": "test-webhook",
        "type": "webhook",
        "secret": WEBHOOK_SECRET,
        "rate_limit": 100,
        "rate_capacity": 200,
        "max_payload_bytes": 1_048_576,
    })

    app_module.app.config["TESTING"] = True
    with app_module.app.test_client() as client:
        with app_module.app.app_context():
            yield client

    app_module._webhook_connector = None
    app_module.DB_PATH = orig_app_db
    ds_module.DB_PATH = orig_ds_db


def _sign(body: bytes, secret: str = WEBHOOK_SECRET) -> str:
    """Compute HMAC-SHA256 signature header value."""
    sig = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    return f"sha256={sig}"


def _valid_payload(**overrides):
    """Build a valid webhook payload dict."""
    data = {
        "source_entity_ref": "mlflow://experiment-1/test-model",
        "event_type": "metric",
        "timestamp": "2026-07-30T14:00:00Z",
        "payload": {"metric_name": "accuracy", "metric_value": 0.934},
    }
    data.update(overrides)
    return data


def _post_webhook(client, data=None, secret=WEBHOOK_SECRET, headers=None, content_type="application/json"):
    """Helper to POST to webhook endpoint with proper signing."""
    if data is None:
        data = _valid_payload()
    body = json.dumps(data).encode("utf-8")
    sig = _sign(body, secret)

    h = {"Content-Type": content_type, "X-Webhook-Signature": sig}
    if headers:
        h.update(headers)

    return client.post("/api/ingest/webhook", data=body, headers=h)


# ── Test: HMAC Signature Verification ──────────────────────────────────────

class TestHMACVerification:

    def test_valid_signature(self, webhook):
        body = b'{"key": "value"}'
        sig = _sign(body)
        assert webhook.verify_signature(body, sig) is True

    def test_invalid_signature(self, webhook):
        body = b'{"key": "value"}'
        assert webhook.verify_signature(body, "sha256=wrong") is False

    def test_missing_signature(self, webhook):
        body = b'{"key": "value"}'
        assert webhook.verify_signature(body, None) is False

    def test_malformed_signature(self, webhook):
        body = b'{"key": "value"}'
        assert webhook.verify_signature(body, "bad-format") is False

    def test_no_secret_accepts_all(self):
        """No secret configured → accept all (dev mode)."""
        wc = WebhookConnector({"id": "no-secret", "secret": ""})
        assert wc.verify_signature(b"anything", None) is True


# ── Test: Payload Validation ────────────────────────────────────────────────

class TestPayloadValidation:

    def test_valid_payload(self, webhook):
        ok, err = webhook.validate_payload(_valid_payload())
        assert ok is True
        assert err is None

    def test_missing_source_entity_ref(self, webhook):
        data = _valid_payload()
        del data["source_entity_ref"]
        ok, err = webhook.validate_payload(data)
        assert ok is False
        assert "source_entity_ref" in err

    def test_missing_event_type(self, webhook):
        data = _valid_payload()
        del data["event_type"]
        ok, err = webhook.validate_payload(data)
        assert ok is False
        assert "event_type" in err

    def test_missing_timestamp(self, webhook):
        data = _valid_payload()
        del data["timestamp"]
        ok, err = webhook.validate_payload(data)
        assert ok is False
        assert "timestamp" in err

    def test_missing_payload(self, webhook):
        data = _valid_payload()
        del data["payload"]
        ok, err = webhook.validate_payload(data)
        assert ok is False
        assert "payload" in err

    def test_payload_not_dict(self, webhook):
        data = _valid_payload(payload="not a dict")
        ok, err = webhook.validate_payload(data)
        assert ok is False
        assert "JSON object" in err

    def test_invalid_event_type(self, webhook):
        data = _valid_payload(event_type="invalid_type")
        ok, err = webhook.validate_payload(data)
        assert ok is False
        assert "Invalid event_type" in err


# ── Test: Rate Limiting ─────────────────────────────────────────────────────

class TestRateLimiting:

    def test_within_limit(self):
        rl = TokenBucketRateLimiter(rate=100, capacity=10)
        for _ in range(10):
            assert rl.allow() is True

    def test_exceeds_limit(self):
        rl = TokenBucketRateLimiter(rate=0.1, capacity=3)
        for _ in range(3):
            assert rl.allow() is True
        # Bucket exhausted
        assert rl.allow() is False

    def test_webhook_rate_limit(self, webhook):
        # Capacity is 20, so first 20 should pass
        results = [webhook.check_rate_limit() for _ in range(25)]
        assert sum(results) == 20  # 20 allowed, 5 rejected


# ── Test: Idempotency ──────────────────────────────────────────────────────

class TestIdempotency:

    def test_new_key_not_duplicate(self, webhook):
        is_dup, eid = webhook.check_idempotency("key-001")
        assert is_dup is False
        assert eid is None

    def test_recorded_key_is_duplicate(self, webhook):
        webhook.record_idempotency("key-001", "event-abc")
        is_dup, eid = webhook.check_idempotency("key-001")
        assert is_dup is True
        assert eid == "event-abc"

    def test_none_key_never_duplicate(self, webhook):
        is_dup, eid = webhook.check_idempotency(None)
        assert is_dup is False


# ── Test: CTE Creation ─────────────────────────────────────────────────────

class TestCTECreation:

    def test_creates_valid_cte(self, webhook):
        data = _valid_payload()
        cte = webhook.create_cte(data)
        assert cte.source_connector == "test-webhook"
        assert cte.source_entity_ref == "mlflow://experiment-1/test-model"
        assert cte.event_type == "metric"
        assert cte.payload["metric_name"] == "accuracy"
        assert cte.processing_status == "pending"
        assert len(cte.event_id) == 32


# ── Test: Flask Webhook Endpoint ────────────────────────────────────────────

class TestWebhookEndpoint:

    def test_valid_post_returns_201(self, webhook_client):
        r = _post_webhook(webhook_client)
        assert r.status_code == 201
        data = json.loads(r.data)
        assert data["status"] == "accepted"
        assert "event_id" in data

    def test_cte_in_staging(self, webhook_client):
        """Valid POST creates a CTE in staging_events."""
        r = _post_webhook(webhook_client)
        assert r.status_code == 201
        event_id = json.loads(r.data)["event_id"]

        import app as app_module
        conn = sqlite3.connect(app_module.DB_PATH)
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT * FROM staging_events WHERE event_id = ?", (event_id,)
        ).fetchone()
        conn.close()
        assert row is not None
        assert row["processing_status"] == "pending"
        assert row["source_connector"] == "test-webhook"

    def test_invalid_signature_returns_401(self, webhook_client):
        data = _valid_payload()
        body = json.dumps(data).encode("utf-8")
        r = webhook_client.post("/api/ingest/webhook", data=body, headers={
            "Content-Type": "application/json",
            "X-Webhook-Signature": "sha256=wrong",
        })
        assert r.status_code == 401

    def test_missing_signature_returns_401(self, webhook_client):
        data = _valid_payload()
        body = json.dumps(data).encode("utf-8")
        r = webhook_client.post("/api/ingest/webhook", data=body, headers={
            "Content-Type": "application/json",
        })
        assert r.status_code == 401

    def test_missing_required_fields_returns_400(self, webhook_client):
        data = {"event_type": "metric"}  # missing source_entity_ref, timestamp, payload
        r = _post_webhook(webhook_client, data=data)
        assert r.status_code == 400
        assert "source_entity_ref" in json.loads(r.data)["error"]

    def test_non_json_content_type_returns_400(self, webhook_client):
        r = webhook_client.post("/api/ingest/webhook", data=b"not json", headers={
            "Content-Type": "text/plain",
            "X-Webhook-Signature": "sha256=x",
        })
        assert r.status_code == 400

    def test_duplicate_idempotency_key_returns_409(self, webhook_client):
        data = _valid_payload()
        body = json.dumps(data).encode("utf-8")
        sig = _sign(body)
        headers = {
            "Content-Type": "application/json",
            "X-Webhook-Signature": sig,
            "X-Idempotency-Key": "unique-key-001",
        }

        r1 = webhook_client.post("/api/ingest/webhook", data=body, headers=headers)
        assert r1.status_code == 201

        r2 = webhook_client.post("/api/ingest/webhook", data=body, headers=headers)
        assert r2.status_code == 409
        assert "Duplicate" in json.loads(r2.data)["error"]

    def test_content_based_dedup_returns_409(self, webhook_client):
        """Same content posted twice (no idempotency key) → 409 on second."""
        data = _valid_payload()
        r1 = _post_webhook(webhook_client, data=data)
        assert r1.status_code == 201

        r2 = _post_webhook(webhook_client, data=data)
        assert r2.status_code == 409

    def test_different_events_both_accepted(self, webhook_client):
        d1 = _valid_payload(timestamp="2026-07-30T14:00:00Z")
        d2 = _valid_payload(timestamp="2026-07-30T15:00:00Z")
        r1 = _post_webhook(webhook_client, data=d1)
        r2 = _post_webhook(webhook_client, data=d2)
        assert r1.status_code == 201
        assert r2.status_code == 201

    def test_unknown_entity_ref_accepted(self, webhook_client):
        """Events for unknown entities are accepted (entity resolution happens later)."""
        data = _valid_payload(source_entity_ref="mlflow://unknown/entity")
        r = _post_webhook(webhook_client, data=data)
        assert r.status_code == 201


# ── Test: Connector Registry ────────────────────────────────────────────────

class TestWebhookRegistry:

    def test_create_webhook_connector(self):
        from ingestion.connector_registry import create_connector
        conn = create_connector({
            "id": "wh-1",
            "type": "webhook",
            "secret": "s3cr3t",
        })
        assert isinstance(conn, WebhookConnector)
        assert conn.connector_id() == "wh-1"
        assert conn.connector_type() == "webhook"

    def test_webhook_poll_returns_empty(self):
        """Webhook is push-based; poll returns nothing."""
        wc = WebhookConnector({"id": "wh", "secret": ""})
        assert wc.poll() == []

    def test_webhook_health_always_true(self):
        wc = WebhookConnector({"id": "wh", "secret": ""})
        assert wc.health_check() is True
