"""Existing-project import and conservative reverse-engineering primitives.

The import boundary deliberately produces findings and candidates, never
trusted engineering facts.  It reads source bytes and metadata only; build
systems and project scripts are not executed here.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from collections import Counter, defaultdict
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import TypedDict
from urllib.parse import urlparse
from uuid import UUID, uuid5

from eea_adapters.sandbox import SafeArchiveMaterializer
from eea_core.enums import EngineeringErrorCode
from eea_core.errors import EngineeringError
from eea_core.sandbox import SafePath, SandboxPolicy
from eea_core.source import source_file_manifest, source_manifest_hash


class ImportSourceType(StrEnum):
    LOCAL_FOLDER = "LOCAL_FOLDER"
    GIT_REPOSITORY = "GIT_REPOSITORY"
    ARCHIVE = "ARCHIVE"


class ImportStatus(StrEnum):
    CREATED = "CREATED"
    SCANNED = "SCANNED"
    REVIEWED = "REVIEWED"
    WORKSPACE_CREATED = "WORKSPACE_CREATED"
    FAILED = "FAILED"


class ImportReviewAction(StrEnum):
    ACCEPT = "ACCEPT"
    EDIT = "EDIT"
    REJECT = "REJECT"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True, slots=True)
class MaterializationResult:
    root: Path
    resolved_commit: str | None
    source_label: str


class ModuleNode(TypedDict):
    name: str
    files: list[str]
    dependencies: list[str]


_MCU_PATTERN = re.compile(
    r"\b(STM32[A-Z]\d{3,6}[A-Z0-9]*|ATSAMD\w+|ESP32\w*|NRF52\w*)\b", re.I
)
_PIN_PATTERN = re.compile(r"\bP[A-Z]\d{1,2}\b")
_INCLUDE_PATTERN = re.compile(r"^\s*#\s*include\s*[<\"]([^>\"]+)[>\"]", re.M)
_REF_PATTERN = re.compile(r"^[A-Za-z0-9._/@+:-]+$")


def _error(code: EngineeringErrorCode, message: str, **details: object) -> EngineeringError:
    return EngineeringError(code, message, details=details)


def _safe_root(root: Path) -> Path:
    requested = root.absolute()
    if requested.exists() and requested.is_symlink():
        raise _error(
            EngineeringErrorCode.SANDBOX_VIOLATION,
            "Import source root must not be a symlink",
            path=str(requested),
        )
    return requested.resolve(strict=False)


def _run_git(args: list[str], *, cwd: Path | None = None, timeout_seconds: float = 120.0) -> str:
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=cwd,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            shell=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise _error(
            EngineeringErrorCode.CAPABILITY_UNAVAILABLE,
            "Git import could not execute the bounded Git operation",
            operation=args[0] if args else "git",
        ) from exc
    if result.returncode != 0:
        raise _error(
            EngineeringErrorCode.CAPABILITY_UNAVAILABLE,
            "Git import operation failed",
            operation=args[0] if args else "git",
            stderr=result.stderr.strip()[-2000:],
        )
    return result.stdout.strip()


def _validate_git_ref(value: str | None) -> str | None:
    if value is None or not value.strip():
        return None
    candidate = value.strip()
    if candidate.startswith("-") or not _REF_PATTERN.fullmatch(candidate):
        raise _error(EngineeringErrorCode.VALIDATION_ERROR, "Git ref contains unsafe characters")
    return candidate


def _validate_git_source(value: str) -> str:
    candidate = value.strip()
    if not candidate or candidate.startswith("-") or "\x00" in candidate:
        raise _error(EngineeringErrorCode.VALIDATION_ERROR, "Git repository URL is invalid")
    if Path(candidate).exists():
        return candidate
    parsed = urlparse(candidate)
    if parsed.scheme and parsed.scheme not in {"http", "https", "ssh", "git", "file"}:
        raise _error(
            EngineeringErrorCode.VALIDATION_ERROR,
            "Git repository URL scheme is not allowed",
        )
    if parsed.username or parsed.password:
        raise _error(
            EngineeringErrorCode.VALIDATION_ERROR,
            "Git repository credentials must not be embedded in the URL",
        )
    return candidate


def _copy_tree(source: Path, destination: Path, *, preserve_git: bool) -> None:
    source = _safe_root(source)
    if not source.is_dir():
        raise _error(
            EngineeringErrorCode.VALIDATION_ERROR,
            "Import source must be a directory",
            path=str(source),
        )
    destination = _safe_root(destination)
    destination.mkdir(parents=True, exist_ok=True)
    guard = SafePath(destination)
    for current, directories, filenames in os.walk(source, followlinks=False):
        current_path = Path(current)
        relative_dir = current_path.relative_to(source).as_posix()
        kept_directories: list[str] = []
        for name in directories:
            candidate = current_path / name
            if candidate.is_symlink():
                raise _error(
                    EngineeringErrorCode.SANDBOX_VIOLATION,
                    "Import source contains a symlink",
                    path=str(candidate),
                )
            if name == ".eea" or (name == ".git" and not preserve_git):
                continue
            kept_directories.append(name)
            relative = f"{relative_dir}/{name}" if relative_dir != "." else name
            guard.resolve(relative).mkdir(parents=True, exist_ok=True)
        directories[:] = kept_directories
        for name in filenames:
            candidate = current_path / name
            if candidate.is_symlink():
                raise _error(
                    EngineeringErrorCode.SANDBOX_VIOLATION,
                    "Import source contains a symlink",
                    path=str(candidate),
                )
            relative = f"{relative_dir}/{name}" if relative_dir != "." else name
            target = guard.resolve(relative)
            target.parent.mkdir(parents=True, exist_ok=True)
            # Imported bytes are source material, not a mode-preserving
            # checkout.  Keeping Git object files writable is important for
            # a later isolated rescan on Windows.
            shutil.copyfile(candidate, target)


def copy_materialized_tree(source: Path, destination: Path, *, preserve_git: bool) -> None:
    """Copy an already-materialized import into a project-owned workspace."""

    _copy_tree(source, destination, preserve_git=preserve_git)


def materialize_import(
    source_type: ImportSourceType,
    source_locator: Mapping[str, str],
    destination: Path,
    *,
    requested_ref: str | None = None,
) -> MaterializationResult:
    """Materialize source bytes into a new isolated directory.

    Only Git itself is invoked, and only for repository materialization.  No
    imported build, test, install, or post-checkout hook is invoked.
    """

    destination = _safe_root(destination)
    if destination.exists() and any(destination.iterdir()):
        raise _error(
            EngineeringErrorCode.SANDBOX_VIOLATION,
            "Import staging directory must be empty",
            path=str(destination),
        )
    destination.mkdir(parents=True, exist_ok=True)
    if source_type is ImportSourceType.LOCAL_FOLDER:
        source = Path(source_locator.get("path", ""))
        _copy_tree(source, destination, preserve_git=False)
        return MaterializationResult(destination, None, source.name or str(source))
    if source_type is ImportSourceType.ARCHIVE:
        archive = _safe_root(Path(source_locator.get("path", "")))
        if archive.is_symlink() or not archive.is_file():
            raise _error(
                EngineeringErrorCode.ARCHIVE_UNSAFE,
                "Archive must be a regular, non-symlink file",
                path=str(archive),
            )
        SafeArchiveMaterializer().extract(
            archive,
            destination,
            SandboxPolicy(max_archive_bytes=256 * 1024 * 1024, max_member_bytes=64 * 1024 * 1024),
        )
        return MaterializationResult(destination, None, archive.name)
    if source_type is not ImportSourceType.GIT_REPOSITORY:
        raise _error(EngineeringErrorCode.VALIDATION_ERROR, "Unsupported import source type")
    repository = _validate_git_source(source_locator.get("url", ""))
    revision = _validate_git_ref(requested_ref)
    _run_git(
        ["clone", "--no-checkout", "--no-recurse-submodules", "--", repository, str(destination)],
        timeout_seconds=180.0,
    )
    resolved = _run_git(["rev-parse", f"{revision or 'HEAD'}^{{commit}}"], cwd=destination)
    _run_git(["checkout", "--detach", resolved], cwd=destination)
    return MaterializationResult(destination, resolved, repository)


def _finding(
    session_id: UUID,
    key: str,
    *,
    category: str,
    title: str,
    value: object,
    confidence: str,
    source: str,
    evidence: list[str],
    state: str = "CANDIDATE",
) -> dict[str, object]:
    return {
        "id": str(uuid5(session_id, key)),
        "category": category,
        "title": title,
        "value": value,
        "confidence": confidence,
        "source": source,
        "evidence": sorted(set(evidence)),
        "state": state,
        "review_status": "PENDING",
        "review_note": None,
    }


def _text_files(files: Mapping[str, bytes]) -> dict[str, str]:
    result: dict[str, str] = {}
    for path, content in files.items():
        if len(content) > 2 * 1024 * 1024 or b"\x00" in content[:8192]:
            continue
        try:
            result[path] = content.decode("utf-8")
        except UnicodeDecodeError:
            continue
    return result


def scan_import(
    root: Path,
    *,
    session_id: UUID,
    source_type: ImportSourceType,
    resolved_commit: str | None = None,
    scan_revision: int = 1,
) -> dict[str, object]:
    """Scan a materialized tree without executing any imported command."""

    workspace = _safe_root(root)
    files: dict[str, bytes] = {}
    for candidate in workspace.rglob("*"):
        relative_parts = candidate.relative_to(workspace).parts
        if ".git" in relative_parts or ".eea" in relative_parts:
            continue
        if candidate.is_symlink():
            raise _error(
                EngineeringErrorCode.SANDBOX_VIOLATION,
                "Imported workspace contains a symlink",
                path=str(candidate),
            )
        if candidate.is_file():
            relative = candidate.relative_to(workspace).as_posix()
            files[relative] = candidate.read_bytes()
    if len(files) > 50_000:
        raise _error(EngineeringErrorCode.RESOURCE_LIMIT_EXCEEDED, "Import contains too many files")
    text_files = _text_files(files)
    names = set(files)
    findings: list[dict[str, object]] = []
    seen: set[str] = set()

    def add(**kwargs: object) -> None:
        key = f"{kwargs['category']}:{kwargs['title']}:{kwargs['value']}"
        if key not in seen:
            seen.add(key)
            findings.append(_finding(session_id, key, **kwargs))  # type: ignore[arg-type]

    build_detectors = {
        "CMake": [name for name in names if Path(name).name == "CMakeLists.txt"],
        "Makefile": [
            name for name in names if Path(name).name.lower() in {"makefile", "gnumakefile"}
        ],
        "PlatformIO": [name for name in names if Path(name).name == "platformio.ini"],
        "STM32Cube": [name for name in names if name.lower().endswith(".ioc")],
    }
    for build, evidence in build_detectors.items():
        if evidence:
            add(
                category="build",
                title="Build system detected",
                value=build,
                confidence="HIGH",
                source="filename detector",
                evidence=evidence,
            )

    mcu_matches: dict[str, list[str]] = defaultdict(list)
    for path, text in text_files.items():
        for match in _MCU_PATTERN.findall(text):
            mcu_matches[match.upper()].append(path)
    for path, text in text_files.items():
        if path.lower().endswith(".ioc"):
            for match in _MCU_PATTERN.findall(text):
                mcu_matches[match.upper()].append(path)
    for mcu, evidence in sorted(mcu_matches.items()):
        add(
            category="platform",
            title="MCU / SoC detected",
            value=mcu,
            confidence=(
                "HIGH" if any(path.lower().endswith(".ioc") for path in evidence) else "MEDIUM"
            ),
            source="source and configuration scan",
            evidence=evidence,
        )
    if not mcu_matches:
        add(
            category="platform",
            title="MCU / SoC unresolved",
            value="UNKNOWN",
            confidence="LOW",
            source="no authoritative device evidence",
            evidence=[],
            state="UNKNOWN",
        )

    framework_patterns = {
        "STM32 HAL": ("HAL_", "stm32_hal"),
        "STM32 LL": ("LL_", "stm32_ll"),
        "CMSIS": ("CMSIS", "cmsis"),
        "FreeRTOS": ("FreeRTOS", "freertos", "xTaskCreate"),
        "Zephyr": ("zephyr", "CONFIG_SOC_", "k_thread"),
        "DeviceTree": (".dts", "devicetree"),
    }
    for label, patterns in framework_patterns.items():
        evidence = [
            path
            for path, text in text_files.items()
            if any(item.lower() in text.lower() for item in patterns)
        ]
        if label == "DeviceTree":
            evidence.extend(path for path in names if path.lower().endswith((".dts", ".dtsi")))
        if evidence:
            add(
                category="platform",
                title="Framework / RTOS detected",
                value=label,
                confidence="MEDIUM",
                source="source content and file extension detector",
                evidence=evidence,
            )

    generated_markers = ("generated", "autogen", "middlewares", "cube_generated")
    classifications: dict[str, str] = {}
    for path, _content in files.items():
        lower = path.lower()
        if any(marker in lower for marker in generated_markers):
            category = "Generated Source"
        elif any(marker in lower for marker in ("third_party", "third-party", "vendor", "lib/")):
            category = "Third-party"
        elif any(marker in lower for marker in ("build/", "cmakefiles", "compile_commands.json")):
            category = "Build"
        elif lower.endswith(
            (".ioc", ".config", ".ini", ".toml", ".yaml", ".yml", ".json", ".conf")
        ):
            category = "Configuration"
        elif lower.endswith((".kicad_sch", ".kicad_pcb", ".sch", ".brd", ".kicad_pro", ".dbc")):
            category = "Hardware"
        elif lower.endswith((".md", ".rst", ".txt", ".pdf")):
            category = "Documentation"
        elif any(part in lower.split("/") for part in ("test", "tests")) or lower.endswith(
            ("_test.c", "_test.cpp")
        ):
            category = "Tests"
        elif lower.endswith((".c", ".h", ".cc", ".cpp", ".cxx", ".py", ".rs")):
            category = "User Source"
        else:
            category = "Unknown"
        classifications[path] = category

    module_files: dict[str, list[str]] = defaultdict(list)
    for path in files:
        parts = path.split("/")
        module_name = parts[0] if len(parts) > 1 else "root"
        module_files[module_name].append(path)
    module_graph: list[ModuleNode] = [
        {"name": module, "files": sorted(paths), "dependencies": []}
        for module, paths in sorted(module_files.items())
    ]
    modules_by_file = {path: module for module, paths in module_files.items() for path in paths}
    dependency_edges: set[tuple[str, str]] = set()
    for path, text in text_files.items():
        current_module = modules_by_file.get(path, "root")
        for include in _INCLUDE_PATTERN.findall(text):
            matches = [
                candidate for candidate in files if Path(candidate).name == Path(include).name
            ]
            for include_candidate in matches[:10]:
                target_module = modules_by_file.get(include_candidate, "root")
                if target_module != current_module:
                    dependency_edges.add((current_module, target_module))
    for node in module_graph:
        node["dependencies"] = sorted(
            target
            for source, target in dependency_edges
            if source == node["name"]
        )

    resources: Counter[str] = Counter()
    resource_patterns = {
        "GPIO": ("HAL_GPIO", "GPIO_Init", "GPIO_PIN_"),
        "Timer": ("HAL_TIM", "TIM_"),
        "PWM": ("PWM", "HAL_TIM_PWM"),
        "ADC": ("HAL_ADC", "ADC_"),
        "DMA": ("HAL_DMA", "DMA_"),
        "IRQ": ("IRQHandler", "NVIC", "IRQn"),
        "Clock": ("SystemClock", "RCC_", "HAL_RCC"),
        "CAN": ("HAL_CAN", "CAN_", "FDCAN"),
        "UART": ("HAL_UART", "UART_", "USART"),
        "SPI": ("HAL_SPI", "SPI_"),
        "I2C": ("HAL_I2C", "I2C_"),
    }
    for label, patterns in resource_patterns.items():
        resources[label] = sum(
            any(pattern.lower() in text.lower() for pattern in patterns)
            for text in text_files.values()
        )
        if resources[label]:
            evidence = [
                path
                for path, text in text_files.items()
                if any(pattern.lower() in text.lower() for pattern in patterns)
            ]
            add(
                category="resource",
                title="MCU resource detected",
                value={"resource": label, "references": resources[label]},
                confidence="MEDIUM",
                source="source content scan",
                evidence=evidence,
            )

    ioc_paths = [path for path in names if path.lower().endswith(".ioc")]
    ioc_pins = sorted(
        {pin for path in ioc_paths for pin in _PIN_PATTERN.findall(text_files.get(path, ""))}
    )
    source_pins = sorted(
        {
            pin
            for path, text in text_files.items()
            if not path.lower().endswith(".ioc")
            for pin in _PIN_PATTERN.findall(text)
        }
    )
    issues: list[dict[str, object]] = []
    if ioc_pins and source_pins and set(ioc_pins) != set(source_pins):
        issues.append(
            {
                "code": "CONFIG_SOURCE_MISMATCH",
                "severity": "HIGH",
                "title": ".ioc pin configuration differs from source",
                "details": {"configuration_pins": ioc_pins, "source_pins": source_pins},
                "evidence": ioc_paths
                + [
                    path
                    for path in text_files
                    if path not in ioc_paths and _PIN_PATTERN.search(text_files[path])
                ],
                "status": "OPEN",
            }
        )

    hardware_paths = [
        path
        for path in names
        if path.lower().endswith((".kicad_sch", ".kicad_pcb", ".kicad_pro", ".sch", ".brd"))
    ]
    hardware_candidates: list[dict[str, object]] = []
    if hardware_paths:
        hardware_candidates.append(
            {
                "kind": "HardwareIR",
                "status": "CANDIDATE",
                "confidence": "MEDIUM",
                "source": "KiCad file detector",
                "evidence": sorted(hardware_paths),
                "unresolved_fields": ["nets", "component_values", "power_contracts"],
            }
        )
        add(
            category="hardware",
            title="KiCad hardware project detected",
            value="HardwareIR candidate",
            confidence="MEDIUM",
            source="KiCad file detector",
            evidence=hardware_paths,
        )

    protocol_paths = [path for path in names if path.lower().endswith(".dbc")]
    protocol_evidence = protocol_paths + [
        path
        for path, text in text_files.items()
        if re.search(r"\b(CAN|Modbus|EtherCAT|UART)\b", text, re.I)
    ]
    protocol_candidates: list[dict[str, object]] = []
    if protocol_evidence:
        protocol_candidates.append(
            {
                "kind": "ProtocolIR",
                "status": "CANDIDATE",
                "confidence": "MEDIUM",
                "source": "protocol/file content detector",
                "evidence": sorted(set(protocol_evidence)),
                "unresolved_fields": ["message_fields", "serialization", "bitrate"],
            }
        )
        add(
            category="protocol",
            title="Protocol definition detected",
            value="ProtocolIR candidate",
            confidence="MEDIUM",
            source="protocol/file content detector",
            evidence=sorted(set(protocol_evidence)),
        )

    entry_points = sorted(
        path
        for path in names
        if Path(path).name.lower() in {"main.c", "main.cpp", "main.cc", "main.py"}
    )
    if not entry_points:
        entry_points = sorted(
            path
            for path, text in text_files.items()
            if re.search(r"\bint\s+main\s*\(", text)
        )
    if not entry_points:
        add(
            category="architecture",
            title="Entry point unresolved",
            value="UNKNOWN",
            confidence="LOW",
            source="no entry point evidence",
            evidence=[],
            state="UNKNOWN",
        )

    manifest = source_file_manifest(files)
    unknown_count = sum(value == "Unknown" for value in classifications.values())
    summary = {
        "platform": sorted(mcu_matches),
        "build": sorted(build for build, evidence in build_detectors.items() if evidence),
        "rtos": sorted(
            finding["value"]
            for finding in findings
            if finding["category"] == "platform" and finding["title"] == "Framework / RTOS detected"
            and finding["value"] in {"FreeRTOS", "Zephyr"}
        ),
        "hardware": bool(hardware_paths),
        "protocols": sorted(
            {Path(path).suffix.lower() for path in protocol_paths} | {"CAN"}
            if protocol_evidence
            else set()
        ),
        "generated_code": sorted(
            path for path, value in classifications.items() if value == "Generated Source"
        ),
        "entry_points": entry_points,
        "resources": {key: count for key, count in resources.items() if count},
    }
    stages = [
        "Reading files",
        "Detecting build systems",
        "Detecting MCU / SoC",
        "Detecting generated files",
        "Detecting configuration files",
        "Detecting hardware files",
        "Classifying source",
        "Building dependency index",
    ]
    return {
        "scan_revision": scan_revision,
        "source_type": source_type.value,
        "resolved_commit": resolved_commit,
        "file_count": len(files),
        "file_manifest": manifest,
        "source_manifest_hash": source_manifest_hash(manifest),
        "summary": summary,
        "findings": findings,
        "issues": issues,
        "candidates": {"hardware": hardware_candidates, "protocol": protocol_candidates},
        "classifications": classifications,
        "modules": module_graph,
        "dependency_edges": [
            {"source": source, "target": target}
            for source, target in sorted(dependency_edges)
        ],
        "stages": stages,
        "unknown_count": unknown_count + sum(finding["state"] == "UNKNOWN" for finding in findings),
        "build_executed": False,
    }


def apply_review_action(
    findings: list[dict[str, object]],
    finding_id: str,
    action: ImportReviewAction,
    *,
    value: object | None = None,
    note: str | None = None,
) -> list[dict[str, object]]:
    updated = [dict(item) for item in findings]
    for item in updated:
        if item.get("id") != finding_id:
            continue
        if action is ImportReviewAction.EDIT:
            if value is None:
                raise _error(EngineeringErrorCode.VALIDATION_ERROR, "Edit action requires a value")
            item["value"] = value
            item["review_status"] = "EDITED_CANDIDATE"
        elif action is ImportReviewAction.ACCEPT:
            item["review_status"] = "ACCEPTED_CANDIDATE"
        elif action is ImportReviewAction.REJECT:
            item["review_status"] = "REJECTED"
        elif action is ImportReviewAction.UNKNOWN:
            item["state"] = "UNKNOWN"
            item["review_status"] = "MARKED_UNKNOWN"
        item["review_note"] = note
        return updated
    raise _error(
        EngineeringErrorCode.VALIDATION_ERROR,
        "Import finding was not found",
        finding_id=finding_id,
    )


__all__ = [
    "ImportReviewAction",
    "ImportSourceType",
    "ImportStatus",
    "MaterializationResult",
    "apply_review_action",
    "copy_materialized_tree",
    "materialize_import",
    "scan_import",
]
