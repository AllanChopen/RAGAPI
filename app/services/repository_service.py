import shutil
from git import Git
from git.exc import GitCommandError
from sqlalchemy.orm import Session

from app.core.settings import settings
from app.models.context_chunk import ContextChunk
from app.schemas.repository_schema import (
    RepositoryBranchInfo,
    RepositoryBranchesResponse,
    RepositoryBranchIngestSummary,
    RepositoryFileChange,
    RepositoryIngestRequest,
    RepositoryIngestResponse,
)
from app.services.embedding_service import EmbeddingService
from app.services.git_service import GitService


class RepositoryService:
    @staticmethod
    def list_branches(repository_url: str) -> RepositoryBranchesResponse:
        repo_name = GitService.repo_name_from_url(repository_url)
        try:
            output = Git().ls_remote(
                "--symref",
                repository_url,
                "HEAD",
                "refs/heads/*",
            )
        except GitCommandError as exc:
            raise RuntimeError(f"No fue posible acceder al repositorio Git: {exc}") from exc

        default_branch: str | None = None
        commits: dict[str, str] = {}

        for line in output.splitlines():
            if line.startswith("ref: ") and line.endswith("\tHEAD"):
                ref = line.split("\t", 1)[0].removeprefix("ref: ")
                if ref.startswith("refs/heads/"):
                    default_branch = ref.removeprefix("refs/heads/")
                continue

            parts = line.split("\t", 1)
            if len(parts) != 2:
                continue
            commit, ref = parts
            if ref.startswith("refs/heads/"):
                commits[ref.removeprefix("refs/heads/")] = commit

        branches = [
            RepositoryBranchInfo(
                name=name,
                commit=commit,
                default=name == default_branch,
            )
            for name, commit in sorted(commits.items(), key=lambda item: item[0].casefold())
        ]

        if not branches:
            raise ValueError("No se encontraron ramas en el repositorio")

        return RepositoryBranchesResponse(
            repository=repo_name,
            default_branch=default_branch,
            branches=branches,
        )

    @staticmethod
    def ingest(payload: RepositoryIngestRequest, db: Session) -> RepositoryIngestResponse:
        temp_dir: str | None = None

        try:
            repo, repo_root, repo_name, temp_dir = GitService.prepare_remote_repository(payload.repository_url)
            branch_refs = GitService.remote_branch_refs(repo)
            selected_refs = RepositoryService._select_branches(branch_refs, payload.branches)
            remote_branches = [
                (branch_name, repo.commit(checkout_ref).hexsha)
                for branch_name, checkout_ref in branch_refs
            ]
            selected_branch_names = {branch_name for branch_name, _ in selected_refs}
            source = RepositoryService._source_name(payload.project_id, repo_name)

            rows_to_insert: list[ContextChunk] = []
            summaries: list[RepositoryBranchIngestSummary] = []
            total_files = 0

            for branch_name, checkout_ref in selected_refs:
                repo.git.checkout("--force", checkout_ref)
                commit = repo.head.commit.hexsha
                files = GitService.collect_files(repo_root, settings.rag_repository_max_files)

                branch_files = 0
                branch_chunks = 0

                for rel_path in files:
                    file_chunks = GitService.extract_chunks_for_file(
                        full_path=repo_root / rel_path,
                        rel_path=rel_path,
                        chunk_size=settings.rag_chunk_size,
                        chunk_overlap=settings.rag_chunk_overlap,
                        max_chunks=settings.rag_repository_max_chunks_per_file,
                    )
                    if not file_chunks:
                        continue

                    embedding_texts = [
                        RepositoryService._embedding_text(
                            repository=repo_name,
                            branch=branch_name,
                            file_path=rel_path,
                            artifact_type=str(chunk.get("artifact_type") or "artifact"),
                            content=str(chunk["content"]),
                        )
                        for chunk in file_chunks
                    ]
                    embeddings = RepositoryService._embed_in_batches(embedding_texts)
                    branch_files += 1

                    for chunk_index, (chunk_info, embedding) in enumerate(zip(file_chunks, embeddings)):
                        rows_to_insert.append(
                            ContextChunk(
                                source=source,
                                content=str(chunk_info["content"]),
                                metadata_json={
                                    "project_id": payload.project_id,
                                    "source_type": "repository",
                                    "repository": repo_name,
                                    "branch": branch_name,
                                    "commit": commit,
                                    "file_path": rel_path,
                                    "chunk_index": chunk_index,
                                    "line_start": chunk_info.get("line_start"),
                                    "line_end": chunk_info.get("line_end"),
                                    "page": chunk_info.get("page"),
                                    "tab": chunk_info.get("tab"),
                                    "document_type": chunk_info.get("document_type"),
                                    "artifact_type": chunk_info.get("artifact_type"),
                                },
                                embedding=embedding,
                            )
                        )
                        branch_chunks += 1

                total_files += branch_files
                summaries.append(
                    RepositoryBranchIngestSummary(
                        name=branch_name,
                        commit=commit,
                        files_processed=branch_files,
                        chunks_created=branch_chunks,
                    )
                )

            manifest_content = RepositoryService._repository_manifest(
                repository=repo_name,
                remote_branches=remote_branches,
                indexed_branches=selected_branch_names,
            )
            manifest_embedding = EmbeddingService.embed_text(manifest_content)
            rows_to_insert.append(
                ContextChunk(
                    source=source,
                    content=manifest_content,
                    metadata_json={
                        "project_id": payload.project_id,
                        "source_type": "repository_metadata",
                        "repository": repo_name,
                        "artifact_type": "repository_manifest",
                        "branches": [
                            {
                                "name": branch_name,
                                "commit": commit,
                                "indexed": branch_name in selected_branch_names,
                            }
                            for branch_name, commit in remote_branches
                        ],
                    },
                    embedding=manifest_embedding,
                )
            )

            RepositoryService._delete_existing_repository_chunks(
                db=db,
                project_id=payload.project_id,
                repository=repo_name,
            )
            if rows_to_insert:
                db.add_all(rows_to_insert)
            db.commit()

            return RepositoryIngestResponse(
                project_id=payload.project_id,
                repository=repo_name,
                branches=summaries,
                total_files=total_files,
                total_chunks=len(rows_to_insert),
            )
        except GitCommandError as exc:
            db.rollback()
            raise RuntimeError(f"No fue posible acceder al repositorio Git: {exc}") from exc
        except Exception:
            db.rollback()
            raise
        finally:
            if temp_dir:
                shutil.rmtree(temp_dir, ignore_errors=True)

    @staticmethod
    def diff_branches(
        repository_url: str,
        branch_a: str,
        branch_b: str,
    ) -> tuple[str, list[RepositoryFileChange]]:
        temp_dir: str | None = None

        try:
            repo, _, repo_name, temp_dir = GitService.prepare_remote_repository(repository_url)
            refs = dict(GitService.remote_branch_refs(repo))

            missing = [branch for branch in (branch_a, branch_b) if branch not in refs]
            if missing:
                raise ValueError(f"Rama(s) desconocida(s): {', '.join(missing)}")

            output = repo.git.diff("--name-status", refs[branch_a], refs[branch_b])
            changes: list[RepositoryFileChange] = []

            for line in output.splitlines():
                parts = line.split("\t")
                if len(parts) < 2:
                    continue
                status = parts[0]
                if status.startswith("R") and len(parts) >= 3:
                    changes.append(
                        RepositoryFileChange(
                            status=status,
                            previous_path=parts[1],
                            path=parts[2],
                        )
                    )
                else:
                    changes.append(
                        RepositoryFileChange(
                            status=status,
                            path=parts[1],
                        )
                    )

            return repo_name, changes
        except GitCommandError as exc:
            raise RuntimeError(f"No fue posible comparar las ramas Git: {exc}") from exc
        finally:
            if temp_dir:
                shutil.rmtree(temp_dir, ignore_errors=True)

    @staticmethod
    def _select_branches(
        branch_refs: list[tuple[str, str]],
        requested: list[str] | None,
    ) -> list[tuple[str, str]]:
        if not requested:
            return branch_refs

        available = {name: ref for name, ref in branch_refs}
        missing = [branch for branch in requested if branch not in available]
        if missing:
            raise ValueError(f"Rama(s) desconocida(s): {', '.join(missing)}")

        return [(branch, available[branch]) for branch in requested]

    @staticmethod
    def _embedding_text(
        repository: str,
        branch: str,
        file_path: str,
        artifact_type: str,
        content: str,
    ) -> str:
        return "\n".join(
            [
                f"repository: {repository}",
                f"branch: {branch}",
                f"file: {file_path}",
                f"artifact: {artifact_type}",
                content,
            ]
        )

    @staticmethod
    def _embed_in_batches(contents: list[str]) -> list[list[float]]:
        results: list[list[float]] = []
        batch_size = max(1, settings.embedding_batch_size)
        for start in range(0, len(contents), batch_size):
            results.extend(EmbeddingService.embed_texts(contents[start : start + batch_size]))
        return results

    @staticmethod
    def _delete_existing_repository_chunks(
        db: Session,
        project_id: str,
        repository: str,
    ) -> None:
        db.query(ContextChunk).filter(
            ContextChunk.metadata_json["project_id"].astext == project_id,
            ContextChunk.metadata_json["source_type"].astext.in_(
                ["repository", "repository_metadata"]
            ),
            ContextChunk.metadata_json["repository"].astext == repository,
        ).delete(synchronize_session=False)

    @staticmethod
    def _repository_manifest(
        repository: str,
        remote_branches: list[tuple[str, str]],
        indexed_branches: set[str],
    ) -> str:
        lines = [f"Repositorio: {repository}", "Ramas remotas detectadas:"]
        for branch_name, commit in remote_branches:
            status = "indexada" if branch_name in indexed_branches else "no indexada"
            lines.append(f"- {branch_name} (commit {commit}) [{status}]")
        return "\n".join(lines)

    @staticmethod
    def _source_name(project_id: str, repository: str) -> str:
        return f"project:{project_id}:repository:{repository}"
