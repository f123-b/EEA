"""Core-neutral source authority and build-input snapshots.

Editable source bytes live in the project workspace. These models contain only
immutable snapshots, proposal metadata, and generator ownership metadata; they
do not persist a second editable source tree.
"""

import hashlib
import json
from collections.abc import Mapping
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from eea_core.entities import EntityBase, Sha256
from eea_core.enums import BuildProfile


class SourceRevision(EntityBase):
    """A precise working-tree or committed source snapshot used by a build."""

    model_config = ConfigDict(extra="forbid")

    project_id: UUID
    repository_id: str = Field(min_length=1, max_length=300)
    commit_sha: str | None = Field(default=None, min_length=1, max_length=100)
    tree_hash: Sha256
    dirty: bool
    base_commit: str | None = Field(default=None, min_length=1, max_length=100)
    workspace_revision: int = Field(default=0, ge=0)
    source_manifest_hash: Sha256
    file_manifest: dict[str, Sha256] = Field(default_factory=dict)
    created_by: str = Field(min_length=1, max_length=200)


def source_file_manifest(files: Mapping[str, bytes]) -> dict[str, str]:
    """Return the canonical SHA-256 manifest for source bytes."""

    return {
        path.replace("\\", "/"): hashlib.sha256(files[path]).hexdigest() for path in sorted(files)
    }


def source_manifest_hash(file_manifest: Mapping[str, str]) -> str:
    """Hash a source file manifest using the Source Authority canonical form."""

    payload = json.dumps(
        {key.replace("\\", "/"): file_manifest[key] for key in sorted(file_manifest)},
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


class PatchProposalStatus(StrEnum):
    DRAFT = "DRAFT"
    READY = "READY"
    APPLIED = "APPLIED"
    STALE = "STALE"
    REJECTED = "REJECTED"
    FAILED = "FAILED"


class GeneratedOwnershipStatus(StrEnum):
    ACTIVE = "ACTIVE"
    DIVERGED = "DIVERGED"


class PatchProposal(EntityBase):
    """A reviewable source change; it is not itself a source snapshot."""

    model_config = ConfigDict(extra="forbid")

    project_id: UUID
    base_source_revision_id: UUID
    base_workspace_revision: int = Field(ge=0)
    affected_files: list[str] = Field(min_length=1)
    expected_file_hashes: dict[str, str | None] = Field(default_factory=dict)
    patch: str | None = None
    structured_edits: dict[str, str] = Field(default_factory=dict)
    rationale: str = Field(min_length=1, max_length=20_000)
    evidence_ids: list[UUID] = Field(default_factory=list)
    expected_impact: dict[str, object] = Field(default_factory=dict)
    required_builds: list[str] = Field(default_factory=list)
    required_tests: list[str] = Field(default_factory=list)
    created_by: str = Field(min_length=1, max_length=200)
    status: PatchProposalStatus = PatchProposalStatus.DRAFT
    failure_reason: str | None = Field(default=None, max_length=4000)


class GeneratedSourceCandidate(BaseModel):
    """Generator output awaiting an explicit apply decision."""

    model_config = ConfigDict(extra="forbid")

    id: UUID
    project_id: UUID
    generator_id: str = Field(min_length=1, max_length=200)
    generator_version: str = Field(min_length=1, max_length=100)
    input_hash: Sha256
    files: dict[str, str] = Field(default_factory=dict)
    generated_owned_files: list[str] = Field(default_factory=list)


class SourceWorkspaceStatus(BaseModel):
    """Current workspace metadata returned by the source authority service."""

    model_config = ConfigDict(extra="forbid")

    project_id: UUID
    repository_id: str
    workspace_revision: int = Field(ge=0)
    source_revision_id: UUID
    dirty: bool
    commit_sha: str | None = None
    base_commit: str | None = None
    tree_hash: Sha256
    source_manifest_hash: Sha256
    file_count: int = Field(ge=0)
    generated_owned_paths: list[str] = Field(default_factory=list)


class SourceFileContent(BaseModel):
    """A byte-exact UTF-8 source read with stable optimistic-concurrency data."""

    model_config = ConfigDict(extra="forbid")

    path: str
    content: str
    content_hash: Sha256
    source_revision_id: UUID
    workspace_revision: int = Field(ge=0)
    etag: str


class BuildInputSnapshot(EntityBase):
    """Frozen hashes for every declared input participating in one build."""

    model_config = ConfigDict(extra="forbid")

    project_id: UUID
    source_revision_id: UUID
    tracked_file_manifest_hash: Sha256
    allowed_untracked_input_hash: Sha256
    generated_input_hash: Sha256
    submodule_commit_map: dict[str, str] = Field(default_factory=dict)
    build_config_hash: Sha256
    build_profile: BuildProfile = BuildProfile.HOST_SMOKE
    toolchain_id: str = Field(min_length=1, max_length=200)
    toolchain_version: str = Field(default="UNKNOWN", max_length=200)
    environment_profile_hash: Sha256
    source_manifest_hash: Sha256
    dependency_lock_hash: Sha256
    component_manifest_hash: Sha256
    toolchain_manifest_hash: Sha256 | None = None
    build_input_hash: Sha256


__all__ = [
    "BuildInputSnapshot",
    "GeneratedOwnershipStatus",
    "GeneratedSourceCandidate",
    "PatchProposal",
    "PatchProposalStatus",
    "SourceFileContent",
    "SourceRevision",
    "SourceWorkspaceStatus",
    "source_file_manifest",
    "source_manifest_hash",
]
