"""M0 API response schemas."""

from typing import Literal

from pydantic import BaseModel, ConfigDict


class ApiEnvelope[DataT](BaseModel):
    """Successful response envelope required by the V1 API contract."""

    model_config = ConfigDict(frozen=True)

    success: Literal[True] = True
    data: DataT
    request_id: str


class VersionData(BaseModel):
    """Version and compatibility metadata."""

    product: str
    version: str
    api_version: str
    milestone: str


class HealthResponse(BaseModel):
    """Process and database health response."""

    status: Literal["ok"]
    version: str
    database: Literal["ok"]
