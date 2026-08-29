"""M24A Engineering Planning Copilot application boundary.

This module is intentionally side-effect free.  Providers return structured
proposals; the application validates targets, authority, completeness and
the M24A no-execution policy before a backend adapter persists anything.
"""

# Deterministic provider fixtures intentionally keep each plan field readable
# beside its evidence-bearing value; the long prose literals are reviewed as
# structured content rather than production algorithmic code.
# ruff: noqa: E501

from __future__ import annotations

from collections.abc import Mapping, Sequence
from contextlib import suppress
from dataclasses import dataclass
from typing import Protocol
from uuid import UUID, uuid4

from eea_core.enums import EngineeringErrorCode
from eea_core.errors import EngineeringError
from eea_core.m24a_planning import (
    AcceptanceCriterionMapping,
    ContextAuthority,
    ContextFreshness,
    ContextItem,
    ContextTrust,
    EngineeringAssumption,
    EngineeringPlan,
    EngineeringPlanStatus,
    EngineeringPlanStep,
    EngineeringRequirement,
    EngineeringRisk,
    EngineeringRiskCategory,
    EngineeringRiskLikelihood,
    EngineeringRiskSeverity,
    EngineeringUnknown,
    PlanningActionType,
    PlanningContextSnapshot,
    PlanningTargetType,
    PlanVerification,
    ProposedChangeStatus,
    ProposedEngineeringChange,
)
from pydantic import BaseModel, ConfigDict, Field

PLANNING_POLICY_VERSION = "m24a-planning-policy-1"
PLANNING_PROMPT_TEMPLATE_VERSION = "m24a-planning-prompt-1"
PLANNING_PROVIDER_VERSION = "deterministic-m24a-1"


class PlanningModelOutput(BaseModel):
    """Provider-owned structured output; server identity fields are absent."""

    model_config = ConfigDict(extra="forbid")

    summary: str = Field(min_length=1, max_length=12_000)
    assumptions: list[EngineeringAssumption] = Field(default_factory=list)
    unknowns: list[EngineeringUnknown] = Field(default_factory=list)
    risks: list[EngineeringRisk] = Field(default_factory=list)
    steps: list[EngineeringPlanStep] = Field(default_factory=list)
    proposed_changes: list[ProposedEngineeringChange] = Field(default_factory=list)
    affected_components: list[str] = Field(default_factory=list)
    evidence_refs: list[UUID] = Field(default_factory=list)
    memory_refs: list[UUID] = Field(default_factory=list)
    acceptance_criteria_mapping: list[AcceptanceCriterionMapping] = Field(default_factory=list)
    verification_plans: list[PlanVerification] = Field(default_factory=list)


class PlanningModelProvider(Protocol):
    """Provider-neutral M24A boundary."""

    name: str
    version: str

    def generate_plan(
        self,
        requirement: EngineeringRequirement,
        context: PlanningContextSnapshot,
        constraints: Mapping[str, object],
    ) -> PlanningModelOutput | Mapping[str, object]:
        """Return only a structured proposal; never execute an action."""


@dataclass(frozen=True, slots=True)
class PlanningValidation:
    valid: bool
    issues: tuple[str, ...] = ()
    quality_issues: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class PlanningResult:
    plan: EngineeringPlan
    context: PlanningContextSnapshot
    validation: PlanningValidation


def _mapping_value(value: object) -> Mapping[str, object]:
    return value if isinstance(value, Mapping) else {}


def _text(value: object) -> str:
    return value if isinstance(value, str) else ""


def _serialize(value: object) -> str:
    if isinstance(value, Mapping):
        return " ".join(f"{key} {_serialize(item)}" for key, item in value.items())
    if isinstance(value, (list, tuple, set, frozenset)):
        return " ".join(_serialize(item) for item in value)
    return str(value)


class EngineeringContextAssembler:
    """Select bounded context while preserving authority and freshness."""

    max_selected = 120
    max_excluded = 120

    def assemble(
        self,
        requirement: EngineeringRequirement,
        *,
        source_revision_id: UUID | None,
        source_revision: Mapping[str, object] | None = None,
        claims: Sequence[Mapping[str, object]] = (),
        hardware: Sequence[Mapping[str, object]] = (),
        protocols: Sequence[Mapping[str, object]] = (),
        firmware: Sequence[Mapping[str, object]] = (),
        dependencies: Sequence[Mapping[str, object]] = (),
        issues: Sequence[Mapping[str, object]] = (),
        builds: Sequence[Mapping[str, object]] = (),
        static_analysis: Sequence[Mapping[str, object]] = (),
        erc: Sequence[Mapping[str, object]] = (),
        test_runs: Sequence[Mapping[str, object]] = (),
        evidence: Sequence[Mapping[str, object]] = (),
        memories: Sequence[Mapping[str, object]] = (),
    ) -> PlanningContextSnapshot:
        query = " ".join(
            [requirement.title, requirement.description, *requirement.constraints]
        ).lower()
        selected: list[ContextItem] = []
        excluded: list[ContextItem] = []
        reasons: dict[str, str] = {}
        claim_revisions: dict[str, int] = {}
        evidence_revisions: dict[str, int] = {}
        selected_memory_refs: list[UUID] = []
        selected_evidence_refs: list[UUID] = []

        def add(item: ContextItem, *, score: int, selection_reason: str) -> None:
            if item.canonical_ref not in reasons:
                reasons[item.canonical_ref] = selection_reason
            if score > 0 or item.authority is ContextAuthority.USER_REQUIREMENT:
                if len(selected) < self.max_selected:
                    selected.append(item)
            elif len(excluded) < self.max_excluded:
                excluded.append(
                    item.model_copy(
                        update={
                            "reason": selection_reason or "outside deterministic context budget"
                        }
                    )
                )

        requirement_item = ContextItem(
            kind="Requirement",
            canonical_ref=f"EngineeringRequirement:{requirement.id}",
            value=requirement.model_dump(mode="json"),
            authority=ContextAuthority.USER_REQUIREMENT,
            trust=ContextTrust.REVIEWED,
            freshness=ContextFreshness.CURRENT,
            reason="explicit user requirement",
        )
        add(requirement_item, score=10_000, selection_reason="explicit user requirement")

        if source_revision is not None and source_revision_id is not None:
            add(
                ContextItem(
                    kind="SourceRevision",
                    canonical_ref=f"SourceRevision:{source_revision_id}",
                    value=dict(source_revision),
                    authority=ContextAuthority.CANONICAL,
                    trust=ContextTrust.TRUSTED,
                    freshness=ContextFreshness.CURRENT,
                    source_revision_ref=source_revision_id,
                    reason="current project source revision",
                ),
                score=100,
                selection_reason="current source revision is required for planning",
            )
            manifest = _mapping_value(source_revision.get("file_manifest"))
            for path in sorted(str(value) for value in manifest):
                score = self._relevance(path, query)
                add(
                    ContextItem(
                        kind="SourceFile",
                        canonical_ref=f"SourceFile:{path}",
                        value={"path": path, "content_is_untrusted": True},
                        authority=ContextAuthority.UNTRUSTED_SOURCE,
                        trust=ContextTrust.UNTRUSTED,
                        freshness=ContextFreshness.CURRENT,
                        source_revision_ref=source_revision_id,
                        reason="source path is data, never an instruction",
                    ),
                    score=score,
                    selection_reason="filename relevance to requirement"
                    if score
                    else "not relevant",
                )
        else:
            excluded.append(
                ContextItem(
                    kind="SourceRevision",
                    canonical_ref="SourceRevision:UNKNOWN",
                    value=None,
                    authority=ContextAuthority.CANONICAL,
                    trust=ContextTrust.UNKNOWN,
                    freshness=ContextFreshness.UNKNOWN,
                    reason="no project SourceRevision is available",
                )
            )

        def add_records(
            kind: str,
            values: Sequence[Mapping[str, object]],
            *,
            authority: ContextAuthority = ContextAuthority.CANONICAL,
            default_trust: ContextTrust = ContextTrust.TRUSTED,
            revision_store: dict[str, int] | None = None,
        ) -> None:
            for index, record in enumerate(values):
                record_id = str(record.get("id", index))
                canonical_ref = str(record.get("canonical_ref", f"{kind}:{record_id}"))
                freshness = str(record.get("freshness", "CURRENT"))
                trust = str(record.get("trust", default_trust.value))
                try:
                    freshness_value = ContextFreshness(freshness)
                except ValueError:
                    freshness_value = ContextFreshness.UNKNOWN
                try:
                    trust_value = ContextTrust(trust)
                except ValueError:
                    trust_value = ContextTrust.UNKNOWN
                item = ContextItem(
                    kind=kind,
                    canonical_ref=canonical_ref,
                    value=dict(record),
                    authority=authority,
                    trust=trust_value,
                    freshness=freshness_value,
                    evidence_refs=self._uuid_list(record.get("evidence_ids")),
                    source_revision_ref=source_revision_id,
                    reason="authoritative project record"
                    if authority is ContextAuthority.CANONICAL
                    else "memory is context only",
                )
                score = self._relevance(_serialize(record), query)
                if kind in {"HardwareIR", "ProtocolIR", "FirmwareIR", "Dependency"}:
                    score += 2
                add(
                    item,
                    score=score,
                    selection_reason=f"selected by deterministic relevance score {score}",
                )
                if revision_store is not None and record.get("id") is not None:
                    revision = record.get("revision")
                    if isinstance(revision, int):
                        revision_store[str(record["id"])] = revision

        add_records("EngineeringClaim", claims, revision_store=claim_revisions)
        add_records("HardwareIR", hardware)
        add_records("ProtocolIR", protocols)
        add_records("FirmwareIR", firmware)
        add_records("Dependency", dependencies)
        add_records("Issue", issues)
        add_records("BuildRun", builds)
        add_records("StaticAnalysis", static_analysis)
        add_records("ERC", erc)
        add_records("TestRun", test_runs)
        add_records("Evidence", evidence, revision_store=evidence_revisions)

        for record in memories:
            memory_id = record.get("id")
            lifecycle = str(record.get("lifecycle", "UNKNOWN"))
            freshness = str(record.get("freshness_status", record.get("freshness", "UNKNOWN")))
            trusted = lifecycle in {"ACTIVE", "TRUSTED"} and freshness == "CURRENT"
            item = ContextItem(
                kind="Memory",
                canonical_ref=f"Memory:{memory_id or 'UNKNOWN'}",
                value=dict(record),
                authority=ContextAuthority.MEMORY,
                trust=ContextTrust.REVIEWED if trusted else ContextTrust.UNTRUSTED,
                freshness=(ContextFreshness.CURRENT if trusted else ContextFreshness.STALE),
                evidence_refs=self._uuid_list(record.get("evidence_ids")),
                source_revision_ref=source_revision_id,
                reason="active current memory"
                if trusted
                else "memory is not trusted planning authority",
            )
            score = self._relevance(_serialize(record), query)
            add(item, score=score if trusted else 0, selection_reason=item.reason)
            if trusted and memory_id:
                with suppress(ValueError):
                    selected_memory_refs.append(UUID(str(memory_id)))

        for item in selected:
            selected_evidence_refs.extend(item.evidence_refs)

        return PlanningContextSnapshot(
            project_id=requirement.project_id,
            source_revision_id=source_revision_id,
            selected_context=selected,
            excluded_context=excluded,
            selection_reason=reasons,
            claim_revisions=claim_revisions,
            evidence_revisions=evidence_revisions,
            memory_refs=sorted(set(selected_memory_refs), key=str),
            evidence_refs=sorted(set(selected_evidence_refs), key=str),
            source_content_is_untrusted=True,
        )

    @staticmethod
    def _relevance(value: str, query: str) -> int:
        value_lower = value.lower()
        tokens = {
            token for token in query.replace("/", " ").replace(".", " ").split() if len(token) > 2
        }
        return sum(1 for token in tokens if token in value_lower)

    @staticmethod
    def _uuid_list(value: object) -> list[UUID]:
        if not isinstance(value, (list, tuple)):
            return []
        result: list[UUID] = []
        for item in value:
            try:
                result.append(UUID(str(item)))
            except ValueError:
                continue
        return result


class DeterministicPlanningProvider:
    """Stable offline provider used by CI and the first desktop workflow."""

    name = "deterministic"
    version = PLANNING_PROVIDER_VERSION

    def generate_plan(
        self,
        requirement: EngineeringRequirement,
        context: PlanningContextSnapshot,
        constraints: Mapping[str, object],
    ) -> PlanningModelOutput:
        text = f"{requirement.title} {requirement.description}".lower()
        source_files = [
            str(_mapping_value(item.value).get("path"))
            for item in context.selected_context
            if item.kind == "SourceFile" and _mapping_value(item.value).get("path")
        ]
        target_file = self._best_file(source_files, text)
        criteria = requirement.acceptance_criteria
        if any(token in text for token in ("pin", "uart tx", "mcu", ".ioc")):
            output = self._pin_change(requirement, context, target_file)
        elif any(token in text for token in ("foc", "low-speed", "stability", "stabil")):
            output = self._foc_investigation(requirement, context)
        elif any(token in text for token in ("can", "heartbeat", "100 ms", "100ms")):
            output = self._can_heartbeat(requirement, context, target_file)
        else:
            output = self._generic(requirement, context, target_file)
        return output.model_copy(
            update={"acceptance_criteria_mapping": self._map_criteria(criteria, output.steps)}
        )

    @staticmethod
    def _best_file(files: list[str], text: str) -> str | None:
        if not files:
            return None
        tokens = ("can", "fdcan", "uart", "usart", "motor", "control", "scheduler", "task", "ioc")
        ranked = sorted(
            files,
            key=lambda path: (
                -sum(token in path.lower() or token in text for token in tokens),
                path,
            ),
        )
        return ranked[0]

    @staticmethod
    def _map_criteria(
        criteria: list[str], steps: list[EngineeringPlanStep]
    ) -> list[AcceptanceCriterionMapping]:
        if not criteria:
            return []
        verification = [
            f"V-{step.order}: {step.verification_plan[0]}"
            for step in steps
            if step.verification_plan
        ]
        return [
            AcceptanceCriterionMapping(
                criterion=criterion,
                step_ids=[step.id for step in steps],
                verification_refs=verification or ["NEEDS_INPUT: define verification evidence"],
            )
            for criterion in criteria
        ]

    @staticmethod
    def _base_unknown(requirement: EngineeringRequirement) -> EngineeringUnknown | None:
        if not requirement.acceptance_criteria:
            return EngineeringUnknown(
                question="What observable acceptance criteria define success?",
                why_needed="Every requirement must map to a future verification plan.",
                blocking=True,
                recommended_resolution="Add one or more measurable acceptance criteria.",
                related_refs=[f"EngineeringRequirement:{requirement.id}"],
            )
        return None

    def _can_heartbeat(
        self,
        requirement: EngineeringRequirement,
        context: PlanningContextSnapshot,
        target_file: str | None,
    ) -> PlanningModelOutput:
        target_type = PlanningTargetType.FILE if target_file else PlanningTargetType.REQUIREMENT
        target_ref = target_file or str(requirement.id)
        steps = [
            EngineeringPlanStep(
                order=1,
                title="Trace CAN timing path",
                description="Inspect the authoritative protocol and scheduler context for the heartbeat period and ownership.",
                action_type=PlanningActionType.ANALYZE,
                target_type=PlanningTargetType.REQUIREMENT,
                target_ref=str(requirement.id),
                reason="timing must be established from project facts",
                dependencies=[],
                preconditions=["current SourceRevision available"],
                expected_result="Resolved CAN message and scheduler owner",
                verification_plan=["Review protocol timing evidence"],
                risk_level=EngineeringRiskSeverity.MEDIUM,
                evidence_refs=context.evidence_refs,
            ),
            EngineeringPlanStep(
                order=2,
                title="Propose firmware integration",
                description="Describe the source-level change to schedule and publish the heartbeat without creating a patch.",
                action_type=PlanningActionType.MODIFY_SOURCE,
                target_type=target_type,
                target_ref=target_ref,
                reason="the implementation target must be a real source target",
                dependencies=["step-1"],
                preconditions=["CAN owner and period resolved"],
                expected_result="A reviewable change intent for the CAN publisher",
                verification_plan=[
                    "Unit test message construction",
                    "Protocol test period and payload",
                ],
                risk_level=EngineeringRiskSeverity.MEDIUM,
                evidence_refs=context.evidence_refs,
            ),
            EngineeringPlanStep(
                order=3,
                title="Define timing verification",
                description="Specify measurements for 100 ms cadence and scheduler jitter.",
                action_type=PlanningActionType.ADD_TEST,
                target_type=PlanningTargetType.REQUIREMENT,
                target_ref=str(requirement.id),
                reason="timing is an acceptance concern",
                dependencies=["step-2"],
                preconditions=["test instrumentation defined"],
                expected_result="A deterministic timing verification record",
                verification_plan=["Measure inter-frame period and jitter"],
                risk_level=EngineeringRiskSeverity.MEDIUM,
                evidence_refs=context.evidence_refs,
            ),
        ]
        unknown = self._base_unknown(requirement)
        return PlanningModelOutput(
            summary="Plan-only proposal for a 100 ms CAN heartbeat with scheduler, protocol, and timing verification boundaries.",
            assumptions=[
                EngineeringAssumption(
                    description="The project has one authoritative CAN publisher path.",
                    basis="Requires current ProtocolIR/FirmwareIR or reviewer confirmation.",
                    confidence=EngineeringRiskSeverity.UNKNOWN,
                    evidence_refs=context.evidence_refs,
                    validation_required=not bool(context.evidence_refs),
                )
            ],
            unknowns=[unknown] if unknown else [],
            risks=[
                EngineeringRisk(
                    category=EngineeringRiskCategory.TIMING,
                    severity=EngineeringRiskSeverity.MEDIUM,
                    likelihood=EngineeringRiskLikelihood.MEDIUM,
                    description="Scheduler jitter or bus load could violate the 100 ms cadence.",
                    affected_ref="CAN heartbeat",
                    mitigation="Define bus-load and jitter limits before implementation.",
                    verification="Measure inter-frame timing under representative load.",
                    reason="timing evidence is not execution",
                    evidence_refs=context.evidence_refs,
                ),
                EngineeringRisk(
                    category=EngineeringRiskCategory.PROTOCOL,
                    severity=EngineeringRiskSeverity.MEDIUM,
                    likelihood=EngineeringRiskLikelihood.UNKNOWN,
                    description="The heartbeat identifier and payload contract may be unspecified.",
                    affected_ref="CAN",
                    mitigation="Resolve the protocol item during human review.",
                    verification="Protocol compatibility test.",
                    reason="no unsupported identifier is invented",
                    evidence_refs=context.evidence_refs,
                ),
            ],
            steps=steps,
            proposed_changes=[
                ProposedEngineeringChange(
                    change_type=PlanningActionType.MODIFY_SOURCE,
                    target_kind=target_type,
                    target_ref=target_ref,
                    current_state="UNKNOWN",
                    proposed_state="Schedule and publish a 100 ms CAN heartbeat",
                    reason="Requirement requests heartbeat reporting.",
                    impact="Touches scheduler, CAN protocol, and tests.",
                    risk=EngineeringRiskSeverity.MEDIUM,
                    confidence=EngineeringRiskSeverity.UNKNOWN,
                    evidence_refs=context.evidence_refs,
                    expected_diff_intent="Describe scheduler and publisher intent only; no executable patch.",
                )
            ],
            affected_components=["CAN/Protocol", "scheduler/task", "firmware", "verification"],
            evidence_refs=context.evidence_refs,
            memory_refs=context.memory_refs,
            verification_plans=[],
        )

    def _pin_change(
        self,
        requirement: EngineeringRequirement,
        context: PlanningContextSnapshot,
        target_file: str | None,
    ) -> PlanningModelOutput:
        target_type = PlanningTargetType.FILE if target_file else PlanningTargetType.REQUIREMENT
        target_ref = target_file or str(requirement.id)
        unknown = EngineeringUnknown(
            question="Which board and schematic evidence prove the destination UART pin is electrically valid?",
            why_needed="A pin move can affect MCUConfig, firmware, schematic and PCB connectivity.",
            blocking=True,
            recommended_resolution="Provide reviewed board/schematic evidence and the target pin constraint.",
            related_refs=["MCUConfigIR", "SchematicIR", "HardwareIR"],
        )
        steps = [
            EngineeringPlanStep(
                order=1,
                title="Resolve MCU pin constraints",
                description="Compare the current MCU configuration with valid alternate functions and board constraints.",
                action_type=PlanningActionType.ANALYZE,
                target_type=target_type,
                target_ref=target_ref,
                reason="pin validity must come from current configuration and device facts",
                dependencies=[],
                preconditions=["MCUConfigIR and device package available"],
                expected_result="Candidate destination pin with evidence",
                verification_plan=["Run pin rule validation after M24B change execution"],
                risk_level=EngineeringRiskSeverity.HIGH,
                evidence_refs=context.evidence_refs,
            ),
            EngineeringPlanStep(
                order=2,
                title="Trace downstream impact",
                description="Inspect firmware, schematic and PCB-facing interfaces affected by the pin move.",
                action_type=PlanningActionType.ANALYZE,
                target_type=PlanningTargetType.REQUIREMENT,
                target_ref=str(requirement.id),
                reason="pin changes propagate beyond the .ioc file",
                dependencies=["step-1"],
                preconditions=["destination pin evidence resolved"],
                expected_result="Impact chain for MCUConfig, firmware and hardware",
                verification_plan=["Review dependency graph and electrical connectivity"],
                risk_level=EngineeringRiskSeverity.HIGH,
                evidence_refs=context.evidence_refs,
            ),
            EngineeringPlanStep(
                order=3,
                title="Define verification sequence",
                description="Specify configuration, firmware build, electrical and interface verification for a future controlled change.",
                action_type=PlanningActionType.VERIFY,
                target_type=PlanningTargetType.REQUIREMENT,
                target_ref=str(requirement.id),
                reason="verification is planned but not executed in M24A",
                dependencies=["step-2"],
                preconditions=["hardware evidence and acceptance criteria approved"],
                expected_result="Ordered verification checklist",
                verification_plan=[
                    "Configuration rule check",
                    "Firmware compile check",
                    "UART loopback/interface test",
                    "Schematic/ERC review",
                ],
                risk_level=EngineeringRiskSeverity.HIGH,
                evidence_refs=context.evidence_refs,
            ),
        ]
        return PlanningModelOutput(
            summary="Plan-only pin-change investigation spanning MCUConfig, firmware, schematic/PCB evidence, build and verification.",
            assumptions=[
                EngineeringAssumption(
                    description="The requested destination pin has a valid alternate function.",
                    basis="No destination pin was supplied with authoritative hardware evidence.",
                    confidence=EngineeringRiskSeverity.UNKNOWN,
                    evidence_refs=[],
                    validation_required=True,
                )
            ],
            unknowns=[unknown],
            risks=[
                EngineeringRisk(
                    category=EngineeringRiskCategory.HARDWARE,
                    severity=EngineeringRiskSeverity.HIGH,
                    likelihood=EngineeringRiskLikelihood.UNKNOWN,
                    description="The destination pin may conflict with board routing or electrical constraints.",
                    affected_ref="MCUConfigIR/SchematicIR",
                    mitigation="Obtain reviewed board and schematic evidence before approval.",
                    verification="Electrical connectivity and ERC review.",
                    reason="hardware evidence is missing",
                    evidence_refs=context.evidence_refs,
                ),
                EngineeringRisk(
                    category=EngineeringRiskCategory.COMPATIBILITY,
                    severity=EngineeringRiskSeverity.MEDIUM,
                    likelihood=EngineeringRiskLikelihood.MEDIUM,
                    description="Firmware peripheral mappings may remain on the old pin.",
                    affected_ref="firmware",
                    mitigation="Trace every downstream reference before any controlled change.",
                    verification="Firmware build and interface test.",
                    reason="transitive impact requires review",
                    evidence_refs=context.evidence_refs,
                ),
            ],
            steps=steps,
            proposed_changes=[
                ProposedEngineeringChange(
                    change_type=PlanningActionType.MODIFY_CONFIG,
                    target_kind=target_type,
                    target_ref=target_ref,
                    current_state="Current pin assignment unresolved",
                    proposed_state="Move UART TX to a reviewer-selected valid pin",
                    reason="Requested UART TX change.",
                    impact="MCUConfig → firmware → schematic/PCB → build/test",
                    risk=EngineeringRiskSeverity.HIGH,
                    confidence=EngineeringRiskSeverity.UNKNOWN,
                    evidence_refs=context.evidence_refs,
                    expected_diff_intent="Describe the configuration intent only; do not emit .ioc mutation.",
                )
            ],
            affected_components=[
                "MCUConfigIR",
                ".ioc",
                "firmware",
                "HardwareIR",
                "SchematicIR",
                "build",
                "test",
            ],
            evidence_refs=context.evidence_refs,
            memory_refs=context.memory_refs,
        )

    def _foc_investigation(
        self, requirement: EngineeringRequirement, context: PlanningContextSnapshot
    ) -> PlanningModelOutput:
        steps = [
            EngineeringPlanStep(
                order=1,
                title="Collect low-speed measurements",
                description="Define operating points and measurements for current, speed, position and bus conditions.",
                action_type=PlanningActionType.INVESTIGATE,
                target_type=PlanningTargetType.REQUIREMENT,
                target_ref=str(requirement.id),
                reason="evidence is insufficient to choose control parameters",
                dependencies=[],
                preconditions=["test setup and safe operating envelope documented"],
                expected_result="Comparable low-speed measurement set",
                verification_plan=["Record repeatable low-speed runs"],
                risk_level=EngineeringRiskSeverity.HIGH,
                evidence_refs=context.evidence_refs,
            ),
            EngineeringPlanStep(
                order=2,
                title="Analyze possible causes",
                description="Compare feedback quality, sampling/timing, current sensing and controller saturation hypotheses.",
                action_type=PlanningActionType.ANALYZE,
                target_type=PlanningTargetType.REQUIREMENT,
                target_ref=str(requirement.id),
                reason="avoid inventing a Ki or other tuning value",
                dependencies=["step-1"],
                preconditions=["measurements available"],
                expected_result="Ranked, evidence-backed cause hypotheses",
                verification_plan=["Review hypotheses against measurements"],
                risk_level=EngineeringRiskSeverity.MEDIUM,
                evidence_refs=context.evidence_refs,
            ),
            EngineeringPlanStep(
                order=3,
                title="Define controlled experiment",
                description="Specify one-variable-at-a-time experiments and acceptance thresholds for stability.",
                action_type=PlanningActionType.ADD_TEST,
                target_type=PlanningTargetType.REQUIREMENT,
                target_ref=str(requirement.id),
                reason="parameter changes belong to a later controlled-change phase",
                dependencies=["step-2"],
                preconditions=["hypothesis and safety limits reviewed"],
                expected_result="Experiment matrix without parameter mutation",
                verification_plan=["Compare stability metrics against baseline"],
                risk_level=EngineeringRiskSeverity.HIGH,
                evidence_refs=context.evidence_refs,
            ),
        ]
        return PlanningModelOutput(
            summary="Investigation plan for low-speed FOC stability; no controller parameter value is invented.",
            assumptions=[
                EngineeringAssumption(
                    description="A safe, repeatable low-speed test envelope can be defined.",
                    basis="Required before collecting evidence.",
                    confidence=EngineeringRiskSeverity.UNKNOWN,
                    evidence_refs=[],
                    validation_required=True,
                )
            ],
            unknowns=[
                EngineeringUnknown(
                    question="What measured symptom defines low-speed instability and what limits apply?",
                    why_needed="Without symptom and safety limits, a tuning proposal would be speculative.",
                    blocking=True,
                    recommended_resolution="Provide baseline traces, operating point, feedback/sampling configuration and safe limits.",
                    related_refs=["FirmwareIR", "TestRun", "HardwareIR"],
                )
            ],
            risks=[
                EngineeringRisk(
                    category=EngineeringRiskCategory.SAFETY,
                    severity=EngineeringRiskSeverity.HIGH,
                    likelihood=EngineeringRiskLikelihood.UNKNOWN,
                    description="Unbounded experiments could cause unsafe motor behavior.",
                    affected_ref="motor control test setup",
                    mitigation="Review safe operating envelope before any experiment.",
                    verification="Safety checklist and bounded test evidence.",
                    reason="M24A does not execute experiments",
                    evidence_refs=context.evidence_refs,
                ),
                EngineeringRisk(
                    category=EngineeringRiskCategory.TIMING,
                    severity=EngineeringRiskSeverity.MEDIUM,
                    likelihood=EngineeringRiskLikelihood.UNKNOWN,
                    description="Sampling and scheduler timing may contribute to the symptom.",
                    affected_ref="control loop",
                    mitigation="Measure timing before tuning.",
                    verification="Timing trace review.",
                    reason="no false precision",
                    evidence_refs=context.evidence_refs,
                ),
            ],
            steps=steps,
            proposed_changes=[],
            affected_components=[
                "FOC/control loop",
                "feedback",
                "current sensing",
                "scheduler",
                "measurement",
            ],
            evidence_refs=context.evidence_refs,
            memory_refs=context.memory_refs,
        )

    def _generic(
        self,
        requirement: EngineeringRequirement,
        context: PlanningContextSnapshot,
        target_file: str | None,
    ) -> PlanningModelOutput:
        target_type = PlanningTargetType.FILE if target_file else PlanningTargetType.REQUIREMENT
        target_ref = target_file or str(requirement.id)
        unknown = self._base_unknown(requirement)
        step = EngineeringPlanStep(
            order=1,
            title="Analyze requirement against project facts",
            description="Resolve affected components, dependencies and evidence before proposing a future change.",
            action_type=PlanningActionType.ANALYZE,
            target_type=target_type,
            target_ref=target_ref,
            reason="generic planning begins with authoritative context",
            dependencies=[],
            preconditions=["current SourceRevision available"],
            expected_result="Reviewable affected-component and verification outline",
            verification_plan=["Human review of context and acceptance criteria"],
            risk_level=EngineeringRiskSeverity.UNKNOWN,
            evidence_refs=context.evidence_refs,
        )
        return PlanningModelOutput(
            summary="Plan-only engineering analysis with explicit evidence and unresolved information.",
            assumptions=[],
            unknowns=[unknown] if unknown else [],
            risks=[
                EngineeringRisk(
                    category=EngineeringRiskCategory.MAINTAINABILITY,
                    severity=EngineeringRiskSeverity.UNKNOWN,
                    likelihood=EngineeringRiskLikelihood.UNKNOWN,
                    description="Impact cannot be scored precisely until the target and acceptance evidence are resolved.",
                    affected_ref=target_ref,
                    mitigation="Resolve unknowns during human review.",
                    verification="Review plan context and acceptance mapping.",
                    reason="insufficient evidence",
                    evidence_refs=context.evidence_refs,
                )
            ],
            steps=[step],
            proposed_changes=[],
            affected_components=["unresolved"],
            evidence_refs=context.evidence_refs,
            memory_refs=context.memory_refs,
        )


class EngineeringPlanValidator:
    """Deterministic safety and target validator for provider output."""

    forbidden_fragments = (
        "subprocess",
        "os.system",
        "shell command",
        "git commit",
        "apply patch",
        "execute shell",
        "flash device",
    )

    def validate(
        self,
        output: PlanningModelOutput,
        requirement: EngineeringRequirement,
        context: PlanningContextSnapshot,
    ) -> PlanningValidation:
        issues: list[str] = []
        known_files = {
            str(_mapping_value(item.value).get("path"))
            for item in (*context.selected_context, *context.excluded_context)
            if item.kind == "SourceFile" and _mapping_value(item.value).get("path")
        }
        known_refs = {
            item.canonical_ref for item in (*context.selected_context, *context.excluded_context)
        }
        known_refs.update({str(requirement.id), f"EngineeringRequirement:{requirement.id}"})
        step_ids = {step.id for step in output.steps}
        for step in output.steps:
            if step.target_type is PlanningTargetType.FILE and step.target_ref not in known_files:
                issues.append(f"INVALID_TARGET:file:{step.target_ref}")
            if step.target_type is PlanningTargetType.SYMBOL and step.target_ref not in known_refs:
                issues.append(f"UNRESOLVED_TARGET:symbol:{step.target_ref}")
            if not step.verification_plan:
                issues.append(f"MISSING_VERIFICATION:step:{step.id}")
        for change in output.proposed_changes:
            if change.status in {ProposedChangeStatus.ACCEPTED, ProposedChangeStatus.BLOCKED}:
                issues.append(f"PROVIDER_STATUS_NOT_PROPOSED:change:{change.id}")
            if (
                change.target_kind is PlanningTargetType.FILE
                and change.target_ref not in known_files
            ):
                issues.append(f"INVALID_TARGET:file:{change.target_ref}")
        all_text = _serialize(output.model_dump(mode="json")).lower()
        for fragment in self.forbidden_fragments:
            if fragment in all_text:
                issues.append(f"EXECUTION_ATTEMPT:{fragment}")
        for mapping in output.acceptance_criteria_mapping:
            if mapping.criterion not in requirement.acceptance_criteria:
                issues.append(f"UNKNOWN_ACCEPTANCE_CRITERION:{mapping.criterion}")
            if not set(mapping.step_ids) <= step_ids:
                issues.append(f"INVALID_ACCEPTANCE_STEP:{mapping.criterion}")
        mapped = {item.criterion for item in output.acceptance_criteria_mapping}
        for criterion in requirement.acceptance_criteria:
            if criterion not in mapped:
                issues.append(f"UNCOVERED_ACCEPTANCE_CRITERION:{criterion}")
        quality = PlanQualityChecker().check(output, requirement, context)
        return PlanningValidation(
            not issues, tuple(sorted(set(issues))), tuple(sorted(set(quality)))
        )


class PlanQualityChecker:
    """Deterministic coverage checks independent from model confidence."""

    def check(
        self,
        output: PlanningModelOutput,
        requirement: EngineeringRequirement,
        context: PlanningContextSnapshot,
    ) -> list[str]:
        issues: list[str] = []
        if not output.steps:
            issues.append("PLAN_INCOMPLETE:no_steps")
        if requirement.acceptance_criteria and not output.acceptance_criteria_mapping:
            issues.append("PLAN_INCOMPLETE:acceptance_criteria_mapping")
        if (
            output.proposed_changes
            and not output.verification_plans
            and not any(step.verification_plan for step in output.steps)
        ):
            # A provider may encode verification in the step itself, but every
            # proposed change still needs an explicit future verification plan.
            issues.append("PLAN_INCOMPLETE:verification")
        if output.proposed_changes and not output.evidence_refs and not context.evidence_refs:
            issues.append("PLAN_INCOMPLETE:evidence")
        if not output.risks:
            issues.append("PLAN_INCOMPLETE:risks")
        return issues


class PlanningPolicy:
    """M24A trust boundary expressed as executable application policy."""

    allow_file_mutation = False
    allow_shell = False
    allow_build = False
    allow_test_execution = False
    allow_hardware_action = False
    allow_canonical_mutation = False

    def constraints(self) -> dict[str, object]:
        return {
            "policy_version": PLANNING_POLICY_VERSION,
            "allow_file_mutation": self.allow_file_mutation,
            "allow_shell": self.allow_shell,
            "allow_build": self.allow_build,
            "allow_test_execution": self.allow_test_execution,
            "allow_hardware_action": self.allow_hardware_action,
            "allow_canonical_mutation": self.allow_canonical_mutation,
        }

    def assert_plan_only(self, plan: EngineeringPlan) -> None:
        if any(
            change.status
            not in {ProposedChangeStatus.PROPOSED, ProposedChangeStatus.NEEDS_REVISION}
            for change in plan.proposed_changes
        ):
            raise EngineeringError(
                EngineeringErrorCode.VALIDATION_ERROR, "M24A proposed changes must remain proposals"
            )


class EngineeringPlanningService:
    """Compose context, call a provider, and create a gated immutable plan."""

    def __init__(
        self,
        provider: PlanningModelProvider | None = None,
        *,
        assembler: EngineeringContextAssembler | None = None,
        validator: EngineeringPlanValidator | None = None,
        policy: PlanningPolicy | None = None,
    ) -> None:
        self.provider = provider or DeterministicPlanningProvider()
        self.assembler = assembler or EngineeringContextAssembler()
        self.validator = validator or EngineeringPlanValidator()
        self.policy = policy or PlanningPolicy()

    def generate(
        self,
        requirement: EngineeringRequirement,
        *,
        source_revision_id: UUID | None,
        source_revision: Mapping[str, object] | None = None,
        claims: Sequence[Mapping[str, object]] = (),
        hardware: Sequence[Mapping[str, object]] = (),
        protocols: Sequence[Mapping[str, object]] = (),
        firmware: Sequence[Mapping[str, object]] = (),
        dependencies: Sequence[Mapping[str, object]] = (),
        issues: Sequence[Mapping[str, object]] = (),
        builds: Sequence[Mapping[str, object]] = (),
        static_analysis: Sequence[Mapping[str, object]] = (),
        erc: Sequence[Mapping[str, object]] = (),
        test_runs: Sequence[Mapping[str, object]] = (),
        evidence: Sequence[Mapping[str, object]] = (),
        memories: Sequence[Mapping[str, object]] = (),
        created_by: str,
        supersedes_plan_id: UUID | None = None,
    ) -> PlanningResult:
        context = self.assembler.assemble(
            requirement,
            source_revision_id=source_revision_id,
            source_revision=source_revision,
            claims=claims,
            hardware=hardware,
            protocols=protocols,
            firmware=firmware,
            dependencies=dependencies,
            issues=issues,
            builds=builds,
            static_analysis=static_analysis,
            erc=erc,
            test_runs=test_runs,
            evidence=evidence,
            memories=memories,
        )
        try:
            raw = self.provider.generate_plan(requirement, context, self.policy.constraints())
            output = (
                raw
                if isinstance(raw, PlanningModelOutput)
                else PlanningModelOutput.model_validate(raw)
            )
        except Exception as exc:
            raise EngineeringError(
                EngineeringErrorCode.VALIDATION_ERROR,
                "Planning model output is invalid",
                details={"reason": "PLANNING_OUTPUT_INVALID", "error": str(exc)},
            ) from exc
        validation = self.validator.validate(output, requirement, context)
        blocking_unknown = any(item.blocking for item in output.unknowns)
        missing_source = source_revision_id is None
        status = (
            EngineeringPlanStatus.BLOCKED
            if validation.issues
            else EngineeringPlanStatus.NEEDS_INPUT
            if blocking_unknown or missing_source or validation.quality_issues
            else EngineeringPlanStatus.READY_FOR_REVIEW
        )
        plan = EngineeringPlan(
            id=uuid4(),
            project_id=requirement.project_id,
            requirement_id=requirement.id,
            source_revision_id=source_revision_id,
            context_snapshot_id=context.id,
            status=status,
            summary=output.summary,
            assumptions=output.assumptions,
            unknowns=output.unknowns,
            risks=output.risks,
            steps=output.steps,
            proposed_changes=output.proposed_changes,
            affected_components=output.affected_components,
            evidence_refs=sorted({*context.evidence_refs, *output.evidence_refs}, key=str),
            memory_refs=sorted({*context.memory_refs, *output.memory_refs}, key=str),
            acceptance_criteria_mapping=output.acceptance_criteria_mapping,
            verification_plans=output.verification_plans,
            provider=self.provider.name,
            model_version=self.provider.version,
            prompt_template_version=PLANNING_PROMPT_TEMPLATE_VERSION,
            planning_policy_version=PLANNING_POLICY_VERSION,
            created_by=created_by,
            supersedes_plan_id=supersedes_plan_id,
            metadata={
                "validation_issues": list(validation.issues),
                "quality_issues": list(validation.quality_issues),
                "m24a_plan_only": True,
            },
        )
        self.policy.assert_plan_only(plan)
        return PlanningResult(plan=plan, context=context, validation=validation)


__all__ = [
    "PLANNING_POLICY_VERSION",
    "PLANNING_PROMPT_TEMPLATE_VERSION",
    "DeterministicPlanningProvider",
    "EngineeringContextAssembler",
    "EngineeringPlanValidator",
    "EngineeringPlanningService",
    "PlanQualityChecker",
    "PlanningModelOutput",
    "PlanningModelProvider",
    "PlanningPolicy",
    "PlanningResult",
    "PlanningValidation",
]
