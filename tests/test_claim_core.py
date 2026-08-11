"""M3 Claim Core and FIX-02 canonical-unit acceptance tests."""

from uuid import UUID, uuid4

import pytest
from eea_application.claims import (
    ENGINEERING_VALUE_SCHEMA_REF,
    JSON_VALUE_SCHEMA_REF,
    ClaimPredicateRegistry,
    ClaimResolver,
    ClaimService,
)
from eea_core.claims import (
    ClaimConflict,
    ClaimPredicateDefinition,
    EngineeringClaim,
    EngineeringValue,
)
from eea_core.enums import (
    ClaimConflictStatus,
    ClaimConflictStrategy,
    EngineeringDimension,
    EngineeringErrorCode,
    VerificationLevel,
)
from eea_core.errors import EngineeringError
from eea_core.units import UnitNormalizationError, UnitNormalizationService
from pydantic import ValidationError


class InMemoryPredicateRepository:
    def __init__(self) -> None:
        self.items: dict[str, ClaimPredicateDefinition] = {}

    def add(self, definition: ClaimPredicateDefinition) -> ClaimPredicateDefinition:
        if definition.predicate in self.items:
            raise ValueError("duplicate predicate")
        self.items[definition.predicate] = definition
        return definition

    def get(self, predicate: str) -> ClaimPredicateDefinition | None:
        return self.items.get(predicate)


class InMemoryClaimRepository:
    def __init__(self) -> None:
        self.items: list[EngineeringClaim] = []

    def add(self, claim: EngineeringClaim) -> EngineeringClaim:
        self.items.append(claim)
        return claim

    def list_for_subject_predicate(
        self,
        *,
        project_id: UUID | None,
        subject_ref: str,
        predicate: str,
    ) -> list[EngineeringClaim]:
        return [
            claim
            for claim in self.items
            if claim.subject_ref == subject_ref
            and claim.predicate == predicate
            and (claim.project_id is None or claim.project_id == project_id)
        ]


class InMemoryConflictRepository:
    def __init__(self) -> None:
        self.items: list[ClaimConflict] = []

    def add(self, conflict: ClaimConflict) -> ClaimConflict:
        self.items.append(conflict)
        return conflict

    def list_for_claim(self, claim_id: UUID) -> list[ClaimConflict]:
        return [
            conflict
            for conflict in self.items
            if claim_id in {conflict.claim_a_id, conflict.claim_b_id}
        ]


def engineering_value(value: float, unit: str, dimension: EngineeringDimension) -> EngineeringValue:
    return EngineeringValue(unit=unit, dimension=dimension, nominal=value)


def make_claim(
    *,
    value: EngineeringValue | str | int,
    applicability: dict[str, object] | None = None,
    source_priority: int = 100,
    source_version: str | None = "1.0",
    predicate: str = "device.max-voltage",
    schema_ref: str = ENGINEERING_VALUE_SCHEMA_REF,
) -> EngineeringClaim:
    return EngineeringClaim(
        subject_ref="device:stm32g4",
        predicate=predicate,
        value_schema_ref=schema_ref,
        value=value,
        applicability=applicability or {},
        confidence=0.8,
        source_priority=source_priority,
        source_version=source_version,
    )


def build_service(
    *, strategy: ClaimConflictStrategy = ClaimConflictStrategy.SOURCE_PRIORITY
) -> tuple[ClaimService, InMemoryConflictRepository]:
    predicates = InMemoryPredicateRepository()
    registry = ClaimPredicateRegistry(predicates)
    registry.register(
        ClaimPredicateDefinition(
            predicate="device.max-voltage",
            value_schema_ref=ENGINEERING_VALUE_SCHEMA_REF,
            unit_dimension=EngineeringDimension.VOLTAGE,
            conflict_strategy=strategy,
        )
    )
    conflicts = InMemoryConflictRepository()
    return ClaimService(InMemoryClaimRepository(), conflicts, registry), conflicts


def test_fix_02_canonical_unit_conversions_and_comparisons() -> None:
    twenty_four_volts = engineering_value(24, "V", EngineeringDimension.VOLTAGE)
    twenty_four_thousand_millivolts = engineering_value(24000, "mV", EngineeringDimension.VOLTAGE)
    forty_eight_volts = engineering_value(48, "V", EngineeringDimension.VOLTAGE)
    forty_volts = engineering_value(40, "V", EngineeringDimension.VOLTAGE)
    one_kilohertz = engineering_value(1, "kHz", EngineeringDimension.FREQUENCY)
    one_thousand_hertz = engineering_value(1000, "Hz", EngineeringDimension.FREQUENCY)
    one_thousand_microseconds = engineering_value(1000, "us", EngineeringDimension.TIME)
    one_millisecond = engineering_value(1, "ms", EngineeringDimension.TIME)

    assert twenty_four_volts.canonical_unit == "V"
    assert twenty_four_volts.equivalent_to(twenty_four_thousand_millivolts)
    assert UnitNormalizationService.compare(forty_eight_volts, forty_volts, ">")
    assert one_kilohertz.equivalent_to(one_thousand_hertz)
    assert one_thousand_microseconds.equivalent_to(one_millisecond)

    with pytest.raises(UnitNormalizationError, match="Cannot compare"):
        UnitNormalizationService.compare(twenty_four_volts, one_kilohertz, ">")
    with pytest.raises(ValidationError, match="belongs to"):
        EngineeringValue(unit="mA", dimension=EngineeringDimension.VOLTAGE, nominal=1)
    with pytest.raises(ValidationError, match="derived"):
        EngineeringValue(
            unit="V",
            dimension=EngineeringDimension.VOLTAGE,
            nominal=24,
            normalized_nominal=25,
        )


def test_all_frozen_dimensions_have_a_canonical_unit() -> None:
    assert [dimension.value for dimension in EngineeringDimension] == [
        "VOLTAGE",
        "CURRENT",
        "RESISTANCE",
        "CAPACITANCE",
        "INDUCTANCE",
        "FREQUENCY",
        "TIME",
        "TEMPERATURE",
        "ANGLE",
        "ANGULAR_VELOCITY",
        "LENGTH",
        "POWER",
        "ENERGY",
        "DIMENSIONLESS",
    ]
    assert all(
        UnitNormalizationService.canonical_unit(dimension) for dimension in EngineeringDimension
    )


def test_document_verified_claim_requires_evidence() -> None:
    with pytest.raises(ValidationError, match="DOCUMENT_VERIFIED"):
        EngineeringClaim(
            subject_ref="device:test",
            predicate="device.max-voltage",
            value_schema_ref=ENGINEERING_VALUE_SCHEMA_REF,
            value=engineering_value(24, "V", EngineeringDimension.VOLTAGE),
            confidence=0.8,
            source_priority=100,
            verification_levels=[VerificationLevel.DOCUMENT_VERIFIED],
        )

    claim = EngineeringClaim(
        subject_ref="device:test",
        predicate="device.max-voltage",
        value_schema_ref=ENGINEERING_VALUE_SCHEMA_REF,
        value=engineering_value(24, "V", EngineeringDimension.VOLTAGE),
        confidence=0.8,
        source_priority=100,
        evidence_ids=[uuid4()],
        verification_levels=[VerificationLevel.DOCUMENT_VERIFIED],
    )
    assert claim.evidence_ids


def test_predicate_registry_requires_registered_matching_contract() -> None:
    service, _ = build_service()
    with pytest.raises(EngineeringError) as captured:
        service.create(
            make_claim(
                value=24,
                predicate="unknown.predicate",
                schema_ref=JSON_VALUE_SCHEMA_REF,
            )
        )
    assert captured.value.code is EngineeringErrorCode.SCHEMA_VERSION_UNSUPPORTED

    with pytest.raises(EngineeringError) as captured:
        service.create(make_claim(value=engineering_value(24, "A", EngineeringDimension.CURRENT)))
    assert captured.value.code is EngineeringErrorCode.VALIDATION_ERROR


def test_errata_priority_conflict_is_retained_and_resolved() -> None:
    service, conflicts = build_service()
    datasheet = service.create(
        make_claim(
            value=engineering_value(36, "V", EngineeringDimension.VOLTAGE),
            applicability={"package": "LQFP64", "revision": "A"},
            source_priority=100,
        )
    )
    errata = service.create(
        make_claim(
            value=engineering_value(30, "V", EngineeringDimension.VOLTAGE),
            applicability={"package": "LQFP64", "revision": "A"},
            source_priority=200,
            source_version="1.1",
        )
    )

    assert datasheet.conflicts == ()
    assert len(errata.conflicts) == 1
    conflict = errata.conflicts[0]
    assert conflict.status is ClaimConflictStatus.RESOLVED
    assert conflict.selected_claim_id == errata.claim.id
    assert conflict.overlapping_applicability == {"package": "LQFP64", "revision": "A"}
    assert conflicts.items == [conflict]


@pytest.mark.parametrize(
    "applicability",
    [
        {"package": "LQFP48", "revision": "A"},
        {"package": "LQFP64", "revision": "B"},
    ],
)
def test_package_and_revision_scopes_do_not_create_false_conflicts(
    applicability: dict[str, object],
) -> None:
    service, conflicts = build_service()
    service.create(
        make_claim(
            value=engineering_value(36, "V", EngineeringDimension.VOLTAGE),
            applicability={"package": "LQFP64", "revision": "A"},
        )
    )
    submitted = service.create(
        make_claim(
            value=engineering_value(30, "V", EngineeringDimension.VOLTAGE),
            applicability=applicability,
        )
    )

    assert submitted.conflicts == ()
    assert conflicts.items == []


def test_source_version_strategy_selects_newer_revision_and_manual_stays_open() -> None:
    service, _ = build_service(strategy=ClaimConflictStrategy.SOURCE_VERSION)
    service.create(
        make_claim(
            value=engineering_value(36, "V", EngineeringDimension.VOLTAGE),
            source_version="1.0",
        )
    )
    newer = service.create(
        make_claim(
            value=engineering_value(30, "V", EngineeringDimension.VOLTAGE),
            source_version="1.2",
        )
    )
    assert newer.conflicts[0].selected_claim_id == newer.claim.id

    resolver = ClaimResolver()
    manual_definition = ClaimPredicateDefinition(
        predicate="device.max-voltage",
        value_schema_ref=ENGINEERING_VALUE_SCHEMA_REF,
        unit_dimension=EngineeringDimension.VOLTAGE,
        conflict_strategy=ClaimConflictStrategy.MANUAL_REVIEW,
    )
    open_conflict = resolver.resolve(
        make_claim(value=engineering_value(36, "V", EngineeringDimension.VOLTAGE)),
        make_claim(value=engineering_value(30, "V", EngineeringDimension.VOLTAGE)),
        manual_definition,
    )
    assert open_conflict is not None
    assert open_conflict.status is ClaimConflictStatus.OPEN
