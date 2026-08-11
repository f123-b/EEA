"""FastAPI application factory for the EEA backend."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from uuid import uuid4

from eea_adapters.ai import LiteLLMProvider
from eea_adapters.components import Stm32CubeG4Provider
from eea_adapters.secrets import KeyringSecretService
from eea_application.claims import ClaimPredicateRegistry
from eea_application.requirements import (
    build_claim_predicate_definitions,
    build_foc_benchmark_profile,
    ensure_requirement_prompt_registered,
)
from eea_core.enums import EngineeringErrorCode
from eea_core.errors import EngineeringError
from eea_ports.ai import AIProvider
from eea_ports.secrets import SecretReference
from fastapi import APIRouter, Depends, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from sqlalchemy import inspect
from sqlalchemy.orm import Session

from eea_backend.api import router as core_router
from eea_backend.claim_repositories import SqlAlchemyClaimPredicateRepository
from eea_backend.database import check_database, create_database_engine
from eea_backend.errors import engineering_error_handler, validation_error_handler
from eea_backend.repositories import SqlAlchemyPromptRepository
from eea_backend.requirement_repositories import SqlAlchemyRequirementProfileRepository
from eea_backend.schemas import ApiEnvelope, HealthResponse, VersionData
from eea_backend.security import require_session_token
from eea_backend.settings import Settings
from eea_backend.version import __version__


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
    settings: Settings | None = None, *, ai_provider: AIProvider | None = None
) -> FastAPI:
    """Create an isolated application instance, suitable for runtime and tests."""

    resolved_settings = settings or Settings()
    engine = create_database_engine(resolved_settings)
    resolved_ai_provider = (
        ai_provider if ai_provider is not None else _configured_ai_provider(resolved_settings)
    )

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
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
        yield
        engine.dispose()

    application = FastAPI(
        title="Embedded Engineering Agent API",
        version=__version__,
        description="Versioned API for the Embedded Engineering Agent platform.",
        lifespan=lifespan,
    )
    application.state.settings = resolved_settings
    application.state.engine = engine
    application.state.ai_provider = resolved_ai_provider
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
            milestone="M6",
        )
        return ApiEnvelope(data=data, request_id=request.state.request_id)

    api.include_router(core_router)
    application.include_router(api)
    return application


app = create_app()
