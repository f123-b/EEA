"""M1 versioned API routes."""

import re
from base64 import b64decode
from binascii import Error as Base64Error
from collections.abc import Iterator
from typing import Annotated, Any, cast
from uuid import UUID

from eea_adapters.devices import Stm32G431FixtureProvider
from eea_application.ai import PromptRegistry, StructuredGenerationService
from eea_application.architecture import ArchitectureService
from eea_application.circuit import CircuitService
from eea_application.components import ComponentMaterializer, ComponentRegistryService
from eea_application.domains import DomainExtensionService
from eea_application.firmware import FirmwareBuildService, FirmwareService
from eea_application.intelligence import DocumentService, MultiSourceDeviceProvider
from eea_application.mcu_config import MCUConfigService
from eea_application.pin_planner import PinPlannerService
from eea_application.projects import ProjectService
from eea_application.requirements import (
    RequirementAnalysisService,
    RequirementProfileRegistry,
)
from eea_application.schematic import SchematicService
from eea_application.static_analysis import FirmwareStaticAnalysisService
from eea_core.architecture import ArchitectureBundle
from eea_core.build import BuildRun
from eea_core.circuit import CircuitBundle
from eea_core.components import (
    ComponentMaterialization,
    DependencyLock,
    SoftwareComponentDescriptor,
)
from eea_core.entities import Evidence, Project
from eea_core.enums import (
    ArtifactStatus,
    ClaimConflictStatus,
    ClaimConflictStrategy,
    ClaimConflictType,
    ClaimLifecycle,
    DecisionStatus,
    DeviceCategory,
    DeviceMergeConflictType,
    DocumentParseStatus,
    DocumentType,
    DomainActivationStatus,
    EngineeringDimension,
    EngineeringErrorCode,
    EvidenceType,
    IssueSeverity,
    IssueStatus,
    JobStatus,
    Permission,
    ProjectStatus,
    RequirementFieldStatus,
    RequirementPriority,
    RequirementStatus,
    RequirementType,
    RequirementValueType,
    StaticAnalysisStatus,
    TraceabilityRelation,
    VerificationLevel,
)
from eea_core.errors import EngineeringError
from eea_core.firmware import FirmwareBundle
from eea_core.intelligence import Device, DevicePin, Document
from eea_core.mcu_config import MCUConfigBundle
from eea_core.pin_planner import PinAssignment, PinLock, PinPlan, PinRequirement
from eea_core.requirements import RequirementProfile
from eea_core.schema_registry import create_core_schema_registry
from eea_core.schematic import SchematicBundle
from eea_core.static_analysis import FirmwareStaticAnalysis
from fastapi import APIRouter, Depends, Header, Request, Response, status
from sqlalchemy.orm import Session

from eea_backend.architecture_repositories import SqlAlchemyArchitectureRepository
from eea_backend.build_repositories import SqlAlchemyBuildRunRepository
from eea_backend.circuit_repositories import SqlAlchemyCircuitRepository
from eea_backend.claim_repositories import SqlAlchemyEngineeringClaimRepository
from eea_backend.component_repositories import (
    SqlAlchemyComponentMaterializationRepository,
    SqlAlchemyComponentRepository,
    SqlAlchemyDependencyLockRepository,
)
from eea_backend.document_repositories import SqlAlchemyDocumentRepository
from eea_backend.domain_repositories import SqlAlchemyDomainActivationRepository
from eea_backend.firmware_repositories import SqlAlchemyFirmwareRepository
from eea_backend.mcu_config_repositories import SqlAlchemyMCUConfigRepository
from eea_backend.pin_planner_repositories import SqlAlchemyPinPlanRepository
from eea_backend.repositories import (
    SqlAlchemyAIUsageRepository,
    SqlAlchemyEvidenceRepository,
    SqlAlchemyProjectRepository,
    SqlAlchemyPromptRepository,
)
from eea_backend.requirement_repositories import (
    SqlAlchemyRequirementAnalysisRepository,
    SqlAlchemyRequirementProfileRepository,
    SqlAlchemyRequirementRepository,
    persist_requirement_analysis_bundle,
)
from eea_backend.schemas import (
    ApiEnvelope,
    ArchitectureBundleData,
    ArchitectureGenerateRequest,
    BuildListData,
    BuildRequest,
    BuildRunData,
    CircuitBundleData,
    CircuitGenerateRequest,
    CircuitValidateRequest,
    CircuitValidationData,
    ComponentCatalogData,
    ComponentDetailData,
    ComponentMaterializationData,
    ComponentMaterializeRequest,
    ComponentReleaseData,
    ComponentResolveRequest,
    DependencyLockData,
    DeviceData,
    DevicePinData,
    DevicePinQueryData,
    DocumentData,
    DocumentUploadRequest,
    DomainActivationData,
    DomainActivationListData,
    DomainActivationRequest,
    DomainArtifactsData,
    DomainAvailableData,
    DomainAvailableListData,
    DomainCompositionData,
    DomainDescriptorData,
    DomainSchemaData,
    DomainUIExtensionsData,
    DomainValidationRequest,
    EnumCatalogData,
    EnumValues,
    ErcImportRequest,
    EvidenceCreateRequest,
    EvidenceData,
    FirmwareBundleData,
    FirmwareGenerateRequest,
    FirmwareStaticAnalysisData,
    MCUConfigBundleData,
    MCUConfigGenerateRequest,
    MCUConfigValidateRequest,
    MCUConfigValidationData,
    PinAssignmentData,
    PinAssignmentMutationData,
    PinAssignmentMutationRequest,
    PinLockData,
    PinPlanData,
    PinPlannerGenerateRequest,
    PinPlanValidationData,
    PinPlanValidationRequest,
    ProjectCreate,
    ProjectData,
    ProjectListData,
    ProjectUpdate,
    RequirementAnalysisData,
    RequirementNaturalLanguageAnalysisRequest,
    RequirementProfileData,
    RequirementStructuredAnalysisRequest,
    SchemaData,
    SchemaDescriptorData,
    SchemaListData,
    SchematicBundleData,
    SchematicGenerateRequest,
    SchematicValidateRequest,
    SoftwareComponentData,
    StaticAnalysisListData,
    StaticAnalysisRequest,
)
from eea_backend.schematic_repositories import SqlAlchemySchematicRepository
from eea_backend.static_analysis_repositories import SqlAlchemyFirmwareStaticAnalysisRepository

router = APIRouter()
schema_registry = create_core_schema_registry()
device_provider = MultiSourceDeviceProvider([Stm32G431FixtureProvider()])
ETAG_PATTERN = re.compile(r'^(?:W/)?"(?P<revision>[1-9][0-9]*)"$')


def get_session(request: Request) -> Iterator[Session]:
    with Session(request.app.state.engine) as session:
        yield session


SessionDependency = Annotated[Session, Depends(get_session)]


def _service(session: Session) -> ProjectService:
    return ProjectService(SqlAlchemyProjectRepository(session))


def _project_data(project: Project) -> ProjectData:
    return ProjectData.model_validate(project, from_attributes=True)


def _document_data(document: Document) -> DocumentData:
    return DocumentData.model_validate(document.model_dump(mode="json"))


def _evidence_data(evidence: Evidence) -> EvidenceData:
    return EvidenceData.model_validate(evidence.model_dump(mode="json"))


def _pin_data(pin: DevicePin) -> DevicePinData:
    return DevicePinData.model_validate(pin.model_dump(mode="json"))


def _device_data(device: Device) -> DeviceData:
    return DeviceData.model_validate(device.model_dump(mode="json"))


def _pin_plan_data(plan: PinPlan) -> PinPlanData:
    return PinPlanData.model_validate(plan.model_dump(mode="json"))


def _pin_assignment_data(assignment: PinAssignment) -> PinAssignmentData:
    return PinAssignmentData.model_validate(assignment.model_dump(mode="json"))


def _pin_lock_data(lock: PinLock | None) -> PinLockData | None:
    if lock is None:
        return None
    return PinLockData.model_validate(lock.model_dump(mode="json"))


def _architecture_bundle_data(bundle: ArchitectureBundle) -> ArchitectureBundleData:
    return ArchitectureBundleData.model_validate(bundle.model_dump(mode="json"))


def _circuit_bundle_data(bundle: CircuitBundle) -> CircuitBundleData:
    return CircuitBundleData.model_validate(bundle.model_dump(mode="json"))


def _schematic_bundle_data(bundle: SchematicBundle) -> SchematicBundleData:
    return SchematicBundleData.model_validate(bundle.model_dump(mode="json"))


def _mcu_config_bundle_data(bundle: MCUConfigBundle) -> MCUConfigBundleData:
    return MCUConfigBundleData.model_validate(bundle.model_dump(mode="json"))


def _firmware_bundle_data(bundle: FirmwareBundle) -> FirmwareBundleData:
    return FirmwareBundleData.model_validate(bundle.model_dump(mode="json"))


def _build_run_data(build: BuildRun) -> BuildRunData:
    return BuildRunData.model_validate(build.model_dump(mode="json"))


def _static_analysis_data(analysis: FirmwareStaticAnalysis) -> FirmwareStaticAnalysisData:
    return FirmwareStaticAnalysisData.model_validate(analysis.model_dump(mode="json"))


def _component_data(
    descriptor: SoftwareComponentDescriptor,
    releases: list[object],
) -> dict[str, object]:
    return {
        "descriptor": descriptor.model_dump(mode="json"),
        "releases": [cast(Any, release).model_dump(mode="json") for release in releases],
    }


def _dependency_lock_data(lock: DependencyLock) -> DependencyLockData:
    return DependencyLockData.model_validate(lock.model_dump(mode="json"))


def _materialization_data(
    materialization: ComponentMaterialization,
) -> ComponentMaterializationData:
    return ComponentMaterializationData.model_validate(materialization.model_dump(mode="json"))


def _domain_service(request: Request, session: Session) -> DomainExtensionService:
    return DomainExtensionService(
        request.app.state.domain_registry,
        SqlAlchemyDomainActivationRepository(session),
        SqlAlchemyProjectRepository(session),
    )


def _domain_descriptor_data(descriptor: object) -> DomainDescriptorData:
    return DomainDescriptorData.model_validate(
        cast(Any, descriptor).model_dump(mode="json", by_alias=True)
    )


def _domain_activation_data(activation: object) -> DomainActivationData:
    return DomainActivationData.model_validate(cast(Any, activation).model_dump(mode="json"))


def _domain_composition_data(composition: object) -> DomainCompositionData:
    return DomainCompositionData.model_validate(cast(Any, composition).model_dump(mode="json"))


def _domain_validation_inputs(
    project_id: UUID, payload: DomainValidationRequest, session: Session
) -> dict[str, object]:
    inputs: dict[str, object] = {}
    if payload.domain_ir is not None:
        inputs["domain_ir"] = payload.domain_ir
    if payload.mcu_config_id is not None:
        bundle = SqlAlchemyMCUConfigRepository(session).get(
            payload.mcu_config_id, project_id=project_id
        )
        if bundle is None:
            raise EngineeringError(
                EngineeringErrorCode.KNOWLEDGE_SCOPE_DENIED,
                "MCUConfigIR is not available for this project",
                details={
                    "mcu_config_id": str(payload.mcu_config_id),
                    "project_id": str(project_id),
                },
            )
        _ensure_current_mcu_config_sources(session, project_id, bundle)
        inputs["mcu_config"] = bundle.config
    return inputs


def _ensure_latest_hardware(session: Session, project_id: UUID, hardware_id: UUID) -> None:
    latest = SqlAlchemyArchitectureRepository(session).latest_for_project(project_id)
    if latest is None:
        raise EngineeringError(
            EngineeringErrorCode.KNOWLEDGE_SCOPE_DENIED,
            "No current HardwareIR is available for schematic generation",
            details={"project_id": str(project_id)},
        )
    if latest.hardware.id != hardware_id:
        raise EngineeringError(
            EngineeringErrorCode.INVALID_REQUIREMENT,
            "Schematic source HardwareIR is stale",
            details={
                "reason": "STALE_HARDWARE_IR",
                "hardware_ir_id": str(hardware_id),
                "latest_hardware_ir_id": str(latest.hardware.id),
            },
        )


def _ensure_current_mcu_config_sources(
    session: Session, project_id: UUID, bundle: MCUConfigBundle
) -> None:
    hardware = SqlAlchemyArchitectureRepository(session).latest_for_project(project_id)
    circuit = SqlAlchemyCircuitRepository(session).latest_for_project(project_id)
    schematic = SqlAlchemySchematicRepository(session).latest_for_project(project_id)
    if hardware is None or circuit is None or schematic is None:
        raise EngineeringError(
            EngineeringErrorCode.KNOWLEDGE_SCOPE_DENIED,
            "MCUConfigIR source snapshots are not available",
            details={"config_id": str(bundle.config.id)},
        )
    config = bundle.config
    if (
        config.hardware_ir_id != hardware.hardware.id
        or config.hardware_ir_revision != hardware.hardware.revision
        or config.circuit_id != circuit.circuit.id
        or config.circuit_revision != circuit.circuit.revision
        or config.schematic_id != schematic.schematic.id
        or config.schematic_revision != schematic.schematic.revision
    ):
        raise EngineeringError(
            EngineeringErrorCode.INVALID_REQUIREMENT,
            "MCUConfigIR source snapshot is stale",
            details={"reason": "STALE_MCU_CONFIG_SOURCE", "config_id": str(config.id)},
        )


def _ensure_current_firmware_mcu_config(
    session: Session, project_id: UUID, bundle: FirmwareBundle
) -> None:
    latest = SqlAlchemyMCUConfigRepository(session).latest_for_project(project_id)
    if latest is None:
        raise EngineeringError(
            EngineeringErrorCode.KNOWLEDGE_SCOPE_DENIED,
            "No current MCUConfigIR is available for firmware generation",
            details={"project_id": str(project_id)},
        )
    if (
        latest.config.id != bundle.firmware.mcu_config_id
        or latest.config.revision != bundle.firmware.mcu_config_revision
    ):
        raise EngineeringError(
            EngineeringErrorCode.INVALID_REQUIREMENT,
            "Firmware source MCUConfigIR is stale",
            details={
                "reason": "STALE_MCU_CONFIG_IR",
                "mcu_config_id": str(bundle.firmware.mcu_config_id),
                "latest_mcu_config_id": str(latest.config.id),
            },
        )


def _requirement_profile_repository(session: Session) -> SqlAlchemyRequirementProfileRepository:
    return SqlAlchemyRequirementProfileRepository(session)


def _requirement_profile_data(profile: RequirementProfile) -> RequirementProfileData:
    return RequirementProfileData.model_validate(profile.model_dump(mode="json"))


def _request_id(request: Request) -> str:
    return str(request.state.request_id)


def _component_providers(request: Request) -> list[object]:
    return list(getattr(request.app.state, "component_providers", []))


def _component_descriptor_data(descriptor: SoftwareComponentDescriptor) -> SoftwareComponentData:
    return SoftwareComponentData.model_validate(descriptor.model_dump(mode="json"))


@router.get("/components", response_model=ApiEnvelope[ComponentCatalogData], tags=["components"])
def list_components(
    request: Request,
    session: SessionDependency,
) -> ApiEnvelope[ComponentCatalogData]:
    providers = _component_providers(request)
    descriptors = SqlAlchemyComponentRepository(session).list_descriptors()
    for provider in providers:
        descriptors.extend(cast(Any, provider).descriptors())
    by_key = {descriptor.component_key: descriptor for descriptor in descriptors}
    data = ComponentCatalogData(
        components=[_component_descriptor_data(by_key[key]) for key in sorted(by_key)]
    )
    return ApiEnvelope(data=data, request_id=_request_id(request))


@router.get(
    "/components/{component_key}",
    response_model=ApiEnvelope[ComponentDetailData],
    tags=["components"],
)
def get_component(
    component_key: str,
    request: Request,
    session: SessionDependency,
) -> ApiEnvelope[ComponentDetailData]:
    descriptor = SqlAlchemyComponentRepository(session).get(component_key)
    releases: list[object] = []
    for provider in _component_providers(request):
        for candidate in cast(Any, provider).descriptors():
            if candidate.component_key == component_key:
                descriptor = candidate
                releases.extend(cast(Any, provider).releases(candidate.id))
    if descriptor is None:
        raise EngineeringError(
            EngineeringErrorCode.COMPONENT_UNAVAILABLE,
            "Software component is not registered.",
            details={"component_key": component_key},
        )
    data = ComponentDetailData(
        descriptor=_component_descriptor_data(descriptor),
        releases=[
            ComponentReleaseData.model_validate(cast(Any, release).model_dump(mode="json"))
            for release in releases
        ],
    )
    return ApiEnvelope(data=data, request_id=_request_id(request))


@router.post(
    "/projects/{project_id}/dependencies/resolve",
    response_model=ApiEnvelope[DependencyLockData],
    status_code=status.HTTP_201_CREATED,
    tags=["components"],
)
def resolve_dependencies(
    project_id: UUID,
    payload: ComponentResolveRequest,
    request: Request,
    session: SessionDependency,
) -> ApiEnvelope[DependencyLockData]:
    _service(session).get(project_id)
    config = SqlAlchemyMCUConfigRepository(session).get(
        payload.mcu_config_id, project_id=project_id
    )
    if config is None:
        raise EngineeringError(
            EngineeringErrorCode.KNOWLEDGE_SCOPE_DENIED,
            "MCUConfigIR is not available for dependency resolution.",
            details={"mcu_config_id": str(payload.mcu_config_id)},
        )
    providers = _component_providers(request)
    if not providers:
        raise EngineeringError(
            EngineeringErrorCode.COMPONENT_UNAVAILABLE,
            "No ESCR component provider is installed.",
        )
    lock = ComponentRegistryService(cast(list[Any], providers)).resolve(
        project_id=project_id,
        mcu_config_id=config.config.id,
        mcu_config_revision=config.config.revision,
        requirements=payload.requirements,
        architecture=payload.architecture,
        device=payload.device,
        toolchain_id=payload.toolchain_id,
        build_system=payload.build_system,
        capabilities=payload.capabilities,
        rtos=payload.rtos,
    )
    saved = SqlAlchemyDependencyLockRepository(session).add(lock)
    return ApiEnvelope(data=_dependency_lock_data(saved), request_id=_request_id(request))


@router.get(
    "/projects/{project_id}/dependencies",
    response_model=ApiEnvelope[DependencyLockData],
    tags=["components"],
)
def get_latest_dependencies(
    project_id: UUID,
    request: Request,
    session: SessionDependency,
) -> ApiEnvelope[DependencyLockData]:
    _service(session).get(project_id)
    lock = SqlAlchemyDependencyLockRepository(session).latest_for_project(project_id)
    if lock is None:
        raise EngineeringError(
            EngineeringErrorCode.DEPENDENCY_LOCK_REQUIRED,
            "No dependency lock exists for this project.",
        )
    return ApiEnvelope(data=_dependency_lock_data(lock), request_id=_request_id(request))


@router.get(
    "/projects/{project_id}/dependency-locks/{lock_id}",
    response_model=ApiEnvelope[DependencyLockData],
    tags=["components"],
)
def get_dependency_lock(
    project_id: UUID,
    lock_id: UUID,
    request: Request,
    session: SessionDependency,
) -> ApiEnvelope[DependencyLockData]:
    _service(session).get(project_id)
    lock = SqlAlchemyDependencyLockRepository(session).get(lock_id, project_id=project_id)
    if lock is None:
        raise EngineeringError(
            EngineeringErrorCode.KNOWLEDGE_SCOPE_DENIED,
            "DependencyLock is not available for this project.",
            details={"lock_id": str(lock_id)},
        )
    return ApiEnvelope(data=_dependency_lock_data(lock), request_id=_request_id(request))


@router.post(
    "/projects/{project_id}/dependencies/materialize",
    response_model=ApiEnvelope[list[ComponentMaterializationData]],
    status_code=status.HTTP_201_CREATED,
    tags=["components"],
)
def materialize_dependencies(
    project_id: UUID,
    payload: ComponentMaterializeRequest,
    request: Request,
    session: SessionDependency,
) -> ApiEnvelope[list[ComponentMaterializationData]]:
    _service(session).get(project_id)
    lock = SqlAlchemyDependencyLockRepository(session).get(payload.lock_id, project_id=project_id)
    if lock is None:
        raise EngineeringError(
            EngineeringErrorCode.DEPENDENCY_LOCK_REQUIRED,
            "DependencyLock is not available for materialization.",
        )
    providers = cast(list[Any], _component_providers(request))
    if not providers:
        raise EngineeringError(
            EngineeringErrorCode.COMPONENT_UNAVAILABLE, "No ESCR provider is installed."
        )
    records = ComponentMaterializer(
        request.app.state.settings.data_dir / "component-cache"
    ).materialize(lock, providers, project_id=project_id)
    repository = SqlAlchemyComponentMaterializationRepository(session)
    saved = [
        repository.add(record.model_copy(update={"project_id": project_id}), commit=False)
        for record in records
    ]
    session.commit()
    return ApiEnvelope(
        data=[_materialization_data(record) for record in saved], request_id=_request_id(request)
    )


def _set_etag(response: Response, revision: int) -> None:
    response.headers["ETag"] = f'W/"{revision}"'


def _expected_revision(if_match: str | None, body_revision: int | None) -> int:
    header_revision: int | None = None
    if if_match is not None:
        match = ETAG_PATTERN.fullmatch(if_match.strip())
        if match is None:
            raise EngineeringError(
                EngineeringErrorCode.VALIDATION_ERROR,
                "If-Match must contain a numeric ETag",
                details={"if_match": if_match},
            )
        header_revision = int(match.group("revision"))
    if (
        header_revision is not None
        and body_revision is not None
        and header_revision != body_revision
    ):
        raise EngineeringError(
            EngineeringErrorCode.VALIDATION_ERROR,
            "If-Match and expected_revision disagree",
        )
    revision = header_revision if header_revision is not None else body_revision
    if revision is None:
        raise EngineeringError(
            EngineeringErrorCode.VALIDATION_ERROR,
            "If-Match or expected_revision is required",
        )
    return revision


@router.get("/meta/enums", response_model=ApiEnvelope[EnumCatalogData], tags=["meta"])
def enums(request: Request) -> ApiEnvelope[EnumCatalogData]:
    catalog = {
        enum_type.__name__: [member.value for member in enum_type]
        for enum_type in (
            ArtifactStatus,
            ClaimConflictStatus,
            ClaimConflictStrategy,
            ClaimConflictType,
            ClaimLifecycle,
            DecisionStatus,
            DeviceCategory,
            DeviceMergeConflictType,
            DocumentParseStatus,
            DocumentType,
            EngineeringDimension,
            EngineeringErrorCode,
            EvidenceType,
            IssueSeverity,
            IssueStatus,
            JobStatus,
            Permission,
            ProjectStatus,
            RequirementFieldStatus,
            RequirementPriority,
            RequirementStatus,
            RequirementType,
            RequirementValueType,
            StaticAnalysisStatus,
            TraceabilityRelation,
            VerificationLevel,
        )
    }
    return ApiEnvelope(
        data=EnumCatalogData(enums=EnumValues.model_validate(catalog)),
        request_id=_request_id(request),
    )


@router.get("/schemas", response_model=ApiEnvelope[SchemaListData], tags=["schemas"])
def schemas(request: Request) -> ApiEnvelope[SchemaListData]:
    items = [
        SchemaDescriptorData(name=item.name, schema_version=item.version)
        for item in schema_registry.list()
    ]
    return ApiEnvelope(data=SchemaListData(items=items), request_id=_request_id(request))


@router.get("/schemas/{schema_name}", response_model=ApiEnvelope[SchemaData], tags=["schemas"])
def schema(schema_name: str, request: Request) -> ApiEnvelope[SchemaData]:
    registration = schema_registry.get(schema_name)
    json_schema = schema_registry.json_schema(schema_name)
    if registration is None or json_schema is None:
        raise EngineeringError(
            EngineeringErrorCode.SCHEMA_VERSION_UNSUPPORTED,
            "Schema is not registered",
            details={"schema_name": schema_name},
        )
    data = SchemaData(
        name=registration.name,
        schema_version=registration.version,
        json_schema=json_schema,
    )
    return ApiEnvelope(data=data, request_id=_request_id(request))


@router.get(
    "/requirement-profiles/{profile_name}/{profile_version}",
    response_model=ApiEnvelope[RequirementProfileData],
    tags=["requirements"],
)
def get_requirement_profile(
    profile_name: str,
    profile_version: str,
    request: Request,
    session: SessionDependency,
) -> ApiEnvelope[RequirementProfileData]:
    profile = _requirement_profile_repository(session).get(profile_name, profile_version)
    if profile is None:
        raise EngineeringError(
            EngineeringErrorCode.SCHEMA_VERSION_UNSUPPORTED,
            "Requirement profile version is not registered",
            details={"profile_name": profile_name, "profile_version": profile_version},
        )
    return ApiEnvelope(data=_requirement_profile_data(profile), request_id=_request_id(request))


@router.post(
    "/projects/{project_id}/pin-planner/generate",
    response_model=ApiEnvelope[PinPlanData],
    status_code=status.HTTP_201_CREATED,
    tags=["pin-planner"],
)
@router.post(
    "/projects/{project_id}/pin-planner/replan",
    response_model=ApiEnvelope[PinPlanData],
    status_code=status.HTTP_201_CREATED,
    tags=["pin-planner"],
)
def generate_pin_plan(
    project_id: UUID,
    payload: PinPlannerGenerateRequest,
    request: Request,
    session: SessionDependency,
) -> ApiEnvelope[PinPlanData]:
    _service(session).get(project_id)
    analysis = SqlAlchemyRequirementAnalysisRepository(session).get(payload.analysis_id)
    if analysis is None or analysis.project_id != project_id:
        raise EngineeringError(
            EngineeringErrorCode.KNOWLEDGE_SCOPE_DENIED,
            "Requirement analysis is not available for this project",
            details={"analysis_id": str(payload.analysis_id), "project_id": str(project_id)},
        )
    canonical_requirement_ids = {
        item.id for item in SqlAlchemyRequirementRepository(session).list_for_project(project_id)
    }
    canonical_claims = SqlAlchemyEngineeringClaimRepository(session)
    for requirement in payload.requirements:
        if not set(requirement.requirement_ids) <= canonical_requirement_ids:
            raise EngineeringError(
                EngineeringErrorCode.INVALID_REQUIREMENT,
                "Pin requirement references a non-canonical requirement",
                details={"signal_name": requirement.signal_name},
            )
        for claim_id in requirement.claim_ids:
            claim = canonical_claims.get(claim_id)
            if claim is None or (claim.project_id is not None and claim.project_id != project_id):
                raise EngineeringError(
                    EngineeringErrorCode.INVALID_REQUIREMENT,
                    "Pin requirement references a non-canonical claim",
                    details={"signal_name": requirement.signal_name},
                )
    pin_requirements = [
        PinRequirement(project_id=project_id, **item.model_dump()) for item in payload.requirements
    ]
    plan = PinPlannerService().plan_from_analysis(
        analysis=analysis,
        device_ref=payload.device_ref,
        package=payload.package,
        requirements=pin_requirements,
        device_provider=device_provider,
    )
    plan = SqlAlchemyPinPlanRepository(session).add(plan)
    return ApiEnvelope(
        data=_pin_plan_data(plan),
        request_id=_request_id(request),
    )


@router.get(
    "/projects/{project_id}/pin-planner/map",
    response_model=ApiEnvelope[PinPlanData],
    tags=["pin-planner"],
)
def get_pin_map(
    project_id: UUID,
    request: Request,
    session: SessionDependency,
) -> ApiEnvelope[PinPlanData]:
    _service(session).get(project_id)
    plan = SqlAlchemyPinPlanRepository(session).latest_for_project(project_id)
    if plan is None:
        raise EngineeringError(
            EngineeringErrorCode.INVALID_REQUIREMENT,
            "No pin plan has been generated for this project",
            details={"project_id": str(project_id)},
        )
    return ApiEnvelope(data=_pin_plan_data(plan), request_id=_request_id(request))


@router.post(
    "/projects/{project_id}/pin-planner/validate",
    response_model=ApiEnvelope[PinPlanValidationData],
    tags=["pin-planner"],
)
def validate_pin_plan(
    project_id: UUID,
    payload: PinPlanValidationRequest,
    request: Request,
    session: SessionDependency,
) -> ApiEnvelope[PinPlanValidationData]:
    _service(session).get(project_id)
    plan = SqlAlchemyPinPlanRepository(session).get(payload.plan_id, project_id=project_id)
    if plan is None:
        raise EngineeringError(
            EngineeringErrorCode.KNOWLEDGE_SCOPE_DENIED,
            "Pin plan is not available for this project",
            details={"plan_id": str(payload.plan_id), "project_id": str(project_id)},
        )
    results = PinPlannerService().validate(plan, device_provider)
    data = PinPlanValidationData(
        plan_id=plan.id,
        plan_revision=plan.revision,
        rule_results=[result.model_dump(mode="json") for result in results],
    )
    return ApiEnvelope(data=data, request_id=_request_id(request))


@router.post(
    "/projects/{project_id}/pin-planner/assignments/{assignment_id}/lock",
    response_model=ApiEnvelope[PinAssignmentMutationData],
    tags=["pin-planner"],
)
def lock_pin_assignment(
    project_id: UUID,
    assignment_id: UUID,
    payload: PinAssignmentMutationRequest,
    request: Request,
    response: Response,
    session: SessionDependency,
    if_match: Annotated[str | None, Header(alias="If-Match")] = None,
) -> ApiEnvelope[PinAssignmentMutationData]:
    _service(session).get(project_id)
    repository = SqlAlchemyPinPlanRepository(session)
    context = repository.get_assignment(assignment_id, project_id=project_id)
    if context is None:
        raise EngineeringError(
            EngineeringErrorCode.KNOWLEDGE_SCOPE_DENIED,
            "Pin assignment is not available for this project",
            details={"assignment_id": str(assignment_id), "project_id": str(project_id)},
        )
    current, _ = context
    expected_revision = _expected_revision(if_match, payload.expected_revision)
    if current.revision != expected_revision:
        raise EngineeringError(
            EngineeringErrorCode.REVISION_CONFLICT,
            "The pin assignment changed after it was read",
            details={"entity_id": str(assignment_id), "expected_revision": expected_revision},
        )
    locked, lock = PinPlannerService().lock_assignment(
        current, locked_by=payload.actor, reason=payload.reason
    )
    saved = repository.save_assignment(locked, expected_revision=expected_revision, commit=False)
    if saved is None:
        session.rollback()
        raise EngineeringError(
            EngineeringErrorCode.REVISION_CONFLICT,
            "The pin assignment changed after it was read",
            details={"entity_id": str(assignment_id), "expected_revision": expected_revision},
        )
    saved_lock = repository.add_lock(lock, commit=False)
    session.commit()
    _set_etag(response, saved.revision)
    return ApiEnvelope(
        data=PinAssignmentMutationData(
            assignment=_pin_assignment_data(saved),
            lock=_pin_lock_data(saved_lock),
        ),
        request_id=_request_id(request),
    )


@router.post(
    "/projects/{project_id}/pin-planner/assignments/{assignment_id}/unlock",
    response_model=ApiEnvelope[PinAssignmentMutationData],
    tags=["pin-planner"],
)
def unlock_pin_assignment(
    project_id: UUID,
    assignment_id: UUID,
    payload: PinAssignmentMutationRequest,
    request: Request,
    response: Response,
    session: SessionDependency,
    if_match: Annotated[str | None, Header(alias="If-Match")] = None,
) -> ApiEnvelope[PinAssignmentMutationData]:
    _service(session).get(project_id)
    repository = SqlAlchemyPinPlanRepository(session)
    context = repository.get_assignment(assignment_id, project_id=project_id)
    if context is None:
        raise EngineeringError(
            EngineeringErrorCode.KNOWLEDGE_SCOPE_DENIED,
            "Pin assignment is not available for this project",
            details={"assignment_id": str(assignment_id), "project_id": str(project_id)},
        )
    current, _ = context
    expected_revision = _expected_revision(if_match, payload.expected_revision)
    if current.revision != expected_revision:
        raise EngineeringError(
            EngineeringErrorCode.REVISION_CONFLICT,
            "The pin assignment changed after it was read",
            details={"entity_id": str(assignment_id), "expected_revision": expected_revision},
        )
    unlocked = PinPlannerService().unlock_assignment(
        current, unlocked_by=payload.actor, reason=payload.reason
    )
    saved = repository.save_assignment(unlocked, expected_revision=expected_revision, commit=False)
    if saved is None:
        session.rollback()
        raise EngineeringError(
            EngineeringErrorCode.REVISION_CONFLICT,
            "The pin assignment changed after it was read",
            details={"entity_id": str(assignment_id), "expected_revision": expected_revision},
        )
    if not repository.release_lock(
        assignment_id,
        project_id=project_id,
        released_by=payload.actor,
        reason=payload.reason,
        commit=False,
    ):
        session.rollback()
        raise EngineeringError(
            EngineeringErrorCode.VALIDATION_ERROR,
            "The active pin lock was not found",
            details={"assignment_id": str(assignment_id)},
        )
    session.commit()
    _set_etag(response, saved.revision)
    return ApiEnvelope(
        data=PinAssignmentMutationData(
            assignment=_pin_assignment_data(saved),
            lock=None,
        ),
        request_id=_request_id(request),
    )


@router.post(
    "/projects/{project_id}/architecture/generate",
    response_model=ApiEnvelope[ArchitectureBundleData],
    status_code=status.HTTP_201_CREATED,
    tags=["architecture"],
)
def generate_architecture(
    project_id: UUID,
    payload: ArchitectureGenerateRequest,
    request: Request,
    session: SessionDependency,
) -> ApiEnvelope[ArchitectureBundleData]:
    _service(session).get(project_id)
    pin_plans = SqlAlchemyPinPlanRepository(session)
    plan = pin_plans.get(payload.pin_plan_id, project_id=project_id)
    latest = pin_plans.latest_for_project(project_id)
    if plan is None or latest is None:
        raise EngineeringError(
            EngineeringErrorCode.KNOWLEDGE_SCOPE_DENIED,
            "Pin plan is not available for architecture generation",
            details={"pin_plan_id": str(payload.pin_plan_id), "project_id": str(project_id)},
        )
    bundle = ArchitectureService().generate(plan, latest_plan_id=latest.id)
    saved = SqlAlchemyArchitectureRepository(session).add(bundle)
    return ApiEnvelope(data=_architecture_bundle_data(saved), request_id=_request_id(request))


@router.get(
    "/projects/{project_id}/architecture",
    response_model=ApiEnvelope[ArchitectureBundleData],
    tags=["architecture"],
)
def get_architecture(
    project_id: UUID,
    request: Request,
    session: SessionDependency,
) -> ApiEnvelope[ArchitectureBundleData]:
    _service(session).get(project_id)
    bundle = SqlAlchemyArchitectureRepository(session).latest_for_project(project_id)
    if bundle is None:
        raise EngineeringError(
            EngineeringErrorCode.INVALID_REQUIREMENT,
            "No architecture has been generated for this project",
            details={"project_id": str(project_id)},
        )
    return ApiEnvelope(data=_architecture_bundle_data(bundle), request_id=_request_id(request))


@router.post(
    "/projects/{project_id}/circuit/generate",
    response_model=ApiEnvelope[CircuitBundleData],
    status_code=status.HTTP_201_CREATED,
    tags=["circuit"],
)
def generate_circuit(
    project_id: UUID,
    payload: CircuitGenerateRequest,
    request: Request,
    session: SessionDependency,
) -> ApiEnvelope[CircuitBundleData]:
    _service(session).get(project_id)
    architectures = SqlAlchemyArchitectureRepository(session)
    selected = architectures.get_by_hardware_id(payload.hardware_ir_id, project_id=project_id)
    latest = architectures.latest_for_project(project_id)
    if selected is None or latest is None:
        raise EngineeringError(
            EngineeringErrorCode.KNOWLEDGE_SCOPE_DENIED,
            "HardwareIR is not available for circuit generation",
            details={"hardware_ir_id": str(payload.hardware_ir_id), "project_id": str(project_id)},
        )
    if selected.hardware.id != latest.hardware.id:
        raise EngineeringError(
            EngineeringErrorCode.INVALID_REQUIREMENT,
            "Selected HardwareIR is stale",
            details={
                "reason": "STALE_HARDWARE_IR",
                "hardware_ir_id": str(payload.hardware_ir_id),
                "latest_hardware_ir_id": str(latest.hardware.id),
            },
        )
    bundle = CircuitService().generate(
        selected.hardware,
        components=payload.components,
        nets=payload.nets,
        power_nets=payload.power_nets,
        constraints=payload.constraints,
    )
    saved = SqlAlchemyCircuitRepository(session).add(bundle)
    SqlAlchemySchematicRepository(session).mark_stale_for_circuit(project_id, saved.circuit.id)
    return ApiEnvelope(data=_circuit_bundle_data(saved), request_id=_request_id(request))


@router.get(
    "/projects/{project_id}/circuit",
    response_model=ApiEnvelope[CircuitBundleData],
    tags=["circuit"],
)
def get_circuit(
    project_id: UUID,
    request: Request,
    session: SessionDependency,
) -> ApiEnvelope[CircuitBundleData]:
    _service(session).get(project_id)
    bundle = SqlAlchemyCircuitRepository(session).latest_for_project(project_id)
    if bundle is None:
        raise EngineeringError(
            EngineeringErrorCode.INVALID_REQUIREMENT,
            "No circuit has been generated for this project",
            details={"project_id": str(project_id)},
        )
    return ApiEnvelope(data=_circuit_bundle_data(bundle), request_id=_request_id(request))


@router.post(
    "/projects/{project_id}/circuit/validate",
    response_model=ApiEnvelope[CircuitValidationData],
    tags=["circuit"],
)
def validate_circuit(
    project_id: UUID,
    payload: CircuitValidateRequest,
    request: Request,
    session: SessionDependency,
) -> ApiEnvelope[CircuitValidationData]:
    _service(session).get(project_id)
    circuits = SqlAlchemyCircuitRepository(session)
    bundle = circuits.get(payload.circuit_id, project_id=project_id)
    if bundle is None:
        raise EngineeringError(
            EngineeringErrorCode.KNOWLEDGE_SCOPE_DENIED,
            "Circuit is not available for this project",
            details={"circuit_id": str(payload.circuit_id), "project_id": str(project_id)},
        )
    architectures = SqlAlchemyArchitectureRepository(session)
    hardware_bundle = architectures.get_by_hardware_id(
        bundle.circuit.hardware_ir_id, project_id=project_id
    )
    latest = architectures.latest_for_project(project_id)
    if hardware_bundle is None or latest is None:
        raise EngineeringError(
            EngineeringErrorCode.KNOWLEDGE_SCOPE_DENIED,
            "Circuit source HardwareIR is not available",
            details={"hardware_ir_id": str(bundle.circuit.hardware_ir_id)},
        )
    if hardware_bundle.hardware.id != latest.hardware.id:
        raise EngineeringError(
            EngineeringErrorCode.INVALID_REQUIREMENT,
            "Circuit source HardwareIR is stale",
            details={
                "reason": "STALE_HARDWARE_IR",
                "hardware_ir_id": str(bundle.circuit.hardware_ir_id),
                "latest_hardware_ir_id": str(latest.hardware.id),
            },
        )
    results = CircuitService().validate(bundle.circuit, hardware_bundle.hardware)
    data = CircuitValidationData(
        circuit_id=bundle.circuit.id,
        circuit_revision=bundle.circuit.revision,
        rule_results=[result.model_dump(mode="json") for result in results],
    )
    return ApiEnvelope(data=data, request_id=_request_id(request))


@router.post(
    "/projects/{project_id}/schematic/generate",
    response_model=ApiEnvelope[SchematicBundleData],
    status_code=status.HTTP_201_CREATED,
    tags=["schematic"],
)
def generate_schematic(
    project_id: UUID,
    payload: SchematicGenerateRequest,
    request: Request,
    session: SessionDependency,
) -> ApiEnvelope[SchematicBundleData]:
    _service(session).get(project_id)
    circuits = SqlAlchemyCircuitRepository(session)
    selected = circuits.get(payload.circuit_id, project_id=project_id)
    latest = circuits.latest_for_project(project_id)
    if selected is None or latest is None:
        raise EngineeringError(
            EngineeringErrorCode.KNOWLEDGE_SCOPE_DENIED,
            "Circuit is not available for schematic generation",
            details={"circuit_id": str(payload.circuit_id), "project_id": str(project_id)},
        )
    if selected.circuit.id != latest.circuit.id:
        raise EngineeringError(
            EngineeringErrorCode.INVALID_REQUIREMENT,
            "Selected CircuitIR is stale",
            details={
                "reason": "STALE_CIRCUIT_IR",
                "circuit_id": str(payload.circuit_id),
                "latest_circuit_id": str(latest.circuit.id),
            },
        )
    _ensure_latest_hardware(session, project_id, selected.circuit.hardware_ir_id)
    bundle = SchematicService().generate(selected.circuit)
    saved = SqlAlchemySchematicRepository(session).add(bundle)
    return ApiEnvelope(data=_schematic_bundle_data(saved), request_id=_request_id(request))


@router.get(
    "/projects/{project_id}/schematic",
    response_model=ApiEnvelope[SchematicBundleData],
    tags=["schematic"],
)
def get_schematic(
    project_id: UUID,
    request: Request,
    session: SessionDependency,
) -> ApiEnvelope[SchematicBundleData]:
    _service(session).get(project_id)
    bundle = SqlAlchemySchematicRepository(session).latest_for_project(project_id)
    if bundle is None:
        raise EngineeringError(
            EngineeringErrorCode.INVALID_REQUIREMENT,
            "No current schematic has been generated for this project",
            details={"project_id": str(project_id)},
        )
    return ApiEnvelope(data=_schematic_bundle_data(bundle), request_id=_request_id(request))


@router.post(
    "/projects/{project_id}/schematic/validate",
    response_model=ApiEnvelope[SchematicBundleData],
    tags=["schematic"],
)
def validate_schematic(
    project_id: UUID,
    payload: SchematicValidateRequest,
    request: Request,
    session: SessionDependency,
) -> ApiEnvelope[SchematicBundleData]:
    _service(session).get(project_id)
    schematics = SqlAlchemySchematicRepository(session)
    bundle = schematics.get(payload.schematic_id, project_id=project_id)
    if bundle is None:
        raise EngineeringError(
            EngineeringErrorCode.KNOWLEDGE_SCOPE_DENIED,
            "Schematic is not available for this project",
            details={"schematic_id": str(payload.schematic_id), "project_id": str(project_id)},
        )
    circuits = SqlAlchemyCircuitRepository(session)
    circuit_bundle = circuits.get(bundle.schematic.circuit_id, project_id=project_id)
    latest = circuits.latest_for_project(project_id)
    if circuit_bundle is None or latest is None:
        raise EngineeringError(
            EngineeringErrorCode.KNOWLEDGE_SCOPE_DENIED,
            "Schematic source CircuitIR is not available",
            details={"circuit_id": str(bundle.schematic.circuit_id)},
        )
    if circuit_bundle.circuit.id != latest.circuit.id:
        raise EngineeringError(
            EngineeringErrorCode.INVALID_REQUIREMENT,
            "Schematic source CircuitIR is stale",
            details={
                "reason": "STALE_CIRCUIT_IR",
                "circuit_id": str(bundle.schematic.circuit_id),
                "latest_circuit_id": str(latest.circuit.id),
            },
        )
    _ensure_latest_hardware(session, project_id, circuit_bundle.circuit.hardware_ir_id)
    report = SchematicService().validate(bundle.schematic, circuit_bundle.circuit)
    schematics.save_erc_report(report)
    refreshed = schematics.get(bundle.schematic.id, project_id=project_id) or bundle
    return ApiEnvelope(data=_schematic_bundle_data(refreshed), request_id=_request_id(request))


@router.post(
    "/projects/{project_id}/schematic/erc/import",
    response_model=ApiEnvelope[SchematicBundleData],
    tags=["schematic"],
)
def import_schematic_erc(
    project_id: UUID,
    payload: ErcImportRequest,
    request: Request,
    session: SessionDependency,
) -> ApiEnvelope[SchematicBundleData]:
    _service(session).get(project_id)
    schematics = SqlAlchemySchematicRepository(session)
    bundle = schematics.get(payload.schematic_id, project_id=project_id)
    if bundle is None:
        raise EngineeringError(
            EngineeringErrorCode.KNOWLEDGE_SCOPE_DENIED,
            "Schematic is not available for this project",
            details={"schematic_id": str(payload.schematic_id), "project_id": str(project_id)},
        )
    circuits = SqlAlchemyCircuitRepository(session)
    circuit_bundle = circuits.get(bundle.schematic.circuit_id, project_id=project_id)
    latest = circuits.latest_for_project(project_id)
    if circuit_bundle is None or latest is None or circuit_bundle.circuit.id != latest.circuit.id:
        raise EngineeringError(
            EngineeringErrorCode.INVALID_REQUIREMENT,
            "Schematic source CircuitIR is stale or unavailable",
            details={"reason": "STALE_CIRCUIT_IR", "circuit_id": str(bundle.schematic.circuit_id)},
        )
    _ensure_latest_hardware(session, project_id, circuit_bundle.circuit.hardware_ir_id)
    report = SchematicService().import_erc(
        bundle.schematic,
        circuit_bundle.circuit,
        status=payload.status,
        tool_name=payload.tool_name,
        tool_version=payload.tool_version,
        issues=payload.issues,
        evidence_ids=payload.evidence_ids,
    )
    schematics.save_erc_report(report)
    refreshed = schematics.get(bundle.schematic.id, project_id=project_id) or bundle
    return ApiEnvelope(data=_schematic_bundle_data(refreshed), request_id=_request_id(request))


@router.post(
    "/projects/{project_id}/mcu-config/generate",
    response_model=ApiEnvelope[MCUConfigBundleData],
    status_code=status.HTTP_201_CREATED,
    tags=["mcu-config"],
)
def generate_mcu_config(
    project_id: UUID,
    payload: MCUConfigGenerateRequest,
    request: Request,
    session: SessionDependency,
) -> ApiEnvelope[MCUConfigBundleData]:
    _service(session).get(project_id)
    architectures = SqlAlchemyArchitectureRepository(session)
    hardware_bundle = architectures.get_by_hardware_id(
        payload.hardware_ir_id, project_id=project_id
    )
    latest_hardware = architectures.latest_for_project(project_id)
    if hardware_bundle is None or latest_hardware is None:
        raise EngineeringError(
            EngineeringErrorCode.KNOWLEDGE_SCOPE_DENIED,
            "HardwareIR is not available for MCUConfigIR generation",
            details={"hardware_ir_id": str(payload.hardware_ir_id), "project_id": str(project_id)},
        )
    if hardware_bundle.hardware.id != latest_hardware.hardware.id:
        raise EngineeringError(
            EngineeringErrorCode.INVALID_REQUIREMENT,
            "Selected HardwareIR is stale",
            details={
                "reason": "STALE_HARDWARE_IR",
                "hardware_ir_id": str(payload.hardware_ir_id),
                "latest_hardware_ir_id": str(latest_hardware.hardware.id),
            },
        )

    circuits = SqlAlchemyCircuitRepository(session)
    circuit_bundle = circuits.get(payload.circuit_id, project_id=project_id)
    latest_circuit = circuits.latest_for_project(project_id)
    if circuit_bundle is None or latest_circuit is None:
        raise EngineeringError(
            EngineeringErrorCode.KNOWLEDGE_SCOPE_DENIED,
            "CircuitIR is not available for MCUConfigIR generation",
            details={"circuit_id": str(payload.circuit_id), "project_id": str(project_id)},
        )
    if circuit_bundle.circuit.id != latest_circuit.circuit.id:
        raise EngineeringError(
            EngineeringErrorCode.INVALID_REQUIREMENT,
            "Selected CircuitIR is stale",
            details={
                "reason": "STALE_CIRCUIT_IR",
                "circuit_id": str(payload.circuit_id),
                "latest_circuit_id": str(latest_circuit.circuit.id),
            },
        )

    schematics = SqlAlchemySchematicRepository(session)
    schematic_bundle = schematics.get(payload.schematic_id, project_id=project_id)
    latest_schematic = schematics.latest_for_project(project_id)
    if schematic_bundle is None or latest_schematic is None:
        raise EngineeringError(
            EngineeringErrorCode.KNOWLEDGE_SCOPE_DENIED,
            "SchematicIR is not available for MCUConfigIR generation",
            details={"schematic_id": str(payload.schematic_id), "project_id": str(project_id)},
        )
    if schematic_bundle.schematic.id != latest_schematic.schematic.id:
        raise EngineeringError(
            EngineeringErrorCode.INVALID_REQUIREMENT,
            "Selected SchematicIR is stale",
            details={
                "reason": "STALE_SCHEMATIC_IR",
                "schematic_id": str(payload.schematic_id),
                "latest_schematic_id": str(latest_schematic.schematic.id),
            },
        )
    bundle = MCUConfigService().generate(
        hardware_bundle.hardware,
        circuit_bundle.circuit,
        schematic_bundle.schematic,
        device_instance_id=payload.device_instance_id,
        clock=payload.clock,
        gpio=payload.gpio,
        peripherals=payload.peripherals,
        dma=payload.dma,
        interrupts=payload.interrupts,
        memory=payload.memory,
        debug=payload.debug,
        capability_snapshot=payload.capability_snapshot,
    )
    saved = SqlAlchemyMCUConfigRepository(session).add(bundle)
    return ApiEnvelope(data=_mcu_config_bundle_data(saved), request_id=_request_id(request))


@router.get(
    "/projects/{project_id}/mcu-config",
    response_model=ApiEnvelope[MCUConfigBundleData],
    tags=["mcu-config"],
)
def get_mcu_config(
    project_id: UUID,
    request: Request,
    session: SessionDependency,
) -> ApiEnvelope[MCUConfigBundleData]:
    _service(session).get(project_id)
    bundle = SqlAlchemyMCUConfigRepository(session).latest_for_project(project_id)
    if bundle is None:
        raise EngineeringError(
            EngineeringErrorCode.INVALID_REQUIREMENT,
            "No current MCUConfigIR has been generated for this project",
            details={"project_id": str(project_id)},
        )
    _ensure_current_mcu_config_sources(session, project_id, bundle)
    return ApiEnvelope(data=_mcu_config_bundle_data(bundle), request_id=_request_id(request))


@router.post(
    "/projects/{project_id}/mcu-config/validate",
    response_model=ApiEnvelope[MCUConfigValidationData],
    tags=["mcu-config"],
)
def validate_mcu_config(
    project_id: UUID,
    payload: MCUConfigValidateRequest,
    request: Request,
    session: SessionDependency,
) -> ApiEnvelope[MCUConfigValidationData]:
    _service(session).get(project_id)
    repository = SqlAlchemyMCUConfigRepository(session)
    bundle = repository.get(payload.config_id, project_id=project_id)
    if bundle is None:
        raise EngineeringError(
            EngineeringErrorCode.KNOWLEDGE_SCOPE_DENIED,
            "MCUConfigIR is not available for this project",
            details={"config_id": str(payload.config_id), "project_id": str(project_id)},
        )
    architectures = SqlAlchemyArchitectureRepository(session)
    hardware_bundle = architectures.get_by_hardware_id(
        bundle.config.hardware_ir_id, project_id=project_id
    )
    circuits = SqlAlchemyCircuitRepository(session)
    circuit_bundle = circuits.get(bundle.config.circuit_id, project_id=project_id)
    schematics = SqlAlchemySchematicRepository(session)
    schematic_bundle = schematics.get(bundle.config.schematic_id, project_id=project_id)
    latest_hardware = architectures.latest_for_project(project_id)
    latest_circuit = circuits.latest_for_project(project_id)
    latest_schematic = schematics.latest_for_project(project_id)
    if (
        hardware_bundle is None
        or circuit_bundle is None
        or schematic_bundle is None
        or latest_hardware is None
        or latest_circuit is None
        or latest_schematic is None
    ):
        raise EngineeringError(
            EngineeringErrorCode.KNOWLEDGE_SCOPE_DENIED,
            "MCUConfigIR source snapshots are not available",
            details={"config_id": str(payload.config_id)},
        )
    if (
        hardware_bundle.hardware.id != latest_hardware.hardware.id
        or circuit_bundle.circuit.id != latest_circuit.circuit.id
        or schematic_bundle.schematic.id != latest_schematic.schematic.id
    ):
        raise EngineeringError(
            EngineeringErrorCode.INVALID_REQUIREMENT,
            "MCUConfigIR source snapshot is stale",
            details={"reason": "STALE_MCU_CONFIG_SOURCE", "config_id": str(payload.config_id)},
        )
    results = MCUConfigService().validate(
        bundle.config,
        hardware_bundle.hardware,
        circuit_bundle.circuit,
        schematic_bundle.schematic,
    )
    data = MCUConfigValidationData(
        config_id=bundle.config.id,
        config_revision=bundle.config.revision,
        rule_results=[result.model_dump(mode="json") for result in results],
    )
    return ApiEnvelope(data=data, request_id=_request_id(request))


@router.post(
    "/projects/{project_id}/firmware/generate",
    response_model=ApiEnvelope[FirmwareBundleData],
    status_code=status.HTTP_201_CREATED,
    tags=["firmware"],
)
def generate_firmware(
    project_id: UUID,
    payload: FirmwareGenerateRequest,
    request: Request,
    session: SessionDependency,
) -> ApiEnvelope[FirmwareBundleData]:
    _service(session).get(project_id)
    configs = SqlAlchemyMCUConfigRepository(session)
    selected = configs.get(payload.mcu_config_id, project_id=project_id)
    latest = configs.latest_for_project(project_id)
    if selected is None or latest is None:
        raise EngineeringError(
            EngineeringErrorCode.KNOWLEDGE_SCOPE_DENIED,
            "MCUConfigIR is not available for firmware generation",
            details={"mcu_config_id": str(payload.mcu_config_id), "project_id": str(project_id)},
        )
    if selected.config.id != latest.config.id:
        raise EngineeringError(
            EngineeringErrorCode.INVALID_REQUIREMENT,
            "Selected MCUConfigIR is stale",
            details={
                "reason": "STALE_MCU_CONFIG_IR",
                "mcu_config_id": str(payload.mcu_config_id),
                "latest_mcu_config_id": str(latest.config.id),
            },
        )
    _ensure_current_mcu_config_sources(session, project_id, selected)
    dependency_lock = None
    if payload.dependency_lock_id is not None:
        dependency_lock = SqlAlchemyDependencyLockRepository(session).get(
            payload.dependency_lock_id, project_id=project_id
        )
        if dependency_lock is None:
            raise EngineeringError(
                EngineeringErrorCode.DEPENDENCY_LOCK_REQUIRED,
                "Requested DependencyLock is not available for this project.",
                details={"lock_id": str(payload.dependency_lock_id)},
            )
    bundle = FirmwareService().generate(
        selected.config,
        build_target=payload.build_target,
        board_name=payload.board_name,
        dependency_lock=dependency_lock,
    )
    saved = SqlAlchemyFirmwareRepository(session).add(bundle)
    return ApiEnvelope(data=_firmware_bundle_data(saved), request_id=_request_id(request))


@router.get(
    "/projects/{project_id}/firmware",
    response_model=ApiEnvelope[FirmwareBundleData],
    tags=["firmware"],
)
def get_firmware(
    project_id: UUID,
    request: Request,
    session: SessionDependency,
) -> ApiEnvelope[FirmwareBundleData]:
    _service(session).get(project_id)
    bundle = SqlAlchemyFirmwareRepository(session).latest_for_project(project_id)
    if bundle is None:
        raise EngineeringError(
            EngineeringErrorCode.INVALID_REQUIREMENT,
            "No current FirmwareIR has been generated for this project",
            details={"project_id": str(project_id)},
        )
    _ensure_current_firmware_mcu_config(session, project_id, bundle)
    return ApiEnvelope(data=_firmware_bundle_data(bundle), request_id=_request_id(request))


@router.post(
    "/projects/{project_id}/build",
    response_model=ApiEnvelope[BuildRunData],
    status_code=status.HTTP_201_CREATED,
    tags=["build"],
)
def build_firmware(
    project_id: UUID,
    payload: BuildRequest,
    request: Request,
    session: SessionDependency,
) -> ApiEnvelope[BuildRunData]:
    _service(session).get(project_id)
    firmwares = SqlAlchemyFirmwareRepository(session)
    bundle = firmwares.get(payload.firmware_id, project_id=project_id)
    latest = firmwares.latest_for_project(project_id)
    if bundle is None or latest is None:
        raise EngineeringError(
            EngineeringErrorCode.KNOWLEDGE_SCOPE_DENIED,
            "FirmwareIR is not available for build",
            details={"firmware_id": str(payload.firmware_id), "project_id": str(project_id)},
        )
    if bundle.firmware.id != latest.firmware.id:
        raise EngineeringError(
            EngineeringErrorCode.INVALID_REQUIREMENT,
            "Selected FirmwareIR is stale",
            details={
                "reason": "STALE_FIRMWARE_IR",
                "firmware_id": str(payload.firmware_id),
                "latest_firmware_id": str(latest.firmware.id),
            },
        )
    _ensure_current_firmware_mcu_config(session, project_id, bundle)
    snapshot, build = FirmwareBuildService().build(
        bundle,
        request.app.state.settings.data_dir / "m12-builds" / str(project_id),
        component_cache_root=request.app.state.settings.data_dir / "component-cache",
    )
    saved = SqlAlchemyBuildRunRepository(session).add(snapshot, build)
    return ApiEnvelope(data=_build_run_data(saved), request_id=_request_id(request))


@router.get(
    "/projects/{project_id}/builds",
    response_model=ApiEnvelope[BuildListData],
    tags=["build"],
)
def list_builds(
    project_id: UUID,
    request: Request,
    session: SessionDependency,
) -> ApiEnvelope[BuildListData]:
    _service(session).get(project_id)
    builds = SqlAlchemyBuildRunRepository(session).list_for_project(project_id)
    return ApiEnvelope(
        data=BuildListData(builds=[_build_run_data(build) for build in builds]),
        request_id=_request_id(request),
    )


@router.get(
    "/projects/{project_id}/builds/{build_id}",
    response_model=ApiEnvelope[BuildRunData],
    tags=["build"],
)
def get_build(
    project_id: UUID,
    build_id: UUID,
    request: Request,
    session: SessionDependency,
) -> ApiEnvelope[BuildRunData]:
    _service(session).get(project_id)
    build = SqlAlchemyBuildRunRepository(session).get(build_id, project_id=project_id)
    if build is None:
        raise EngineeringError(
            EngineeringErrorCode.KNOWLEDGE_SCOPE_DENIED,
            "BuildRun is not available for this project",
            details={"build_id": str(build_id), "project_id": str(project_id)},
        )
    return ApiEnvelope(data=_build_run_data(build), request_id=_request_id(request))


@router.post(
    "/projects/{project_id}/analysis/static",
    response_model=ApiEnvelope[FirmwareStaticAnalysisData],
    status_code=status.HTTP_201_CREATED,
    tags=["analysis"],
)
def analyze_firmware_static(
    project_id: UUID,
    payload: StaticAnalysisRequest,
    request: Request,
    session: SessionDependency,
) -> ApiEnvelope[FirmwareStaticAnalysisData]:
    _service(session).get(project_id)
    firmwares = SqlAlchemyFirmwareRepository(session)
    bundle = firmwares.get(payload.firmware_id, project_id=project_id)
    latest = firmwares.latest_for_project(project_id)
    if bundle is None or latest is None:
        raise EngineeringError(
            EngineeringErrorCode.KNOWLEDGE_SCOPE_DENIED,
            "FirmwareIR is not available for static analysis",
            details={"firmware_id": str(payload.firmware_id), "project_id": str(project_id)},
        )
    if bundle.firmware.id != latest.firmware.id:
        raise EngineeringError(
            EngineeringErrorCode.INVALID_REQUIREMENT,
            "Selected FirmwareIR is stale",
            details={
                "reason": "STALE_FIRMWARE_IR",
                "firmware_id": str(payload.firmware_id),
                "latest_firmware_id": str(latest.firmware.id),
            },
        )
    _ensure_current_firmware_mcu_config(session, project_id, bundle)
    config_bundle = SqlAlchemyMCUConfigRepository(session).get(
        bundle.firmware.mcu_config_id, project_id=project_id
    )
    analysis = FirmwareStaticAnalysisService(
        getattr(request.app.state, "static_analysis_provider", None)
    ).analyze(
        bundle,
        mcu_config=config_bundle.config if config_bundle is not None else None,
        run_cppcheck=payload.run_cppcheck,
    )
    saved = SqlAlchemyFirmwareStaticAnalysisRepository(session).add(analysis)
    return ApiEnvelope(data=_static_analysis_data(saved), request_id=_request_id(request))


@router.get(
    "/projects/{project_id}/analysis/static",
    response_model=ApiEnvelope[StaticAnalysisListData],
    tags=["analysis"],
)
def list_firmware_static_analyses(
    project_id: UUID,
    request: Request,
    session: SessionDependency,
) -> ApiEnvelope[StaticAnalysisListData]:
    _service(session).get(project_id)
    analyses = SqlAlchemyFirmwareStaticAnalysisRepository(session).list_for_project(project_id)
    return ApiEnvelope(
        data=StaticAnalysisListData(
            analyses=[_static_analysis_data(analysis) for analysis in analyses]
        ),
        request_id=_request_id(request),
    )


@router.get(
    "/projects/{project_id}/analysis/static/{analysis_id}",
    response_model=ApiEnvelope[FirmwareStaticAnalysisData],
    tags=["analysis"],
)
def get_firmware_static_analysis(
    project_id: UUID,
    analysis_id: UUID,
    request: Request,
    session: SessionDependency,
) -> ApiEnvelope[FirmwareStaticAnalysisData]:
    _service(session).get(project_id)
    analysis = SqlAlchemyFirmwareStaticAnalysisRepository(session).get(
        analysis_id, project_id=project_id
    )
    if analysis is None:
        raise EngineeringError(
            EngineeringErrorCode.KNOWLEDGE_SCOPE_DENIED,
            "Firmware static analysis is not available for this project",
            details={"analysis_id": str(analysis_id), "project_id": str(project_id)},
        )
    return ApiEnvelope(data=_static_analysis_data(analysis), request_id=_request_id(request))


@router.post(
    "/projects/{project_id}/evidence",
    response_model=ApiEnvelope[EvidenceData],
    status_code=status.HTTP_201_CREATED,
    tags=["evidence"],
)
def register_evidence(
    project_id: UUID,
    payload: EvidenceCreateRequest,
    request: Request,
    session: SessionDependency,
) -> ApiEnvelope[EvidenceData]:
    _service(session).get(project_id)
    evidence = SqlAlchemyEvidenceRepository(session).add(
        Evidence(
            project_id=project_id,
            evidence_type=payload.evidence_type,
            locator=payload.locator,
            source_uri=payload.source_uri,
            content_hash=payload.content_hash,
            summary=payload.summary,
        )
    )
    return ApiEnvelope(data=_evidence_data(evidence), request_id=_request_id(request))


@router.get(
    "/projects/{project_id}/evidence/{evidence_id}",
    response_model=ApiEnvelope[EvidenceData],
    tags=["evidence"],
)
def get_evidence(
    project_id: UUID,
    evidence_id: UUID,
    request: Request,
    session: SessionDependency,
) -> ApiEnvelope[EvidenceData]:
    _service(session).get(project_id)
    repository = SqlAlchemyEvidenceRepository(session)
    evidence = repository.get(evidence_id, project_id=project_id)
    if evidence is None:
        if repository.exists(evidence_id):
            raise EngineeringError(
                EngineeringErrorCode.KNOWLEDGE_SCOPE_DENIED,
                "Evidence belongs to a different project",
                details={"evidence_id": str(evidence_id), "project_id": str(project_id)},
            )
        raise EngineeringError(
            EngineeringErrorCode.INVALID_REQUIREMENT,
            "Evidence was not found",
            details={"evidence_id": str(evidence_id)},
        )
    return ApiEnvelope(data=_evidence_data(evidence), request_id=_request_id(request))


@router.post(
    "/requirements/analyze/structured",
    response_model=ApiEnvelope[RequirementAnalysisData],
    status_code=status.HTTP_201_CREATED,
    tags=["requirements"],
)
def analyze_structured_requirements(
    payload: RequirementStructuredAnalysisRequest,
    request: Request,
    session: SessionDependency,
) -> ApiEnvelope[RequirementAnalysisData]:
    _service(session).get(payload.project_id)
    repository = _requirement_profile_repository(session)
    analysis = RequirementAnalysisService(
        RequirementProfileRegistry(repository),
        evidence_repository=SqlAlchemyEvidenceRepository(session),
    ).analyze_structured(
        project_id=payload.project_id,
        profile_name=payload.profile_name,
        profile_version=payload.profile_version,
        values=payload.values,
        evidence_refs=payload.evidence_refs,
    )
    saved = persist_requirement_analysis_bundle(session, analysis)
    return ApiEnvelope(
        data=RequirementAnalysisData.model_validate(saved.model_dump(mode="json")),
        request_id=_request_id(request),
    )


@router.post(
    "/requirements/analyze/natural-language",
    response_model=ApiEnvelope[RequirementAnalysisData],
    status_code=status.HTTP_201_CREATED,
    tags=["requirements"],
)
async def analyze_natural_language_requirements(
    payload: RequirementNaturalLanguageAnalysisRequest,
    request: Request,
    session: SessionDependency,
) -> ApiEnvelope[RequirementAnalysisData]:
    _service(session).get(payload.project_id)
    repository = _requirement_profile_repository(session)
    provider = getattr(request.app.state, "ai_provider", None)
    generation = None
    if provider is not None:
        generation = StructuredGenerationService(
            provider,
            PromptRegistry(SqlAlchemyPromptRepository(session)),
            SqlAlchemyAIUsageRepository(session),
        )
    analysis = await RequirementAnalysisService(
        RequirementProfileRegistry(repository),
        structured_generation=generation,
        evidence_repository=SqlAlchemyEvidenceRepository(session),
    ).analyze_natural_language(
        project_id=payload.project_id,
        profile_name=payload.profile_name,
        profile_version=payload.profile_version,
        source_text=payload.source_text,
        evidence_refs=payload.evidence_refs,
    )
    saved = persist_requirement_analysis_bundle(session, analysis)
    return ApiEnvelope(
        data=RequirementAnalysisData.model_validate(saved.model_dump(mode="json")),
        request_id=_request_id(request),
    )


@router.post(
    "/projects/{project_id}/documents",
    response_model=ApiEnvelope[DocumentData],
    status_code=status.HTTP_201_CREATED,
    tags=["documents"],
)
def upload_document(
    project_id: UUID,
    payload: DocumentUploadRequest,
    request: Request,
    session: SessionDependency,
) -> ApiEnvelope[DocumentData]:
    _service(session).get(project_id)
    try:
        content = b64decode(payload.content_base64, validate=True)
    except (Base64Error, ValueError):
        raise EngineeringError(
            EngineeringErrorCode.VALIDATION_ERROR,
            "content_base64 is not valid base64",
        ) from None
    document = DocumentService(
        SqlAlchemyDocumentRepository(session), request.app.state.settings.data_dir
    ).upload(
        content,
        filename=payload.filename,
        project_id=project_id,
        document_type=payload.document_type,
        vendor=payload.vendor,
        product=payload.product,
        version_label=payload.version_label,
    )
    return ApiEnvelope(data=_document_data(document), request_id=_request_id(request))


@router.get(
    "/projects/{project_id}/documents/{document_id}",
    response_model=ApiEnvelope[DocumentData],
    tags=["documents"],
)
def get_document(
    project_id: UUID, document_id: UUID, request: Request, session: SessionDependency
) -> ApiEnvelope[DocumentData]:
    _service(session).get(project_id)
    document = DocumentService(
        SqlAlchemyDocumentRepository(session), request.app.state.settings.data_dir
    ).get(document_id, project_id=project_id)
    return ApiEnvelope(data=_document_data(document), request_id=_request_id(request))


@router.get("/devices/{device_ref}", response_model=ApiEnvelope[DeviceData], tags=["devices"])
def get_device(
    device_ref: str,
    request: Request,
    package: str | None = None,
) -> ApiEnvelope[DeviceData]:
    device = device_provider.get_device(device_ref, package=package)
    if device is None:
        raise EngineeringError(
            EngineeringErrorCode.DEVICE_NOT_FOUND,
            "Device or package was not found",
            details={"device_ref": device_ref, "package": package},
        )
    return ApiEnvelope(data=_device_data(device), request_id=_request_id(request))


@router.get(
    "/devices/{device_ref}/pins/{pin_name}",
    response_model=ApiEnvelope[DevicePinQueryData],
    tags=["devices"],
)
def query_device_pin(
    device_ref: str,
    pin_name: str,
    request: Request,
    package: str | None = None,
    peripheral: str | None = None,
    signal: str | None = None,
) -> ApiEnvelope[DevicePinQueryData]:
    pin = device_provider.query_pin(
        device_ref,
        pin_name,
        package=package,
        peripheral=peripheral,
        signal=signal,
    )
    return ApiEnvelope(data=DevicePinQueryData(pin=_pin_data(pin)), request_id=_request_id(request))


@router.post(
    "/projects",
    response_model=ApiEnvelope[ProjectData],
    status_code=status.HTTP_201_CREATED,
    tags=["projects"],
)
def create_project(
    payload: ProjectCreate,
    request: Request,
    response: Response,
    session: SessionDependency,
) -> ApiEnvelope[ProjectData]:
    project = _service(session).create(**payload.model_dump())
    _set_etag(response, project.revision)
    return ApiEnvelope(data=_project_data(project), request_id=_request_id(request))


@router.get("/projects", response_model=ApiEnvelope[ProjectListData], tags=["projects"])
def list_projects(request: Request, session: SessionDependency) -> ApiEnvelope[ProjectListData]:
    items = [_project_data(project) for project in _service(session).list()]
    return ApiEnvelope(data=ProjectListData(items=items), request_id=_request_id(request))


@router.get("/projects/{project_id}", response_model=ApiEnvelope[ProjectData], tags=["projects"])
def get_project(
    project_id: UUID,
    request: Request,
    response: Response,
    session: SessionDependency,
) -> ApiEnvelope[ProjectData]:
    project = _service(session).get(project_id)
    _set_etag(response, project.revision)
    return ApiEnvelope(data=_project_data(project), request_id=_request_id(request))


@router.patch("/projects/{project_id}", response_model=ApiEnvelope[ProjectData], tags=["projects"])
def update_project(
    project_id: UUID,
    payload: ProjectUpdate,
    request: Request,
    response: Response,
    session: SessionDependency,
    if_match: Annotated[str | None, Header(alias="If-Match")] = None,
) -> ApiEnvelope[ProjectData]:
    expected_revision = _expected_revision(if_match, payload.expected_revision)
    changes = payload.model_dump(exclude={"expected_revision"}, exclude_unset=True)
    project = _service(session).update(
        project_id,
        expected_revision=expected_revision,
        **changes,
    )
    _set_etag(response, project.revision)
    return ApiEnvelope(data=_project_data(project), request_id=_request_id(request))


@router.delete("/projects/{project_id}", response_model=ApiEnvelope[ProjectData], tags=["projects"])
def delete_project(
    project_id: UUID,
    request: Request,
    response: Response,
    session: SessionDependency,
    if_match: Annotated[str | None, Header(alias="If-Match")] = None,
    expected_revision: int | None = None,
) -> ApiEnvelope[ProjectData]:
    revision = _expected_revision(if_match, expected_revision)
    project = _service(session).delete(project_id, expected_revision=revision)
    _set_etag(response, project.revision)
    return ApiEnvelope(data=_project_data(project), request_id=_request_id(request))


@router.get(
    "/projects/{project_id}/domains",
    response_model=ApiEnvelope[DomainActivationListData],
    tags=["domains"],
)
def list_domain_activations(
    project_id: UUID, request: Request, session: SessionDependency
) -> ApiEnvelope[DomainActivationListData]:
    items = [
        _domain_activation_data(item)
        for item in _domain_service(request, session).list_activations(project_id)
    ]
    return ApiEnvelope(data=DomainActivationListData(items=items), request_id=_request_id(request))


@router.get(
    "/projects/{project_id}/domains/available",
    response_model=ApiEnvelope[DomainAvailableListData],
    tags=["domains"],
)
def list_available_domains(
    project_id: UUID, request: Request, session: SessionDependency
) -> ApiEnvelope[DomainAvailableListData]:
    available = _domain_service(request, session).available(project_id)
    items = [
        DomainAvailableData(
            descriptor=_domain_descriptor_data(descriptor),
            active=active,
        )
        for descriptor, active in available
    ]
    return ApiEnvelope(data=DomainAvailableListData(items=items), request_id=_request_id(request))


@router.post(
    "/projects/{project_id}/domains/resolve-composition",
    response_model=ApiEnvelope[DomainCompositionData],
    tags=["domains"],
)
def resolve_domain_composition(
    project_id: UUID,
    payload: DomainValidationRequest,
    request: Request,
    session: SessionDependency,
) -> ApiEnvelope[DomainCompositionData]:
    composition = _domain_service(request, session).validate(
        project_id,
        payload.domain_ids,
        selected_capabilities=payload.selected_capabilities,
        validation_inputs=_domain_validation_inputs(project_id, payload, session),
    )
    return ApiEnvelope(data=_domain_composition_data(composition), request_id=_request_id(request))


@router.post(
    "/projects/{project_id}/domains/{domain_id}/activate",
    response_model=ApiEnvelope[DomainActivationData],
    status_code=status.HTTP_201_CREATED,
    tags=["domains"],
)
def activate_domain(
    project_id: UUID,
    domain_id: str,
    payload: DomainActivationRequest,
    request: Request,
    session: SessionDependency,
) -> ApiEnvelope[DomainActivationData]:
    activation = _domain_service(request, session).activate(
        project_id,
        domain_id,
        configuration=payload.configuration,
        activated_by=payload.activated_by,
    )
    return ApiEnvelope(data=_domain_activation_data(activation), request_id=_request_id(request))


@router.post(
    "/projects/{project_id}/domains/{domain_id}/deactivate",
    response_model=ApiEnvelope[DomainActivationData],
    tags=["domains"],
)
def deactivate_domain(
    project_id: UUID,
    domain_id: str,
    request: Request,
    session: SessionDependency,
) -> ApiEnvelope[DomainActivationData]:
    activation = _domain_service(request, session).deactivate(project_id, domain_id)
    return ApiEnvelope(data=_domain_activation_data(activation), request_id=_request_id(request))


@router.get(
    "/projects/{project_id}/domains/{domain_id}/state",
    response_model=ApiEnvelope[DomainActivationData],
    tags=["domains"],
)
def get_domain_state(
    project_id: UUID,
    domain_id: str,
    request: Request,
    session: SessionDependency,
) -> ApiEnvelope[DomainActivationData]:
    activation = _domain_service(request, session).state(project_id, domain_id)
    return ApiEnvelope(data=_domain_activation_data(activation), request_id=_request_id(request))


@router.get(
    "/projects/{project_id}/domains/{domain_id}/schema",
    response_model=ApiEnvelope[DomainSchemaData],
    tags=["domains"],
)
def get_domain_schema(
    project_id: UUID,
    domain_id: str,
    request: Request,
    session: SessionDependency,
) -> ApiEnvelope[DomainSchemaData]:
    service = _domain_service(request, session)
    service.ensure_project(project_id)
    descriptor = service.registry.get_descriptor(domain_id)
    return ApiEnvelope(
        data=DomainSchemaData(
            domain_id=domain_id,
            schema_version=descriptor.schema_version,
            json_schema=service.registry.schema(domain_id),
        ),
        request_id=_request_id(request),
    )


@router.post(
    "/projects/{project_id}/domains/{domain_id}/validate",
    response_model=ApiEnvelope[DomainCompositionData],
    tags=["domains"],
)
def validate_domain_composition(
    project_id: UUID,
    domain_id: str,
    payload: DomainValidationRequest,
    request: Request,
    session: SessionDependency,
) -> ApiEnvelope[DomainCompositionData]:
    service = _domain_service(request, session)
    composition = service.validate(
        project_id,
        [domain_id, *payload.domain_ids],
        selected_capabilities=payload.selected_capabilities,
        validation_inputs=_domain_validation_inputs(project_id, payload, session),
    )
    return ApiEnvelope(data=_domain_composition_data(composition), request_id=_request_id(request))


@router.get(
    "/projects/{project_id}/domains/{domain_id}/artifacts",
    response_model=ApiEnvelope[DomainArtifactsData],
    tags=["domains"],
)
def list_domain_artifacts(
    project_id: UUID,
    domain_id: str,
    request: Request,
    session: SessionDependency,
) -> ApiEnvelope[DomainArtifactsData]:
    service = _domain_service(request, session)
    service.ensure_project(project_id)
    return ApiEnvelope(
        data=DomainArtifactsData(items=service.registry.artifacts(domain_id)),
        request_id=_request_id(request),
    )


@router.get(
    "/projects/{project_id}/ui/extensions",
    response_model=ApiEnvelope[DomainUIExtensionsData],
    tags=["domains"],
)
def list_domain_ui_extensions(
    project_id: UUID, request: Request, session: SessionDependency
) -> ApiEnvelope[DomainUIExtensionsData]:
    service = _domain_service(request, session)
    active = [
        item.domain_id
        for item in service.list_activations(project_id)
        if item.status is DomainActivationStatus.ACTIVE
    ]
    return ApiEnvelope(
        data=DomainUIExtensionsData(items=service.registry.ui_extensions(active)),
        request_id=_request_id(request),
    )
