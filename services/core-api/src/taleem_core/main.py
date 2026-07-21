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
from fastapi.responses import JSONResponse, PlainTextResponse
from pydantic import BaseModel, ConfigDict, Field

from . import __version__
from .auth import pdp
from .auth.dependencies import bearer_claims
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
from .contexts.health.service import Check, HealthService
from .contexts.learning.adapters.api import LearningApiDeps, build_learning_router
from .contexts.learning.adapters.curriculum_read_model import CurriculumStudioReadModel
from .contexts.learning.adapters.memory import InMemorySessionRepository
from .contexts.learning.adapters.persistence.base import (
    LearningBase,
    create_learning_engine,
    create_learning_session_factory,
)
from .contexts.learning.adapters.persistence.uow import LearningUnitOfWork
from .contexts.learning.application.analytics import LearningAnalytics
from .contexts.learning.application.knowledge_service import KnowledgeService
from .contexts.learning.application.session_service import SessionService
from .contexts.learning.domain.decision import DecisionConfig
from .contexts.learning.domain.estimator import BKTEstimator
from .contexts.learning.domain.forgetting import HalfLifeForgettingModel
from .contexts.learning.domain.runtime import TemplatedTeachingRuntime
from .contexts.sync.domain import DeltaType, SyncDelta, SyncEngine, SyncStore
from .platform import correlation
from .platform.config import Settings, load_settings
from .platform.errors import Problem, forbidden, unauthorized
from .platform.logging import StructuredLogger
from .platform.metrics import registry
from .platform.plugins import Module
from .platform.plugins import registry as module_registry


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

    app = FastAPI(
        title="Project Taleem — Core API",
        version=__version__,
        description="M1 walking skeleton. Governance-safe scaffolding only — no child data.",
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
        ],
    )

    # Shared, process-local state for the walking skeleton (synthetic only).
    sync_store = SyncStore()
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
            yield CurriculumStudioService(uow.lessons, uow.publish)
            uow.commit()  # reached only on success; the UoW rolls back on any raised exception

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

    # Register the modules this deployable composes (plugin architecture).
    reg = module_registry()
    for module in (
        Module("health", "/health", lambda: True),
        Module("sync", "/v1/sync", lambda: True, events_published=("ProgressSynced",)),
        Module(
            "curriculum_studio", "/v1/studio", lambda: True, events_published=("LessonPublished",)
        ),
        Module("learning", "/v1/learning", lambda: True, events_published=("ObjectiveMastered",)),
    ):
        # Idempotent across reloads/tests: re-registering the same module is a no-op.
        with contextlib.suppress(ValueError):
            reg.register(module)

    @app.middleware("http")
    async def observability(request: Request, call_next: Any) -> Any:
        cid = correlation.ensure_correlation_id(request.headers.get("x-correlation-id"))
        start = time.perf_counter()
        registry().inc("taleem_requests_total", method=request.method, path=request.url.path)
        try:
            response = await call_next(request)
        except Problem as problem:  # domain errors -> RFC9457
            response = JSONResponse(
                status_code=problem.status, content=problem.to_dict(str(request.url.path))
            )
        duration_ms = (time.perf_counter() - start) * 1000.0
        registry().observe("taleem_request_duration_ms", duration_ms, path=request.url.path)
        response.headers["x-correlation-id"] = cid
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

    # ---- sync engine prototype ----
    @app.post("/v1/sync/batch", tags=["sync"])
    def sync_batch(batch: BatchIn) -> dict[str, Any]:
        engine = SyncEngine(sync_store)
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
        results, cursor = engine.apply_batch(deltas)
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
