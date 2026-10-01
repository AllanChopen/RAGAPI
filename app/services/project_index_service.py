from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.context_chunk import ContextChunk
from app.schemas.api_rag_schema import (
    RAGIndexedBranch,
    RAGIndexedCommit,
    RAGIndexedDocument,
    RAGIndexedRepository,
    RAGProjectSourcesResponse,
)


class ProjectIndexService:
    @staticmethod
    def list_sources(db: Session, project_id: str) -> RAGProjectSourcesResponse:
        metadata = ContextChunk.metadata_json
        project_filter = metadata["project_id"].astext == project_id
        source_type = metadata["source_type"].astext
        repository = metadata["repository"].astext
        branch = metadata["branch"].astext
        commit = metadata["commit"].astext
        document = metadata["document"].astext
        artifact_type = metadata["artifact_type"].astext

        repository_rows = (
            db.query(source_type, repository, branch, commit, func.count(ContextChunk.id))
            .filter(
                project_filter,
                source_type.in_(["repository", "repository_metadata"]),
                repository.isnot(None),
            )
            .group_by(source_type, repository, branch, commit)
            .all()
        )
        document_rows = (
            db.query(document, func.min(artifact_type), func.count(ContextChunk.id))
            .filter(
                project_filter,
                source_type == "document",
                document.isnot(None),
            )
            .group_by(document)
            .all()
        )
        commit_rows = (
            db.query(
                repository,
                commit,
                func.max(metadata["commit_message"].astext),
                func.count(ContextChunk.id),
            )
            .filter(
                project_filter,
                source_type.in_(["repository_commit", "commit_metadata", "commit_diff"]),
                repository.isnot(None),
                commit.isnot(None),
            )
            .group_by(repository, commit)
            .all()
        )

        repositories: dict[str, RAGIndexedRepository] = {}
        for kind, name, branch_name, commit_sha, count in repository_rows:
            item = repositories.setdefault(
                name,
                RAGIndexedRepository(name=name, chunks=0, branches=[]),
            )
            item.chunks += count
            if kind == "repository" and branch_name:
                item.branches.append(
                    RAGIndexedBranch(name=branch_name, commit=commit_sha, chunks=count)
                )

        for name, sha, message, count in commit_rows:
            item = repositories.setdefault(
                name,
                RAGIndexedRepository(name=name, chunks=0, branches=[]),
            )
            item.chunks += count
            item.commits.append(RAGIndexedCommit(sha=sha, message=message, chunks=count))

        documents = [
            RAGIndexedDocument(name=name, artifact_type=kind, chunks=count)
            for name, kind, count in document_rows
        ]
        ordered_repositories = sorted(repositories.values(), key=lambda item: item.name.casefold())
        for item in ordered_repositories:
            item.branches.sort(key=lambda branch_item: branch_item.name.casefold())
            item.commits.sort(key=lambda commit_item: commit_item.sha)
        documents.sort(key=lambda item: item.name.casefold())

        return RAGProjectSourcesResponse(
            project_id=project_id,
            repositories=ordered_repositories,
            documents=documents,
            total_chunks=sum(item.chunks for item in ordered_repositories)
            + sum(item.chunks for item in documents),
        )
