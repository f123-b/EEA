"""Map deterministic engineering errors to the V1 API envelope."""

from collections.abc import Mapping

from eea_core.enums import EngineeringErrorCode
from eea_core.errors import EngineeringError
from fastapi import Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from eea_backend.schemas import ErrorData, ErrorEnvelope

HTTP_STATUS_BY_CODE = {
    EngineeringErrorCode.AUTH_REQUIRED: status.HTTP_401_UNAUTHORIZED,
    EngineeringErrorCode.PROJECT_NOT_FOUND: status.HTTP_404_NOT_FOUND,
    EngineeringErrorCode.DOMAIN_NOT_FOUND: status.HTTP_404_NOT_FOUND,
    EngineeringErrorCode.REVISION_CONFLICT: status.HTTP_409_CONFLICT,
    EngineeringErrorCode.SOURCE_REVISION_CONFLICT: status.HTTP_409_CONFLICT,
    EngineeringErrorCode.SOURCE_FILE_NOT_FOUND: status.HTTP_404_NOT_FOUND,
    EngineeringErrorCode.PATCH_PROPOSAL_NOT_FOUND: status.HTTP_404_NOT_FOUND,
    EngineeringErrorCode.GENERATED_SOURCE_DIVERGED: status.HTTP_409_CONFLICT,
    EngineeringErrorCode.DOMAIN_COMPOSITION_CONFLICT: status.HTTP_409_CONFLICT,
    EngineeringErrorCode.DOMAIN_DEPENDENCY_MISSING: status.HTTP_422_UNPROCESSABLE_CONTENT,
    EngineeringErrorCode.DOMAIN_INCOMPATIBLE: status.HTTP_409_CONFLICT,
    EngineeringErrorCode.DOMAIN_CONFIGURATION_INVALID: status.HTTP_422_UNPROCESSABLE_CONTENT,
    EngineeringErrorCode.COMMISSIONING_REQUIRED: status.HTTP_409_CONFLICT,
    EngineeringErrorCode.COMMISSIONING_BLOCKED: status.HTTP_409_CONFLICT,
    EngineeringErrorCode.SAFETY_LIMIT_VIOLATION: status.HTTP_422_UNPROCESSABLE_CONTENT,
    EngineeringErrorCode.TARGET_IDENTITY_MISMATCH: status.HTTP_409_CONFLICT,
    EngineeringErrorCode.SAFE_STATE_FAILED: status.HTTP_409_CONFLICT,
    EngineeringErrorCode.EMERGENCY_STOP_ACTIVE: status.HTTP_409_CONFLICT,
    EngineeringErrorCode.RECOVERY_REQUIRED: status.HTTP_409_CONFLICT,
    EngineeringErrorCode.BUILD_INPUT_UNDECLARED: status.HTTP_422_UNPROCESSABLE_CONTENT,
    EngineeringErrorCode.VALIDATION_ERROR: status.HTTP_422_UNPROCESSABLE_CONTENT,
    EngineeringErrorCode.KNOWLEDGE_SCOPE_DENIED: status.HTTP_400_BAD_REQUEST,
}


def _json_safe(value: object) -> object:
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if isinstance(value, BaseException):
        return str(value)
    return value


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
            details={"errors": _json_safe(exc.errors())},
        ),
        request_id=_request_id(request),
    )
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        content=envelope.model_dump(mode="json"),
    )
