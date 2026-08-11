"""SQLAlchemy adapters for the M3 Claim Core persistence ports."""

from typing import cast
from uuid import UUID

from eea_core.claims import (
    ClaimConflict,
    ClaimPredicateDefinition,
    EngineeringClaim,
    EngineeringValue,
    JsonValue,
)
from eea_core.enums import (
    ClaimConflictStatus,
    ClaimConflictStrategy,
    ClaimConflictType,
    ClaimLifecycle,
    EngineeringDimension,
    VerificationLevel,
)
from sqlalchemy import desc, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from eea_backend.models import (
    ClaimConflictRecord,
    ClaimPredicateDefinitionRecord,
    EngineeringClaimRecord,
)

ENGINEERING_VALUE_SCHEMA_REF = "core://engineering-value/v1"


def _to_predicate(record: ClaimPredicateDefinitionRecord) -> ClaimPredicateDefinition:
    return ClaimPredicateDefinition(
        id=UUID(record.id),
        schema_version=record.schema_version,
        revision=record.revision,
        created_at=record.created_at,
        updated_at=record.updated_at,
        metadata=record.entity_metadata,
        predicate=record.predicate,
        value_schema_ref=record.value_schema_ref,
        applicability_schema_ref=record.applicability_schema_ref,
        unit_dimension=EngineeringDimension(record.unit_dimension)
        if record.unit_dimension
        else None,
        conflict_strategy=ClaimConflictStrategy(record.conflict_strategy),
        validator_ref=record.validator_ref,
    )


class SqlAlchemyClaimPredicateRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, definition: ClaimPredicateDefinition) -> ClaimPredicateDefinition:
        record = ClaimPredicateDefinitionRecord(
            id=str(definition.id),
            schema_version=definition.schema_version,
            revision=definition.revision,
            created_at=definition.created_at,
            updated_at=definition.updated_at,
            entity_metadata=definition.metadata,
            predicate=definition.predicate,
            value_schema_ref=definition.value_schema_ref,
            applicability_schema_ref=definition.applicability_schema_ref,
            unit_dimension=definition.unit_dimension.value if definition.unit_dimension else None,
            conflict_strategy=definition.conflict_strategy.value,
            validator_ref=definition.validator_ref,
        )
        self._session.add(record)
        try:
            self._session.commit()
        except IntegrityError:
            self._session.rollback()
            raise ValueError(
                "Claim predicate is already registered for schema version: "
                f"{definition.predicate}@{definition.schema_version}"
            ) from None
        self._session.refresh(record)
        return _to_predicate(record)

    def get(self, predicate: str) -> ClaimPredicateDefinition | None:
        statement = (
            select(ClaimPredicateDefinitionRecord)
            .where(ClaimPredicateDefinitionRecord.predicate == predicate)
            .order_by(
                desc(ClaimPredicateDefinitionRecord.created_at),
                desc(ClaimPredicateDefinitionRecord.schema_version),
            )
        )
        record = self._session.scalar(statement.limit(1))
        return _to_predicate(record) if record else None


def _value_from_record(record: EngineeringClaimRecord) -> EngineeringValue | JsonValue:
    if record.value_schema_ref == ENGINEERING_VALUE_SCHEMA_REF:
        return EngineeringValue.model_validate(record.value_json)
    return cast(JsonValue, record.value_json)


def _to_claim(record: EngineeringClaimRecord) -> EngineeringClaim:
    return EngineeringClaim(
        id=UUID(record.id),
        schema_version=record.schema_version,
        revision=record.revision,
        created_at=record.created_at,
        updated_at=record.updated_at,
        metadata=record.entity_metadata,
        project_id=UUID(record.project_id) if record.project_id else None,
        subject_ref=record.subject_ref,
        predicate=record.predicate,
        value_schema_ref=record.value_schema_ref,
        value=_value_from_record(record),
        applicability=record.applicability,
        evidence_ids=[UUID(value) for value in record.evidence_ids],
        verification_levels=[VerificationLevel(value) for value in record.verification_levels],
        confidence=record.confidence,
        source_priority=record.source_priority,
        source_version=record.source_version,
        lifecycle=ClaimLifecycle(record.lifecycle),
    )


class SqlAlchemyEngineeringClaimRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, claim: EngineeringClaim) -> EngineeringClaim:
        value = (
            claim.value.model_dump(mode="json")
            if isinstance(claim.value, EngineeringValue)
            else claim.value
        )
        record = EngineeringClaimRecord(
            id=str(claim.id),
            schema_version=claim.schema_version,
            revision=claim.revision,
            created_at=claim.created_at,
            updated_at=claim.updated_at,
            entity_metadata=claim.metadata,
            project_id=str(claim.project_id) if claim.project_id else None,
            subject_ref=claim.subject_ref,
            predicate=claim.predicate,
            value_schema_ref=claim.value_schema_ref,
            value_json=value,
            applicability=claim.applicability,
            evidence_ids=[str(value) for value in claim.evidence_ids],
            verification_levels=[value.value for value in claim.verification_levels],
            confidence=claim.confidence,
            source_priority=claim.source_priority,
            source_version=claim.source_version,
            lifecycle=claim.lifecycle.value,
        )
        self._session.add(record)
        self._session.commit()
        self._session.refresh(record)
        return _to_claim(record)

    def list_for_subject_predicate(
        self,
        *,
        project_id: UUID | None,
        subject_ref: str,
        predicate: str,
    ) -> list[EngineeringClaim]:
        statement = select(EngineeringClaimRecord).where(
            EngineeringClaimRecord.subject_ref == subject_ref,
            EngineeringClaimRecord.predicate == predicate,
        )
        if project_id is None:
            statement = statement.where(EngineeringClaimRecord.project_id.is_(None))
        else:
            statement = statement.where(
                or_(
                    EngineeringClaimRecord.project_id == str(project_id),
                    EngineeringClaimRecord.project_id.is_(None),
                )
            )
        statement = statement.order_by(EngineeringClaimRecord.created_at, EngineeringClaimRecord.id)
        return [_to_claim(record) for record in self._session.scalars(statement)]


def _to_conflict(record: ClaimConflictRecord) -> ClaimConflict:
    return ClaimConflict(
        id=UUID(record.id),
        schema_version=record.schema_version,
        revision=record.revision,
        created_at=record.created_at,
        updated_at=record.updated_at,
        metadata=record.entity_metadata,
        claim_a_id=UUID(record.claim_a_id),
        claim_b_id=UUID(record.claim_b_id),
        conflict_type=ClaimConflictType(record.conflict_type),
        overlapping_applicability=record.overlapping_applicability,
        resolver=record.resolver,
        resolution=record.resolution,
        selected_claim_id=UUID(record.selected_claim_id) if record.selected_claim_id else None,
        reason=record.reason,
        status=ClaimConflictStatus(record.status),
    )


class SqlAlchemyClaimConflictRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, conflict: ClaimConflict) -> ClaimConflict:
        record = ClaimConflictRecord(
            id=str(conflict.id),
            schema_version=conflict.schema_version,
            revision=conflict.revision,
            created_at=conflict.created_at,
            updated_at=conflict.updated_at,
            entity_metadata=conflict.metadata,
            claim_a_id=str(conflict.claim_a_id),
            claim_b_id=str(conflict.claim_b_id),
            conflict_type=conflict.conflict_type.value,
            overlapping_applicability=conflict.overlapping_applicability,
            resolver=conflict.resolver,
            resolution=conflict.resolution,
            selected_claim_id=(
                str(conflict.selected_claim_id) if conflict.selected_claim_id else None
            ),
            reason=conflict.reason,
            status=conflict.status.value,
        )
        self._session.add(record)
        self._session.commit()
        self._session.refresh(record)
        return _to_conflict(record)

    def list_for_claim(self, claim_id: UUID) -> list[ClaimConflict]:
        statement = (
            select(ClaimConflictRecord)
            .where(
                or_(
                    ClaimConflictRecord.claim_a_id == str(claim_id),
                    ClaimConflictRecord.claim_b_id == str(claim_id),
                )
            )
            .order_by(ClaimConflictRecord.created_at, ClaimConflictRecord.id)
        )
        return [_to_conflict(record) for record in self._session.scalars(statement)]
