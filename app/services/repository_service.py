import shutil
from pathlib import Path

from git import Git, Repo
from git.exc import BadName, BadObject, GitCommandError
from sqlalchemy.orm import Session

from app.core.settings import settings
from app.models.context_chunk import ContextChunk
from app.schemas.repository_schema import (
    RepositoryBranchInfo,
    RepositoryBranchesResponse,
    RepositoryCommitInfo,
    RepositoryCommitsResponse,
    RepositoryCommitIngestRequest,
    RepositoryCommitIngestResponse,
    RepositoryCommitIngestSummary,
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
    def list_commits(
        repository_url: str,
        branch: str | None,
        limit: int,
    ) -> RepositoryCommitsResponse:
        temp_dir: str | None = None
        try:
            repo, _, repo_name, temp_dir = GitService.prepare_remote_repository(
                repository_url, depth=limit
            )
            refs = dict(GitService.remote_branch_refs(repo))
            selected_branch = branch or repo.active_branch.name
            if selected_branch not in refs:
                raise ValueError(f"Rama desconocida: {selected_branch}")
            commits = [
                RepositoryCommitInfo(
                    sha=commit.hexsha,
                    message=commit.summary,
                    authored_at=commit.authored_datetime.isoformat(),
                )
                for commit in repo.iter_commits(refs[selected_branch], max_count=limit)
            ]
            return RepositoryCommitsResponse(
                repository=repo_name,
                branch=selected_branch,
                commits=commits,
            )
        except GitCommandError as exc:
            raise RuntimeError(f"No fue posible consultar los commits Git: {exc}") from exc
        finally:
            if temp_dir:
                shutil.rmtree(temp_dir, ignore_errors=True)

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
                revision_chunks, branch_files = RepositoryService._index_revision(
                    repo_root=repo_root,
                    project_id=payload.project_id,
                    repository=repo_name,
                    branch=branch_name,
                    commit=commit,
                    source_type="repository",
                    source=source,
                )
                rows_to_insert.extend(revision_chunks)
                branch_chunks = len(revision_chunks)

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
    def ingest_commits(
        payload: RepositoryCommitIngestRequest,
        db: Session,
    ) -> RepositoryCommitIngestResponse:
        temp_dir: str | None = None
        try:
            repo, repo_root, repo_name, temp_dir = GitService.prepare_remote_repository(
                payload.repository_url, depth=None
            )
            source = RepositoryService._source_name(payload.project_id, repo_name)
            rows_to_insert: list[ContextChunk] = []
            summaries: list[RepositoryCommitIngestSummary] = []
            total_files = 0
            resolved_commits: set[str] = set()

            for requested_sha in payload.commits:
                try:
                    commit_obj = repo.commit(requested_sha)
                except (BadName, BadObject) as exc:
                    raise ValueError(f"Commit desconocido en el repositorio: {requested_sha}") from exc
                sha = commit_obj.hexsha
                if sha in resolved_commits:
                    continue
                resolved_commits.add(sha)
                repo.git.checkout("--force", sha)

                snapshot_chunks, files_processed = RepositoryService._index_revision(
                    repo_root=repo_root,
                    project_id=payload.project_id,
                    repository=repo_name,
                    branch=None,
                    commit=sha,
                    source_type="repository_commit",
                    source=source,
                )
                commit_chunks = RepositoryService._index_commit_changes(
                    repo=repo,
                    project_id=payload.project_id,
                    repository=repo_name,
                    commit=commit_obj,
                    source=source,
                )
                rows_to_insert.extend(snapshot_chunks)
                rows_to_insert.extend(commit_chunks)
                total_files += files_processed
                summaries.append(
                    RepositoryCommitIngestSummary(
                        sha=sha,
                        message=commit_obj.summary,
                        files_processed=files_processed,
                        chunks_created=len(snapshot_chunks) + len(commit_chunks),
                    )
                )

            for sha in resolved_commits:
                db.query(ContextChunk).filter(
                    ContextChunk.metadata_json["project_id"].astext == payload.project_id,
                    ContextChunk.metadata_json["repository"].astext == repo_name,
                    ContextChunk.metadata_json["commit"].astext == sha,
                    ContextChunk.metadata_json["source_type"].astext.in_(
                        ["repository_commit", "commit_metadata", "commit_diff"]
                    ),
                ).delete(synchronize_session=False)
            db.add_all(rows_to_insert)
            db.commit()

            return RepositoryCommitIngestResponse(
                project_id=payload.project_id,
                repository=repo_name,
                commits=summaries,
                total_files=total_files,
                total_chunks=len(rows_to_insert),
            )
        except GitCommandError as exc:
            db.rollback()
            raise RuntimeError(f"No fue posible acceder al commit Git: {exc}") from exc
        except Exception:
            db.rollback()
            raise
        finally:
            if temp_dir:
                shutil.rmtree(temp_dir, ignore_errors=True)

    @staticmethod
    def _index_revision(
        repo_root: Path,
        project_id: str,
        repository: str,
        branch: str | None,
        commit: str,
        source_type: str,
        source: str,
    ) -> tuple[list[ContextChunk], int]:
        rows: list[ContextChunk] = []
        files_processed = 0
        for rel_path in GitService.collect_files(repo_root, settings.rag_repository_max_files):
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
                    repository=repository,
                    branch=branch,
                    commit=commit,
                    file_path=rel_path,
                    artifact_type=str(chunk.get("artifact_type") or "artifact"),
                    content=str(chunk["content"]),
                )
                for chunk in file_chunks
            ]
            embeddings = RepositoryService._embed_in_batches(embedding_texts)
            files_processed += 1
            for chunk_index, (chunk_info, embedding) in enumerate(zip(file_chunks, embeddings)):
                rows.append(
                    ContextChunk(
                        source=source,
                        content=str(chunk_info["content"]),
                        metadata_json={
                            "project_id": project_id,
                            "source_type": source_type,
                            "repository": repository,
                            "branch": branch,
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
        return rows, files_processed

    @staticmethod
    def _index_commit_changes(
        repo: Repo,
        project_id: str,
        repository: str,
        commit,
        source: str,
    ) -> list[ContextChunk]:
        sha = commit.hexsha
        parent_sha = commit.parents[0].hexsha if commit.parents else None
        if parent_sha:
            name_status = repo.git.diff("--name-status", parent_sha, sha)
        else:
            name_status = repo.git.diff_tree(
                "--root", "--no-commit-id", "--name-status", "-r", sha
            )
        changes = [line.split("\t") for line in name_status.splitlines() if "\t" in line]
        listed_changes = changes[: settings.rag_commit_max_diff_files]
        message = commit.message.strip()
        if len(message) > 4000:
            message = message[:4000] + "\n[Mensaje recortado]"
        summary_lines = [
            f"Commit: {sha}",
            f"Mensaje: {message}",
            f"Fecha: {commit.authored_datetime.isoformat()}",
            f"Commit padre: {parent_sha or 'ninguno'}",
            f"Archivos modificados: {len(changes)}",
        ]
        summary_lines.extend(f"- {' '.join(parts)}" for parts in listed_changes)
        if len(changes) > len(listed_changes):
            summary_lines.append(f"... {len(changes) - len(listed_changes)} archivos adicionales")
        summary = "\n".join(summary_lines)
        rows = [
            ContextChunk(
                source=source,
                content=summary,
                metadata_json={
                    "project_id": project_id,
                    "source_type": "commit_metadata",
                    "repository": repository,
                    "commit": sha,
                    "parent_commit": parent_sha,
                    "commit_message": commit.summary,
                    "artifact_type": "commit_summary",
                },
                embedding=EmbeddingService.embed_text(summary),
            )
        ]

        for parts in listed_changes:
            paths = parts[1:]
            if not paths:
                continue
            file_path = paths[-1]
            if parent_sha:
                patch = repo.git.diff(
                    "--no-ext-diff", "--no-color", "--unified=3",
                    parent_sha, sha, "--", *paths,
                )
            else:
                patch = repo.git.show(
                    "--format=", "--no-ext-diff", "--no-color", "--unified=3",
                    sha, "--", *paths,
                )
            if not patch.strip():
                continue
            patch_truncated = len(patch) > settings.rag_commit_max_patch_chars
            if patch_truncated:
                patch = patch[: settings.rag_commit_max_patch_chars]
            max_chunks = settings.rag_commit_max_diff_chunks_per_file
            extracted_chunks = GitService._split_text_with_lines(
                patch,
                settings.rag_chunk_size,
                settings.rag_chunk_overlap,
                max_chunks + 1,
            )
            if len(extracted_chunks) > max_chunks:
                patch_truncated = True
            file_chunks = extracted_chunks[:max_chunks]
            if patch_truncated and file_chunks:
                file_chunks[-1]["content"] += "\n[Diff recortado]"
            embeddings = RepositoryService._embed_in_batches([
                f"repository: {repository}\ncommit: {sha}\nfile: {file_path}\nGit diff:\n{chunk['content']}"
                for chunk in file_chunks
            ]) if file_chunks else []
            for index, (chunk, embedding) in enumerate(zip(file_chunks, embeddings)):
                rows.append(
                    ContextChunk(
                        source=source,
                        content=str(chunk["content"]),
                        metadata_json={
                            "project_id": project_id,
                            "source_type": "commit_diff",
                            "repository": repository,
                            "commit": sha,
                            "parent_commit": parent_sha,
                            "file_path": file_path,
                            "chunk_index": index,
                            "artifact_type": "git_diff",
                            "diff_truncated": patch_truncated,
                        },
                        embedding=embedding,
                    )
                )
        return rows

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
        branch: str | None,
        commit: str,
        file_path: str,
        artifact_type: str,
        content: str,
    ) -> str:
        return "\n".join(
            [
                f"repository: {repository}",
                f"branch: {branch or 'sin rama específica'}",
                f"commit: {commit}",
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
