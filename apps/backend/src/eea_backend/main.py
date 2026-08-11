"""FastAPI application factory for the EEA backend."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import uuid4

from eea_application.requirements import (
    build_foc_benchmark_profile,
    ensure_requirement_prompt_registered,
)
from eea_core.enums import EngineeringErrorCode
from eea_core.errors import EngineeringError
from eea_ports.ai import AIProvider
from fastapi import APIRouter, Depends, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from sqlalchemy import inspect
from sqlalchemy.orm import Session

from eea_backend.api import router as core_router
from eea_backend.database import check_database, create_database_engine
from eea_backend.errors import engineering_error_handler, validation_error_handler
from eea_backend.repositories import SqlAlchemyPromptRepository
from eea_backend.requirement_repositories import SqlAlchemyRequirementProfileRepository
from eea_backend.schemas import ApiEnvelope, HealthResponse, VersionData
from eea_backend.security import require_session_token
from eea_backend.settings import Settings
from eea_backend.version import __version__


def seed_builtin_requirement_profiles(session: Session) -> None:
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


def create_app(
    settings: Settings | None = None, *, ai_provider: AIProvider | None = None
) -> FastAPI:
    """Create an isolated application instance, suitable for runtime and tests."""

    resolved_settings = settings or Settings()
    engine = create_database_engine(resolved_settings)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        with engine.connect() as connection:
            if inspect(connection).has_table("requirement_profiles") and inspect(
                connection
            ).has_table("prompt_definitions"):
                with Session(engine) as session:
                    seed_builtin_requirement_profiles(session)
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
    application.state.ai_provider = ai_provider
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
