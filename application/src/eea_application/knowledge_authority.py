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


@dataclass(frozen=True, slots=True)
class FreshnessDecision:
    status: Literal["CURRENT", "STALE", "CONFLICTED"]
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
            and current_source_revision_id is not None
            and entry.source_revision_id != current_source_revision_id
        ):
            reason = (
                "source revision changed"
                if entry.source_revision_id != current_source_revision_id
                else f"evidence stale: {', '.join(str(value) for value in stale_evidence_ids)}"
            )
            decision = FreshnessDecision("STALE", reason)
            status = KnowledgeLifecycle.STALE
        else:
            decision = FreshnessDecision("CURRENT", None)
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
    "VerificationAuthorityResolver",
    "VerificationDecision",
]
