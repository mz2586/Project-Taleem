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
import os
import time
from collections.abc import Iterator
from typing import Any

from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm.exc import StaleDataError

from . import __version__
from .auth import pdp
from .auth.dependencies import authorize, bearer_claims_from, require_owner_or
from .auth.jwt_verifier import Claims
from .auth.learner_gate import (
    LEARNER_INACTIVE,
    IdentityLearnerGate,
    LearnerRefusedError,
    learner_permission_dependency,
    refusal_problem,
)
from .auth.setup import build_auth_context
from .contexts.curriculum_studio.adapters.api import build_studio_router
from .contexts.curriculum_studio.adapters.persistence import (
    Base as CurriculumBase,
)
from .contexts.curriculum_studio.adapters.persistence import (
    create_db_engine,
    create_session_factory,
    studio_audio_resolver,
    unit_of_work,
)
from .contexts.curriculum_studio.application.service import CurriculumStudioService
from .contexts.guardian.adapters.guardian_api import build_guardian_router
from .contexts.guardian.adapters.identity_links import build_guardian_links
from .contexts.guardian.application.guardian_service import GuardianService
from .contexts.health.service import Check, HealthService
from .contexts.identity.adapters.identity_api import build_identity_router
from .contexts.identity.adapters.persistence.base import (
    IdentityBase,
    create_identity_engine,
    create_identity_session_factory,
)
from .contexts.identity.adapters.persistence.models import LearnerRow
from .contexts.identity.adapters.persistence.rate_limit_store import SqlRateLimitStore
from .contexts.identity.adapters.persistence.uow import SqlIdentityUnitOfWork
from .contexts.identity.adapters.rate_limit import Limiter, RateLimiter, SharedRateLimiter
from .contexts.identity.adapters.staff_api import build_staff_router, staff_gate_dependency
from .contexts.identity.application.identity_service import IdentityService
from .contexts.identity.application.staff_service import StaffService
from .contexts.identity.application.tokens import (
    GUARDIAN_TOKEN_TTL_SECONDS,
    IssuedToken,
    TokenIssuer,
)
from .contexts.identity.domain.consent import ConsentEvidence, ConsentScope, derive_state
from .contexts.identity.domain.credentials import SecretHasher
from .contexts.learning.adapters.ai_teacher_api import build_ai_teacher_router
from .contexts.learning.adapters.api import LearningApiDeps, build_learning_router
from .contexts.learning.adapters.curriculum_read_model import CurriculumStudioReadModel
from .contexts.learning.adapters.memory import InMemorySessionRepository
from .contexts.learning.adapters.offline_api import build_offline_router
from .contexts.learning.adapters.package_signer import Ed25519PackageSigner
from .contexts.learning.adapters.persistence.ai_usage_ledger import SqlLearnerUsageLedger
from .contexts.learning.adapters.persistence.base import (
    LearningBase,
    create_learning_engine,
    create_learning_session_factory,
)
from .contexts.learning.adapters.persistence.uow import LearningUnitOfWork
from .contexts.learning.adapters.placement_api import build_placement_router
from .contexts.learning.adapters.progression_api import (
    ProgressionApiDeps,
    build_progression_router,
)
from .contexts.learning.adapters.student_api import build_student_router
from .contexts.learning.application.ai_teacher_service import (
    SAFETY_LOG_ALLOW,
    AITeacherService,
    GenerativeTier,
    logging_safety_sink,
)
from .contexts.learning.application.analytics import LearningAnalytics
from .contexts.learning.application.knowledge_service import KnowledgeService
from .contexts.learning.application.offline_service import OfflinePackageService
from .contexts.learning.application.placement_service import PlacementService
from .contexts.learning.application.progression_service import ProgressionService
from .contexts.learning.application.report_records import LearnerRecordsService
from .contexts.learning.application.session_service import SessionService
from .contexts.learning.application.student_queries import StudentQueryService
from .contexts.learning.application.sync_consumer import SyncEvidenceConsumer
from .contexts.learning.application.written_work import WrittenWorkService
from .contexts.learning.domain.decision import DecisionConfig
from .contexts.learning.domain.estimator import BKTEstimator
from .contexts.learning.domain.forgetting import HalfLifeForgettingModel
from .contexts.learning.domain.runtime import TemplatedTeachingRuntime
from .contexts.ops.adapters.ops_api import build_ops_router
from .contexts.ops.adapters.persistence.base import (
    OpsBase,
    create_ops_engine,
    create_ops_session_factory,
)
from .contexts.ops.adapters.persistence.kill_switch_store import SqlKillSwitchState
from .contexts.privacy.adapters.privacy_api import build_privacy_router
from .contexts.privacy.adapters.wiring import build_privacy_service
from .contexts.reporting.adapters.context_ports import (
    CallableLearnerDirectory,
    CallableLearningRecords,
    CallablePublishedLessons,
    CallableSchoolDirectory,
)
from .contexts.reporting.adapters.persistence.base import (
    ReportingBase,
    create_reporting_session_factory,
    reporting_engine_sharing,
)
from .contexts.reporting.adapters.persistence.uow import SqlReportingUnitOfWork
from .contexts.reporting.adapters.reporting_api import (
    build_reporting_learner_router,
    build_reporting_router,
)
from .contexts.reporting.application.service import ReportingService
from .contexts.safeguarding.adapters.persistence.base import (
    SafeguardingBase,
    create_safeguarding_session_factory,
    safeguarding_engine_sharing,
)
from .contexts.safeguarding.adapters.persistence.uow import SqlSafeguardingUnitOfWork
from .contexts.safeguarding.adapters.safeguarding_api import (
    RAISE_LIMIT,
    RAISE_WINDOW_SECONDS,
    build_safeguarding_router,
)
from .contexts.safeguarding.application.service import SafeguardingService
from .contexts.safeguarding.domain.model import SlaPolicy
from .contexts.school.adapters.audit_log import SqlSchoolAuditLog
from .contexts.school.adapters.context_ports import (
    CallableExplanationReader,
    CallablePublishedCurriculum,
    CallableSharingConsent,
    CallableWrittenWork,
    IdentityLearnerDirectory,
    KnowledgeProgressReader,
)
from .contexts.school.adapters.persistence.base import (
    SchoolBase,
    create_school_session_factory,
    school_engine_sharing,
)
from .contexts.school.adapters.persistence.uow import SqlSchoolUnitOfWork
from .contexts.school.adapters.school_api import build_school_learner_router, build_school_router
from .contexts.school.application.homework_sync import HomeworkSyncConsumer
from .contexts.school.application.school_service import SchoolService
from .contexts.sync.domain import DeltaType, SyncDelta, SyncStore
from .contexts.sync.service import DurableSyncCoordinator
from .platform import correlation
from .platform import observability as obs
from .platform.cohort import REAL, install_reader, reset_reader
from .platform.concurrency import ConcurrencyConflictError
from .platform.config import Settings, load_settings
from .platform.errors import Problem, conflict, forbidden
from .platform.feature_flags import StaticFlagProvider
from .platform.kill_switch import KillSwitch, is_child_facing
from .platform.logging import StructuredLogger
from .platform.metrics import registry
from .platform.plugins import Module
from .platform.plugins import registry as module_registry
from .platform.security_headers import apply_security_headers
from .ports.llm import (
    InMemoryCostLedger,
    LearnerQuota,
    LearnerUsageLedger,
    LLMGateway,
    StubLLMGateway,
)
from .ports.llm_anthropic import ANTHROPIC_PROVIDER, AnthropicNotApprovedError, anthropic_gateway
from .ports.llm_inert import InertProviderGateway


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
                "name": "safeguarding",
                "description": "Safeguarding concerns: raise (child, guardian) and triage (lead)",
            },
            {
                "name": "guardian",
                "description": "Guardian Portal — read-only view of linked children",
            },
            {
                "name": "reporting",
                "description": "Report cards: issued, immutable, derived snapshots",
            },
            {
                "name": "identity",
                "description": (
                    "Guardian accounts, verifiable consent, learner enrolment, child-safe sign-in"
                ),
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

    # Process-local synthetic state for the walking skeleton. Safe to keep per-instance: the
    # durable idempotency check for attempts is the evidence table inside the sink, and the other
    # delta policies are idempotent by construction (monotonic max / idempotent set / server-order-
    # wins), so a replay against a different instance re-applies as a no-op.
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

    # Operator halt for child-facing traffic (ops control). The flag lives in the database so it is
    # shared by every instance — a kill switch held in process memory fails OPEN as soon as more
    # than one instance serves traffic (a second replica, or a fresh serverless invocation), which
    # is the one failure mode a safety control must not have. In-memory SQLite (the governance-safe
    # dev default) is single-process anyway, so behaviour there is unchanged.
    ops_engine = create_ops_engine(db_url)
    if ops_engine.dialect.name == "sqlite":
        OpsBase.metadata.create_all(ops_engine)
    ops_sf = create_ops_session_factory(ops_engine)
    kill_switch = KillSwitch(time.time, SqlKillSwitchState(ops_sf))
    app.state.ops_session_factory = ops_sf
    # Session factories are exposed for seeding in tests / ops tooling (not a request path).
    app.state.studio_session_factory = studio_sf
    app.state.learning_session_factory = learning_sf

    # AuthN: every business route requires a verified bearer token; the actor's role comes from
    # the token, not the request body (CTO B1). Deny-by-default PDP does authorization. The verifier
    # is asymmetric (EdDSA/JWKS) in production and HS256 in dev/test (FD-14). The auth context is
    # exposed on app.state so the identity/login flow can issue tokens with the signing key.
    auth = build_auth_context(settings)
    app.state.auth = auth
    claims_dependency = bearer_claims_from(auth.verifier)

    # ---- Identity, consent & child-safe sign-in (FD-14) ----
    # This is the context that issues tokens, so it is the one place holding the signing key. In
    # production ``auth.signer`` is always present (config refuses to boot without an Ed25519
    # seed); locally it may be absent, and the issuer falls back to the HS256 development path that
    # the dev verifier already accepts.
    identity_engine = create_identity_engine(db_url)
    if identity_engine.dialect.name == "sqlite":
        IdentityBase.metadata.create_all(identity_engine)
    identity_sf = create_identity_session_factory(identity_engine)
    app.state.identity_session_factory = identity_sf

    # One token issuer (the identity context's) for every token, teacher tokens included.
    token_issuer = TokenIssuer(
        issuer=settings.jwt_issuer,
        audience=settings.jwt_audience,
        signer=auth.signer,
        hs256_secret=None if settings.is_production else settings.jwt_dev_secret,
    )
    identity_service = IdentityService(
        lambda: SqlIdentityUnitOfWork(identity_sf),
        token_issuer,
        time.time,
        SecretHasher(iterations=settings.kdf_iterations),
    )
    app.state.identity_service = identity_service
    # Public-route rate limits are shared across instances whenever a real database is configured:
    # a process-local budget is per serverless invocation, i.e. no limit at all in production.
    rate_limit_store = (
        SqlRateLimitStore(identity_engine) if identity_engine.dialect.name == "postgresql" else None
    )
    app.include_router(
        build_identity_router(
            identity_service,
            claims_dependency,
            clock=time.time,
            rate_limit_store=rate_limit_store,
            client_ip_header=settings.client_ip_header,
        )
    )

    # ---- Curriculum Studio staff accounts (operator-provisioned; one Studio role each) ----
    staff_service = StaffService(
        lambda: SqlIdentityUnitOfWork(identity_sf),
        token_issuer,
        time.time,
        SecretHasher(iterations=settings.kdf_iterations),
        identity_service,  # staff sessions refresh through identity's registered-role hook
    )
    app.state.staff_service = staff_service
    app.include_router(
        build_staff_router(
            staff_service,
            claims_dependency,
            clock=time.time,
            rate_limit_store=rate_limit_store,
            client_ip_header=settings.client_ip_header,
        )
    )
    # A Studio-role token is re-checked against its live staff account on every Studio request, so
    # a suspension takes effect at once. Production refuses Studio tokens with no staff account.
    staff_permitted = [
        Depends(
            staff_gate_dependency(
                staff_service, claims_dependency, require_account=settings.is_production
            )
        )
    ]

    # ---- Per-request learner permission gate (child safety; e2e GAP 2) ----
    # A learner's access token outlives a consent withdrawal or a suspension by up to its TTL. So
    # every route a student token can call that reads or writes learning data re-checks the learner
    # against LIVE identity state on every request (no cache): learning, student read models, the
    # AI teacher, offline packages — and every learner a sync batch writes for. Production also
    # refuses learners with no identity account (dev/test HS256 tokens may name synthetic learners).
    def _learner_lookup(student_ref: str) -> Any:
        with SqlIdentityUnitOfWork(identity_sf) as uow:
            return uow.learners.get(student_ref)

    learner_gate = IdentityLearnerGate(
        identity_service.consent_state_for,
        _learner_lookup,
        require_enrolled=settings.is_production,
    )
    learner_permitted = [Depends(learner_permission_dependency(learner_gate, claims_dependency))]

    # ---- Curriculum Studio (CTO H2: SQL-backed, request-scoped Unit of Work) ----
    def studio_service_provider() -> Iterator[CurriculumStudioService]:
        with unit_of_work(studio_sf) as uow:
            # The service commits inside each mutating method (on_commit) so an optimistic-lock
            # conflict at commit is caught in the request handler (409), not in dependency teardown
            # (which would surface as a 500). The UoW still rolls back on any raised exception.
            # Recorded audio must resolve in the media registry; synthetic fixture refs are
            # accepted outside production only.
            audio = studio_audio_resolver(uow.audio_assets, production=settings.is_production)
            yield CurriculumStudioService(
                uow.lessons,
                uow.publish,
                on_commit=uow.commit,
                audio_assets=audio,
                hierarchy=uow.hierarchy,
            )

    app.include_router(
        build_studio_router(studio_service_provider, claims_dependency),
        dependencies=staff_permitted,
    )

    # ---- Learning Intelligence Platform (CTO H1: now mounted in the deployable) ----
    def learning_uow() -> LearningUnitOfWork:
        return LearningUnitOfWork(learning_sf)

    knowledge_service = KnowledgeService(
        learning_uow, BKTEstimator(), HalfLifeForgettingModel(), time.time
    )
    read_model = CurriculumStudioReadModel(studio_sf)
    session_repo = InMemorySessionRepository()
    session_service = SessionService(
        session_repo,
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
    app.include_router(
        build_learning_router(learning_deps, claims_dependency), dependencies=learner_permitted
    )
    app.state.session_service = session_service  # tests read a session's recorded rationale

    # ---- Diagnostic placement (R2): seeds priors for a learner with no history ----
    placement_service = PlacementService(
        learning_uow, read_model, read_model.published_graph, time.time
    )
    app.include_router(
        build_placement_router(placement_service, claims_dependency),
        dependencies=learner_permitted,
    )

    # ---- Student query surface (derived read models: homework, reviews, history, …) ----
    student_queries = StudentQueryService(learning_uow, read_model, time.time)
    app.include_router(
        build_student_router(student_queries, claims_dependency), dependencies=learner_permitted
    )

    # ---- Offline lesson packages (Phase 6.2A: content-hashed; 6.2C-1: Ed25519-signed) ----
    package_signer = Ed25519PackageSigner(
        settings.offline_signing_seed_hex, settings.offline_signing_key_id
    )
    offline_service = OfflinePackageService(read_model, time.time, signer=package_signer)
    app.include_router(
        build_offline_router(offline_service, claims_dependency), dependencies=learner_permitted
    )

    # ---- School / organization pilot minimum (teachers, classes, assignments) ----
    # Identity, learning and curriculum are reached only through the school ports, wired here.
    # Teacher visibility of a learner is LIVE per request: the learner gate (consent + account)
    # AND the guardian's progress_sharing scope — the scope identity defines for "share progress
    # with an assigned mentor/teacher". Joining a class with a code is the guardian's grant.
    # Shares the identity engine's pool (one pool per app, not one more per context).
    school_engine = school_engine_sharing(identity_engine)
    if school_engine.dialect.name == "sqlite":
        SchoolBase.metadata.create_all(school_engine)
    school_sf = create_school_session_factory(school_engine)
    app.state.school_session_factory = school_sf

    def _grant_class_sharing(guardian_ref: str, student_ref: str, attestation: str) -> object:
        # learning_data is required by every grant record; the join refuses a learner without it,
        # so including it here never restores a withdrawn learning consent.
        return identity_service.grant_consent(
            guardian_ref=guardian_ref,
            student_ref=student_ref,
            scopes={ConsentScope.LEARNING_DATA, ConsentScope.PROGRESS_SHARING},
            evidence=ConsentEvidence(method="class_join", attestation=attestation),
        )

    def _teacher_access(teacher_ref: str, now: float) -> IssuedToken:
        # ``school_service`` is built below; resolved at call time. The cohort claim is for display
        # only (DEMO_COHORT_CONTRACT §2); the server reads the cohort from the account.
        return token_issuer.issue(
            subject=teacher_ref,
            role="teacher",
            now=now,
            ttl_seconds=GUARDIAN_TOKEN_TTL_SECONDS,
            cohort=school_service.teacher_cohort(teacher_ref),
        )

    def _issue_teacher_token(*, teacher_ref: str, now: float) -> dict[str, object]:
        return _teacher_access(teacher_ref, now).to_dict()

    class _TeacherSessions:
        def open(self, *, teacher_ref: str, device_id: str) -> str:
            return identity_service.issue_refresh_token(teacher_ref, "teacher", device_id)

    school_limiter: Limiter = (
        SharedRateLimiter("school.sign_in", 10, 60.0, time.time, rate_limit_store)
        if rate_limit_store is not None
        else RateLimiter(10, 60.0, time.time)
    )
    school_ip_header = settings.client_ip_header.strip().lower()

    def _school_sign_in_guard(request: Request) -> None:
        key = ""
        if school_ip_header:
            key = request.headers.get(school_ip_header, "").split(",")[0].strip()
        if not key:
            key = request.client.host if request.client else "unknown"
        school_limiter.check(key[:64])

    school_audit = SqlSchoolAuditLog(school_sf, log)  # durable: school.enrolment_audit (0011)

    def _visible_to_teacher(student_refs: list[str]) -> dict[str, str]:
        # The same live rules as IdentityLearnerDirectory.shares_with_teacher (an identity
        # account, the learner gate's refusal, and progress_sharing consent), read for a whole
        # class in ONE identity transaction instead of several per learner. Nothing is cached.
        with SqlIdentityUnitOfWork(identity_sf) as uow:
            accounts = {ref: uow.learners.get(ref) for ref in student_refs}
            states = {
                ref: derive_state(ref, uow.consents.history(ref))
                for ref, account in accounts.items()
                if account is not None
            }
        gate = IdentityLearnerGate(
            states.__getitem__, accounts.get, require_enrolled=settings.is_production
        )
        return {
            ref: str(account.display_name)
            for ref, account in accounts.items()
            if account is not None
            and gate.refusal(ref) is None
            and states[ref].allows(ConsentScope.PROGRESS_SHARING)
        }

    app.state.school_audit = school_audit
    # Homework + marking (HOMEWORK_AND_MARKING_CONTRACT): written items and the human-graded
    # evidence come from the learning context, through the school's WrittenWork port.
    written_work = WrittenWorkService(read_model, knowledge_service)

    class _TeacherConcerns:
        # "Raise a safeguarding concern" from a marking row. ``safeguarding_service`` and
        # ``raise_limiter`` are built below; they resolve at call time. The same per-subject raise
        # limit as /v1/safeguarding/concerns applies.
        def raise_teacher_concern(
            self,
            *,
            teacher_ref: str,
            student_ref: str,
            submission_id: str,
            category: str,
            text: str | None,
        ) -> dict[str, Any]:
            raise_limiter.check(f"teacher:{teacher_ref}")
            return safeguarding_service.raise_by_teacher(
                teacher_ref=teacher_ref,
                student_ref=student_ref,
                category=category,
                text=text,
                submission_id=submission_id,
                screen="teacher/marking",
                lesson_id=None,
            )

    class _DisclosureScreen:
        # Every submitted homework text passes the safeguarding disclosure screen (contract §6).
        # ``safeguarding_service`` is built below; it resolves at call time.
        def screen_submission(
            self,
            *,
            student_ref: str,
            submission_id: str,
            text: str,
            attempt: int,
            submitted_at: float,
            item_ref: str,
            objective_code: str,
        ) -> bool:
            return safeguarding_service.screen_submission(
                student_ref=student_ref,
                submission_id=submission_id,
                text=text,
                attempt=attempt,
                submitted_at=submitted_at,
                item_ref=item_ref,
                objective_code=objective_code,
            )

    school_service = SchoolService(
        lambda: SqlSchoolUnitOfWork(school_sf),
        hasher=SecretHasher(iterations=settings.kdf_iterations),
        issue_token=_issue_teacher_token,
        learners=IdentityLearnerDirectory(
            learner_lookup=_learner_lookup,
            learner_refusal=learner_gate.refusal,
            sharing_allowed=lambda ref: identity_service.consent_state_for(ref).allows(
                ConsentScope.PROGRESS_SHARING
            ),
            visible_many=_visible_to_teacher,
        ),
        sharing_consent=CallableSharingConsent(_grant_class_sharing),
        progress=KnowledgeProgressReader(
            knowledge_service.snapshot,
            progress_many=lambda refs, code, since: knowledge_service.objective_progress(
                refs, code, since=since
            ),
        ),
        curriculum=CallablePublishedCurriculum(read_model.lesson_for, read_model.published_catalog),
        audit=school_audit,
        clock=time.time,
        sessions=_TeacherSessions(),
        # The teacher learner panel's "why": read only after the live visibility check passes.
        # (`ai_teacher` is built below; the lambda resolves it at call time.)
        explanations=CallableExplanationReader(
            lambda ref: ai_teacher.explained_recommendations(ref)
        ),
        written=CallableWrittenWork(
            written_work.written_lesson,
            written_work.record_marked,
            check_answer=written_work.check_answer,
            studied_objectives=written_work.studied_objectives,
        ),
        concerns=_TeacherConcerns(),
        disclosures=_DisclosureScreen(),
    )
    # AI rubric marking of open answers (HOMEWORK_AND_MARKING_CONTRACT §6) is deliberately NOT
    # wired: FD-03 and an in-region distress classifier come first. The port lives in
    # ``contexts/learning/application/written_marker.py``; no submission path reaches it.
    app.state.written_marker = None
    app.state.school_service = school_service
    # Teachers continue sessions through identity's rotating refresh tokens (rotation, replay
    # revokes the family, device binding, sign-out). The live check runs on every refresh.
    identity_service.register_session_subject(
        "teacher",
        is_active=school_service.teacher_may_continue,
        issue_access=_teacher_access,
        profile=school_service.teacher_session_profile,
    )
    app.include_router(
        build_school_router(school_service, claims_dependency, sign_in_guard=_school_sign_in_guard)
    )
    # The learner's homework: behind the same live learner gate as every learner surface.
    app.include_router(
        build_school_learner_router(school_service, claims_dependency),
        dependencies=learner_permitted,
    )

    # ---- Durable offline sync (Phase 6.2B) ----
    # attempt.submitted deltas record durable AssessmentEvidence idempotently (gap G3); other
    # delta types keep the existing in-memory conflict policy. Idempotency is durable via the
    # evidence table (a replay after restart is still a DUPLICATE).
    sync_consumer = SyncEvidenceConsumer(
        learning_uow, read_model, BKTEstimator(), HalfLifeForgettingModel(), time.time
    )

    # The same learner gate: every learner a batch writes for (a student caller, and each attempt's
    # student_ref — which also covers operator tokens) is re-checked before anything is applied.
    # homework.submitted deltas (a written answer sent while offline) are applied by the SAME
    # school service as the online submit routes (HOMEWORK_AND_MARKING_CONTRACT §2, §6).
    sync_coordinator = DurableSyncCoordinator(
        sync_store, sync_consumer, learner_gate, homework=HomeworkSyncConsumer(school_service)
    )

    # ---- AI Teacher (Phase 8): templated, curriculum-grounded, explainable ----
    # Phase D generative tier: OFF unless the `ai_teacher.generative_rephrase` flag is enabled, and
    # then only per request under live `ai_teaching` consent, a disengaged kill switch, and the
    # learner's inference quota. Per FD-03 no provider is configured anywhere, so by default no
    # generative tier is wired at all; the Claude adapter needs every FD-03 approval setting, and
    # any other named provider is inert (refuses every call).
    flags = StaticFlagProvider(settings.enabled_flags())
    app.state.flags = flags
    # Per-learner usage ledger: shared in PostgreSQL (quotas hold across instances); process-local
    # for the in-memory SQLite dev/test default.
    ai_cost_ledger: LearnerUsageLedger = (
        InMemoryCostLedger()
        if learning_engine.dialect.name == "sqlite"
        else SqlLearnerUsageLedger(learning_sf)
    )
    app.state.ai_cost_ledger = ai_cost_ledger
    provider = settings.ai_provider.strip()
    ai_gateway: LLMGateway | None = None
    if provider.lower() == "stub":
        ai_gateway = StubLLMGateway()
    elif provider.lower() == ANTHROPIC_PROVIDER:
        # FD-03 Claude adapter: built only with every approval setting present. Otherwise the AI
        # Teacher stays on the deterministic engine (production already refused a partial set in
        # load_settings; a directly-constructed production Settings fails closed here too).
        try:
            ai_gateway = anthropic_gateway(settings)
        except AnthropicNotApprovedError as exc:
            if settings.is_production:
                raise
            log.warn(
                "ai_provider_not_approved",
                event="ai_provider_not_approved",
                outcome="deterministic_engine",
                count=len(exc.problems),
            )
    elif provider:
        ai_gateway = InertProviderGateway(provider)
    app.state.ai_gateway = ai_gateway
    generative = (
        GenerativeTier(
            gateway=ai_gateway,
            flags=flags,
            ai_teaching_consent=lambda ref: identity_service.consent_state_for(ref).allows(
                ConsentScope.AI_TEACHING
            ),
            kill_switch_engaged=lambda: kill_switch.engaged,
            cost_meter=ai_cost_ledger,
            safety_events=logging_safety_sink(
                StructuredLogger(settings.service_name, settings.log_level, allow=SAFETY_LOG_ALLOW)
            ),
            quota=LearnerQuota(
                max_calls=settings.ai_learner_daily_calls,
                max_tokens=settings.ai_learner_daily_tokens,
                max_cost_micros=settings.ai_learner_daily_cost_micros or None,
            ),
        )
        if ai_gateway is not None
        else None
    )
    ai_teacher = AITeacherService(
        session_service,
        knowledge_service,
        read_model,
        TemplatedTeachingRuntime(),
        read_model.published_graph,
        DecisionConfig(),
        time.time,
        generative=generative,
    )
    # Router-level wiring: the AI teacher router itself is untouched (owned elsewhere).
    app.include_router(
        build_ai_teacher_router(ai_teacher, session_service, claims_dependency),
        dependencies=learner_permitted,
    )

    # ---- Guardian Portal: read-only aggregation over the EXISTING learning read models. No new
    # child-data surfaces. Which children a guardian may see comes from the identity context
    # (enrolled learners with live consent); the static seed is a dev/demo aid, ignored in prod.
    guardian_directory = build_guardian_links(
        identity_service,
        seed_csv=settings.guardian_links_csv,
        production=settings.is_production,
    )
    guardian_service = GuardianService(
        guardian_directory,
        student_queries,  # reuse the same student query surface
        LearningAnalytics(learning_uow),  # reuse learning analytics
        ai_teacher,  # reuse the AI Teacher plan
        time.time,
    )
    app.include_router(build_guardian_router(guardian_service, claims_dependency))

    # ---- Safeguarding concerns (raise + triage). Software only: not approved or staffed (M-Safe,
    # FD-04, FD-06). Raising is deliberately outside the learner consent gate and the kill switch's
    # child-facing list — a safety channel stays open when learning is halted. Triage is
    # safeguarding_lead only, behind the same live staff-account gate as the Studio.
    safeguarding_engine = safeguarding_engine_sharing(identity_engine)
    if safeguarding_engine.dialect.name == "sqlite":
        SafeguardingBase.metadata.create_all(safeguarding_engine)
    safeguarding_sf = create_safeguarding_session_factory(safeguarding_engine)
    app.state.safeguarding_session_factory = safeguarding_sf

    class _LearnerGuardians:
        def guardian_of(self, student_ref: str) -> str | None:
            account = _learner_lookup(student_ref)
            return str(account.guardian_ref) if account is not None else None

    class _TeacherRoster:
        # A teacher may raise a concern only about a learner in one of their own classes.
        def may_raise_about(
            self, *, teacher_ref: str, student_ref: str, submission_id: str | None
        ) -> bool:
            return school_service.teacher_may_raise_concern(
                teacher_ref=teacher_ref, student_ref=student_ref, submission_id=submission_id
            )

    safeguarding_service = SafeguardingService(
        lambda: SqlSafeguardingUnitOfWork(safeguarding_sf),
        _LearnerGuardians(),
        time.time,
        SlaPolicy.from_json(settings.safeguarding_ack_sla_json),
        require_enrolled=settings.is_production,
        teachers=_TeacherRoster(),
        submissions=school_service,
    )
    app.state.safeguarding_service = safeguarding_service
    raise_limiter: Limiter = (
        SharedRateLimiter(
            "safeguarding.raise", RAISE_LIMIT, RAISE_WINDOW_SECONDS, time.time, rate_limit_store
        )
        if rate_limit_store is not None
        else RateLimiter(RAISE_LIMIT, RAISE_WINDOW_SECONDS, time.time)
    )
    app.include_router(
        build_safeguarding_router(
            safeguarding_service, claims_dependency, raise_limiter=raise_limiter
        ),
        dependencies=staff_permitted,
    )

    # ---- Report cards (REPORT_CARD_CONTRACT): immutable issued snapshots, derived at issue time
    # from learning evidence + mastery events, school's marked homework and the published lesson
    # versions — each reached through a reporting port wired here. Shares the identity pool.
    reporting_engine = reporting_engine_sharing(identity_engine)
    if reporting_engine.dialect.name == "sqlite":
        ReportingBase.metadata.create_all(reporting_engine)
    reporting_sf = create_reporting_session_factory(reporting_engine)
    app.state.reporting_session_factory = reporting_sf
    learner_records = LearnerRecordsService(learning_uow)

    def _guardian_of(student_ref: str) -> str | None:
        account = _learner_lookup(student_ref)
        return str(account.guardian_ref) if account is not None else None

    def _teacher_visibility(student_refs: list[str]) -> dict[str, dict[str, Any]]:
        # The same live rules as _visible_to_teacher, with the reason a learner is hidden (a
        # stable code for the issue's ``skipped`` list). One identity transaction, no cache.
        with SqlIdentityUnitOfWork(identity_sf) as uow:
            accounts = {ref: uow.learners.get(ref) for ref in student_refs}
            states = {
                ref: derive_state(ref, uow.consents.history(ref))
                for ref, account in accounts.items()
                if account is not None
            }
        gate = IdentityLearnerGate(
            states.__getitem__, accounts.get, require_enrolled=settings.is_production
        )
        out: dict[str, dict[str, Any]] = {}
        for ref, account in accounts.items():
            if account is None:
                out[ref] = {"display_name": None, "reason": "inactive"}
                continue
            refusal = gate.refusal(ref)
            if refusal == LEARNER_INACTIVE:
                reason: str | None = "inactive"
            elif refusal is not None or not states[ref].allows(ConsentScope.PROGRESS_SHARING):
                reason = "consent_withdrawn"
            else:
                reason = None
            out[ref] = {"display_name": str(account.display_name), "reason": reason}
        return out

    def _learner_status(student_ref: str) -> dict[str, Any] | None:
        account = _learner_lookup(student_ref)
        if account is None:
            return None
        refusal = learner_gate.refusal(student_ref)
        return {
            "display_name": str(account.display_name),
            "refusal": (
                None
                if refusal is None
                else "inactive" if refusal == LEARNER_INACTIVE else "consent_withdrawn"
            ),
        }

    reporting_service = ReportingService(
        lambda: SqlReportingUnitOfWork(reporting_sf, time.time),
        school=CallableSchoolDirectory(
            lambda teacher_ref, class_id: school_service.reporting_roster(
                teacher_ref=teacher_ref, class_id=class_id
            ),
            school_service.reporting_rosters,
            school_service.marked_homework,
        ),
        learners=CallableLearnerDirectory(_guardian_of, _teacher_visibility, _learner_status),
        records=CallableLearningRecords(learner_records.records),
        lessons=CallablePublishedLessons(read_model.published_versions),
        clock=time.time,
    )
    app.state.reporting_service = reporting_service

    def _all_learner_refs() -> list[str]:
        # The scheduler's roster (``python -m taleem_core.contexts.reporting.issue_due``): every
        # learner account; eligibility (active + live learning consent) is checked per learner.
        with identity_sf() as s:
            return [
                str(r)
                for r in s.scalars(select(LearnerRow.student_ref).order_by(LearnerRow.student_ref))
            ]

    app.state.reporting_learner_refs = _all_learner_refs
    # The scheduler derives each learner's card as that learner reads (their cohort's lessons).
    app.state.learner_cohort = identity_service.learner_cohort
    # Issuing and previewing derive a whole class's cards: bounded per teacher (shared when a real
    # database is configured, like every other limit).
    reporting_limiter: Limiter = (
        SharedRateLimiter("reporting.issue", 30, 60.0, time.time, rate_limit_store)
        if rate_limit_store is not None
        else RateLimiter(30, 60.0, time.time)
    )
    app.include_router(
        build_reporting_router(
            reporting_service, claims_dependency, issue_guard=reporting_limiter.check
        )
    )
    # The learner's own cards: behind the same live learner gate as every learner surface.
    app.include_router(
        build_reporting_learner_router(reporting_service, claims_dependency),
        dependencies=learner_permitted,
    )

    # ---- Path, unit checks and the academic record (PROGRESSION_AND_EXAMINATION_CONTRACT) ----
    # The learner's grade comes from their enrolment; the path is the published curriculum the
    # reader may see (cohort-filtered read model). Sittings live in the learning schema (0019).
    def _grade_of(student_ref: str) -> int | None:
        account = _learner_lookup(student_ref)
        return int(account.grade_level) if account is not None else None

    progression_service = ProgressionService(
        learning_uow, read_model, knowledge_service, _grade_of, time.time
    )
    app.state.progression_service = progression_service

    def _teacher_sees(teacher_ref: str, student_ref: str) -> bool:
        # In one of the teacher's own classes AND visible now (the same live rules as reporting).
        try:
            rosters = school_service.reporting_rosters(teacher_ref)
        except Problem:
            return False
        if not any(student_ref in (r.get("student_refs") or ()) for r in rosters):
            return False
        seen = _teacher_visibility([student_ref]).get(student_ref)
        return seen is not None and seen.get("reason") is None

    def _record_cards(role: str, actor_ref: str, student_ref: str) -> list[dict[str, Any]]:
        if role == "teacher":
            return reporting_service.learner_cards_for_teacher(
                teacher_ref=actor_ref, student_ref=student_ref
            )
        return reporting_service.learner_cards(student_ref)

    app.include_router(
        build_progression_router(
            ProgressionApiDeps(
                service=progression_service,
                guardian_of=_guardian_of,
                teacher_sees=_teacher_sees,
                report_cards=_record_cards,
            ),
            claims_dependency,
        ),
        dependencies=learner_permitted,
    )

    # ---- Privacy: per-learner export, two-step erasure, retention dry-run (R1) ----
    privacy_service = build_privacy_service(
        identity_sf=identity_sf,
        learning_sf=learning_sf,
        school_sf=school_sf,
        safeguarding_sf=safeguarding_sf,
        reporting_sf=reporting_sf,
        session_store=session_repo,
        sync_store=sync_store,
        ai_ledger=ai_cost_ledger,
        env=os.environ,
        production=settings.is_production,
        clock=time.time,
    )
    app.state.privacy_service = privacy_service
    app.include_router(build_privacy_router(privacy_service, claims_dependency))

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
        Module("identity", "/v1/identity", lambda: True, events_published=("ConsentGranted",)),
        Module("privacy", "/v1/privacy", lambda: True),
        Module("school", "/v1/school", lambda: True),
        Module("safeguarding", "/v1/safeguarding", lambda: True),
        Module("reporting", "/v1/reporting", lambda: True, events_published=("ReportCardIssued",)),
    ):
        # Idempotent across reloads/tests: re-registering the same module is a no-op.
        with contextlib.suppress(ValueError):
            reg.register(module)

    # ---- Reader cohort (DEMO_COHORT_CONTRACT §3) ----
    # Every published-curriculum read is filtered by the reader's cohort. Per request a LAZY
    # resolver is installed: only when a read needs it does it verify the bearer token and read the
    # cohort from the ACCOUNT (learner / guardian / teacher) — never from the token's informational
    # ``cohort`` claim. No token, a bad token, any other role or any failure = the real cohort.
    def _reader_cohort(authorization: str) -> str:
        if not authorization.lower().startswith("bearer "):
            return REAL
        claims = auth.verifier.verify(authorization.split(" ", 1)[1])
        if claims.role == "student":
            return identity_service.learner_cohort(claims.sub)
        if claims.role == "guardian":
            return identity_service.guardian_cohort(claims.sub)
        if claims.role == "teacher":
            return school_service.teacher_cohort(claims.sub)
        return REAL

    @app.middleware("http")
    async def reader_cohort(request: Request, call_next: Any) -> Any:
        header = request.headers.get("authorization", "")
        token = install_reader(lambda: _reader_cohort(header))
        try:
            return await call_next(request)
        finally:
            reset_reader(token)

    @app.middleware("http")
    async def observability(request: Request, call_next: Any) -> Any:
        cid = correlation.ensure_correlation_id(request.headers.get("x-correlation-id"))
        start = time.perf_counter()
        # Kill switch: when engaged, child-facing routes fail closed (503); health/ops stay up.
        # The path test comes first so only child-facing requests read the flag (a database read);
        # for those the read stays live on every request — engaging it takes effect immediately.
        if is_child_facing(request.url.path) and kill_switch.engaged:
            registry().inc("taleem_kill_switch_blocked_total")
            registry().inc("taleem_requests_total", method=request.method, path=obs.HALTED_ROUTE)
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
            obs.record_problem(problem.status, problem.code)
            response = JSONResponse(
                status_code=problem.status, content=problem.to_dict(str(request.url.path))
            )
        except Exception:
            # An unhandled error becomes a 500 further out (ServerErrorMiddleware). Count it here,
            # or the 5xx golden signal — and the alert on it — would miss exactly these.
            _record_request(request, start, status=500)
            raise
        duration_ms = _record_request(request, start, status=response.status_code)
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

    def _record_request(request: Request, start: float, *, status: int) -> float:
        duration_ms = (time.perf_counter() - start) * 1000.0
        # Labelled by the route TEMPLATE, not the raw path: raw paths carry session/learner ids and
        # grew one series per id for the life of the process (see tests/perf/README.md).
        route = obs.route_label(request.scope)
        registry().inc("taleem_requests_total", method=request.method, path=route)
        registry().observe("taleem_request_duration_ms", duration_ms, path=route)
        # Bucketed twin (seconds) so the p95/p99 budget alerts can use histogram_quantile.
        registry().observe_histogram(
            "taleem_http_request_duration_seconds",
            duration_ms / 1000.0,
            method=request.method,
            route=route,
        )
        # Error golden signal: count client (4xx) vs server (5xx) responses for monitoring/alerting.
        if status >= 500:
            registry().inc("taleem_errors_total", kind="server")
        elif status >= 400:
            registry().inc("taleem_errors_total", kind="client")
        return duration_ms

    @app.exception_handler(Problem)
    async def problem_handler(request: Request, exc: Problem) -> JSONResponse:
        obs.record_problem(exc.status, exc.code)
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
        # Point-in-time gauges, refreshed per scrape (alerts: kill switch engaged, pool saturation).
        registry().set_gauge("taleem_kill_switch_engaged", 1.0 if kill_switch.engaged else 0.0)
        registry().set_gauge("taleem_ready", 1.0 if health.ready()[0] else 0.0)
        # Safeguarding queue gauges, read from the database (identical on every instance). A failed
        # read must not take the whole scrape down with it; it is counted, and alerted on instead.
        try:
            safeguarding = safeguarding_service.gauges()
        except Exception as exc:  # any store failure: the scrape must still render
            registry().inc("taleem_safeguarding_gauge_errors_total")
            log.info("safeguarding_gauges_unavailable", error=type(exc).__name__)
        else:
            for priority, count in safeguarding["unacknowledged"].items():
                registry().set_gauge(
                    "taleem_safeguarding_concerns_unacknowledged", count, priority=priority
                )
            for priority, count in safeguarding["overdue"].items():
                registry().set_gauge(
                    "taleem_safeguarding_concerns_overdue", count, priority=priority
                )
        registry().set_gauge(
            "taleem_safeguarding_sla_configured",
            1.0 if safeguarding_service.sla.fully_configured else 0.0,
        )
        for pool_name, engine in (
            ("curriculum", curriculum_engine),
            ("learning", learning_engine),
            ("ops", ops_engine),
            ("identity", identity_engine),  # school shares this pool
        ):
            obs.record_db_pool(pool_name, engine)
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
            elif d.type is DeltaType.HOMEWORK_SUBMITTED:
                # Exactly the online submit's guard: the learner's own homework, nobody else's —
                # not even an operator (a child's words are sent only by that child).
                owner = str(d.payload.get("student_ref", ""))
                if not owner:
                    raise Problem(422, "MISSING_STUDENT_REF", "homework missing student_ref", "")
                authorize(claims, "operate", "school.homework")
                require_owner_or(claims, owner, privileged_roles=())
        acting_learner = claims.sub if claims.role == "student" else None
        try:
            results, cursor = sync_coordinator.apply_batch(deltas, acting_learner=acting_learner)
        except LearnerRefusedError as exc:
            # Nothing was applied. The client holds the batch (never deletes it) until the
            # learner's session changes; the code tells it why. No student_ref in the body.
            registry().inc("taleem_sync_batches_refused_total", code=exc.code)
            raise refusal_problem(exc.code) from exc
        for r in results:  # per-delta outcome (applied/duplicate/ignored/conflict) for alerting
            registry().inc("taleem_sync_deltas_total", status=r.status.value)
        return {
            "cursor": cursor,
            "results": [
                {
                    "clientEventId": r.client_event_id,
                    "status": r.status.value,
                    "version": r.server_version,
                    # Only when present (older clients ignore them): why nothing was applied,
                    # and the server's answer the device shows (homework: the submit view).
                    **({"reason": r.reason} if r.reason else {}),
                    **({"result": r.result} if r.result is not None else {}),
                }
                for r in results
            ],
        }

    # ---- JWKS: publish the public verification keys (asymmetric token signing, FD-14) ----
    # Standard discovery endpoint so clients/other resource servers can verify tokens and so key
    # rotation is an overlap (new key appears here before signing switches to it). Public keys only.
    @app.get("/.well-known/jwks.json", tags=["auth"])
    def jwks() -> dict[str, Any]:
        return auth.keyset.jwks()

    # ---- AuthN/AuthZ seam demo ----
    @app.get("/v1/skeleton/protected", tags=["skeleton"])
    def protected(claims: Claims = Depends(claims_dependency)) -> dict[str, Any]:
        decision = pdp.authorize(claims.role, "read", "skeleton.protected")
        if not decision.allow:
            raise forbidden("Not permitted")
        return {"ok": True, "role": claims.role, "policy": decision.reason}

    return app


app = create_app()
