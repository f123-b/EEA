"""Core-neutral source and build-input snapshots for reproducible builds."""

from uuid import UUID

from pydantic import ConfigDict, Field

from eea_core.entities import EntityBase, Sha256


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
    toolchain_id: str = Field(min_length=1, max_length=200)
    toolchain_version: str = Field(default="UNKNOWN", max_length=200)
    environment_profile_hash: Sha256
    source_manifest_hash: Sha256
    build_input_hash: Sha256


__all__ = ["BuildInputSnapshot", "SourceRevision"]
