"""Minimal bearer-token guard for versioned local API routes."""

import hmac
from dataclasses import dataclass
from typing import Annotated

from eea_core.enums import EngineeringErrorCode
from eea_core.errors import EngineeringError
from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

bearer_scheme = HTTPBearer(auto_error=False)


@dataclass(frozen=True, slots=True)
class AuthenticatedPrincipal:
    """Identity established by the backend authentication boundary."""

    actor_id: str
    user_id: str
    organization_id: str | None
    session_id: str
    permissions: frozenset[str]


def _local_principal(request: Request) -> AuthenticatedPrincipal:
    return AuthenticatedPrincipal(
        actor_id="local:single-user",
        user_id="local:single-user",
        organization_id=None,
        session_id=str(request.state.request_id),
        permissions=frozenset({"memory:read", "memory:write", "memory:review"}),
    )


def require_session_token(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
) -> None:
    """Require a bearer token when ``EEA_SESSION_TOKEN`` is configured."""

    configured = request.app.state.settings.session_token
    if configured is None:
        production = request.app.state.settings.env.lower() == "production"
        if (
            production
            or request.app.state.settings.local_auth_required
            or not request.app.state.settings.insecure_local_dev
        ):
            configured = request.app.state.local_session_token
    if configured is None:
        request.state.principal = _local_principal(request)
        return
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise EngineeringError(EngineeringErrorCode.AUTH_REQUIRED, "Missing bearer token")
    if not hmac.compare_digest(credentials.credentials, configured.get_secret_value()):
        raise EngineeringError(EngineeringErrorCode.AUTH_REQUIRED, "Invalid bearer token")
    request.state.principal = _local_principal(request)


def authenticated_actor_id(request: Request) -> str:
    principal = authenticated_principal(request)
    actor_id = principal.actor_id
    if not isinstance(actor_id, str) or not actor_id:
        raise EngineeringError(EngineeringErrorCode.AUTH_REQUIRED, "authenticated actor is missing")
    return actor_id


def authenticated_principal(request: Request) -> AuthenticatedPrincipal:
    """Return the principal produced by the auth dependency, never request data."""

    principal = getattr(request.state, "principal", None)
    if not isinstance(principal, AuthenticatedPrincipal):
        raise EngineeringError(
            EngineeringErrorCode.AUTH_REQUIRED, "authenticated principal is missing"
        )
    return principal


__all__ = [
    "AuthenticatedPrincipal",
    "authenticated_actor_id",
    "authenticated_principal",
    "require_session_token",
]
