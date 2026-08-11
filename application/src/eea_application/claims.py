"""M3 Claim Core services: registry normalization and deterministic resolution."""

import json
import re
from dataclasses import dataclass
from uuid import UUID

from eea_core.claims import (
    ClaimConflict,
    ClaimPredicateDefinition,
    EngineeringClaim,
    EngineeringValue,
)
from eea_core.enums import ClaimConflictStatus, ClaimConflictStrategy, EngineeringErrorCode
from eea_core.errors import EngineeringError
from eea_core.repositories import (
    ClaimConflictRepository,
    ClaimPredicateRepository,
    EngineeringClaimRepository,
)
from eea_core.units import UnitNormalizationError

ENGINEERING_VALUE_SCHEMA_REF = "core://engineering-value/v1"
JSON_VALUE_SCHEMA_REF = "json://value/v1"
JSON_APPLICABILITY_SCHEMA_REF = "json://applicability/v1"


class ClaimPredicateRegistry:
    """Registry that validates claim payloads before persistence or comparison."""

    def __init__(self, repository: ClaimPredicateRepository) -> None:
        self._repository = repository

    def register(self, definition: ClaimPredicateDefinition) -> ClaimPredicateDefinition:
        if definition.value_schema_ref not in {ENGINEERING_VALUE_SCHEMA_REF, JSON_VALUE_SCHEMA_REF}:
            raise EngineeringError(
                EngineeringErrorCode.SCHEMA_VERSION_UNSUPPORTED,
                "Claim predicate uses an unsupported value schema",
                details={"predicate": definition.predicate},
            )
        if definition.applicability_schema_ref not in {None, JSON_APPLICABILITY_SCHEMA_REF}:
            raise EngineeringError(
                EngineeringErrorCode.SCHEMA_VERSION_UNSUPPORTED,
                "Claim predicate uses an unsupported applicability schema",
                details={"predicate": definition.predicate},
            )
        if definition.unit_dimension is not None and (
            definition.value_schema_ref != ENGINEERING_VALUE_SCHEMA_REF
        ):
            raise EngineeringError(
                EngineeringErrorCode.VALIDATION_ERROR,
                "Unit-constrained predicates must use EngineeringValue",
                details={"predicate": definition.predicate},
            )
        return self._repository.add(definition)

    def require(self, predicate: str) -> ClaimPredicateDefinition:
        definition = self._repository.get(predicate)
        if definition is None:
            raise EngineeringError(
                EngineeringErrorCode.SCHEMA_VERSION_UNSUPPORTED,
                "Claim predicate is not registered",
                details={"predicate": predicate},
            )
        return definition

    def normalize(
        self, claim: EngineeringClaim
    ) -> tuple[EngineeringClaim, ClaimPredicateDefinition]:
        definition = self.require(claim.predicate)
        if claim.value_schema_ref != definition.value_schema_ref:
            raise EngineeringError(
                EngineeringErrorCode.SCHEMA_VERSION_UNSUPPORTED,
                "Claim value schema does not match the predicate contract",
                details={"predicate": claim.predicate},
            )
        if definition.value_schema_ref == ENGINEERING_VALUE_SCHEMA_REF:
            try:
                value = EngineeringValue.model_validate(claim.value)
            except ValueError as exc:
                raise EngineeringError(
                    EngineeringErrorCode.VALIDATION_ERROR,
                    "Claim value must be a normalized EngineeringValue",
                    details={"predicate": claim.predicate},
                ) from exc
            if (
                definition.unit_dimension is not None
                and value.dimension is not definition.unit_dimension
            ):
                raise EngineeringError(
                    EngineeringErrorCode.VALIDATION_ERROR,
                    "EngineeringValue dimension does not match the predicate contract",
                    details={
                        "predicate": claim.predicate,
                        "expected_dimension": definition.unit_dimension.value,
                        "actual_dimension": value.dimension.value,
                    },
                )
            normalized = EngineeringClaim.model_validate(
                {**claim.model_dump(), "value": value.model_dump(mode="json")}
            )
        else:
            normalized = claim
        return normalized, definition


class ClaimResolver:
    """Resolve only overlapping, incompatible claims by their registered policy."""

    name = "claim-resolver/v1"

    def resolve(
        self,
        existing: EngineeringClaim,
        incoming: EngineeringClaim,
        definition: ClaimPredicateDefinition,
    ) -> ClaimConflict | None:
        if existing.subject_ref != incoming.subject_ref or existing.predicate != incoming.predicate:
            return None
        overlap = self._overlap(existing.applicability, incoming.applicability)
        if overlap is None or self._values_equal(existing.value, incoming.value):
            return None
        selected_claim_id, resolution, reason = self._select(existing, incoming, definition)
        return ClaimConflict(
            claim_a_id=existing.id,
            claim_b_id=incoming.id,
            overlapping_applicability=overlap,
            resolver=self.name,
            resolution=resolution,
            selected_claim_id=selected_claim_id,
            reason=reason,
            status=(
                ClaimConflictStatus.RESOLVED
                if selected_claim_id is not None
                else ClaimConflictStatus.OPEN
            ),
        )

    @staticmethod
    def _values_equal(left: object, right: object) -> bool:
        if isinstance(left, EngineeringValue) and isinstance(right, EngineeringValue):
            try:
                return left.equivalent_to(right)
            except UnitNormalizationError:
                return False
        return json.dumps(left, sort_keys=True, allow_nan=False) == json.dumps(
            right, sort_keys=True, allow_nan=False
        )

    @staticmethod
    def _overlap(left: dict[str, object], right: dict[str, object]) -> dict[str, object] | None:
        overlapping: dict[str, object] = {}
        for key in left.keys() & right.keys():
            left_value = left[key]
            right_value = right[key]
            if left_value == right_value:
                overlapping[key] = left_value
                continue
            if isinstance(left_value, list) and isinstance(right_value, list):
                shared = [value for value in left_value if value in right_value]
                if shared:
                    overlapping[key] = shared
                    continue
            return None
        return overlapping

    def _select(
        self,
        existing: EngineeringClaim,
        incoming: EngineeringClaim,
        definition: ClaimPredicateDefinition,
    ) -> tuple[UUID | None, str | None, str]:
        if definition.conflict_strategy is ClaimConflictStrategy.SOURCE_PRIORITY:
            if existing.source_priority == incoming.source_priority:
                return None, None, "Claims have equal source priority and require review"
            selected = existing if existing.source_priority > incoming.source_priority else incoming
            return (
                selected.id,
                "SELECTED_BY_SOURCE_PRIORITY",
                "Selected the claim with the higher declared source priority",
            )
        if definition.conflict_strategy is ClaimConflictStrategy.SOURCE_VERSION:
            comparison = self._compare_versions(existing.source_version, incoming.source_version)
            if comparison == 0:
                return None, None, "Claims have no comparable newer source version"
            selected = existing if comparison > 0 else incoming
            return (
                selected.id,
                "SELECTED_BY_SOURCE_VERSION",
                "Selected the claim from the newer comparable source version",
            )
        return None, None, "Predicate requires explicit human conflict resolution"

    @staticmethod
    def _compare_versions(left: str | None, right: str | None) -> int:
        if left is None or right is None:
            return 0
        pattern = re.compile(r"^[0-9]+(?:\.[0-9]+)*$")
        if not pattern.fullmatch(left) or not pattern.fullmatch(right):
            return 0
        left_parts = tuple(int(part) for part in left.split("."))
        right_parts = tuple(int(part) for part in right.split("."))
        width = max(len(left_parts), len(right_parts))
        padded_left = left_parts + (0,) * (width - len(left_parts))
        padded_right = right_parts + (0,) * (width - len(right_parts))
        return (padded_left > padded_right) - (padded_left < padded_right)


@dataclass(frozen=True, slots=True)
class ClaimSubmission:
    claim: EngineeringClaim
    conflicts: tuple[ClaimConflict, ...]


class ClaimService:
    """Persist a validated Claim and retain every deterministic conflict record."""

    def __init__(
        self,
        claim_repository: EngineeringClaimRepository,
        conflict_repository: ClaimConflictRepository,
        predicate_registry: ClaimPredicateRegistry,
        resolver: ClaimResolver | None = None,
    ) -> None:
        self._claim_repository = claim_repository
        self._conflict_repository = conflict_repository
        self._predicate_registry = predicate_registry
        self._resolver = resolver or ClaimResolver()

    def create(self, claim: EngineeringClaim) -> ClaimSubmission:
        normalized, definition = self._predicate_registry.normalize(claim)
        existing = self._claim_repository.list_for_subject_predicate(
            project_id=normalized.project_id,
            subject_ref=normalized.subject_ref,
            predicate=normalized.predicate,
        )
        saved = self._claim_repository.add(normalized)
        conflicts = tuple(
            self._conflict_repository.add(conflict)
            for current in existing
            if (conflict := self._resolver.resolve(current, saved, definition)) is not None
        )
        return ClaimSubmission(claim=saved, conflicts=conflicts)
