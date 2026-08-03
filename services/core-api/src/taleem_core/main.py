"""FastAPI application (ASGI adapter / composition root).

This is the *edge* adapter. All business logic lives in the pure `contexts`/`platform` layers,
which are unit-tested without FastAPI. Running this module requires the runtime deps in
pyproject.toml (installed by CI / Docker).

Endpoints (M1 walking skeleton — governance-safe):
  GET  /health          liveness
  GET  /health/ready    readiness (dependency probes)
  GET  /metrics         Prometheus exposition
  POST /v1/sync/batch   offline sync engine prototype (synthetic data only)
  GET  /v1/skeleton/protected   demo of AuthN(JWT) + AuthZ(PDP) seams
"""

from __future__ import annotations

import contextlib
import time
from collections.abc import Iterator
from typing import Any

from fastapi import Depends, FastAPI, Header, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm.exc import StaleDataError

from . import __version__
from .auth import pdp
from .auth.dependencies import bearer_claims, require_owner_or
from .auth.jwt_verifier import Claims, verify_hs256
from .contexts.curriculum_studio.adapters.api import build_studio_router
from .contexts.curriculum_studio.adapters.persistence import (
    Base as CurriculumBase,
)
from .contexts.curriculum_studio.adapters.persistence import (
    create_db_engine,
    create_session_factory,
    unit_of_work,
)
from .contexts.curriculum_studio.application.service import CurriculumStudioService
from .contexts.guardian.adapters.guardian_api import build_guardian_router
from .contexts.guardian.application.directory import GuardianDirectory
from .contexts.guardian.application.guardian_service import GuardianService
from .contexts.health.service import Check, HealthService
from .contexts.learning.adapters.ai_teacher_api import build_ai_teacher_router
from .contexts.learning.adapters.api import LearningApiDeps, build_learning_router
from .contexts.learning.adapters.curriculum_read_model import CurriculumStudioReadModel
from .contexts.learning.adapters.memory import InMemorySessionRepository
from .contexts.learning.adapters.offline_api import build_offline_router
from .contexts.learning.adapters.package_signer import Ed25519PackageSigner
from .contexts.learning.adapters.persistence.base import (
    LearningBase,
    create_learning_engine,
    create_learning_session_factory,
)
from .contexts.learning.adapters.persistence.uow import LearningUnitOfWork
from .contexts.learning.adapters.student_api import build_student_router
from .contexts.learning.application.ai_teacher_service import AITeacherService
from .contexts.learning.application.analytics import LearningAnalytics
from .contexts.learning.application.knowledge_service import KnowledgeService
from .contexts.learning.application.offline_service import OfflinePackageService
from .contexts.learning.application.session_service import SessionService
from .contexts.learning.application.student_queries import StudentQueryService
from .contexts.learning.application.sync_consumer import SyncEvidenceConsumer
from .contexts.learning.domain.decision import DecisionConfig
from .contexts.learning.domain.estimator import BKTEstimator
from .contexts.learning.domain.forgetting import HalfLifeForgettingModel
from .contexts.learning.domain.runtime import TemplatedTeachingRuntime
from .contexts.ops.adapters.ops_api import build_ops_router
from .contexts.sync.domain import DeltaType, SyncDelta, SyncStore
from .contexts.sync.service import DurableSyncCoordinator
from .platform import correlation
from .platform.concurrency import ConcurrencyConflictError
from .platform.config import Settings, load_settings
from .platform.errors import Problem, conflict, forbidden, unauthorized
from .platform.kill_switch import KillSwitch, is_child_facing
from .platform.logging import StructuredLogger
from .platform.metrics import registry
from .platform.plugins import Module
from .platform.plugins import registry as module_registry
from .platform.security_headers import apply_security_headers


# Request models live at MODULE scope: with `from __future__ import annotations`, FastAPI resolves
# endpoint body types via the module globals, so locally-nested models would not be recognized.
class DeltaIn(BaseModel):
    # snake_case Python fields with camelCase wire aliases (keeps the JSON contract stable).
    model_config = ConfigDict(populate_by_name=True)
    client_event_id: str = Field(alias="clientEventId", min_length=1, max_length=128)
    type: str
    entity_key: str = Field(alias="entityKey", min_length=1, max_length=256)
    payload: dict[str, Any] = Field(default_factory=dict)
    client_seq: int = Field(default=0, alias="clientSeq")


class BatchIn(BaseModel):
    cursor: int = 0
    deltas: list[DeltaIn] = Field(default_factory=list, max_length=200)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or load_settings()
    log = StructuredLogger(settings.service_name, settings.log_level)

    # Interactive API docs (Swagger/ReDoc) and the OpenAPI schema describe the full API surface;
    # keep them off in production (information-disclosure hardening) but available in dev/local.
    _docs_disabled = settings.is_production
    app = FastAPI(
        title="Project Taleem — Core API",
        version=__version__,
        description="M1 walking skeleton. Governance-safe scaffolding only — no child data.",
        docs_url=None if _docs_disabled else "/docs",
        redoc_url=None if _docs_disabled else "/redoc",
        openapi_url=None if _docs_disabled else "/openapi.json",
        openapi_tags=[
            {"name": "health", "description": "Liveness & readiness"},
            {"name": "observability", "description": "Metrics"},
            {"name": "sync", "description": "Offline sync engine prototype (synthetic data)"},
            {"name": "skeleton", "description": "AuthN/AuthZ seam demo"},
            {
                "name": "curriculum-studio",
                "description": "Curriculum authoring platform (no child data)",
            },
            {
                "name": "learning",
                "description": "Learning Intelligence Platform (governance-gated)",
            },
            {
                "name": "offline",
                "description": "Offline lesson packages (content-hashed; no child data)",
            },
            {
                "name": "ai-teacher",
                "description": "AI Teacher — templated, curriculum-grounded, explainable (no LLM)",
            },
            {"name": "ops", "description": "Operational controls — kill switch + status"},
            {
                "name": "guardian",
                "description": "Guardian Portal — read-only view of linked children",
            },
        ],
    )

    # CORS: the browser SPA is a different origin than the API, so cross-origin requests need an
    # explicit allowlist (handles preflight OPTIONS + adds Access-Control-Allow-Origin). Only exact
    # configured origins are allowed — never "*", since the API is credentialed (bearer JWT). Empty
    # allowlist => no CORS headers (same-origin only).
    cors_origins = settings.cors_allowed_origins()
    if cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=cors_origins,
            allow_credentials=True,
            allow_methods=["GET", "POST", "OPTIONS"],
            allow_headers=["Authorization", "Content-Type", "X-Correlation-Id"],
            expose_headers=["X-Correlation-Id"],
            max_age=600,
        )

    # Shared, process-local state for the walking skeleton (synthetic only).
    sync_store = SyncStore()
    kill_switch = KillSwitch(time.time)  # operator halt for child-facing traffic (ops control)
    health = HealthService(
        __version__,
        checks=[Check("self", lambda: True)],  # real dep probes added as contexts land
    )

    # ---- persistence wiring (CTO H2) ----
    # SQL persistence for both contexts. Empty DATABASE_URL => in-memory SQLite (governance-safe
    # dev default): the tables are created from the ORM. A real PostgreSQL URL uses the schema
    # created by the Alembic migrations (never create_all in production).
    db_url = settings.database_url or "sqlite://"
    curriculum_engine = create_db_engine(db_url)
    learning_engine = create_learning_engine(db_url)
    if curriculum_engine.dialect.name == "sqlite":
        CurriculumBase.metadata.create_all(curriculum_engine)
    if learning_engine.dialect.name == "sqlite":
        LearningBase.metadata.create_all(learning_engine)
    studio_sf = create_session_factory(curriculum_engine)
    learning_sf = create_learning_session_factory(learning_engine)
    # Session factories are exposed for seeding in tests / ops tooling (not a request path).
    app.state.studio_session_factory = studio_sf
    app.state.learning_session_factory = learning_sf

    # AuthN: every business route requires a verified bearer token; the actor's role comes from
    # the token, not the request body (CTO B1). Deny-by-default PDP does authorization.
    claims_dependency = bearer_claims(settings.jwt_dev_secret)

    # ---- Curriculum Studio (CTO H2: SQL-backed, request-scoped Unit of Work) ----
    def studio_service_provider() -> Iterator[CurriculumStudioService]:
        with unit_of_work(studio_sf) as uow:
            # The service commits inside each mutating method (on_commit) so an optimistic-lock
            # conflict at commit is caught in the request handler (409), not in dependency teardown
            # (which would surface as a 500). The UoW still rolls back on any raised exception.
            yield CurriculumStudioService(uow.lessons, uow.publish, on_commit=uow.commit)

    app.include_router(build_studio_router(studio_service_provider, claims_dependency))

    # ---- Learning Intelligence Platform (CTO H1: now mounted in the deployable) ----
    def learning_uow() -> LearningUnitOfWork:
        return LearningUnitOfWork(learning_sf)

    knowledge_service = KnowledgeService(
        learning_uow, BKTEstimator(), HalfLifeForgettingModel(), time.time
    )
    read_model = CurriculumStudioReadModel(studio_sf)
    session_service = SessionService(
        InMemorySessionRepository(),
        knowledge_service,
        read_model,
        TemplatedTeachingRuntime(),
        read_model.published_graph,  # dynamic graph from currently-published curriculum
        DecisionConfig(),
        time.time,
        learning_uow,
    )
    learning_deps = LearningApiDeps(
        session_service=session_service,
        knowledge_service=knowledge_service,
        analytics=LearningAnalytics(learning_uow),
        curriculum=read_model,
    )
    app.include_router(build_learning_router(learning_deps, claims_dependency))

    # ---- Student query surface (derived read models: homework, reviews, history, …) ----
    student_queries = StudentQueryService(learning_uow, read_model, time.time)
    app.include_router(build_student_router(student_queries, claims_dependency))

    # ---- Offline lesson packages (Phase 6.2A: content-hashed; 6.2C-1: Ed25519-signed) ----
    package_signer = Ed25519PackageSigner(
        settings.offline_signing_seed_hex, settings.offline_signing_key_id
    )
    offline_service = OfflinePackageService(read_model, time.time, signer=package_signer)
    app.include_router(build_offline_router(offline_service, claims_dependency))

    # ---- Durable offline sync (Phase 6.2B) ----
    # attempt.submitted deltas record durable AssessmentEvidence idempotently (gap G3); other
    # delta types keep the existing in-memory conflict policy. Idempotency is durable via the
    # evidence table (a replay after restart is still a DUPLICATE).
    sync_consumer = SyncEvidenceConsumer(
        learning_uow, read_model, BKTEstimator(), HalfLifeForgettingModel(), time.time
    )
    sync_coordinator = DurableSyncCoordinator(sync_store, sync_consumer)

    # ---- AI Teacher (Phase 8): templated, curriculum-grounded, explainable (no LLM) ----
    ai_teacher = AITeacherService(
        session_service,
        knowledge_service,
        read_model,
        TemplatedTeachingRuntime(),
        read_model.published_graph,
        DecisionConfig(),
        time.time,
    )
    app.include_router(build_ai_teacher_router(ai_teacher, session_service, claims_dependency))

    # ---- Guardian Portal: read-only aggregation over the EXISTING learning read models. No new
    # child-data surfaces; the only new state is the guardian→children association directory.
    guardian_directory = GuardianDirectory.from_csv(settings.guardian_links_csv)
    guardian_service = GuardianService(
        guardian_directory,
        student_queries,  # reuse the same student query surface
        LearningAnalytics(learning_uow),  # reuse learning analytics
        ai_teacher,  # reuse the AI Teacher plan
        time.time,
    )
    app.include_router(build_guardian_router(guardian_service, claims_dependency))

    # ---- Operational controls (kill switch + status) ----
    def ops_status() -> dict[str, Any]:
        ready, _ = health.ready()
        reg = registry()
        requests = reg.total("taleem_requests_total")
        errors_server = reg.counter_value("taleem_errors_total", kind="server")
        errors_client = reg.counter_value("taleem_errors_total", kind="client")
        return {
            "kill_switch": kill_switch.status().to_dict(),
            "ready": ready,
            "version": __version__,
            "counters": {
                "sessions_started": reg.counter_value("taleem_sessions_started_total"),
                "objectives_mastered": reg.counter_value("taleem_objectives_mastered_total"),
                "misconceptions_detected": reg.counter_value(
                    "taleem_misconceptions_detected_total"
                ),
            },
            # Golden signals (traffic/errors/latency) for monitoring + alert evaluation.
            "monitoring": {
                "requests_total": requests,
                "errors_server": errors_server,
                "errors_client": errors_client,
                "server_error_rate": round(errors_server / requests, 4) if requests else 0.0,
                "avg_request_ms": round(reg.observed_mean("taleem_request_duration_ms"), 2),
            },
        }

    app.include_router(build_ops_router(kill_switch, ops_status, claims_dependency))

    # Register the modules this deployable composes (plugin architecture).
    reg = module_registry()
    for module in (
        Module("health", "/health", lambda: True),
        Module("sync", "/v1/sync", lambda: True, events_published=("ProgressSynced",)),
        Module(
            "curriculum_studio", "/v1/studio", lambda: True, events_published=("LessonPublished",)
        ),
        Module("learning", "/v1/learning", lambda: True, events_published=("ObjectiveMastered",)),
        Module("offline", "/v1/offline", lambda: True),
        Module("ops", "/v1/ops", lambda: True),
        Module("guardian", "/v1/guardian", lambda: True),
    ):
        # Idempotent across reloads/tests: re-registering the same module is a no-op.
        with contextlib.suppress(ValueError):
            reg.register(module)

    @app.middleware("http")
    async def observability(request: Request, call_next: Any) -> Any:
        cid = correlation.ensure_correlation_id(request.headers.get("x-correlation-id"))
        start = time.perf_counter()
        registry().inc("taleem_requests_total", method=request.method, path=request.url.path)
        # Kill switch: when engaged, child-facing routes fail closed (503); health/ops stay up.
        if kill_switch.engaged and is_child_facing(request.url.path):
            registry().inc("taleem_kill_switch_blocked_total")
            response = JSONResponse(
                status_code=503,
                content=Problem(
                    503, "SERVICE_HALTED", "Service temporarily halted by operator", "kill switch"
                ).to_dict(str(request.url.path)),
            )
            response.headers["x-correlation-id"] = cid
            apply_security_headers(response.headers)
            return response
        try:
            response = await call_next(request)
        except Problem as problem:  # domain errors -> RFC9457
            response = JSONResponse(
                status_code=problem.status, content=problem.to_dict(str(request.url.path))
            )
        duration_ms = (time.perf_counter() - start) * 1000.0
        registry().observe("taleem_request_duration_ms", duration_ms, path=request.url.path)
        # Error golden signal: count client (4xx) vs server (5xx) responses for monitoring/alerting.
        if response.status_code >= 500:
            registry().inc("taleem_errors_total", kind="server")
        elif response.status_code >= 400:
            registry().inc("taleem_errors_total", kind="client")
        response.headers["x-correlation-id"] = cid
        apply_security_headers(response.headers)
        log.info(
            "request",
            method=request.method,
            path=request.url.path,
            status=response.status_code,
            duration_ms=round(duration_ms, 2),
        )
        return response

    @app.exception_handler(Problem)
    async def problem_handler(request: Request, exc: Problem) -> JSONResponse:
        return JSONResponse(status_code=exc.status, content=exc.to_dict(str(request.url.path)))

    def _conflict_response(request: Request) -> JSONResponse:
        problem = conflict("resource was modified concurrently; reload and retry")
        body = problem.to_dict(str(request.url.path))
        return JSONResponse(status_code=problem.status, content=body)

    @app.exception_handler(ConcurrencyConflictError)
    async def conflict_handler(request: Request, exc: ConcurrencyConflictError) -> JSONResponse:
        # Optimistic-lock conflict -> a retryable 409, never a 500.
        return _conflict_response(request)

    @app.exception_handler(StaleDataError)
    async def stale_data_handler(request: Request, exc: StaleDataError) -> JSONResponse:
        # A raw optimistic-lock loser (the version-guarded UPDATE matched 0 rows) — e.g. a
        # double-submitted Curriculum Studio review. Map to 409, never a 500. Caught at app level
        # because the conflict may surface during a flush inside save(), not only at commit().
        return _conflict_response(request)

    @app.exception_handler(OperationalError)
    async def operational_error_handler(request: Request, exc: OperationalError) -> JSONResponse:
        # SQLite serializes writers with a lock; treat "database is locked" as a retryable conflict.
        if "database is locked" in str(exc).lower():
            return _conflict_response(request)
        raise exc

    # ---- health ----
    @app.get("/health", tags=["health"])
    def liveness() -> dict[str, object]:
        return health.live()

    @app.get("/health/ready", tags=["health"])
    def readiness() -> JSONResponse:
        ok, body = health.ready()
        return JSONResponse(status_code=200 if ok else 503, content=body)

    # ---- observability ----
    @app.get("/metrics", tags=["observability"], response_class=PlainTextResponse)
    def metrics() -> str:
        return registry().render()

    # ---- offline sync (Phase 6.2B: durable evidence for attempts + in-memory policy for the rest)
    @app.post("/v1/sync/batch", tags=["sync"])
    def sync_batch(batch: BatchIn, claims: Claims = Depends(claims_dependency)) -> dict[str, Any]:
        try:
            deltas = [
                SyncDelta(
                    client_event_id=d.client_event_id,
                    type=DeltaType(d.type),
                    entity_key=d.entity_key,
                    payload=d.payload,
                    client_seq=d.client_seq,
                )
                for d in batch.deltas
            ]
        except ValueError as exc:
            raise Problem(422, "UNKNOWN_DELTA_TYPE", "Unknown delta type", str(exc)) from exc
        # IDOR guard: a learner may only submit durable attempt evidence for THEMSELVES (the delta's
        # student_ref must equal the token subject); a privileged operator may sync any. Without
        # this a hostile caller could forge assessment evidence for any child.
        for d in deltas:
            if d.type is DeltaType.ATTEMPT_SUBMITTED:
                owner = str(d.payload.get("student_ref", ""))
                if not owner:
                    raise Problem(422, "MISSING_STUDENT_REF", "attempt missing student_ref", "")
                require_owner_or(claims, owner, privileged_roles=("system",))
        results, cursor = sync_coordinator.apply_batch(deltas)
        return {
            "cursor": cursor,
            "results": [
                {
                    "clientEventId": r.client_event_id,
                    "status": r.status.value,
                    "version": r.server_version,
                }
                for r in results
            ],
        }

    # ---- AuthN/AuthZ seam demo ----
    def require_claims(authorization: str = Header(default="")) -> Claims:
        if not authorization.lower().startswith("bearer "):
            raise unauthorized("Missing bearer token")
        token = authorization.split(" ", 1)[1]
        return verify_hs256(token, settings.jwt_dev_secret)

    @app.get("/v1/skeleton/protected", tags=["skeleton"])
    def protected(claims: Claims = Depends(require_claims)) -> dict[str, Any]:
        decision = pdp.authorize(claims.role, "read", "skeleton.protected")
        if not decision.allow:
            raise forbidden("Not permitted")
        return {"ok": True, "role": claims.role, "policy": decision.reason}

    return app


app = create_app()
