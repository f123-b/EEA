"""Deterministic Knowledge & Memory lifecycle and recall rules for M23."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import ClassVar
from uuid import UUID

from eea_core.entities import KnowledgeEntry
from eea_core.enums import (
    AuthorityLevel,
    KnowledgeLifecycle,
    KnowledgeScope,
    TrustLevel,
)

_TOKEN_PATTERN = re.compile(r"[a-z0-9][a-z0-9_./:+-]*", re.I)
_TRUST_SCORE = {
    TrustLevel.UNTRUSTED: 0.0,
    TrustLevel.LOW: 0.2,
    TrustLevel.MEDIUM: 0.5,
    TrustLevel.HIGH: 0.8,
    TrustLevel.TRUSTED: 1.0,
}
_AUTHORITY_SCORE = {
    AuthorityLevel.T0_OFFICIAL: 1.0,
    AuthorityLevel.T1_VENDOR: 0.9,
    AuthorityLevel.T2_MAINTAINER: 0.8,
    AuthorityLevel.T3_REVIEWED: 0.7,
    AuthorityLevel.T4_PROJECT: 0.5,
    AuthorityLevel.T5_USER: 0.4,
    AuthorityLevel.T6_AI_INFERENCE: 0.1,
}

_DEFAULT_RECALL_EXCLUDED = frozenset(
    {
        KnowledgeLifecycle.ARCHIVED,
        KnowledgeLifecycle.REJECTED,
        KnowledgeLifecycle.STALE,
        KnowledgeLifecycle.CONFLICTED,
        KnowledgeLifecycle.DEPRECATED,
    }
)


class InvalidMemoryTransition(ValueError):  # noqa: N818 - stable domain error name
    """Raised when a memory lifecycle transition is not policy-approved."""


class MemoryLifecyclePolicy:
    """Single source of truth for memory lifecycle transitions."""

    _allowed: ClassVar[dict[KnowledgeLifecycle, frozenset[KnowledgeLifecycle]]] = {
        KnowledgeLifecycle.CANDIDATE: frozenset(
            {
                KnowledgeLifecycle.ACTIVE,
                KnowledgeLifecycle.STALE,
                KnowledgeLifecycle.CONFLICTED,
                KnowledgeLifecycle.REJECTED,
                KnowledgeLifecycle.ARCHIVED,
            }
        ),
        KnowledgeLifecycle.ACTIVE: frozenset(
            {
                KnowledgeLifecycle.STALE,
                KnowledgeLifecycle.CONFLICTED,
                KnowledgeLifecycle.DEPRECATED,
                KnowledgeLifecycle.ARCHIVED,
                KnowledgeLifecycle.REJECTED,
            }
        ),
        KnowledgeLifecycle.TRUSTED: frozenset(
            {
                KnowledgeLifecycle.STALE,
                KnowledgeLifecycle.CONFLICTED,
                KnowledgeLifecycle.DEPRECATED,
                KnowledgeLifecycle.ARCHIVED,
                KnowledgeLifecycle.REJECTED,
            }
        ),
        KnowledgeLifecycle.STALE: frozenset(
            {
                KnowledgeLifecycle.ACTIVE,
                KnowledgeLifecycle.CONFLICTED,
                KnowledgeLifecycle.ARCHIVED,
                KnowledgeLifecycle.REJECTED,
            }
        ),
        KnowledgeLifecycle.CONFLICTED: frozenset(
            {
                KnowledgeLifecycle.CANDIDATE,
                KnowledgeLifecycle.ACTIVE,
                KnowledgeLifecycle.STALE,
                KnowledgeLifecycle.ARCHIVED,
            }
        ),
        KnowledgeLifecycle.DEPRECATED: frozenset({KnowledgeLifecycle.ARCHIVED}),
        KnowledgeLifecycle.ARCHIVED: frozenset(),
        KnowledgeLifecycle.REJECTED: frozenset(),
    }

    @classmethod
    def assert_transition(cls, current: KnowledgeLifecycle, target: KnowledgeLifecycle) -> None:
        if target is current:
            return
        if target not in cls._allowed.get(current, frozenset()):
            raise InvalidMemoryTransition(f"{current.value} -> {target.value} is not allowed")

    @classmethod
    def allowed_targets(cls, current: KnowledgeLifecycle) -> frozenset[KnowledgeLifecycle]:
        return cls._allowed.get(current, frozenset())


@dataclass(frozen=True, slots=True)
class RecallContext:
    """Explicit scope context required before memory can be recalled."""

    project_id: UUID
    actor_ref: str
    scope_context: tuple[KnowledgeScope, ...]
    query: str
    limit: int = 20
    task_ref: str | None = None
    organization_ref: str | None = None
    organization_ids: frozenset[str] = frozenset()
    include_non_active: bool = False


@dataclass(frozen=True, slots=True)
class RecallMatch:
    entry: KnowledgeEntry
    score: float
    matched_tokens: tuple[str, ...]
    reasons: tuple[str, ...]


def build_search_text(entry: KnowledgeEntry) -> str:
    """Build a deterministic lexical index without duplicating claim values."""

    applicability = " ".join(f"{key} {value}" for key, value in sorted(entry.applicability.items()))
    return " ".join(
        [
            entry.title,
            entry.summary,
            " ".join(entry.tags),
            applicability,
            entry.source_ref or "",
        ]
    ).lower()


def claim_memory_state(has_open_conflict: bool) -> tuple[KnowledgeLifecycle, TrustLevel]:
    """Map canonical claim conditions to a conservative memory projection."""

    if has_open_conflict:
        return KnowledgeLifecycle.CONFLICTED, TrustLevel.UNTRUSTED
    return KnowledgeLifecycle.CANDIDATE, TrustLevel.UNTRUSTED


class KnowledgeMemoryService:
    """Scope filtering, ranking, and review transitions for KnowledgeEntry."""

    def recall(self, entries: list[KnowledgeEntry], context: RecallContext) -> list[RecallMatch]:
        matches: list[RecallMatch] = []
        query_tokens = tuple(dict.fromkeys(_TOKEN_PATTERN.findall(context.query.lower())))
        for entry in entries:
            if not self._visible(entry, context):
                continue
            if entry.lifecycle in _DEFAULT_RECALL_EXCLUDED and not context.include_non_active:
                continue
            matched = tuple(token for token in query_tokens if token in build_search_text(entry))
            lexical = len(matched) / len(query_tokens) if query_tokens else 0.25
            score = (
                lexical * 0.5
                + _TRUST_SCORE[entry.trust_level] * 0.15
                + _AUTHORITY_SCORE[entry.authority_level] * 0.1
                + min(len(entry.verification_levels), 4) / 4 * 0.1
                + entry.freshness_score * 0.1
                + (0.05 if entry.project_id == context.project_id else 0.0)
            )
            if entry.lifecycle is KnowledgeLifecycle.CONFLICTED:
                score -= 0.25
            if entry.lifecycle is KnowledgeLifecycle.STALE:
                score -= 0.15
            reasons = [f"matched {len(matched)}/{len(query_tokens)} query tokens"]
            if entry.project_id == context.project_id:
                reasons.append("project-relevant")
            if entry.lifecycle is KnowledgeLifecycle.ACTIVE:
                reasons.append("active")
            if entry.freshness_score > 0:
                reasons.append("current-freshness")
            if entry.verification_levels:
                reasons.append("verified-evidence-present")
            if entry.lifecycle is KnowledgeLifecycle.CONFLICTED:
                reasons.append("conflict-penalty-applied")
            matches.append(
                RecallMatch(
                    entry=entry,
                    score=max(0.0, min(1.0, score)),
                    matched_tokens=matched,
                    reasons=tuple(reasons),
                )
            )
        matches.sort(key=lambda item: (-item.score, item.entry.title.lower(), str(item.entry.id)))
        return matches[: context.limit]

    def visible(self, entry: KnowledgeEntry, context: RecallContext) -> bool:
        """Expose the same scope predicate to detail and review endpoints."""

        return self._visible(entry, context)

    def _visible(self, entry: KnowledgeEntry, context: RecallContext) -> bool:
        if entry.scope not in context.scope_context:
            return False
        if (
            entry.scope in {KnowledgeScope.PROJECT_PRIVATE, KnowledgeScope.TASK_ONLY}
            and entry.project_id != context.project_id
        ):
            return False
        if entry.scope is KnowledgeScope.USER_PRIVATE and entry.owner_ref != context.actor_ref:
            return False
        if entry.scope is KnowledgeScope.ORGANIZATION_PRIVATE:
            organization_ids = context.organization_ids or frozenset(
                {context.organization_ref} if context.organization_ref else set()
            )
            if not entry.organization_ref or entry.organization_ref not in organization_ids:
                return False
        return not (entry.scope is KnowledgeScope.TASK_ONLY and entry.task_ref != context.task_ref)


__all__ = [
    "InvalidMemoryTransition",
    "KnowledgeMemoryService",
    "MemoryLifecyclePolicy",
    "RecallContext",
    "RecallMatch",
    "build_search_text",
    "claim_memory_state",
]
