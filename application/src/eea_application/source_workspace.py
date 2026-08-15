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
from datetime import UTC, datetime, timedelta
from threading import Lock
from typing import ClassVar, Protocol
from uuid import UUID, uuid4

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
    active_mutation_id: UUID | None = None
    active_mutation_started_at: datetime | None = None
    active_mutation_expected_revision: int | None = None


@dataclass(frozen=True, slots=True)
class SourceMutationJournal:
    id: UUID
    project_id: UUID
    operation_id: UUID
    proposal_id: UUID | None
    previous_source_revision_id: UUID | None
    expected_workspace_revision: int
    affected_files: list[str]
    before_manifest: dict[str, str | None]
    after_manifest: dict[str, str]
    recovery_bundle_path: str | None
    status: str
    last_error: str | None


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

    def claim_source_mutation(
        self,
        project_id: UUID,
        operation_id: UUID,
        expected_source_revision_id: UUID | None,
        expected_workspace_revision: int,
        *,
        commit: bool = True,
    ) -> None: ...

    def release_source_mutation(
        self, project_id: UUID, operation_id: UUID, *, commit: bool = True
    ) -> None: ...

    def finalize_source_mutation(
        self,
        project_id: UUID,
        operation_id: UUID,
        expected_source_revision_id: UUID | None,
        expected_workspace_revision: int,
        new_source_revision_id: UUID,
        new_workspace_revision: int,
        base_commit: str | None,
        *,
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
        proposal_id: UUID | None,
        previous_source_revision_id: UUID | None,
        affected_files: list[str],
        *,
        operation_id: UUID | None = None,
        before_manifest: Mapping[str, str | None] | None = None,
        after_manifest: Mapping[str, str] | None = None,
        recovery_bundle_path: str | None = None,
    ) -> UUID: ...

    def get_source_journal(self, journal_id: UUID) -> SourceMutationJournal | None: ...

    def list_prepared_source_journals(self, project_id: UUID) -> list[SourceMutationJournal]: ...

    def finish_source_journal(
        self, journal_id: UUID, status: str, *, last_error: str | None = None
    ) -> None: ...

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
        mutation_id: UUID | None = None,
    ) -> SourceRevision:
        operation_id = mutation_id or uuid4()
        expected_workspace_revision = before.workspace_revision if before is not None else 0
        if mutation_id is None:
            self.repository.claim_source_mutation(
                self.project_id,
                operation_id,
                before.id if before is not None else None,
                expected_workspace_revision,
            )
        self.repository.save_revision(after, commit=False)
        self.repository.finalize_source_mutation(
            self.project_id,
            operation_id,
            before.id if before is not None else None,
            expected_workspace_revision,
            after.id,
            after.workspace_revision,
            after.base_commit,
            commit=False,
        )
        if emit_event:
            self._publish_change(before, after)
        self.repository.commit()
        return after

    @staticmethod
    def _lease_is_valid(state: SourceWorkspaceState) -> bool:
        if state.active_mutation_started_at is None:
            return False
        started = state.active_mutation_started_at
        if started.tzinfo is None:
            started = started.replace(tzinfo=UTC)
        return datetime.now(UTC) - started.astimezone(UTC) < timedelta(minutes=5)

    def _prepared_journals(self) -> list[SourceMutationJournal]:
        return self.repository.list_prepared_source_journals(self.project_id)

    def _recover_one_journal(
        self,
        journal: SourceMutationJournal,
        current: SourceRevision | None,
        state: SourceWorkspaceState,
        *,
        created_by: str,
    ) -> SourceRevision | None:
        if journal.recovery_bundle_path is None:
            self.repository.finish_source_journal(
                journal.id,
                "RECOVERY_REQUIRED",
                last_error="Prepared source mutation has no recovery bundle",
            )
            self.repository.commit()
            raise EngineeringError(
                EngineeringErrorCode.RECOVERY_REQUIRED,
                "Prepared source mutation has no recovery evidence",
                details={"operation_id": str(journal.operation_id)},
            )
        classification = self.workspace.classify_recovery_bundle(journal.recovery_bundle_path)
        if classification == "PARTIAL":
            try:
                self.workspace.restore_recovery_bundle(journal.recovery_bundle_path, "AFTER")
                classification = self.workspace.classify_recovery_bundle(
                    journal.recovery_bundle_path
                )
            except EngineeringError:
                self.workspace.restore_recovery_bundle(journal.recovery_bundle_path, "BEFORE")
                classification = self.workspace.classify_recovery_bundle(
                    journal.recovery_bundle_path
                )
        if classification == "UNKNOWN":
            self.repository.finish_source_journal(
                journal.id,
                "RECOVERY_REQUIRED",
                last_error="Recovery bundle is neither a complete BEFORE nor AFTER state",
            )
            self.repository.commit()
            raise EngineeringError(
                EngineeringErrorCode.RECOVERY_REQUIRED,
                "Source mutation recovery is indeterminate",
                details={"operation_id": str(journal.operation_id)},
            )
        if classification == "BEFORE":
            if journal.proposal_id is not None:
                proposal = self.repository.get_proposal(journal.proposal_id)
                if proposal is not None and proposal.status in {
                    PatchProposalStatus.DRAFT,
                    PatchProposalStatus.READY,
                }:
                    self.repository.update_proposal(
                        proposal.model_copy(
                            update={
                                "status": PatchProposalStatus.FAILED,
                                "failure_reason": "Source mutation rolled back during recovery",
                            }
                        ),
                        commit=False,
                    )
            self.repository.finish_source_journal(journal.id, "ROLLED_BACK")
            if state.active_mutation_id == journal.operation_id:
                self.repository.release_source_mutation(
                    self.project_id, journal.operation_id, commit=False
                )
            self.repository.commit()
            self.workspace.cleanup_recovery_bundle(journal.recovery_bundle_path)
            return current
        if current is None or current.id != journal.previous_source_revision_id:
            current = self.repository.current_revision(self.project_id)
        if current is None or current.id != journal.previous_source_revision_id:
            raise EngineeringError(
                EngineeringErrorCode.RECOVERY_REQUIRED,
                "Source mutation recovery has no authoritative previous revision",
            )
        if state.active_mutation_id not in {None, journal.operation_id}:
            raise EngineeringError(
                EngineeringErrorCode.RESOURCE_BUSY,
                "Source workspace is owned by another mutation during recovery",
            )
        if state.active_mutation_id is None:
            self.repository.claim_source_mutation(
                self.project_id,
                journal.operation_id,
                current.id,
                journal.expected_workspace_revision,
            )
        files = self.workspace.list_files()
        after = self._snapshot(
            files,
            workspace_revision=journal.expected_workspace_revision + 1,
            created_by=created_by,
            git_status=self._git_status(),
        )
        self.repository.save_revision(after, commit=False)
        if journal.proposal_id is not None:
            proposal = self.repository.get_proposal(journal.proposal_id)
            if proposal is not None and proposal.status in {
                PatchProposalStatus.DRAFT,
                PatchProposalStatus.READY,
            }:
                self.repository.update_proposal(
                    proposal.model_copy(
                        update={"status": PatchProposalStatus.APPLIED, "failure_reason": None}
                    ),
                    commit=False,
                )
        self.repository.finish_source_journal(journal.id, "RECOVERED")
        self.repository.finalize_source_mutation(
            self.project_id,
            journal.operation_id,
            current.id,
            journal.expected_workspace_revision,
            after.id,
            after.workspace_revision,
            after.base_commit,
            commit=False,
        )
        self._publish_change(current, after)
        self.repository.commit()
        self.workspace.cleanup_recovery_bundle(journal.recovery_bundle_path)
        return after

    def _recover_prepared_journals(
        self,
        state: SourceWorkspaceState,
        current: SourceRevision | None,
        *,
        created_by: str,
    ) -> SourceRevision | None:
        journals = self._prepared_journals()
        if state.active_mutation_id is not None and self._lease_is_valid(state):
            return current
        if state.active_mutation_id is not None and not journals:
            raise EngineeringError(
                EngineeringErrorCode.RECOVERY_REQUIRED,
                "Active source mutation has no prepared journal",
                details={"operation_id": str(state.active_mutation_id)},
            )
        for journal in journals:
            if (
                state.active_mutation_id is not None
                and state.active_mutation_id != journal.operation_id
            ):
                raise EngineeringError(
                    EngineeringErrorCode.RESOURCE_BUSY,
                    "Source workspace is owned by another mutation",
                )
            current = self._recover_one_journal(journal, current, state, created_by=created_by)
            state = self.repository.ensure_workspace(self.project_id, str(self.workspace.root))
        return current

    def _reconcile(self, *, created_by: str = "eea:source-reconcile") -> SourceRevision:
        self.workspace.cleanup_temporary()
        self.workspace.ensure_exists()
        state = self.repository.ensure_workspace(self.project_id, str(self.workspace.root))
        current = self.repository.current_revision(self.project_id)
        if state.active_mutation_id is not None and self._lease_is_valid(state):
            if current is None:
                raise EngineeringError(
                    EngineeringErrorCode.RESOURCE_BUSY,
                    "Source workspace has an active initial mutation",
                )
            return current
        recovered = self._recover_prepared_journals(
            state, current, created_by="eea:source-recovery"
        )
        if recovered is not None:
            current = recovered
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
        operation_id = uuid4()
        before_files = {path: files.get(path) for path in proposal.affected_files}
        bundle = None
        journal_id: UUID | None = None
        self.repository.claim_source_mutation(
            self.project_id,
            operation_id,
            current.id,
            current.workspace_revision,
        )
        try:
            claimed_files = self.workspace.list_files()
            for path in proposal.affected_files:
                actual = _hash_bytes(claimed_files[path]) if path in claimed_files else None
                if actual != proposal.expected_file_hashes.get(path):
                    self.repository.release_source_mutation(
                        self.project_id, operation_id, commit=True
                    )
                    self._mark_stale(proposal, f"Expected content hash does not match {path}")
                    raise EngineeringError(
                        EngineeringErrorCode.SOURCE_REVISION_CONFLICT,
                        "Patch proposal content hash changed after mutation claim",
                        details={"path": path},
                    )
            before_files = {path: claimed_files.get(path) for path in proposal.affected_files}
            updates = {
                path: value.encode("utf-8") for path, value in proposal.structured_edits.items()
            }
            if proposal.patch and not updates:
                updates = self._parse_unified_patch(proposal.patch, claimed_files)
            bundle = self.workspace.prepare_recovery_bundle(
                operation_id,
                before_files,
                updates,
                metadata={
                    "project_id": str(self.project_id),
                    "previous_source_revision_id": str(current.id),
                    "expected_workspace_revision": current.workspace_revision,
                    "proposal_id": str(proposal.id),
                },
            )
            journal_id = self.repository.begin_source_journal(
                self.project_id,
                proposal.id,
                current.id,
                proposal.affected_files,
                operation_id=operation_id,
                before_manifest=dict(bundle.before_manifest),
                after_manifest=dict(bundle.after_manifest),
                recovery_bundle_path=str(bundle.path),
            )
            self.repository.commit()
        except Exception:
            if journal_id is None:
                self.repository.release_source_mutation(self.project_id, operation_id, commit=True)
                if bundle is not None:
                    self.workspace.cleanup_recovery_bundle(str(bundle.path))
            raise
        assert bundle is not None
        assert journal_id is not None
        try:
            self.workspace.atomic_replace(updates)
        except Exception as exc:
            classification = self.workspace.classify_recovery_bundle(str(bundle.path))
            if classification == "BEFORE":
                self.repository.finish_source_journal(journal_id, "ROLLED_BACK")
                self.repository.release_source_mutation(self.project_id, operation_id, commit=False)
                self.repository.commit()
                self.workspace.cleanup_recovery_bundle(str(bundle.path))
            elif classification == "AFTER":
                # The replace raised after all bytes reached the staged state;
                # leave PREPARED evidence for deterministic startup finalize.
                self.repository.commit()
            else:
                self.repository.finish_source_journal(
                    journal_id,
                    "PREPARED" if classification == "PARTIAL" else "RECOVERY_REQUIRED",
                    last_error=(
                        "Filesystem replacement stopped before a consistent state"
                        if classification == "PARTIAL"
                        else "Filesystem replacement reached an unknown state"
                    ),
                )
                self.repository.commit()
            raise exc
        try:
            if self.workspace.classify_recovery_bundle(str(bundle.path)) != "AFTER":
                raise EngineeringError(
                    EngineeringErrorCode.RECOVERY_REQUIRED,
                    "Filesystem replacement did not reach the staged recovery state",
                    details={"operation_id": str(operation_id)},
                )
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
            self.repository.finish_source_journal(journal_id, "COMPLETED")
            self._persist_snapshot(current, after, mutation_id=operation_id)
            self.workspace.cleanup_recovery_bundle(str(bundle.path))
            return applied, after
        except Exception:
            self.repository.rollback()
            # The committed PREPARED journal and bundle remain the recovery source
            # of truth when SQL finalization fails after filesystem side effects.
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
        if not message.strip():
            raise EngineeringError(
                EngineeringErrorCode.VALIDATION_ERROR,
                "Commit message must be non-empty",
            )
        operation_id = uuid4()
        self.repository.claim_source_mutation(
            self.project_id,
            operation_id,
            current.id,
            current.workspace_revision,
        )
        try:
            # Re-check the bounded Git status after claiming the database row.
            self._git_status()
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
            return self._persist_snapshot(
                current, after, emit_event=False, mutation_id=operation_id
            )
        except Exception:
            # The Git operation has an unknown outcome if it raised after
            # invoking the external process. Keep the lease for recovery.
            raise

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
