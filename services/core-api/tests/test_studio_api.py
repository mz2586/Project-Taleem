"""Curriculum Studio API integration tests (TestClient)."""

from __future__ import annotations

import unittest

from fastapi.testclient import TestClient

from taleem_core.main import create_app
from tests.studio_helpers import make_valid_lesson

REVIEW = [
    ("approve", "subject_expert"),
    ("approve", "instructional_designer"),
    ("approve", "a11y_specialist"),
    ("approve", "language_editor"),
    ("approve", "safety_officer"),
]


def _client() -> TestClient:
    return TestClient(create_app())


class TestStudioApi(unittest.TestCase):
    def test_hierarchy(self) -> None:
        r = _client().get("/v1/studio/hierarchy")
        self.assertEqual(r.status_code, 200)
        self.assertIn("math", r.json()["subjects_by_grade"]["G1"])

    def test_create_draft_and_validate_shows_findings(self) -> None:
        c = _client()
        body = {
            "lesson_id": "D1",
            "title_ur": "گنتی",
            "title_en": "Counting",
            "grade": "G1",
            "subject": "math",
            "learning_outcomes": ["MATH-G1-N-01"],
            "provenance": {"aligned_slo_codes": ["MATH-G1-N-01"]},
        }
        r = c.post("/v1/studio/lessons", json=body)
        self.assertEqual(r.status_code, 201)
        self.assertEqual(r.json()["state"], "draft")
        v = c.post("/v1/studio/lessons/D1:validate")
        self.assertEqual(v.status_code, 200)
        self.assertFalse(v.json()["ok"])  # a bare draft is incomplete
        self.assertTrue(v.json()["structural"])

    def test_submit_invalid_draft_rejected(self) -> None:
        c = _client()
        c.post(
            "/v1/studio/lessons",
            json={
                "lesson_id": "D2",
                "title_ur": "x",
                "title_en": "x",
                "grade": "G1",
                "subject": "math",
            },
        )
        r = c.post("/v1/studio/lessons/D2:submit", json={"actor_role": "subject_author"})
        self.assertEqual(r.status_code, 422)
        self.assertEqual(r.json()["code"], "STUDIO_RULE_VIOLATION")

    def test_full_lifecycle_over_http(self) -> None:
        app = create_app()
        client = TestClient(app)
        # Seed a complete, valid lesson through the same service the router uses.
        app.state.studio_service.create(make_valid_lesson("D3"))

        self.assertTrue(client.post("/v1/studio/lessons/D3:validate").json()["ok"])
        r = client.post("/v1/studio/lessons/D3:submit", json={"actor_role": "subject_author"})
        self.assertEqual(r.status_code, 200)
        for action, role in REVIEW:
            rr = client.post(
                "/v1/studio/lessons/D3:review", json={"action": action, "actor_role": role}
            )
            self.assertEqual(rr.status_code, 200)
        self.assertEqual(client.get("/v1/studio/lessons/D3").json()["state"], "approved")
        pub = client.post(
            "/v1/studio/lessons/D3:publish",
            json={"actor_role": "curriculum_architect", "change_summary": "v1"},
        )
        self.assertEqual(pub.status_code, 200)
        self.assertEqual(pub.json()["state"], "published")
        self.assertEqual(pub.json()["version"], 1)
        versions = client.get("/v1/studio/lessons/D3/versions").json()["versions"]
        self.assertEqual(len(versions), 1)
        # Rollback over HTTP.
        rb = client.post(
            "/v1/studio/lessons/D3:rollback",
            json={"target_version": 1, "actor_role": "curriculum_architect"},
        )
        self.assertEqual(rb.status_code, 200)

    def test_not_found(self) -> None:
        r = _client().get("/v1/studio/lessons/nope")
        self.assertEqual(r.status_code, 404)


if __name__ == "__main__":
    unittest.main()
