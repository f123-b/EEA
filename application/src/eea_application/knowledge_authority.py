"""Backend-owned authority and freshness decisions for knowledge projections.

Knowledge is deliberately a projection.  This module contains the small,
deterministic decision functions that prevent a caller from promoting a
projection merely by naming a verification level in an HTTP request.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal
from uuid import UUID

from eea_core.entities import KnowledgeEntry
from eea_core.enums import (
    AuthorityLevel,
    EvidenceType,
    KnowledgeLifecycle,
    TrustLevel,
    VerificationLevel,
)


@dataclass(frozen=True, slots=True)
class EvidenceContext:
    """The verified, backend-loaded facts about one evidence record."""

    evidence_id: UUID
    project_id: UUID | None
    evidence_type: EvidenceType
    locator: dict[str, object]
    source_revision_id: UUID | None = None
    producer: str | None = None
    producer_version: str | None = None
    recorded_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class VerificationDecision:
    allowed: bool
    verification_levels: tuple[VerificationLevel, ...]
    trust_level: TrustLevel
    authority_level: AuthorityLevel
    evidence_ids: tuple[UUID, ...]
    reason: str


class VerificationAuthorityResolver:
    """Resolve review authority from backend-loaded evidence only."""

    def resolve(
        self,
        entry: KnowledgeEntry,
        requested_action: Literal["ACCEPT", "VERIFY", "RESOLVE_CONFLICT"],
        requested_level: VerificationLevel | None,
        evidence_context: tuple[EvidenceContext, ...],
        *,
        current_source_revision_id: UUID | None = None,
        conflict_open: bool = False,
        strict_provenance: bool = False,
    ) -> VerificationDecision:
        if requested_action == "ACCEPT":
            return VerificationDecision(
                allowed=True,
                verification_levels=(VerificationLevel.USER_CONFIRMED,),
                trust_level=TrustLevel.MEDIUM,
                authority_level=AuthorityLevel.T5_USER,
                evidence_ids=(),
                reason="explicit human review; no tool or hardware authority granted",
            )

        if requested_action == "RESOLVE_CONFLICT":
            if conflict_open:
                return self._blocked("canonical claim conflict is still open")
            return VerificationDecision(
                allowed=True,
                verification_levels=(),
                trust_level=TrustLevel.UNTRUSTED,
                authority_level=AuthorityLevel.T3_REVIEWED,
                evidence_ids=(),
                reason="conflict closure requires revalidation before trust is restored",
            )

        if requested_level is None:
            return self._blocked("verification level must be selected for VERIFY")
        if requested_level is VerificationLevel.USER_CONFIRMED:
            return self._blocked("USER_CONFIRMED is produced by ACCEPT, not VERIFY")
        if conflict_open:
            return self._blocked("open canonical claim conflict blocks verification")
        if (
            entry.source_revision_id is not None
            and current_source_revision_id is not None
            and entry.source_revision_id != current_source_revision_id
        ):
            return self._blocked("source revision is stale")

        eligible = tuple(
            evidence
            for evidence in evidence_context
            if self._evidence_is_project_scoped(entry, evidence)
            and self._evidence_is_current(entry, evidence, current_source_revision_id)
            and self._evidence_has_provenance(evidence, strict=strict_provenance)
            and self._supports(requested_level, evidence)
        )
        if not eligible:
            return self._blocked(f"no current backend evidence authorizes {requested_level.value}")
        authority = (
            AuthorityLevel.T4_PROJECT
            if requested_level is VerificationLevel.IMPORT_VERIFIED
            else AuthorityLevel.T3_REVIEWED
        )
        return VerificationDecision(
            allowed=True,
            verification_levels=(requested_level,),
            trust_level=TrustLevel.HIGH,
            authority_level=authority,
            evidence_ids=tuple(item.evidence_id for item in eligible),
            reason=f"authorized by {len(eligible)} current backend evidence record(s)",
        )

    @staticmethod
    def _blocked(reason: str) -> VerificationDecision:
        return VerificationDecision(
            allowed=False,
            verification_levels=(),
            trust_level=TrustLevel.UNTRUSTED,
            authority_level=AuthorityLevel.T6_AI_INFERENCE,
            evidence_ids=(),
            reason=reason,
        )

    @staticmethod
    def _evidence_is_project_scoped(entry: KnowledgeEntry, evidence: EvidenceContext) -> bool:
        return evidence.project_id is None or evidence.project_id == entry.project_id

    @staticmethod
    def _evidence_is_current(
        entry: KnowledgeEntry,
        evidence: EvidenceContext,
        current_source_revision_id: UUID | None,
    ) -> bool:
        locator = evidence.locator
        if locator.get("valid") is False or locator.get("stale") is True:
            return False
        if str(locator.get("status", "PASS")).upper() in {"STALE", "INVALID", "FAIL"}:
            return False
        evidence_source = locator.get("source_revision_id")
        if (
            evidence_source is not None
            and entry.source_revision_id is not None
            and str(evidence_source) != str(entry.source_revision_id)
        ):
            return False
        return not (
            current_source_revision_id is not None
            and evidence.source_revision_id is not None
            and evidence.source_revision_id != current_source_revision_id
        )

    @staticmethod
    def _supports(level: VerificationLevel, evidence: EvidenceContext) -> bool:
        locator = evidence.locator
        if level is VerificationLevel.DOCUMENT_VERIFIED:
            return (
                evidence.evidence_type is EvidenceType.DOCUMENT
                and str(locator.get("parse_status", "PARSED")).upper() == "PARSED"
            )
        if level is VerificationLevel.TOOL_VERIFIED:
            return (
                evidence.evidence_type in {EvidenceType.TOOL, EvidenceType.RULE}
                and str(locator.get("status", "PASS")).upper() == "PASS"
            )
        if level is VerificationLevel.HARDWARE_VERIFIED:
            return (
                evidence.evidence_type is EvidenceType.HARDWARE_TEST
                and str(locator.get("status", "PASS")).upper() == "PASS"
                and bool(locator.get("hardware_identity"))
                and bool(locator.get("probe_identity"))
                and bool(locator.get("commissioning_session_id"))
            )
        if level is VerificationLevel.IMPORT_VERIFIED:
            return evidence.evidence_type is EvidenceType.IMPORTED_PROJECT and bool(
                locator.get("import_session_id")
            )
        return False

    @staticmethod
    def _evidence_has_provenance(evidence: EvidenceContext, *, strict: bool) -> bool:
        """Require an auditable producer chain for trust-bearing verification.

        The non-strict mode keeps the pure resolver compatible with historical
        in-memory callers.  HTTP/application write paths always use strict
        mode, so persisted trust cannot be created from a partial assertion.
        """

        if not strict:
            return True
        locator = evidence.locator
        producer = evidence.producer or locator.get("producer")
        producer_version = evidence.producer_version or locator.get("producer_version")
        timestamp = evidence.recorded_at or locator.get("timestamp")
        source_revision = evidence.source_revision_id or _uuid_from_value(
            locator.get("source_revision_id")
        )
        if not producer or not producer_version or not timestamp or source_revision is None:
            return False
        if evidence.evidence_type is EvidenceType.HARDWARE_TEST:
            return bool(
                locator.get("hardware_identity")
                and locator.get("probe_identity")
                and locator.get("commissioning_session_id")
                and locator.get("hardware_configuration")
                and locator.get("measurement")
            )
        return True


def _uuid_from_value(value: object) -> UUID | None:
    if value is None:
        return None
    try:
        return UUID(str(value))
    except (TypeError, ValueError):
        return None


@dataclass(frozen=True, slots=True)
class TrustDecision:
    """Backend-derived trust projection for one memory entry."""

    authority_level: AuthorityLevel
    trust_level: TrustLevel
    verification_levels: tuple[VerificationLevel, ...]
    freshness_score: float
    freshness_status: Literal["CURRENT", "STALE", "CONFLICTED", "UNKNOWN"]


class TrustDerivationService:
    """Derive trust from canonical state, verification evidence and freshness."""

    def derive(
        self,
        entry: KnowledgeEntry,
        evidence_context: tuple[EvidenceContext, ...],
        *,
        freshness_status: Literal["CURRENT", "STALE", "CONFLICTED", "UNKNOWN"],
        conflict_open: bool = False,
    ) -> TrustDecision:
        if conflict_open or freshness_status == "CONFLICTED":
            return TrustDecision(
                authority_level=AuthorityLevel.T6_AI_INFERENCE,
                trust_level=TrustLevel.UNTRUSTED,
                verification_levels=(),
                freshness_score=0.0,
                freshness_status="CONFLICTED",
            )
        if freshness_status == "STALE":
            return TrustDecision(
                authority_level=AuthorityLevel.T6_AI_INFERENCE,
                trust_level=TrustLevel.UNTRUSTED,
                verification_levels=tuple(entry.verification_levels),
                freshness_score=0.0,
                freshness_status="STALE",
            )
        if not evidence_context and not entry.verification_levels:
            return TrustDecision(
                authority_level=entry.authority_level,
                trust_level=TrustLevel.UNTRUSTED,
                verification_levels=(),
                freshness_score=0.0,
                freshness_status="UNKNOWN",
            )
        return TrustDecision(
            authority_level=entry.authority_level,
            trust_level=entry.trust_level,
            verification_levels=tuple(entry.verification_levels),
            freshness_score=entry.freshness_score,
            freshness_status=freshness_status,
        )


@dataclass(frozen=True, slots=True)
class FreshnessDecision:
    status: Literal["CURRENT", "STALE", "CONFLICTED", "UNKNOWN"]
    reason: str | None


class KnowledgeFreshnessService:
    """Project canonical dependency reconciliation for memory projections."""

    def reconcile(
        self,
        entry: KnowledgeEntry,
        *,
        current_source_revision_id: UUID | None,
        conflict_open: bool,
        stale_evidence_ids: tuple[UUID, ...] = (),
    ) -> tuple[KnowledgeEntry, FreshnessDecision]:
        if conflict_open:
            decision = FreshnessDecision("CONFLICTED", "an active canonical claim conflict exists")
            status = KnowledgeLifecycle.CONFLICTED
        elif stale_evidence_ids or (
            entry.source_revision_id is not None
            and entry.source_revision_id != current_source_revision_id
        ):
            reason = (
                "source revision changed"
                if entry.source_revision_id != current_source_revision_id
                else f"evidence stale: {', '.join(str(value) for value in stale_evidence_ids)}"
            )
            decision = FreshnessDecision("STALE", reason)
            status = KnowledgeLifecycle.STALE
        elif entry.source_revision_id is None and not entry.evidence_ids:
            return entry, FreshnessDecision("UNKNOWN", "no canonical freshness anchor is attached")
        else:
            decision = FreshnessDecision("CURRENT", None)
            return entry, decision

        if (
            entry.lifecycle is status
            and entry.trust_level is TrustLevel.UNTRUSTED
            and entry.freshness_score == 0.0
        ):
            return entry, decision

        updated = entry.model_copy(
            update={
                "revision": entry.revision + 1,
                "updated_at": datetime.now(entry.updated_at.tzinfo),
                "lifecycle": status,
                "trust_level": TrustLevel.UNTRUSTED,
                "freshness_score": 0.0,
            }
        )
        return updated, decision


__all__ = [
    "EvidenceContext",
    "FreshnessDecision",
    "KnowledgeFreshnessService",
    "TrustDecision",
    "TrustDerivationService",
    "VerificationAuthorityResolver",
    "VerificationDecision",
]
