"""Integration tests — boot the FastAPI app and exercise every endpoint via TestClient.

Covers: boot, health/readiness, metrics/observability, the sync endpoint (incl. idempotent replay
and the RFC-9457 error path), the AuthN/AuthZ seams, and OpenAPI generation.
"""

from __future__ import annotations

import unittest

from fastapi.testclient import TestClient

from taleem_core.auth.jwt_verifier import sign_hs256
from taleem_core.main import create_app
from taleem_core.platform.config import Settings

SECRET = "dev-only-not-secret"  # noqa: S105 (matches the default dev settings)


def _client() -> TestClient:
    return TestClient(create_app(Settings(jwt_dev_secret=SECRET)))


class TestBootAndHealth(unittest.TestCase):
    def test_app_boots_and_liveness(self) -> None:
        r = _client().get("/health")
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(body["status"], "ok")
        self.assertIn("version", body)

    def test_readiness(self) -> None:
        r = _client().get("/health/ready")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["status"], "ok")
        self.assertIn("checks", r.json())

    def test_correlation_id_echoed(self) -> None:
        r = _client().get("/health", headers={"x-correlation-id": "test-cid-123"})
        self.assertEqual(r.headers.get("x-correlation-id"), "test-cid-123")


class TestObservability(unittest.TestCase):
    def test_metrics_exposition_after_traffic(self) -> None:
        c = _client()
        c.get("/health")
        r = c.get("/metrics")
        self.assertEqual(r.status_code, 200)
        self.assertIn("taleem_requests_total", r.text)


class TestSyncEndpoint(unittest.TestCase):
    def test_batch_apply_then_idempotent_replay(self) -> None:
        c = _client()
        batch = {
            "cursor": 0,
            "deltas": [
                {
                    "clientEventId": "e1",
                    "type": "progress.updated",
                    "entityKey": "S1|L1",
                    "payload": {"block": 3},
                },
                {
                    "clientEventId": "e2",
                    "type": "attempt.submitted",
                    "entityKey": "S1|A1",
                    "payload": {"attempt_id": "att-1"},
                },
            ],
        }
        r1 = c.post("/v1/sync/batch", json=batch)
        self.assertEqual(r1.status_code, 200)
        statuses1 = {x["clientEventId"]: x["status"] for x in r1.json()["results"]}
        self.assertEqual(statuses1, {"e1": "applied", "e2": "applied"})

        r2 = c.post("/v1/sync/batch", json=batch)  # replay same queue
        statuses2 = {x["clientEventId"]: x["status"] for x in r2.json()["results"]}
        self.assertEqual(statuses2, {"e1": "duplicate", "e2": "duplicate"})
        self.assertEqual(r1.json()["cursor"], r2.json()["cursor"])  # cursor did not advance

    def test_unknown_delta_type_returns_problem(self) -> None:
        c = _client()
        r = c.post(
            "/v1/sync/batch",
            json={"deltas": [{"clientEventId": "x", "type": "bogus.type", "entityKey": "k"}]},
        )
        self.assertEqual(r.status_code, 422)
        body = r.json()
        self.assertEqual(body["code"], "UNKNOWN_DELTA_TYPE")
        self.assertIn("traceId", body)  # RFC-9457 shape, no PII/stack

    def test_validation_rejects_missing_required_field(self) -> None:
        c = _client()
        r = c.post("/v1/sync/batch", json={"deltas": [{"type": "progress.updated"}]})
        # pydantic validation: missing required clientEventId / entityKey.
        self.assertEqual(r.status_code, 422)


class TestAuthSeams(unittest.TestCase):
    def test_protected_requires_token(self) -> None:
        r = _client().get("/v1/skeleton/protected")
        self.assertEqual(r.status_code, 401)

    def test_protected_allows_system_role(self) -> None:
        token = sign_hs256({"sub": "sys-1", "role": "system", "exp": 9999999999}, SECRET)
        r = _client().get("/v1/skeleton/protected", headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.json()["ok"])

    def test_protected_denies_non_system_role(self) -> None:
        token = sign_hs256({"sub": "s", "role": "student", "exp": 9999999999}, SECRET)
        r = _client().get("/v1/skeleton/protected", headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(r.status_code, 403)  # PDP deny-by-default


class TestOpenAPI(unittest.TestCase):
    def test_openapi_generation(self) -> None:
        r = _client().get("/openapi.json")
        self.assertEqual(r.status_code, 200)
        spec = r.json()
        self.assertEqual(spec["openapi"][:3], "3.1")
        for path in ("/health", "/v1/sync/batch", "/v1/skeleton/protected", "/metrics"):
            self.assertIn(path, spec["paths"])


if __name__ == "__main__":
    unittest.main()
