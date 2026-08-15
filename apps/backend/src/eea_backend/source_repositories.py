"""SQLAlchemy metadata adapters for M18C Source Authority."""

from __future__ import annotations

from typing import Any, cast
from uuid import UUID, uuid4

from eea_application.source_workspace import GeneratedOwnership, SourceWorkspaceState
from eea_core.entities import utc_now
from eea_core.enums import EngineeringErrorCode
from eea_core.errors import EngineeringError
from eea_core.source import (
    GeneratedOwnershipStatus,
    PatchProposal,
    SourceRevision,
)
from sqlalchemy import desc, select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.orm import Session

from eea_backend.models import (
    GeneratedSourceOwnershipRecord,
    PatchProposalRecord,
    SourceMutationJournalRecord,
    SourceRevisionRecord,
    SourceWorkspaceRecord,
)


def _entity_kwargs(record: object) -> dict[str, Any]:
    typed = cast(Any, record)
    return {
        "id": UUID(typed.id),
        "schema_version": typed.schema_version,
        "revision": typed.revision,
        "created_at": typed.created_at,
        "updated_at": typed.updated_at,
        "metadata": typed.entity_metadata,
    }


def _to_source_revision(record: SourceRevisionRecord) -> SourceRevision:
    return SourceRevision.model_validate(
        {
            **_entity_kwargs(record),
            "project_id": UUID(record.project_id),
            "repository_id": record.repository_id,
            "commit_sha": record.commit_sha,
            "tree_hash": record.tree_hash,
            "dirty": record.dirty,
            "base_commit": record.base_commit,
            "workspace_revision": record.workspace_revision,
            "source_manifest_hash": record.source_manifest_hash,
            "file_manifest": record.file_manifest,
            "created_by": record.created_by,
        }
    )


def _to_proposal(record: PatchProposalRecord) -> PatchProposal:
    return PatchProposal.model_validate(
        {
            **_entity_kwargs(record),
            "project_id": UUID(record.project_id),
            "base_source_revision_id": UUID(record.base_source_revision_id),
            "base_workspace_revision": record.base_workspace_revision,
            "affected_files": record.affected_files,
            "expected_file_hashes": record.expected_file_hashes,
            "patch": record.patch,
            "structured_edits": record.structured_edits,
            "rationale": record.rationale,
            "evidence_ids": [UUID(value) for value in record.evidence_ids],
            "expected_impact": record.expected_impact,
            "required_builds": record.required_builds,
            "required_tests": record.required_tests,
            "created_by": record.created_by,
            "status": record.status,
            "failure_reason": record.failure_reason,
        }
    )


class SqlAlchemySourceRepository:
    """Persist Source Authority metadata without storing source file contents."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def ensure_workspace(self, project_id: UUID, root_path: str) -> SourceWorkspaceState:
        record = self.session.scalar(
            select(SourceWorkspaceRecord).where(SourceWorkspaceRecord.project_id == str(project_id))
        )
        if record is None:
            now = utc_now()
            record = SourceWorkspaceRecord(
                id=str(uuid4()),
                schema_version="1.0",
                revision=1,
                created_at=now,
                updated_at=now,
                entity_metadata={},
                project_id=str(project_id),
                repository_id=f"workspace:{project_id}",
                root_path=root_path,
                current_source_revision_id=None,
                workspace_revision=0,
                base_commit=None,
                last_reconciled_manifest_hash=None,
            )
            self.session.add(record)
            self.session.flush()
        return self._to_workspace(record)

    @staticmethod
    def _to_workspace(record: SourceWorkspaceRecord) -> SourceWorkspaceState:
        return SourceWorkspaceState(
            project_id=UUID(record.project_id),
            repository_id=record.repository_id,
            root_path=record.root_path,
            current_source_revision_id=(
                UUID(record.current_source_revision_id)
                if record.current_source_revision_id
                else None
            ),
            workspace_revision=record.workspace_revision,
            base_commit=record.base_commit,
        )

    def get_workspace(self, project_id: UUID) -> SourceWorkspaceState | None:
        record = self.session.scalar(
            select(SourceWorkspaceRecord).where(SourceWorkspaceRecord.project_id == str(project_id))
        )
        return self._to_workspace(record) if record else None

    def current_revision(self, project_id: UUID) -> SourceRevision | None:
        workspace = self.session.scalar(
            select(SourceWorkspaceRecord).where(SourceWorkspaceRecord.project_id == str(project_id))
        )
        record = None
        if workspace is not None and workspace.current_source_revision_id:
            record = self.session.scalar(
                select(SourceRevisionRecord).where(
                    SourceRevisionRecord.id == workspace.current_source_revision_id,
                    SourceRevisionRecord.project_id == str(project_id),
                )
            )
        if record is None:
            record = self.session.scalar(
                select(SourceRevisionRecord)
                .where(SourceRevisionRecord.project_id == str(project_id))
                .order_by(
                    desc(SourceRevisionRecord.workspace_revision),
                    desc(SourceRevisionRecord.created_at),
                    desc(SourceRevisionRecord.id),
                )
                .limit(1)
            )
        return _to_source_revision(record) if record else None

    def get_revision(
        self, revision_id: UUID, *, project_id: UUID | None = None
    ) -> SourceRevision | None:
        statement = select(SourceRevisionRecord).where(SourceRevisionRecord.id == str(revision_id))
        if project_id is not None:
            statement = statement.where(SourceRevisionRecord.project_id == str(project_id))
        record = self.session.scalar(statement)
        return _to_source_revision(record) if record else None

    def save_revision(self, revision: SourceRevision, *, commit: bool = True) -> SourceRevision:
        self.session.add(
            SourceRevisionRecord(
                id=str(revision.id),
                schema_version=revision.schema_version,
                revision=revision.revision,
                created_at=revision.created_at,
                updated_at=revision.updated_at,
                entity_metadata=revision.metadata,
                project_id=str(revision.project_id),
                repository_id=revision.repository_id,
                commit_sha=revision.commit_sha,
                tree_hash=revision.tree_hash,
                dirty=revision.dirty,
                base_commit=revision.base_commit,
                workspace_revision=revision.workspace_revision,
                source_manifest_hash=revision.source_manifest_hash,
                file_manifest=revision.file_manifest,
                created_by=revision.created_by,
            )
        )
        if commit:
            self.session.commit()
        else:
            self.session.flush()
        return revision

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
    ) -> None:
        record = self.session.scalar(
            select(SourceWorkspaceRecord).where(SourceWorkspaceRecord.project_id == str(project_id))
        )
        if record is None:
            raise ValueError("source workspace metadata is missing")
        if expected_current_revision_id is not None:
            current_id = (
                UUID(record.current_source_revision_id)
                if record.current_source_revision_id
                else None
            )
            if current_id != expected_current_revision_id:
                raise EngineeringError(
                    EngineeringErrorCode.SOURCE_REVISION_CONFLICT,
                    "Source workspace changed during mutation",
                )
        elif record.current_source_revision_id is not None:
            raise EngineeringError(
                EngineeringErrorCode.SOURCE_REVISION_CONFLICT,
                "Source workspace was initialized concurrently",
            )
        if (
            expected_workspace_revision is not None
            and record.workspace_revision != expected_workspace_revision
        ):
            raise EngineeringError(
                EngineeringErrorCode.SOURCE_REVISION_CONFLICT,
                "Workspace revision changed during mutation",
            )
        record.current_source_revision_id = str(revision_id)
        record.workspace_revision = workspace_revision
        record.base_commit = base_commit
        record.updated_at = utc_now()
        record.revision += 1
        revision = self.session.get(SourceRevisionRecord, str(revision_id))
        record.repository_id = revision.repository_id if revision else record.repository_id
        record.last_reconciled_manifest_hash = revision.source_manifest_hash if revision else None
        if commit:
            self.session.commit()
        else:
            self.session.flush()

    def save_proposal(self, proposal: PatchProposal, *, commit: bool = True) -> PatchProposal:
        self.session.add(
            PatchProposalRecord(
                id=str(proposal.id),
                schema_version=proposal.schema_version,
                revision=proposal.revision,
                created_at=proposal.created_at,
                updated_at=proposal.updated_at,
                entity_metadata=proposal.metadata,
                project_id=str(proposal.project_id),
                base_source_revision_id=str(proposal.base_source_revision_id),
                base_workspace_revision=proposal.base_workspace_revision,
                affected_files=proposal.affected_files,
                expected_file_hashes=proposal.expected_file_hashes,
                patch=proposal.patch,
                structured_edits=proposal.structured_edits,
                rationale=proposal.rationale,
                evidence_ids=[str(value) for value in proposal.evidence_ids],
                expected_impact=proposal.expected_impact,
                required_builds=proposal.required_builds,
                required_tests=proposal.required_tests,
                created_by=proposal.created_by,
                status=proposal.status.value,
                failure_reason=proposal.failure_reason,
            )
        )
        if commit:
            self.session.commit()
        else:
            self.session.flush()
        return proposal

    def get_proposal(
        self, proposal_id: UUID, *, project_id: UUID | None = None
    ) -> PatchProposal | None:
        statement = select(PatchProposalRecord).where(PatchProposalRecord.id == str(proposal_id))
        if project_id is not None:
            statement = statement.where(PatchProposalRecord.project_id == str(project_id))
        record = self.session.scalar(statement)
        return _to_proposal(record) if record else None

    def update_proposal(self, proposal: PatchProposal, *, commit: bool = True) -> PatchProposal:
        result = cast(
            CursorResult[Any],
            self.session.execute(
                update(PatchProposalRecord)
                .where(PatchProposalRecord.id == str(proposal.id))
                .values(
                    revision=proposal.revision,
                    updated_at=proposal.updated_at,
                    entity_metadata=proposal.metadata,
                    status=proposal.status.value,
                    failure_reason=proposal.failure_reason,
                )
            ),
        )
        if result.rowcount != 1:
            raise ValueError("patch proposal disappeared during update")
        if commit:
            self.session.commit()
        else:
            self.session.flush()
        return proposal

    def list_ownership(self, project_id: UUID) -> list[GeneratedOwnership]:
        rows = self.session.scalars(
            select(GeneratedSourceOwnershipRecord)
            .where(GeneratedSourceOwnershipRecord.project_id == str(project_id))
            .order_by(GeneratedSourceOwnershipRecord.path)
        )
        return [self._to_ownership(row) for row in rows]

    def get_ownership(self, project_id: UUID, path: str) -> GeneratedOwnership | None:
        row = self.session.scalar(
            select(GeneratedSourceOwnershipRecord).where(
                GeneratedSourceOwnershipRecord.project_id == str(project_id),
                GeneratedSourceOwnershipRecord.path == path,
            )
        )
        return self._to_ownership(row) if row else None

    @staticmethod
    def _to_ownership(record: GeneratedSourceOwnershipRecord) -> GeneratedOwnership:
        return GeneratedOwnership(
            project_id=UUID(record.project_id),
            path=record.path,
            generator_id=record.generator_id,
            generator_version=record.generator_version,
            input_hash=record.input_hash,
            content_hash=record.content_hash,
            status=GeneratedOwnershipStatus(record.status),
        )

    def save_ownership(
        self, ownership: GeneratedOwnership, *, commit: bool = True
    ) -> GeneratedOwnership:
        row = self.session.scalar(
            select(GeneratedSourceOwnershipRecord).where(
                GeneratedSourceOwnershipRecord.project_id == str(ownership.project_id),
                GeneratedSourceOwnershipRecord.path == ownership.path,
            )
        )
        now = utc_now()
        if row is None:
            self.session.add(
                GeneratedSourceOwnershipRecord(
                    id=str(uuid4()),
                    schema_version="1.0",
                    revision=1,
                    created_at=now,
                    updated_at=now,
                    entity_metadata={},
                    project_id=str(ownership.project_id),
                    path=ownership.path,
                    generator_id=ownership.generator_id,
                    generator_version=ownership.generator_version,
                    input_hash=ownership.input_hash,
                    content_hash=ownership.content_hash,
                    status=ownership.status.value,
                )
            )
        else:
            row.revision += 1
            row.updated_at = now
            row.generator_id = ownership.generator_id
            row.generator_version = ownership.generator_version
            row.input_hash = ownership.input_hash
            row.content_hash = ownership.content_hash
            row.status = ownership.status.value
        if commit:
            self.session.commit()
        else:
            self.session.flush()
        return ownership

    def begin_source_journal(
        self,
        project_id: UUID,
        proposal_id: UUID,
        previous_source_revision_id: UUID,
        affected_files: list[str],
    ) -> UUID:
        operation_id = uuid4()
        now = utc_now()
        workspace = self.get_workspace(project_id)
        if workspace is None:
            raise ValueError("source workspace metadata is missing")
        self.session.add(
            SourceMutationJournalRecord(
                id=str(operation_id),
                schema_version="1.0",
                revision=1,
                created_at=now,
                updated_at=now,
                entity_metadata={},
                project_id=str(project_id),
                operation_id=str(operation_id),
                proposal_id=str(proposal_id),
                previous_source_revision_id=str(previous_source_revision_id),
                expected_workspace_revision=workspace.workspace_revision,
                affected_files=affected_files,
                status="PREPARED",
                last_error=None,
            )
        )
        self.session.flush()
        return operation_id

    def finish_source_journal(self, journal_id: UUID, status: str) -> None:
        row = self.session.get(SourceMutationJournalRecord, str(journal_id))
        if row is None:
            raise ValueError("source mutation journal entry is missing")
        row.status = status
        row.updated_at = utc_now()
        row.revision += 1
        self.session.flush()

    def recover_source_journals(self, project_id: UUID, workspace_revision: int) -> int:
        rows = self.session.scalars(
            select(SourceMutationJournalRecord).where(
                SourceMutationJournalRecord.project_id == str(project_id),
                SourceMutationJournalRecord.status == "PREPARED",
            )
        )
        recovered_count = 0
        for row in rows:
            recovered_operation = row.expected_workspace_revision < workspace_revision
            row.status = "RECOVERED" if recovered_operation else "ROLLED_BACK"
            row.last_error = (
                "Workspace reconciliation finalized the filesystem mutation"
                if recovered_operation
                else "Workspace reconciliation found no committed workspace revision"
            )
            row.updated_at = utc_now()
            row.revision += 1
            proposal = self.session.get(PatchProposalRecord, row.proposal_id)
            if proposal is not None and proposal.status in {"DRAFT", "READY"}:
                proposal.status = "APPLIED" if recovered_operation else "FAILED"
                proposal.failure_reason = None if recovered_operation else row.last_error
                proposal.updated_at = utc_now()
                proposal.revision += 1
            recovered_count += 1
        self.session.flush()
        return recovered_count

    def commit(self) -> None:
        self.session.commit()

    def rollback(self) -> None:
        self.session.rollback()


__all__ = ["SqlAlchemySourceRepository"]
