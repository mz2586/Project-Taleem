"""Curriculum Studio API integration tests (TestClient) — authenticated, SQL-backed.

Exercises the composed application (create_app): real SQL persistence per request and bearer-JWT
auth with role derived from the token, not the body (CTO B1/H2).
"""

from __future__ import annotations

import time
import unittest

from fastapi.testclient import TestClient

from taleem_core.auth.jwt_verifier import sign_hs256
from taleem_core.contexts.curriculum_studio.adapters.persistence import unit_of_work
from taleem_core.contexts.curriculum_studio.application.service import CurriculumStudioService
from taleem_core.main import create_app
from tests.studio_helpers import make_valid_lesson

_SECRET = "dev-only-not-secret"  # noqa: S105 (local-env dev secret)
REVIEW_ROLES = [
    "subject_expert",
    "instructional_designer",
    "a11y_specialist",
    "language_editor",
    "safety_officer",
]


def _auth(role: str, sub: str = "u1") -> dict[str, str]:
    token = sign_hs256({"sub": sub, "role": role, "exp": int(time.time()) + 3600}, _SECRET)
    return {"Authorization": f"Bearer {token}"}


class TestStudioApi(unittest.TestCase):
    def test_requires_authentication(self) -> None:
        # CTO B1: no anonymous access; no privilege from the request body.
        c = TestClient(create_app())
        self.assertEqual(c.get("/v1/studio/hierarchy").status_code, 401)
        self.assertEqual(c.post("/v1/studio/lessons", json={}).status_code, 401)

    def test_forbidden_role_cannot_publish(self) -> None:
        c = TestClient(create_app())
        r = c.post("/v1/studio/lessons/x:publish", json={}, headers=_auth("subject_author"))
        self.assertEqual(r.status_code, 403)  # author role may not publish

    def test_hierarchy(self) -> None:
        r = TestClient(create_app()).get("/v1/studio/hierarchy", headers=_auth("subject_author"))
        self.assertEqual(r.status_code, 200)
        self.assertIn("math", r.json()["subjects_by_grade"]["G1"])

    def test_create_draft_and_validate_shows_findings(self) -> None:
        c = TestClient(create_app())
        body = {
            "lesson_id": "D1",
            "title_ur": "گنتی",
            "title_en": "Counting",
            "grade": "G1",
            "subject": "math",
            "learning_outcomes": ["MATH-G1-N-01"],
            "provenance": {"aligned_slo_codes": ["MATH-G1-N-01"]},
        }
        r = c.post("/v1/studio/lessons", json=body, headers=_auth("subject_author"))
        self.assertEqual(r.status_code, 201)
        self.assertEqual(r.json()["state"], "draft")
        v = c.post("/v1/studio/lessons/D1:validate", headers=_auth("subject_author"))
        self.assertEqual(v.status_code, 200)
        self.assertFalse(v.json()["ok"])
        self.assertTrue(v.json()["structural"])

    def test_submit_invalid_draft_rejected(self) -> None:
        c = TestClient(create_app())
        c.post(
            "/v1/studio/lessons",
            json={
                "lesson_id": "D2",
                "title_ur": "x",
                "title_en": "x",
                "grade": "G1",
                "subject": "math",
            },
            headers=_auth("subject_author"),
        )
        r = c.post("/v1/studio/lessons/D2:submit", json={}, headers=_auth("subject_author"))
        self.assertEqual(r.status_code, 422)
        self.assertEqual(r.json()["code"], "STUDIO_RULE_VIOLATION")

    def test_full_lifecycle_over_http(self) -> None:
        app = create_app()
        client = TestClient(app)
        # Seed a complete, valid lesson directly into the app's SQL store (shared in-memory engine).
        with unit_of_work(app.state.studio_session_factory) as uow:
            CurriculumStudioService(uow.lessons, uow.publish).create(make_valid_lesson("D3"))
            uow.commit()

        self.assertTrue(
            client.post("/v1/studio/lessons/D3:validate", headers=_auth("subject_author")).json()[
                "ok"
            ]
        )
        r = client.post("/v1/studio/lessons/D3:submit", json={}, headers=_auth("subject_author"))
        self.assertEqual(r.status_code, 200)
        for role in REVIEW_ROLES:
            rr = client.post(
                "/v1/studio/lessons/D3:review", json={"action": "approve"}, headers=_auth(role)
            )
            self.assertEqual(rr.status_code, 200)
        self.assertEqual(
            client.get("/v1/studio/lessons/D3", headers=_auth("subject_author")).json()["state"],
            "approved",
        )
        pub = client.post(
            "/v1/studio/lessons/D3:publish",
            json={"change_summary": "v1"},
            headers=_auth("curriculum_architect"),
        )
        self.assertEqual(pub.status_code, 200)
        self.assertEqual(pub.json()["state"], "published")
        self.assertEqual(pub.json()["version"], 1)
        versions = client.get(
            "/v1/studio/lessons/D3/versions", headers=_auth("subject_author")
        ).json()["versions"]
        self.assertEqual(len(versions), 1)
        rb = client.post(
            "/v1/studio/lessons/D3:rollback",
            json={"target_version": 1},
            headers=_auth("curriculum_architect"),
        )
        self.assertEqual(rb.status_code, 200)

    def test_not_found(self) -> None:
        r = TestClient(create_app()).get("/v1/studio/lessons/nope", headers=_auth("subject_author"))
        self.assertEqual(r.status_code, 404)


if __name__ == "__main__":
    unittest.main()
