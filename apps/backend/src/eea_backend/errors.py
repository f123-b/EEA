"""Map deterministic engineering errors to the V1 API envelope."""

from eea_core.enums import EngineeringErrorCode
from eea_core.errors import EngineeringError
from fastapi import Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from eea_backend.schemas import ErrorData, ErrorEnvelope

HTTP_STATUS_BY_CODE = {
    EngineeringErrorCode.AUTH_REQUIRED: status.HTTP_401_UNAUTHORIZED,
    EngineeringErrorCode.PROJECT_NOT_FOUND: status.HTTP_404_NOT_FOUND,
    EngineeringErrorCode.REVISION_CONFLICT: status.HTTP_409_CONFLICT,
    EngineeringErrorCode.SOURCE_REVISION_CONFLICT: status.HTTP_409_CONFLICT,
    EngineeringErrorCode.DOMAIN_COMPOSITION_CONFLICT: status.HTTP_409_CONFLICT,
    EngineeringErrorCode.DOMAIN_DEPENDENCY_MISSING: status.HTTP_422_UNPROCESSABLE_CONTENT,
    EngineeringErrorCode.DOMAIN_INCOMPATIBLE: status.HTTP_409_CONFLICT,
    EngineeringErrorCode.COMMISSIONING_REQUIRED: status.HTTP_409_CONFLICT,
    EngineeringErrorCode.COMMISSIONING_BLOCKED: status.HTTP_409_CONFLICT,
    EngineeringErrorCode.SAFETY_LIMIT_VIOLATION: status.HTTP_422_UNPROCESSABLE_CONTENT,
    EngineeringErrorCode.TARGET_IDENTITY_MISMATCH: status.HTTP_409_CONFLICT,
    EngineeringErrorCode.SAFE_STATE_FAILED: status.HTTP_409_CONFLICT,
    EngineeringErrorCode.EMERGENCY_STOP_ACTIVE: status.HTTP_409_CONFLICT,
    EngineeringErrorCode.RECOVERY_REQUIRED: status.HTTP_409_CONFLICT,
    EngineeringErrorCode.BUILD_INPUT_UNDECLARED: status.HTTP_422_UNPROCESSABLE_CONTENT,
    EngineeringErrorCode.VALIDATION_ERROR: status.HTTP_422_UNPROCESSABLE_CONTENT,
}


def _request_id(request: Request) -> str:
    return getattr(request.state, "request_id", "req_unknown")


def engineering_error_handler(request: Request, exc: EngineeringError) -> JSONResponse:
    envelope = ErrorEnvelope(
        error=ErrorData(code=exc.code, message=exc.message, details=exc.details),
        request_id=_request_id(request),
    )
    return JSONResponse(
        status_code=HTTP_STATUS_BY_CODE.get(exc.code, status.HTTP_400_BAD_REQUEST),
        content=envelope.model_dump(mode="json"),
    )


def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    envelope = ErrorEnvelope(
        error=ErrorData(
            code=EngineeringErrorCode.VALIDATION_ERROR,
            message="Request validation failed",
            details={"errors": exc.errors()},
        ),
        request_id=_request_id(request),
    )
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        content=envelope.model_dump(mode="json"),
    )
