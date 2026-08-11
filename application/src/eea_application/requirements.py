"""M6 Requirement DSL registry and analysis services.

Natural-language analysis is deliberately routed through M2's
``StructuredGenerationService``. This module has no provider, subprocess, or
filesystem execution capability.
"""

from collections.abc import Mapping
from typing import cast
from uuid import UUID

from eea_core.claims import EngineeringClaim, EngineeringValue, JsonValue
from eea_core.entities import Issue
from eea_core.enums import (
    EngineeringDimension,
    EngineeringErrorCode,
    EvidenceType,
    IssueSeverity,
    IssueStatus,
    RequirementFieldStatus,
    RequirementStatus,
    RequirementValueType,
)
from eea_core.errors import EngineeringError
from eea_core.repositories import RequirementProfileRepository
from eea_core.requirements import (
    FollowUpQuestion,
    Requirement,
    RequirementAnalysis,
    RequirementAnalysisDraft,
    RequirementClaimDraft,
    RequirementCompleteness,
    RequirementEvidenceContract,
    RequirementFieldObservation,
    RequirementFieldSpec,
    RequirementIssueDraft,
    RequirementProfile,
)

from eea_application.ai import StructuredGenerationService

REQUIREMENT_ANALYSIS_PROMPT_NAME = "requirements.analyze"
REQUIREMENT_ANALYSIS_PROMPT_VERSION = "1.0"
REQUIREMENT_PROFILE_SCHEMA_VERSION = "1.0"


class RequirementProfileRegistry:
    """Version-aware profile lookup with explicit unsupported-version errors."""

    def __init__(self, repository: RequirementProfileRepository) -> None:
        self._repository = repository

    def register(self, profile: RequirementProfile) -> RequirementProfile:
        return self._repository.add(profile)

    def require(self, profile_name: str, profile_version: str) -> RequirementProfile:
        profile = self._repository.get(profile_name, profile_version)
        if profile is None:
            raise EngineeringError(
                EngineeringErrorCode.SCHEMA_VERSION_UNSUPPORTED,
                "Requirement profile version is not registered",
                details={"profile_name": profile_name, "profile_version": profile_version},
            )
        if not profile.active:
            raise EngineeringError(
                EngineeringErrorCode.CAPABILITY_UNAVAILABLE,
                "Requirement profile is not active",
                details={"profile_name": profile_name, "profile_version": profile_version},
            )
        return profile


class RequirementAnalysisService:
    """Analyze requirements and deterministically gate completeness."""

    def __init__(
        self,
        profile_registry: RequirementProfileRegistry,
        structured_generation: StructuredGenerationService | None = None,
    ) -> None:
        self._profiles = profile_registry
        self._structured_generation = structured_generation

    async def analyze_natural_language(
        self,
        *,
        project_id: UUID,
        profile_name: str,
        profile_version: str,
        source_text: str,
        evidence_refs: Mapping[str, UUID] | None = None,
    ) -> RequirementAnalysis:
        """Use M2 structured generation, then run the deterministic gate."""

        if self._structured_generation is None:
            raise EngineeringError(
                EngineeringErrorCode.CAPABILITY_UNAVAILABLE,
                "Structured requirement generation is not configured",
            )
        profile = self._profiles.require(profile_name, profile_version)
        if not source_text.strip():
            raise EngineeringError(
                EngineeringErrorCode.INVALID_REQUIREMENT,
                "Natural-language requirement input cannot be empty",
            )
        resolved_evidence = evidence_refs or {}
        draft = await self._structured_generation.generate(
            prompt_name=REQUIREMENT_ANALYSIS_PROMPT_NAME,
            prompt_version=REQUIREMENT_ANALYSIS_PROMPT_VERSION,
            input_data={
                "project_id": str(project_id),
                "source_text": source_text,
                "profile": profile.model_dump(mode="json"),
                "evidence_refs": {key: str(value) for key, value in resolved_evidence.items()},
            },
            output_model=RequirementAnalysisDraft,
            project_id=project_id,
        )
        return self._complete(
            project_id=project_id,
            profile=profile,
            draft=draft,
            evidence_refs=resolved_evidence,
        )

    def analyze_structured(
        self,
        *,
        project_id: UUID,
        profile_name: str,
        profile_version: str,
        values: Mapping[str, object],
        evidence_refs: Mapping[str, UUID] | None = None,
        requirements: list[Requirement] | None = None,
    ) -> RequirementAnalysis:
        """Analyze deterministic profile input without invoking an AI provider."""

        profile = self._profiles.require(profile_name, profile_version)
        resolved_evidence = evidence_refs or {}
        observations = [
            RequirementFieldObservation(
                field_key=key,
                status=(
                    RequirementFieldStatus.PRESENT
                    if value is not None
                    else RequirementFieldStatus.UNKNOWN
                ),
                value=value,
                evidence_refs=[key] if key in resolved_evidence and value is not None else [],
                confidence=1,
            )
            for key, value in values.items()
        ]
        draft = RequirementAnalysisDraft(
            profile_name=profile_name,
            profile_version=profile_version,
            requirements=requirements or [],
            field_observations=observations,
        )
        return self._complete(
            project_id=project_id,
            profile=profile,
            draft=draft,
            evidence_refs=resolved_evidence,
        )

    def complete_draft(
        self,
        *,
        project_id: UUID,
        profile_name: str,
        profile_version: str,
        draft: RequirementAnalysisDraft,
        evidence_refs: Mapping[str, UUID] | None = None,
    ) -> RequirementAnalysis:
        """Complete a pre-validated provider draft, useful for deterministic tests."""

        profile = self._profiles.require(profile_name, profile_version)
        return self._complete(
            project_id=project_id,
            profile=profile,
            draft=draft,
            evidence_refs=evidence_refs or {},
        )

    def _complete(
        self,
        *,
        project_id: UUID,
        profile: RequirementProfile,
        draft: RequirementAnalysisDraft,
        evidence_refs: Mapping[str, UUID],
    ) -> RequirementAnalysis:
        if (draft.profile_name, draft.profile_version) != (
            profile.profile_name,
            profile.profile_version,
        ):
            raise EngineeringError(
                EngineeringErrorCode.SCHEMA_VERSION_UNSUPPORTED,
                "Requirement analysis output does not match the selected profile",
                details={
                    "expected": f"{profile.profile_name}@{profile.profile_version}",
                    "actual": f"{draft.profile_name}@{draft.profile_version}",
                },
            )

        specs = {field.key: field for field in profile.fields}
        observations = self._validate_observations(draft.field_observations, specs)
        evidence_ids_by_ref = dict(evidence_refs)
        claims = self._build_claims(
            project_id=project_id,
            observations=observations,
            specs=specs,
            explicit_claims=draft.claims,
            evidence_ids_by_ref=evidence_ids_by_ref,
        )
        completeness, generated_issues, generated_questions = self._assess_completeness(
            profile=profile,
            observations=observations,
            evidence_ids_by_ref=evidence_ids_by_ref,
            project_id=project_id,
        )
        issues = generated_issues + [
            self._issue_from_draft(
                project_id=project_id,
                item=item,
                evidence_ids_by_ref=evidence_ids_by_ref,
                claim_ids=[claim.id for claim in claims],
            )
            for item in draft.issues
        ]
        requirements = [
            self._normalize_requirement(item, project_id, completeness.status)
            for item in draft.requirements
        ]
        return RequirementAnalysis(
            project_id=project_id,
            profile_name=profile.profile_name,
            profile_version=profile.profile_version,
            requirements=requirements,
            field_observations=observations,
            claims=claims,
            issues=issues,
            follow_up_questions=[*generated_questions, *draft.follow_up_questions],
            completeness=completeness,
        )

    @staticmethod
    def _validate_observations(
        observations: list[RequirementFieldObservation],
        specs: Mapping[str, RequirementFieldSpec],
    ) -> list[RequirementFieldObservation]:
        seen: set[str] = set()
        normalized: list[RequirementFieldObservation] = []
        for observation in observations:
            spec = specs.get(observation.field_key)
            if spec is None:
                raise EngineeringError(
                    EngineeringErrorCode.INVALID_REQUIREMENT,
                    "Requirement analysis returned an unsupported field",
                    details={"field_key": observation.field_key},
                )
            if observation.field_key in seen:
                raise EngineeringError(
                    EngineeringErrorCode.VALIDATION_ERROR,
                    "Requirement analysis returned a duplicate field",
                    details={"field_key": observation.field_key},
                )
            seen.add(observation.field_key)
            if observation.status is RequirementFieldStatus.PRESENT:
                RequirementAnalysisService._validate_value(spec, observation.value)
            normalized.append(observation)
        return normalized

    @staticmethod
    def _validate_value(spec: RequirementFieldSpec, value: object | None) -> None:
        if value is None:
            raise EngineeringError(
                EngineeringErrorCode.INVALID_REQUIREMENT,
                "A present requirement field must contain a value",
                details={"field_key": spec.key},
            )
        value_type = spec.value_type
        valid = (
            (value_type is RequirementValueType.TEXT and isinstance(value, str))
            or (
                value_type is RequirementValueType.NUMBER
                and isinstance(value, (int, float))
                and not isinstance(value, bool)
            )
            or (value_type is RequirementValueType.BOOLEAN and isinstance(value, bool))
            or (
                value_type is RequirementValueType.ENUM
                and isinstance(value, str)
                and value in spec.allowed_values
            )
            or (value_type is RequirementValueType.OBJECT and isinstance(value, dict))
            or (value_type is RequirementValueType.LIST and isinstance(value, list))
        )
        if value_type is RequirementValueType.ENGINEERING_VALUE:
            try:
                engineering_value = EngineeringValue.model_validate(value)
            except ValueError as exc:
                raise EngineeringError(
                    EngineeringErrorCode.INVALID_REQUIREMENT,
                    "Engineering requirement value is invalid",
                    details={"field_key": spec.key, "reason": str(exc)},
                ) from None
            valid = engineering_value.dimension is spec.engineering_dimension
        if not valid:
            raise EngineeringError(
                EngineeringErrorCode.INVALID_REQUIREMENT,
                "Requirement field value does not match its profile contract",
                details={"field_key": spec.key, "value_type": value_type.value},
            )

    def _build_claims(
        self,
        *,
        project_id: UUID,
        observations: list[RequirementFieldObservation],
        specs: Mapping[str, RequirementFieldSpec],
        explicit_claims: list[RequirementClaimDraft],
        evidence_ids_by_ref: Mapping[str, UUID],
    ) -> list[EngineeringClaim]:
        claims: list[EngineeringClaim] = []
        for observation in observations:
            spec = specs[observation.field_key]
            if (
                spec.claim_predicate is None
                or observation.status is not RequirementFieldStatus.PRESENT
                or observation.value is None
            ):
                continue
            value: object = observation.value
            if spec.value_type is RequirementValueType.ENGINEERING_VALUE:
                value = EngineeringValue.model_validate(value)
            claims.append(
                EngineeringClaim(
                    project_id=project_id,
                    subject_ref=f"project:{project_id}",
                    predicate=spec.claim_predicate,
                    value=cast(JsonValue, value),
                    evidence_ids=self._resolve_evidence_refs(
                        observation.evidence_refs, evidence_ids_by_ref
                    ),
                    confidence=observation.confidence,
                    source_priority=0,
                )
            )
        for draft in explicit_claims:
            claims.append(
                EngineeringClaim(
                    project_id=project_id,
                    subject_ref=draft.subject_ref,
                    predicate=draft.predicate,
                    value=cast(JsonValue, draft.value),
                    applicability=draft.applicability,
                    evidence_ids=self._resolve_evidence_refs(
                        draft.evidence_refs, evidence_ids_by_ref
                    ),
                    confidence=draft.confidence,
                    source_priority=draft.source_priority,
                    source_version=draft.source_version,
                )
            )
        return claims

    def _assess_completeness(
        self,
        *,
        profile: RequirementProfile,
        observations: list[RequirementFieldObservation],
        evidence_ids_by_ref: Mapping[str, UUID],
        project_id: UUID,
    ) -> tuple[RequirementCompleteness, list[Issue], list[FollowUpQuestion]]:
        by_key = {item.field_key: item for item in observations}
        required_fields = [field for field in profile.fields if field.required]
        missing_fields: list[str] = []
        ambiguous_fields: list[str] = []
        missing_evidence: list[str] = []
        issues: list[Issue] = []
        questions: list[FollowUpQuestion] = []
        satisfied = 0
        denominator = (
            len(required_fields)
            + sum(1 for field in required_fields if field.evidence_required)
            + sum(1 for contract in profile.evidence_contracts if contract.required)
        )

        for field in required_fields:
            observation = by_key.get(field.key)
            if observation is None or observation.status in {
                RequirementFieldStatus.MISSING,
                RequirementFieldStatus.UNKNOWN,
            }:
                missing_fields.append(field.key)
                issues.append(
                    Issue(
                        project_id=project_id,
                        code="REQUIREMENT_FIELD_MISSING",
                        title=f"Missing requirement field: {field.label}",
                        description=field.description
                        or f"Required field '{field.key}' is not known.",
                        severity=IssueSeverity.HIGH,
                        status=IssueStatus.OPEN,
                    )
                )
                questions.append(
                    FollowUpQuestion(
                        code="REQUIREMENT_FIELD_FOLLOWUP",
                        question=f"Please provide {field.label}.",
                        field_keys=[field.key],
                        reason="The profile marks this field as required and its value is unknown.",
                    )
                )
            elif observation.status is RequirementFieldStatus.AMBIGUOUS:
                ambiguous_fields.append(field.key)
                issues.append(
                    Issue(
                        project_id=project_id,
                        code="REQUIREMENT_FIELD_AMBIGUOUS",
                        title=f"Ambiguous requirement field: {field.label}",
                        description=observation.ambiguity_reason
                        or "Multiple interpretations remain.",
                        severity=IssueSeverity.HIGH,
                        status=IssueStatus.OPEN,
                    )
                )
                questions.append(
                    FollowUpQuestion(
                        code="REQUIREMENT_AMBIGUITY_FOLLOWUP",
                        question=f"Please clarify {field.label}.",
                        field_keys=[field.key],
                        reason="The supplied requirement contains an unresolved ambiguity.",
                    )
                )
            else:
                satisfied += 1
                if field.evidence_required and not observation.evidence_refs:
                    missing_evidence.append(field.key)
                    issues.append(
                        Issue(
                            project_id=project_id,
                            code="REQUIREMENT_EVIDENCE_MISSING",
                            title=f"Missing evidence: {field.label}",
                            description="The profile requires evidence for this field.",
                            severity=IssueSeverity.HIGH,
                            status=IssueStatus.OPEN,
                        )
                    )
                    questions.append(
                        FollowUpQuestion(
                            code="REQUIREMENT_FIELD_EVIDENCE_FOLLOWUP",
                            question=f"Please provide evidence for {field.label}.",
                            field_keys=[field.key],
                            reason="The selected field contract requires evidence.",
                        )
                    )
                elif field.evidence_required:
                    satisfied += 1

        for contract in profile.evidence_contracts:
            if contract.required and contract.key in evidence_ids_by_ref:
                satisfied += 1

        for contract in profile.evidence_contracts:
            if contract.required and contract.key not in evidence_ids_by_ref:
                missing_evidence.append(contract.key)
                questions.append(
                    FollowUpQuestion(
                        code="REQUIREMENT_EVIDENCE_FOLLOWUP",
                        question=f"Please provide evidence for {contract.description}.",
                        field_keys=[],
                        reason="The selected profile declares this evidence contract as required.",
                    )
                )

        if missing_fields:
            status = RequirementStatus.INCOMPLETE
        elif ambiguous_fields:
            status = RequirementStatus.AMBIGUOUS
        elif missing_evidence:
            status = RequirementStatus.INCOMPLETE
        else:
            status = RequirementStatus.COMPLETE
        if denominator == 0:
            score = 1.0 if status is RequirementStatus.COMPLETE else 0.0
        else:
            score = max(0.0, min(1.0, satisfied / denominator))
        completeness = RequirementCompleteness(
            status=status,
            score=score,
            required_field_keys=[field.key for field in required_fields],
            missing_field_keys=missing_fields,
            ambiguous_field_keys=ambiguous_fields,
            missing_evidence_keys=sorted(set(missing_evidence)),
        )
        return completeness, issues, questions

    @staticmethod
    def _issue_from_draft(
        *,
        project_id: UUID,
        item: RequirementIssueDraft,
        evidence_ids_by_ref: Mapping[str, UUID],
        claim_ids: list[UUID],
    ) -> Issue:
        return Issue(
            project_id=project_id,
            code=item.code,
            title=item.title,
            description=item.description,
            severity=item.severity,
            status=IssueStatus.OPEN,
            claim_ids=claim_ids,
            evidence_ids=RequirementAnalysisService._resolve_evidence_refs(
                item.evidence_refs, evidence_ids_by_ref
            ),
        )

    @staticmethod
    def _normalize_requirement(
        requirement: Requirement,
        project_id: UUID,
        status: RequirementStatus,
    ) -> Requirement:
        if requirement.project_id != project_id:
            raise EngineeringError(
                EngineeringErrorCode.VALIDATION_ERROR,
                "Requirement output belongs to a different project",
            )
        return requirement.model_copy(update={"status": status})

    @staticmethod
    def _resolve_evidence_refs(
        refs: list[str], evidence_ids_by_ref: Mapping[str, UUID]
    ) -> list[UUID]:
        resolved: list[UUID] = []
        for ref in refs:
            evidence_id = evidence_ids_by_ref.get(ref)
            if evidence_id is None:
                try:
                    evidence_id = UUID(ref)
                except ValueError:
                    raise EngineeringError(
                        EngineeringErrorCode.INVALID_REQUIREMENT,
                        "Requirement analysis referenced unknown evidence",
                        details={"evidence_ref": ref},
                    ) from None
            if evidence_id not in resolved:
                resolved.append(evidence_id)
        return resolved


def build_requirement_analysis_prompt_definition() -> object:
    """Build the versioned M6 prompt contract for registration in M2."""

    from decimal import Decimal

    from eea_core.ai import BudgetPolicy, ModelPolicy, PromptDefinition

    return PromptDefinition(
        name=REQUIREMENT_ANALYSIS_PROMPT_NAME,
        prompt_version=REQUIREMENT_ANALYSIS_PROMPT_VERSION,
        purpose="Extract generic, evidence-aware requirements without guessing missing values.",
        system_template=(
            "Return only JSON matching the registered schema. Unknown required fields must be "
            "marked UNKNOWN or MISSING; never invent engineering values or evidence."
        ),
        user_template="Analyze this requirement input: {input_json}",
        model_policy=ModelPolicy(model="configured-by-deployment", temperature=0),
        allowed_tools=[],
        input_schema={"type": "object"},
        output_schema=RequirementAnalysisDraft.model_json_schema(),
        evidence_requirements=["evidence_refs"],
        fallback={"mode": "deterministic_review"},
        max_steps=1,
        budget_policy=BudgetPolicy(
            max_tokens=2000,
            max_llm_cost=Decimal("1"),
            max_runtime_seconds=30,
        ),
    )


__all__ = [
    "REQUIREMENT_ANALYSIS_PROMPT_NAME",
    "REQUIREMENT_ANALYSIS_PROMPT_VERSION",
    "RequirementAnalysisService",
    "RequirementProfileRegistry",
    "build_foc_benchmark_profile",
    "build_requirement_analysis_prompt_definition",
]


def build_foc_benchmark_profile() -> RequirementProfile:
    """Return the deterministic FOC benchmark as generic profile data.

    The profile deliberately uses generic field/value contracts. No motor
    control class or motor-specific schema is added to Core; the future domain
    plugin may consume the resulting claims and references.
    """

    from datetime import UTC, datetime

    return RequirementProfile(
        schema_version=REQUIREMENT_PROFILE_SCHEMA_VERSION,
        profile_name="foc-benchmark",
        profile_version="1.0",
        purpose="Deterministic completeness profile for the STM32G431 reference control system.",
        fields=[
            RequirementFieldSpec(
                key="target.device",
                label="Target device",
                value_type=RequirementValueType.TEXT,
                required=True,
                claim_predicate="target.device",
            ),
            RequirementFieldSpec(
                key="target.package",
                label="Target package",
                value_type=RequirementValueType.TEXT,
                required=True,
                claim_predicate="target.package",
            ),
            RequirementFieldSpec(
                key="power.bus_voltage",
                label="Bus voltage",
                value_type=RequirementValueType.ENGINEERING_VALUE,
                engineering_dimension=EngineeringDimension.VOLTAGE,
                required=True,
                evidence_required=True,
                claim_predicate="power.bus-voltage",
            ),
            RequirementFieldSpec(
                key="power.phase_current",
                label="Phase current",
                value_type=RequirementValueType.ENGINEERING_VALUE,
                engineering_dimension=EngineeringDimension.CURRENT,
                required=True,
                evidence_required=True,
                claim_predicate="power.phase-current",
            ),
            RequirementFieldSpec(
                key="control.loop_frequency",
                label="Control loop frequency",
                value_type=RequirementValueType.ENGINEERING_VALUE,
                engineering_dimension=EngineeringDimension.FREQUENCY,
                required=True,
                evidence_required=True,
                claim_predicate="control.loop-frequency",
            ),
            RequirementFieldSpec(
                key="feedback.position_interface",
                label="Position feedback interface",
                value_type=RequirementValueType.ENUM,
                allowed_values=["ABZ", "SPI", "HALL", "NONE"],
                required=True,
                claim_predicate="feedback.position-interface",
            ),
            RequirementFieldSpec(
                key="pwm.phase_count",
                label="Power-stage phase count",
                value_type=RequirementValueType.NUMBER,
                required=True,
                claim_predicate="pwm.phase-count",
            ),
            RequirementFieldSpec(
                key="pwm.complementary",
                label="Complementary switching outputs",
                value_type=RequirementValueType.BOOLEAN,
                required=True,
                claim_predicate="pwm.complementary",
            ),
            RequirementFieldSpec(
                key="pwm.deadtime",
                label="PWM dead time",
                value_type=RequirementValueType.ENGINEERING_VALUE,
                engineering_dimension=EngineeringDimension.TIME,
                required=True,
                evidence_required=True,
                claim_predicate="pwm.deadtime",
            ),
            RequirementFieldSpec(
                key="current_sense.method",
                label="Current-sense method",
                value_type=RequirementValueType.ENUM,
                allowed_values=["SHUNT_LOW_SIDE", "SHUNT_INLINE", "HALL"],
                required=True,
                claim_predicate="current-sense.method",
            ),
            RequirementFieldSpec(
                key="current_sense.range",
                label="Current-sense range",
                value_type=RequirementValueType.ENGINEERING_VALUE,
                engineering_dimension=EngineeringDimension.CURRENT,
                required=True,
                evidence_required=True,
                claim_predicate="current-sense.range",
            ),
            RequirementFieldSpec(
                key="communication.protocol",
                label="Control communication protocol",
                value_type=RequirementValueType.ENUM,
                allowed_values=["CAN", "UART", "SPI"],
                required=True,
                claim_predicate="communication.protocol",
            ),
            RequirementFieldSpec(
                key="safety.emergency_disable",
                label="Emergency disable path",
                value_type=RequirementValueType.BOOLEAN,
                required=True,
                evidence_required=True,
                claim_predicate="safety.emergency-disable",
            ),
        ],
        evidence_contracts=[
            RequirementEvidenceContract(
                key="device_source",
                description="authoritative device/package source",
                allowed_types=[EvidenceType.DOCUMENT, EvidenceType.DEVICE_DB],
            ),
            RequirementEvidenceContract(
                key="power_source",
                description="power-stage electrical source",
                allowed_types=[EvidenceType.DOCUMENT, EvidenceType.USER_CONFIRMATION],
            ),
            RequirementEvidenceContract(
                key="control_timing_source",
                description="control timing and sampling source",
                allowed_types=[EvidenceType.DOCUMENT, EvidenceType.USER_CONFIRMATION],
            ),
            RequirementEvidenceContract(
                key="safety_source",
                description="emergency disable and safe-state source",
                allowed_types=[EvidenceType.DOCUMENT, EvidenceType.USER_CONFIRMATION],
            ),
        ],
        active=True,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
