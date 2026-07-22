# AI Teacher — Offline Compatibility (WS5)

Status: **Phase 8 · WS5.** How the AI Teacher behaves offline, what degrades gracefully, and how the
learner is told — clearly and calmly. Companion to [AI_TEACHER_ARCHITECTURE.md](AI_TEACHER_ARCHITECTURE.md)
and the offline subsystem ([OFFLINE_ARCHITECTURE.md](OFFLINE_ARCHITECTURE.md)).

**Headline:** because the AI Teacher is **templated and packaged**, teaching works **fully offline** —
there is no model to call and no network dependency to explain, tutor, hint, or correct. Only
server-derived and delivery concerns degrade, and they degrade *gracefully*.

---

## 1. The capability matrix

Exposed at `GET /v1/learning/students/{ref}/ai-teacher/capabilities` (`ai_teacher.offline_capabilities`).

| Capability | Offline state | Why |
| --- | --- | --- |
| Lesson explanation | **available** | packaged `LessonView` content |
| Guided teaching | **available** | authored worked examples in the package |
| Step-by-step tutoring | **available** | packaged items + hints |
| Hints | **available** | authored graduated ladder in the package |
| Misconception correction | **available** | authored corrections in the package |
| Encouragement | **available** | fixed system phrases |
| Confidence indicator | **available** | from the cached mastery snapshot |
| Grading | **queued** | server-side; offline attempts queue + sync (6.2B) |
| Adaptive plan | **cached** | server-derived; cached read model, refreshed on reconnect |
| Mentor escalation | **queued** | flagged on reconnect; the on-site mentor is immediate in the pilot |
| Generative rephrasing | **disabled_offline** | **no generative AI offline, ever** (AR-C-06) |

---

## 2. What works offline (fully)

- **Explain / teach / tutor / hint / correct / encourage** — all sourced from the packaged, signed
  (6.2C-1) offline package. The child gets the complete templated teaching experience with no network.
- **Confidence indicator** — computed from the mastery snapshot cached on the device (last synced).

## 3. What degrades gracefully (with honest messaging)

- **Grading** — offline, the child's answer is captured and **queued**; the server grades it and
  records durable evidence on reconnect (Phase 6.2B). Offline, the teacher shows the authored feedback
  path (hint/correction) but the *confirmed* mastery update lands on sync. Message: *"Your answers are
  saved and will update when you're back online."*
- **Adaptive plan** — the plan is server-derived; offline it is served from the **cached** read model
  (labelled "as of …") and refreshed on reconnect. Message: *"Your plan is up to date as of your last
  connection."*
- **Mentor escalation** — offline, an escalation is **queued** (a flag to sync). In the supervised
  pilot the child is directed to the **present** mentor immediately ("tell your mentor now"); the
  queued flag reaches the remote safeguarding record on reconnect. Automated remote crisis-flag routing
  is the **M-Safe-gated** 6.2C item — not part of the teacher's offline behaviour.

## 4. What is disabled offline (by policy)

- **Generative rephrasing** — there is **no generative model path offline, ever** (AR-C-06). This is
  not a degradation to message around; it simply does not exist in the offline (or child) tier. The
  templated teacher is complete on its own.

## 5. Graceful-degradation principles

- **No dead ends** — every offline teaching action completes; only *confirmation* (grading) and
  *server-derived* views (plan) wait for sync.
- **Honest status** — the UI states plainly what is live vs cached vs queued (the `OfflineBadge` ethos);
  the capability matrix is the source of truth the client renders from.
- **Safety preserved** — grounding, no-answer, no-PII, and escalation all hold offline exactly as
  online (the logic is identical; nothing about being offline weakens a guardrail).
- **Convergence on reconnect** — queued attempts sync as durable evidence with no double-count (6.2B),
  the plan refreshes, and any escalation flag is delivered.

## 6. Summary

The AI Teacher is **offline-first by design**: teaching is fully local and safe; only grading, the
server-derived plan, and remote escalation delivery wait for connectivity — each queued or cached, each
clearly messaged, none blocking the child from learning.
