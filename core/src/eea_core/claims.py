"""M3 engineering values, claims, predicate contracts, and conflicts."""

import json
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from eea_core.entities import EntityBase
from eea_core.enums import (
    ClaimConflictStatus,
    ClaimConflictStrategy,
    ClaimConflictType,
    ClaimLifecycle,
    EngineeringDimension,
    VerificationLevel,
)
from eea_core.units import UnitNormalizationError, UnitNormalizationService

type JsonScalar = str | int | float | bool | None
type JsonValue = JsonScalar | list[object] | dict[str, object]


class EngineeringValue(BaseModel):
    """A display value plus its immutable canonical-unit representation."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    unit: str = Field(min_length=1, max_length=30)
    dimension: EngineeringDimension
    canonical_unit: str | None = Field(default=None, max_length=30)
    nominal: float | None = None
    minimum: float | None = None
    typical: float | None = None
    maximum: float | None = None
    normalized_nominal: float | None = None
    normalized_minimum: float | None = None
    normalized_typical: float | None = None
    normalized_maximum: float | None = None
    tolerance_percent: float | None = Field(default=None, ge=0)
    condition: dict[str, object] = Field(default_factory=dict)
    evidence_ids: list[UUID] = Field(default_factory=list)

    @model_validator(mode="after")
    def normalize_all_numeric_values(self) -> "EngineeringValue":
        if all(value is None for value in (self.nominal, self.minimum, self.typical, self.maximum)):
            raise ValueError("an EngineeringValue requires at least one numeric value")
        try:
            canonical_unit = UnitNormalizationService.canonical_unit(self.dimension)
            normalized = {
                "normalized_nominal": self._normalize(self.nominal),
                "normalized_minimum": self._normalize(self.minimum),
                "normalized_typical": self._normalize(self.typical),
                "normalized_maximum": self._normalize(self.maximum),
            }
        except UnitNormalizationError as exc:
            raise ValueError(str(exc)) from None
        if self.canonical_unit is not None and self.canonical_unit != canonical_unit:
            raise ValueError("canonical_unit does not match the frozen dimension catalog")
        for field_name, value in normalized.items():
            supplied = getattr(self, field_name)
            if supplied is not None and value is not None and abs(supplied - value) > 1e-12:
                raise ValueError(f"{field_name} must be derived from unit normalization")
            object.__setattr__(self, field_name, value)
        object.__setattr__(self, "canonical_unit", canonical_unit)
        return self

    def _normalize(self, value: float | None) -> float | None:
        if value is None:
            return None
        return UnitNormalizationService.normalize(value, self.unit, self.dimension)

    def require_normalized_nominal(self) -> float:
        if self.normalized_nominal is None:
            raise ValueError("nominal value is required for comparison")
        return self.normalized_nominal

    def equivalent_to(self, other: "EngineeringValue") -> bool:
        return UnitNormalizationService.compare(self, other, "==")


class ClaimPredicateDefinition(EntityBase):
    """A registered semantic contract for one claim predicate."""

    predicate: str = Field(min_length=1, max_length=200, pattern=r"^[a-z][a-z0-9_.-]*$")
    value_schema_ref: str = Field(min_length=1, max_length=200)
    applicability_schema_ref: str | None = Field(default=None, max_length=200)
    unit_dimension: EngineeringDimension | None = None
    conflict_strategy: ClaimConflictStrategy = ClaimConflictStrategy.SOURCE_PRIORITY
    validator_ref: str | None = Field(default=None, max_length=200)


class EngineeringClaim(EntityBase):
    """An atomic, evidence-aware engineering fact; never silently overwritten."""

    project_id: UUID | None = None
    subject_ref: str = Field(min_length=1, max_length=500)
    predicate: str = Field(min_length=1, max_length=200, pattern=r"^[a-z][a-z0-9_.-]*$")
    value_schema_ref: str = Field(default="json://value/v1", min_length=1, max_length=200)
    value: EngineeringValue | JsonValue
    applicability: dict[str, object] = Field(default_factory=dict)
    evidence_ids: list[UUID] = Field(default_factory=list)
    verification_levels: list[VerificationLevel] = Field(default_factory=list)
    confidence: float = Field(ge=0, le=1)
    source_priority: int = Field(ge=0, le=1000)
    source_version: str | None = Field(default=None, max_length=200)
    lifecycle: ClaimLifecycle = ClaimLifecycle.CANDIDATE

    @field_validator("value")
    @classmethod
    def value_must_be_json_serializable(
        cls, value: EngineeringValue | JsonValue
    ) -> EngineeringValue | JsonValue:
        if isinstance(value, EngineeringValue):
            return value
        try:
            json.dumps(value, allow_nan=False)
        except (TypeError, ValueError):
            raise ValueError("claim value must be JSON serializable") from None
        return value

    @model_validator(mode="after")
    def document_verified_claims_require_evidence(self) -> "EngineeringClaim":
        if (
            VerificationLevel.DOCUMENT_VERIFIED in self.verification_levels
            and not self.evidence_ids
        ):
            raise ValueError("DOCUMENT_VERIFIED claims require at least one evidence ID")
        if len(set(self.verification_levels)) != len(self.verification_levels):
            raise ValueError("verification levels must not contain duplicates")
        return self


class ClaimConflict(EntityBase):
    """Persistent record of incompatible claims with overlapping applicability."""

    claim_a_id: UUID
    claim_b_id: UUID
    conflict_type: ClaimConflictType = ClaimConflictType.VALUE_MISMATCH
    overlapping_applicability: dict[str, object] = Field(default_factory=dict)
    resolver: str = Field(min_length=1, max_length=100)
    resolution: str | None = Field(default=None, max_length=4000)
    selected_claim_id: UUID | None = None
    reason: str = Field(min_length=1, max_length=4000)
    status: ClaimConflictStatus = ClaimConflictStatus.OPEN

    @model_validator(mode="after")
    def resolved_conflicts_require_a_selected_claim(self) -> "ClaimConflict":
        if self.status is ClaimConflictStatus.RESOLVED and self.selected_claim_id is None:
            raise ValueError("resolved conflicts require a selected claim")
        return self
