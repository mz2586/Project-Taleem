"""AI-led struggle recovery over the real API (no mentor in the loop).

Repeated wrong answers after help return ``post_decision: step_back``; the client re-plans with
``:next`` mid-lesson (which used to fail INTERACTING -> TEACHING with a 500) and the AI teacher
re-teaches. The engine-level step back to a shaky prerequisite is covered in
``test_learning_domain.py``.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from taleem_core.main import create_app
from taleem_core.platform.config import Settings
from taleem_core.vertical_slice.fractions_lesson import OBJECTIVE_CODE
from tests.test_ai_teacher_ask import _auth, _publish_fractions


def test_repeated_failure_steps_back_and_the_ai_teacher_reteaches() -> None:
    app = create_app(Settings(database_url=""))
    client = TestClient(app)
    _publish_fractions(app)
    h = _auth("struggler")
    sid = client.post("/v1/learning/sessions", json={"student_ref": "struggler"}, headers=h).json()[
        "session_id"
    ]
    base = f"/v1/learning/sessions/{sid}"
    assert client.post(f"{base}:next", headers=h).json()["decision"] == "teach"
    taught = client.post(f"{base}:teach", json={"objective_code": OBJECTIVE_CODE}, headers=h)
    item = next(i for i in taught.json()["items"] if i.get("kind", "choose") == "choose")

    posts = []
    for _ in range(4):
        r = client.post(
            f"{base}:answer",
            json={"objective_code": OBJECTIVE_CODE, "item_ref": item["item_ref"], "option": 1},
            headers=h,
        )
        assert r.status_code == 200 and r.json()["outcome"] == "incorrect"
        posts.append(r.json()["post_decision"])
    assert "escalate" not in posts  # a struggling child is never handed to a mentor
    assert posts[-1] == "step_back"

    # Re-plan mid-lesson: the lifecycle closes the objective and the AI teacher teaches again.
    nxt = client.post(f"{base}:next", headers=h)
    assert nxt.status_code == 200, nxt.text
    assert nxt.json()["decision"] in ("continue", "step_back")
    assert nxt.json()["objective_code"] == OBJECTIVE_CODE  # no published prerequisite here
    again = client.post(f"{base}:teach", json={"objective_code": OBJECTIVE_CODE}, headers=h)
    assert again.status_code == 200 and again.json()["items"]
