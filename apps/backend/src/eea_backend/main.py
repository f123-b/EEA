"""FastAPI application factory for the EEA backend."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from secrets import token_urlsafe
from uuid import UUID, uuid4

from eea_adapters.ai import LiteLLMProvider
from eea_adapters.components import Stm32CubeG4Provider
from eea_adapters.hardware import FakeHardwareCommissioningAdapter
from eea_adapters.schematic import KiCadErcAdapter
from eea_adapters.secrets import KeyringSecretService
from eea_adapters.source import FileSystemSourceWorkspaceAdapter, GitCliWorkspaceAdapter
from eea_adapters.static_analysis import CppcheckAdapter
from eea_application.claims import ClaimPredicateRegistry
from eea_application.commissioning import build_safe_commissioning_profile
from eea_application.domains import DomainExtensionRegistry
from eea_application.reliability import (
    EventOutboxService,
    NoopCrashInjector,
    new_recovery_worker_id,
)
from eea_application.requirements import (
    build_claim_predicate_definitions,
    build_foc_benchmark_profile,
    ensure_requirement_prompt_registered,
)
from eea_application.source_workspace import SourceWorkspaceService
from eea_application.testing import TestExecutorRegistry
from eea_core.enums import EngineeringErrorCode
from eea_core.errors import EngineeringError
from eea_core.failure_injection import FailureInjectionHarness
from eea_core.hardware import HardwareIdentity, ProbeIdentity
from eea_ports.ai import AIProvider
from eea_ports.secrets import SecretReference
from fastapi import APIRouter, Depends, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import SecretStr
from sqlalchemy import inspect, select
from sqlalchemy.orm import Session

from eea_backend.api import router as core_router
from eea_backend.claim_repositories import SqlAlchemyClaimPredicateRepository
from eea_backend.commissioning_repositories import SqlAlchemyCommissioningRepository
from eea_backend.database import check_database, create_database_engine
from eea_backend.dependency_bootstrap import reconcile_project_dependencies
from eea_backend.errors import engineering_error_handler, validation_error_handler
from eea_backend.identity_repositories import IdentityRepository
from eea_backend.m18e_api import router as m18e_router
from eea_backend.models import ProjectRecord, SourceWorkspaceRecord
from eea_backend.recovery import OutboxDispatcher, RecoveryService
from eea_backend.reliability_repositories import SqlAlchemyOutboxRepository
from eea_backend.repositories import SqlAlchemyPromptRepository
from eea_backend.requirement_repositories import SqlAlchemyRequirementProfileRepository
from eea_backend.restore_service import RestoreCoordinator
from eea_backend.schemas import ApiEnvelope, HealthResponse, VersionData
from eea_backend.security import require_session_token
from eea_backend.settings import Settings
from eea_backend.source_repositories import SqlAlchemySourceRepository
from eea_backend.version import __version__
from plugins.builtin.motor_control import build_motor_control_plugin


def seed_builtin_requirement_contracts(session: Session) -> None:
    profile_repository = SqlAlchemyRequirementProfileRepository(session)
    expected_profile = build_foc_benchmark_profile()
    existing_profile = profile_repository.get(
        expected_profile.profile_name, expected_profile.profile_version
    )
    comparable = {"id", "revision", "created_at", "updated_at", "metadata"}
    if existing_profile is None:
        try:
            profile_repository.add(expected_profile)
        except ValueError:
            existing_profile = profile_repository.get(
                expected_profile.profile_name, expected_profile.profile_version
            )
            if existing_profile is None:
                raise
    if existing_profile is not None and existing_profile.model_dump(
        mode="json", exclude=comparable
    ) != (expected_profile.model_dump(mode="json", exclude=comparable)):
        raise EngineeringError(
            EngineeringErrorCode.SCHEMA_VERSION_UNSUPPORTED,
            "Durable requirement profile contract does not match the application contract",
            details={
                "profile_name": expected_profile.profile_name,
                "profile_version": expected_profile.profile_version,
            },
        )
    ensure_requirement_prompt_registered(SqlAlchemyPromptRepository(session))

    predicate_repository = SqlAlchemyClaimPredicateRepository(session)
    predicate_registry = ClaimPredicateRegistry(predicate_repository)
    comparable = {"id", "revision", "created_at", "updated_at", "metadata"}
    for expected in build_claim_predicate_definitions(expected_profile):
        existing = predicate_repository.get(expected.predicate)
        if existing is None:
            try:
                predicate_registry.register(expected)
            except ValueError:
                existing = predicate_repository.get(expected.predicate)
                if existing is None:
                    raise
        if existing is not None and existing.model_dump(
            mode="json", exclude=comparable
        ) != expected.model_dump(mode="json", exclude=comparable):
            raise EngineeringError(
                EngineeringErrorCode.SCHEMA_VERSION_UNSUPPORTED,
                "Durable Claim predicate contract does not match the application contract",
                details={"predicate": expected.predicate},
            )


def seed_builtin_requirement_profiles(session: Session) -> None:
    """Backward-compatible name for the complete M6 contract bootstrap."""

    seed_builtin_requirement_contracts(session)


def seed_builtin_commissioning_profiles(session: Session) -> None:
    """Install the deterministic SAFE_COMMISSIONING profile before accepting sessions."""

    repository = SqlAlchemyCommissioningRepository(session)
    profile = build_safe_commissioning_profile()
    if repository.get_profile(profile.id) is None:
        repository.add_profile(profile, commit=True)


def reconcile_source_workspaces(session: Session) -> None:
    """Recover source bytes before transactional outbox delivery resumes."""

    if not inspect(session.get_bind()).has_table("source_workspaces"):
        return
    for record in session.scalars(select(SourceWorkspaceRecord)):
        workspace = FileSystemSourceWorkspaceAdapter(Path(record.root_path))
        SourceWorkspaceService(
            UUID(record.project_id),
            SqlAlchemySourceRepository(session),
            workspace,
            git=GitCliWorkspaceAdapter(workspace.root),
            source_changed=EventOutboxService(SqlAlchemyOutboxRepository(session)),
        ).reconcile(created_by="eea:source-startup-reconcile")


def _configured_ai_provider(settings: Settings) -> AIProvider | None:
    if not settings.ai_provider_enabled:
        return None
    if not settings.requirements_model or not settings.ai_api_key_reference:
        return None
    return LiteLLMProvider(
        KeyringSecretService(),
        SecretReference(settings.ai_api_key_reference),
        model_map={"requirements-default": settings.requirements_model},
    )


def create_app(
    settings: Settings | None = None,
    *,
    ai_provider: AIProvider | None = None,
    domain_registry: DomainExtensionRegistry | None = None,
) -> FastAPI:
    """Create an isolated application instance, suitable for runtime and tests."""

    resolved_settings = settings or Settings()
    engine = create_database_engine(resolved_settings)
    resolved_ai_provider = (
        ai_provider if ai_provider is not None else _configured_ai_provider(resolved_settings)
    )
    recovery_worker_id = new_recovery_worker_id()

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        try:
            with engine.connect() as connection:
                inspector = inspect(connection)
                if all(
                    inspector.has_table(table)
                    for table in (
                        "requirement_profiles",
                        "prompt_definitions",
                        "claim_predicate_definitions",
                    )
                ):
                    with Session(engine) as session:
                        seed_builtin_requirement_contracts(session)
                        if inspect(session.get_bind()).has_table("commissioning_profiles"):
                            seed_builtin_commissioning_profiles(session)
                        if inspect(session.get_bind()).has_table("identity_users"):
                            IdentityRepository(session).ensure_local_user()
                        for project_id in session.scalars(select(ProjectRecord.id)):
                            reconcile_project_dependencies(session, UUID(project_id))
                if inspector.has_table("source_workspaces"):
                    with Session(engine) as session:
                        reconcile_source_workspaces(session)
            with engine.connect() as connection:
                if inspect(connection).has_table("outbox_events"):
                    summary = application.state.recovery_service.startup_recover(batch_limit=100)
                    application.state.startup_recovery_completed = True
                    application.state.last_recovery_summary = summary
                    application.state.outbox_dispatcher.start()
            yield
        finally:
            try:
                await application.state.outbox_dispatcher.stop()
            finally:
                engine.dispose()

    application = FastAPI(
        title="Embedded Engineering Agent API",
        version=__version__,
        description="Versioned API for the Embedded Engineering Agent platform.",
        lifespan=lifespan,
    )
    application.state.settings = resolved_settings
    application.state.local_session_token = SecretStr(token_urlsafe(32))
    application.state.engine = engine
    application.state.ai_provider = resolved_ai_provider
    application.state.domain_registry = (
        domain_registry
        if domain_registry is not None
        else DomainExtensionRegistry((build_motor_control_plugin(),))
    )
    application.state.static_analysis_provider = CppcheckAdapter()
    application.state.schematic_erc_provider = KiCadErcAdapter(
        evidence_root=resolved_settings.build_evidence_dir
    )
    application.state.test_executor_registry = TestExecutorRegistry()
    application.state.crash_injector = NoopCrashInjector()
    application.state.restore_failure_injector = FailureInjectionHarness()
    application.state.recovery_worker_id = recovery_worker_id
    application.state.restore_coordinator = RestoreCoordinator(
        lambda: Session(engine),
        resolved_settings,
        failure_injector=application.state.restore_failure_injector,
    )
    application.state.recovery_service = RecoveryService(
        lambda: Session(engine),
        worker_id=recovery_worker_id,
        crash_injector=application.state.crash_injector,
        restore_recovery=lambda limit: application.state.restore_coordinator.recover_pending(
            limit=limit
        ),
    )
    application.state.outbox_dispatcher = OutboxDispatcher(
        application.state.recovery_service,
        batch_limit=100,
        poll_interval_seconds=1.0,
    )
    application.state.hardware_commissioning_adapter = FakeHardwareCommissioningAdapter(
        identity=HardwareIdentity(target_identifier="unconfigured-target"),
        probe=ProbeIdentity(serial="unconfigured-probe"),
    )
    application.state.startup_recovery_completed = False
    application.state.last_recovery_summary = {}
    component_source = resolved_settings.stm32cube_g4_source
    if component_source is None:
        candidate = Path(".eea-component-cache/source/STM32CubeG4-v1.6.3")
        component_source = candidate if candidate.is_dir() else None
    providers: list[object] = []
    if component_source is not None:
        try:
            providers.append(Stm32CubeG4Provider(component_source))
        except EngineeringError:
            providers = []
    application.state.component_providers = providers
    application.add_exception_handler(EngineeringError, engineering_error_handler)  # type: ignore[arg-type]
    application.add_exception_handler(RequestValidationError, validation_error_handler)  # type: ignore[arg-type]

    @application.middleware("http")
    async def attach_request_id(request: Request, call_next):  # type: ignore[no-untyped-def]
        request_id = request.headers.get("X-Request-ID", f"req_{uuid4().hex}")
        request.state.request_id = request_id
        origin = request.headers.get("Origin")
        allowed_origins = {"http://127.0.0.1", "http://localhost", "tauri://localhost"}
        if origin is not None and origin not in allowed_origins:
            return JSONResponse(
                status_code=403,
                content={
                    "success": False,
                    "error": {
                        "code": EngineeringErrorCode.AUTH_REQUIRED.value,
                        "message": "remote Origin is not allowed",
                    },
                    "request_id": request_id,
                },
            )
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response

    @application.get("/health", response_model=HealthResponse, tags=["system"])
    def health() -> HealthResponse:
        check_database(engine)
        return HealthResponse(status="ok", version=__version__, database="ok")

    api = APIRouter(prefix="/api/v1", dependencies=[Depends(require_session_token)])

    @api.get("/meta/version", response_model=ApiEnvelope[VersionData], tags=["meta"])
    def version(request: Request) -> ApiEnvelope[VersionData]:
        data = VersionData(
            product="Embedded Engineering Agent",
            version=__version__,
            api_version="v1",
            milestone="M15",
        )
        return ApiEnvelope(data=data, request_id=request.state.request_id)

    api.include_router(core_router)
    api.include_router(m18e_router)
    application.include_router(api)
    return application


app = create_app()
