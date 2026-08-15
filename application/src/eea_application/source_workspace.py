"""Source Authority application service.

All editable source bytes cross this service through ``SourceWorkspacePort``.
Database adapters persist only source metadata and recovery state.
"""

from __future__ import annotations

import difflib
import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from threading import Lock
from typing import ClassVar, Protocol
from uuid import UUID

from eea_core.enums import EngineeringErrorCode
from eea_core.errors import EngineeringError
from eea_core.reliability import stable_event_key
from eea_core.source import (
    GeneratedOwnershipStatus,
    GeneratedSourceCandidate,
    PatchProposal,
    PatchProposalStatus,
    SourceFileContent,
    SourceRevision,
    SourceWorkspaceStatus,
)
from eea_ports.source import GitStatus, GitWorkspacePort, SourceWorkspacePort


@dataclass(frozen=True, slots=True)
class SourceWorkspaceState:
    project_id: UUID
    repository_id: str
    root_path: str
    current_source_revision_id: UUID | None
    workspace_revision: int
    base_commit: str | None


@dataclass(frozen=True, slots=True)
class GeneratedOwnership:
    project_id: UUID
    path: str
    generator_id: str
    generator_version: str
    input_hash: str
    content_hash: str
    status: GeneratedOwnershipStatus


class SourceWorkspaceRepository(Protocol):
    def ensure_workspace(self, project_id: UUID, root_path: str) -> SourceWorkspaceState: ...

    def get_workspace(self, project_id: UUID) -> SourceWorkspaceState | None: ...

    def current_revision(self, project_id: UUID) -> SourceRevision | None: ...

    def get_revision(
        self, revision_id: UUID, *, project_id: UUID | None = None
    ) -> SourceRevision | None: ...

    def save_revision(self, revision: SourceRevision, *, commit: bool = True) -> SourceRevision: ...

    def set_current_revision(
        self,
        project_id: UUID,
        revision_id: UUID,
        *,
        workspace_revision: int,
        base_commit: str | None,
        expected_current_revision_id: UUID | None = None,
        expected_workspace_revision: int | None = None,
        commit: bool = True,
    ) -> None: ...

    def save_proposal(self, proposal: PatchProposal, *, commit: bool = True) -> PatchProposal: ...

    def get_proposal(
        self, proposal_id: UUID, *, project_id: UUID | None = None
    ) -> PatchProposal | None: ...

    def update_proposal(self, proposal: PatchProposal, *, commit: bool = True) -> PatchProposal: ...

    def list_ownership(self, project_id: UUID) -> list[GeneratedOwnership]: ...

    def get_ownership(self, project_id: UUID, path: str) -> GeneratedOwnership | None: ...

    def save_ownership(
        self, ownership: GeneratedOwnership, *, commit: bool = True
    ) -> GeneratedOwnership: ...

    def commit(self) -> None: ...

    def rollback(self) -> None: ...

    def begin_source_journal(
        self,
        project_id: UUID,
        proposal_id: UUID,
        previous_source_revision_id: UUID,
        affected_files: list[str],
    ) -> UUID: ...

    def finish_source_journal(self, journal_id: UUID, status: str) -> None: ...

    def recover_source_journals(self, project_id: UUID, workspace_revision: int) -> int: ...


class SourceChangedPublisher(Protocol):
    def enqueue(
        self,
        *,
        event_type: str,
        aggregate_type: str,
        aggregate_id: str,
        aggregate_revision: int | None,
        event_key: str,
        payload: dict[str, object],
        payload_hash: str,
        project_id: UUID | None = None,
        commit: bool = True,
    ) -> object: ...


def _hash_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _hash_manifest(manifest: Mapping[str, str]) -> str:
    serialized = json.dumps(
        {key: manifest[key] for key in sorted(manifest)},
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return _hash_bytes(serialized)


def _manifest(files: Mapping[str, bytes]) -> dict[str, str]:
    return {path: _hash_bytes(files[path]) for path in sorted(files)}


class SourceWorkspaceService:
    """Own source reads, proposals, atomic apply, reconcile, and Git commits."""

    _mutation_locks: ClassVar[dict[UUID, Lock]] = {}
    _mutation_locks_guard: ClassVar[Lock] = Lock()

    def __init__(
        self,
        project_id: UUID,
        repository: SourceWorkspaceRepository,
        workspace: SourceWorkspacePort,
        *,
        git: GitWorkspacePort | None = None,
        source_changed: SourceChangedPublisher | None = None,
    ) -> None:
        self.project_id = project_id
        self.repository = repository
        self.workspace = workspace
        self.git = git
        self.source_changed = source_changed

    def _mutation_lock(self) -> Lock:
        with self._mutation_locks_guard:
            lock = self._mutation_locks.get(self.project_id)
            if lock is None:
                lock = Lock()
                self._mutation_locks[self.project_id] = lock
            return lock

    def _git_status(self) -> GitStatus:
        if self.git is not None:
            return self.git.status()
        return GitStatus(
            repository_id=f"workspace:{self.workspace.root}",
            commit_sha=None,
            base_commit=None,
            branch=None,
            dirty=True,
        )

    def _snapshot(
        self,
        files: Mapping[str, bytes],
        *,
        workspace_revision: int,
        created_by: str,
        git_status: GitStatus,
    ) -> SourceRevision:
        file_manifest = _manifest(files)
        manifest_hash = _hash_manifest(file_manifest)
        return SourceRevision(
            project_id=self.project_id,
            repository_id=git_status.repository_id,
            commit_sha=git_status.commit_sha,
            tree_hash=manifest_hash,
            dirty=git_status.dirty or git_status.commit_sha is None,
            base_commit=git_status.base_commit,
            workspace_revision=workspace_revision,
            source_manifest_hash=manifest_hash,
            file_manifest=file_manifest,
            created_by=created_by,
        )

    def _publish_change(self, before: SourceRevision | None, after: SourceRevision) -> None:
        if before is None or self.source_changed is None:
            return
        payload = {
            "project_id": str(self.project_id),
            "previous_source_revision_id": str(before.id),
            "source_revision_id": str(after.id),
            "workspace_revision": after.workspace_revision,
            "source_manifest_hash": after.source_manifest_hash,
            "file_manifest": after.file_manifest,
        }
        from eea_core.reliability import payload_sha256

        self.source_changed.enqueue(
            event_type="source.changed",
            aggregate_type="SourceRevision",
            aggregate_id=str(after.id),
            aggregate_revision=after.revision,
            event_key=stable_event_key(
                "source.changed", "SourceRevision", after.id, after.revision
            ),
            payload=payload,
            payload_hash=payload_sha256(payload),
            project_id=self.project_id,
            commit=False,
        )

    def _persist_snapshot(
        self,
        before: SourceRevision | None,
        after: SourceRevision,
        *,
        emit_event: bool = True,
    ) -> SourceRevision:
        self.repository.save_revision(after, commit=False)
        self.repository.set_current_revision(
            self.project_id,
            after.id,
            workspace_revision=after.workspace_revision,
            base_commit=after.base_commit,
            expected_current_revision_id=before.id if before is not None else None,
            expected_workspace_revision=before.workspace_revision if before is not None else 0,
            commit=False,
        )
        if emit_event:
            self._publish_change(before, after)
        self.repository.commit()
        return after

    def _reconcile(self, *, created_by: str = "eea:source-reconcile") -> SourceRevision:
        self.workspace.cleanup_temporary()
        self.workspace.ensure_exists()
        state = self.repository.ensure_workspace(self.project_id, str(self.workspace.root))
        current = self.repository.current_revision(self.project_id)
        files = self.workspace.list_files()
        git_status = self._git_status()
        candidate = self._snapshot(
            files,
            workspace_revision=(
                current.workspace_revision + 1 if current else state.workspace_revision
            ),
            created_by=created_by,
            git_status=git_status,
        )
        if current is None:
            result = self._persist_snapshot(None, candidate, emit_event=False)
        elif (
            current.file_manifest != candidate.file_manifest
            or current.commit_sha != candidate.commit_sha
            or current.dirty != candidate.dirty
            or current.base_commit != candidate.base_commit
        ):
            result = self._persist_snapshot(current, candidate)
        else:
            result = current
        recover_journals = getattr(self.repository, "recover_source_journals", None)
        if recover_journals is not None:
            recover_journals(self.project_id, result.workspace_revision)
            self.repository.commit()
        return result

    def reconcile(self, *, created_by: str = "eea:source-reconcile") -> SourceRevision:
        """Reconcile real workspace bytes after an interrupted FS/SQL boundary."""

        return self._reconcile(created_by=created_by)

    def current_revision(self) -> SourceRevision:
        return self._reconcile()

    def status(self) -> SourceWorkspaceStatus:
        revision = self._reconcile()
        ownership = self.repository.list_ownership(self.project_id)
        return SourceWorkspaceStatus(
            project_id=self.project_id,
            repository_id=revision.repository_id,
            workspace_revision=revision.workspace_revision,
            source_revision_id=revision.id,
            dirty=revision.dirty,
            commit_sha=revision.commit_sha,
            base_commit=revision.base_commit,
            tree_hash=revision.tree_hash,
            source_manifest_hash=revision.source_manifest_hash,
            file_count=len(revision.file_manifest),
            generated_owned_paths=sorted(
                item.path for item in ownership if item.status is GeneratedOwnershipStatus.ACTIVE
            ),
        )

    def read_file(self, path: str, *, if_match: str | None = None) -> SourceFileContent:
        revision = self._reconcile()
        try:
            content = self.workspace.read_bytes(path)
        except EngineeringError:
            raise
        content_hash = _hash_bytes(content)
        expected = revision.file_manifest.get(path.replace("\\", "/"))
        if expected != content_hash:
            revision = self._reconcile(created_by="eea:source-read-reconcile")
        if if_match is not None and if_match.strip('W/"') != content_hash:
            raise EngineeringError(
                EngineeringErrorCode.SOURCE_REVISION_CONFLICT,
                "Source file ETag does not match the current content",
                details={"path": path, "expected": if_match, "actual": content_hash},
            )
        try:
            text = content.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise EngineeringError(
                EngineeringErrorCode.VALIDATION_ERROR,
                "Source file is not valid UTF-8 text",
                details={"path": path},
            ) from exc
        return SourceFileContent(
            path=path.replace("\\", "/"),
            content=text,
            content_hash=content_hash,
            source_revision_id=revision.id,
            workspace_revision=revision.workspace_revision,
            etag=f'"{content_hash}"',
        )

    @staticmethod
    def _parse_unified_patch(patch: str, current: Mapping[str, bytes]) -> dict[str, bytes]:
        try:
            decoded = json.loads(patch)
        except json.JSONDecodeError:
            decoded = None
        if isinstance(decoded, dict) and all(isinstance(key, str) for key in decoded):
            structured_result: dict[str, bytes] = {}
            for path, value in decoded.items():
                if not isinstance(value, str):
                    raise EngineeringError(
                        EngineeringErrorCode.VALIDATION_ERROR,
                        "Structured patch values must be strings",
                    )
                structured_result[path] = value.encode("utf-8")
            return structured_result
        lines = patch.splitlines(keepends=True)
        result: dict[str, bytes] = {}
        index = 0
        while index < len(lines):
            if not lines[index].startswith("--- "):
                index += 1
                continue
            if index + 1 >= len(lines) or not lines[index + 1].startswith("+++ "):
                raise EngineeringError(
                    EngineeringErrorCode.VALIDATION_ERROR, "Malformed unified patch"
                )
            path = lines[index + 1][4:].strip().split("\t", 1)[0]
            path = path[2:] if path.startswith("b/") else path
            original = current.get(path, b"").decode("utf-8").splitlines(keepends=True)
            output: list[str] = []
            source_index = 0
            index += 2
            while index < len(lines) and not lines[index].startswith("--- "):
                header = lines[index]
                if not header.startswith("@@"):
                    index += 1
                    continue
                try:
                    old_start = int(header.split(" ", 2)[1].split(",", 1)[0][1:])
                except (IndexError, ValueError) as exc:
                    raise EngineeringError(
                        EngineeringErrorCode.VALIDATION_ERROR,
                        "Malformed unified patch hunk",
                    ) from exc
                output.extend(original[source_index : old_start - 1])
                source_index = old_start - 1
                index += 1
                while index < len(lines) and not lines[index].startswith(("@@", "--- ")):
                    item = lines[index]
                    if item.startswith(" "):
                        expected = item[1:]
                        if source_index >= len(original) or original[source_index] != expected:
                            raise EngineeringError(
                                EngineeringErrorCode.SOURCE_REVISION_CONFLICT,
                                "Unified patch context does not match the workspace",
                                details={"path": path},
                            )
                        output.append(expected)
                        source_index += 1
                    elif item.startswith("-"):
                        expected = item[1:]
                        if source_index >= len(original) or original[source_index] != expected:
                            raise EngineeringError(
                                EngineeringErrorCode.SOURCE_REVISION_CONFLICT,
                                "Unified patch removal does not match the workspace",
                                details={"path": path},
                            )
                        source_index += 1
                    elif item.startswith("+"):
                        output.append(item[1:])
                    elif item.startswith("\\"):
                        pass
                    index += 1
            output.extend(original[source_index:])
            result[path] = "".join(output).encode("utf-8")
        if not result:
            raise EngineeringError(EngineeringErrorCode.VALIDATION_ERROR, "Patch contains no files")
        return result

    def create_proposal(
        self,
        *,
        base_source_revision_id: UUID,
        base_workspace_revision: int,
        affected_files: Sequence[str],
        rationale: str,
        created_by: str,
        expected_file_hashes: Mapping[str, str | None] | None = None,
        patch: str | None = None,
        structured_edits: Mapping[str, str] | None = None,
        evidence_ids: Sequence[UUID] = (),
        expected_impact: Mapping[str, object] | None = None,
        required_builds: Sequence[str] = (),
        required_tests: Sequence[str] = (),
    ) -> PatchProposal:
        current = self._reconcile()
        if base_source_revision_id != current.id:
            # A proposal may be recorded against a historical revision, but it
            # must be visibly stale and can never be applied silently.
            status = PatchProposalStatus.STALE
        else:
            status = PatchProposalStatus.DRAFT
        paths = [path.replace("\\", "/") for path in affected_files]
        if not paths:
            raise EngineeringError(
                EngineeringErrorCode.VALIDATION_ERROR, "affected_files is required"
            )
        expected = dict(expected_file_hashes or {})
        for path in paths:
            if path not in expected:
                expected[path] = current.file_manifest.get(path)
        proposal = PatchProposal(
            project_id=self.project_id,
            base_source_revision_id=base_source_revision_id,
            base_workspace_revision=base_workspace_revision,
            affected_files=paths,
            expected_file_hashes=expected,
            patch=patch,
            structured_edits=dict(structured_edits or {}),
            rationale=rationale,
            evidence_ids=list(evidence_ids),
            expected_impact=dict(expected_impact or {}),
            required_builds=list(required_builds),
            required_tests=list(required_tests),
            created_by=created_by,
            status=status,
        )
        return self.repository.save_proposal(proposal)

    def get_proposal(self, proposal_id: UUID) -> PatchProposal:
        proposal = self.repository.get_proposal(proposal_id, project_id=self.project_id)
        if proposal is None:
            raise EngineeringError(
                EngineeringErrorCode.PATCH_PROPOSAL_NOT_FOUND,
                "Patch proposal was not found for this project",
                details={"proposal_id": str(proposal_id)},
            )
        return proposal

    def diff(self, proposal_id: UUID) -> str:
        proposal = self.get_proposal(proposal_id)
        current_files = self.workspace.list_files()
        proposed = dict(proposal.structured_edits)
        if proposal.patch and not proposed:
            try:
                proposed_bytes = self._parse_unified_patch(proposal.patch, current_files)
            except EngineeringError:
                proposed_bytes = {}
            proposed.update(
                {path: content.decode("utf-8") for path, content in proposed_bytes.items()}
            )
        chunks: list[str] = []
        for path in sorted(proposal.affected_files):
            before = current_files.get(path, b"").decode("utf-8").splitlines(keepends=True)
            after = proposed.get(path, "").splitlines(keepends=True)
            chunks.extend(
                difflib.unified_diff(
                    before,
                    after,
                    fromfile=f"a/{path}",
                    tofile=f"b/{path}",
                )
            )
        return "".join(chunks)

    def _mark_stale(self, proposal: PatchProposal, reason: str) -> None:
        self.repository.update_proposal(
            proposal.model_copy(
                update={"status": PatchProposalStatus.STALE, "failure_reason": reason}
            )
        )

    def apply(
        self,
        proposal_id: UUID,
        *,
        expected_source_revision_id: UUID | None = None,
        expected_workspace_revision: int | None = None,
    ) -> tuple[PatchProposal, SourceRevision]:
        with self._mutation_lock():
            return self._apply_locked(
                proposal_id,
                expected_source_revision_id=expected_source_revision_id,
                expected_workspace_revision=expected_workspace_revision,
            )

    def _apply_locked(
        self,
        proposal_id: UUID,
        *,
        expected_source_revision_id: UUID | None = None,
        expected_workspace_revision: int | None = None,
    ) -> tuple[PatchProposal, SourceRevision]:
        proposal = self.get_proposal(proposal_id)
        current = self._reconcile(created_by="eea:source-apply-reconcile")
        expected_revision = expected_source_revision_id or proposal.base_source_revision_id
        expected_workspace = (
            expected_workspace_revision
            if expected_workspace_revision is not None
            else proposal.base_workspace_revision
        )
        if (
            proposal.status not in {PatchProposalStatus.DRAFT, PatchProposalStatus.READY}
            or expected_revision != current.id
            or expected_workspace != current.workspace_revision
        ):
            self._mark_stale(proposal, "SourceRevision or workspace revision no longer matches")
            raise EngineeringError(
                EngineeringErrorCode.SOURCE_REVISION_CONFLICT,
                "Patch proposal is stale and cannot be applied",
                details={
                    "proposal_id": str(proposal.id),
                    "status": PatchProposalStatus.STALE.value,
                },
            )
        files = self.workspace.list_files()
        for path in proposal.affected_files:
            actual = _hash_bytes(files[path]) if path in files else None
            if actual != proposal.expected_file_hashes.get(path):
                self._mark_stale(proposal, f"Expected content hash does not match {path}")
                raise EngineeringError(
                    EngineeringErrorCode.SOURCE_REVISION_CONFLICT,
                    "Patch proposal content hash is stale",
                    details={
                        "path": path,
                        "expected": proposal.expected_file_hashes.get(path),
                        "actual": actual,
                    },
                )
        updates: dict[str, bytes] = {
            path: value.encode("utf-8") for path, value in proposal.structured_edits.items()
        }
        if proposal.patch and not updates:
            updates = self._parse_unified_patch(proposal.patch, files)
        if not updates or set(updates) != set(proposal.affected_files):
            raise EngineeringError(
                EngineeringErrorCode.VALIDATION_ERROR,
                "Patch proposal affected_files and edit payload do not match",
            )
        journal_id: UUID | None = None
        begin_journal = getattr(self.repository, "begin_source_journal", None)
        if begin_journal is not None:
            journal_id = begin_journal(
                self.project_id,
                proposal.id,
                current.id,
                proposal.affected_files,
            )
            self.repository.commit()
        try:
            self.workspace.atomic_replace(updates)
        except Exception:
            if journal_id is not None:
                self.repository.finish_source_journal(journal_id, "ROLLED_BACK")
                self.repository.commit()
            raise
        try:
            after = self._snapshot(
                self.workspace.list_files(),
                workspace_revision=current.workspace_revision + 1,
                created_by=f"patch:{proposal.id}",
                git_status=self._git_status(),
            )
            applied = proposal.model_copy(
                update={"status": PatchProposalStatus.APPLIED, "failure_reason": None}
            )
            self.repository.update_proposal(applied, commit=False)
            if journal_id is not None:
                self.repository.finish_source_journal(journal_id, "COMPLETED")
            self._persist_snapshot(current, after)
            return applied, after
        except Exception:
            self.repository.rollback()
            # The filesystem is intentionally left for startup reconciliation;
            # DB rollback must never pretend the bytes were not changed.
            raise

    def commit(
        self, *, expected_source_revision_id: UUID, message: str, actor: str
    ) -> SourceRevision:
        current = self._reconcile(created_by="eea:source-commit-reconcile")
        if current.id != expected_source_revision_id:
            raise EngineeringError(
                EngineeringErrorCode.SOURCE_REVISION_CONFLICT,
                "Git commit requires the current SourceRevision",
                details={"expected": str(expected_source_revision_id), "actual": str(current.id)},
            )
        if self.git is None:
            raise EngineeringError(
                EngineeringErrorCode.CAPABILITY_UNAVAILABLE, "Git adapter is unavailable"
            )
        result = self.git.commit(message, actor=actor)
        git_status = self._git_status()
        after = self._snapshot(
            self.workspace.list_files(),
            workspace_revision=current.workspace_revision + 1,
            created_by=f"git:{actor}",
            git_status=GitStatus(
                repository_id=git_status.repository_id,
                commit_sha=result.commit_sha,
                base_commit=result.commit_sha,
                branch=git_status.branch,
                dirty=False,
            ),
        )
        return self._persist_snapshot(current, after, emit_event=False)

    def apply_generated_candidate(
        self,
        candidate: GeneratedSourceCandidate,
        *,
        expected_source_revision_id: UUID,
        created_by: str,
    ) -> tuple[PatchProposal, SourceRevision]:
        if candidate.project_id != self.project_id:
            raise EngineeringError(
                EngineeringErrorCode.KNOWLEDGE_SCOPE_DENIED,
                "Candidate is outside the project scope",
            )
        current = self._reconcile()
        expected: dict[str, str | None] = {}
        for path, _content in candidate.files.items():
            owner = self.repository.get_ownership(self.project_id, path)
            current_hash = current.file_manifest.get(path)
            if (
                owner is not None
                and owner.status is GeneratedOwnershipStatus.ACTIVE
                and current_hash != owner.content_hash
            ):
                self.repository.save_ownership(
                    replace(owner, status=GeneratedOwnershipStatus.DIVERGED)
                )
                raise EngineeringError(
                    EngineeringErrorCode.GENERATED_SOURCE_DIVERGED,
                    "Generated-owned source was edited by a user and will not be "
                    "silently overwritten",
                    details={"path": path},
                )
            expected[path] = current_hash
        proposal = self.create_proposal(
            base_source_revision_id=expected_source_revision_id,
            base_workspace_revision=current.workspace_revision,
            affected_files=list(candidate.files),
            expected_file_hashes=expected,
            structured_edits=candidate.files,
            rationale=f"Apply generated source candidate {candidate.id}",
            created_by=created_by,
        )
        applied, revision = self.apply(
            proposal.id,
            expected_source_revision_id=expected_source_revision_id,
            expected_workspace_revision=current.workspace_revision,
        )
        for path, content in candidate.files.items():
            self.repository.save_ownership(
                GeneratedOwnership(
                    project_id=self.project_id,
                    path=path,
                    generator_id=candidate.generator_id,
                    generator_version=candidate.generator_version,
                    input_hash=candidate.input_hash,
                    content_hash=_hash_bytes(content.encode("utf-8")),
                    status=GeneratedOwnershipStatus.ACTIVE,
                ),
                commit=False,
            )
        self.repository.commit()
        return applied, revision


__all__ = [
    "GeneratedOwnership",
    "SourceWorkspaceRepository",
    "SourceWorkspaceService",
    "SourceWorkspaceState",
]
