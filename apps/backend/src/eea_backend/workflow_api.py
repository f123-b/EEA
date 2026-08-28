"""Generic workflow descriptor API used by the desktop renderer."""

from __future__ import annotations

from fastapi import APIRouter, Request

from eea_backend.schemas import ApiEnvelope
from eea_backend.workflow_descriptor import workflow_descriptor

router = APIRouter()


@router.get(
    "/workflows/descriptor",
    response_model=ApiEnvelope[dict[str, object]],
    tags=["workflow"],
)
def get_workflow_descriptor(request: Request) -> ApiEnvelope[dict[str, object]]:
    """Return capabilities and dependencies; benchmark payloads stay fixture-only."""

    return ApiEnvelope(data=workflow_descriptor(), request_id=str(request.state.request_id))


__all__ = ["router"]
