"""Minimal bearer-token guard for versioned local API routes."""

import hmac
from typing import Annotated

from eea_core.enums import EngineeringErrorCode
from eea_core.errors import EngineeringError
from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

bearer_scheme = HTTPBearer(auto_error=False)


def require_session_token(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
) -> None:
    """Require a bearer token when ``EEA_SESSION_TOKEN`` is configured."""

    configured = request.app.state.settings.session_token
    if configured is None:
        request.state.actor_id = "local-authenticated-session"
        return
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise EngineeringError(EngineeringErrorCode.AUTH_REQUIRED, "Missing bearer token")
    if not hmac.compare_digest(credentials.credentials, configured.get_secret_value()):
        raise EngineeringError(EngineeringErrorCode.AUTH_REQUIRED, "Invalid bearer token")
    request.state.actor_id = "configured-authenticated-session"


def authenticated_actor_id(request: Request) -> str:
    actor_id = getattr(request.state, "actor_id", None)
    if not isinstance(actor_id, str) or not actor_id:
        raise EngineeringError(EngineeringErrorCode.AUTH_REQUIRED, "authenticated actor is missing")
    return actor_id
