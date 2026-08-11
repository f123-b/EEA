"""FastAPI application factory for the EEA backend."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import uuid4

from eea_core.errors import EngineeringError
from fastapi import APIRouter, Depends, FastAPI, Request
from fastapi.exceptions import RequestValidationError

from eea_backend.api import router as core_router
from eea_backend.database import check_database, create_database_engine
from eea_backend.errors import engineering_error_handler, validation_error_handler
from eea_backend.schemas import ApiEnvelope, HealthResponse, VersionData
from eea_backend.security import require_session_token
from eea_backend.settings import Settings
from eea_backend.version import __version__


def create_app(settings: Settings | None = None) -> FastAPI:
    """Create an isolated application instance, suitable for runtime and tests."""

    resolved_settings = settings or Settings()
    engine = create_database_engine(resolved_settings)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
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
            milestone="M3",
        )
        return ApiEnvelope(data=data, request_id=request.state.request_id)

    api.include_router(core_router)
    application.include_router(api)
    return application


app = create_app()
