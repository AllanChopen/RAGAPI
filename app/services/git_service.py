import csv
import json
import re
import shutil
import tempfile
from pathlib import Path
from urllib.parse import urlparse

from git import Repo
from docx import Document
from docx.table import Table
from openpyxl import load_workbook
from pypdf import PdfReader


class GitService:
    DEFAULT_EXTENSIONS = {
        ".py",
        ".js",
        ".ts",
        ".tsx",
        ".jsx",
        ".java",
        ".cs",
        ".go",
        ".rs",
        ".php",
        ".rb",
        ".md",
        ".txt",
        ".mmd",
        ".mermaid",
        ".drawio",
        ".json",
        ".csv",
        ".yaml",
        ".yml",
        ".xml",
        ".pdf",
        ".docx",
        ".xlsx",
        ".sql",
        ".toml",
        ".ini",
        ".conf",
        ".properties",
        ".gradle",
        ".lock",
    }

    SPECIAL_FILENAMES = {
        "dockerfile",
        "docker-compose.yml",
        "docker-compose.yaml",
        "package.json",
        "composer.json",
        "requirements.txt",
        "pyproject.toml",
        "pom.xml",
        "build.gradle",
        "build.gradle.kts",
        "package-lock.json",
        "yarn.lock",
        "pnpm-lock.yaml",
        "go.mod",
        "cargo.toml",
        "cargo.lock",
        ".env.example",
    }

    @staticmethod
    def prepare_remote_repository(
        repository_url: str,
        depth: int | None = 1,
    ) -> tuple[Repo, Path, str, str]:
        temp_dir = tempfile.mkdtemp(prefix="rag_git_")
        try:
            clone_options = {"multi_options": ["--no-single-branch"]}
            if depth is not None:
                clone_options["depth"] = depth
            repo = Repo.clone_from(
                repository_url,
                temp_dir,
                **clone_options,
            )
        except Exception:
            shutil.rmtree(temp_dir, ignore_errors=True)
            raise

        repo_root = Path(temp_dir)
        repo_name = GitService.repo_name_from_url(repository_url)
        return repo, repo_root, repo_name, temp_dir

    @staticmethod
    def remote_branch_refs(repo: Repo) -> list[tuple[str, str]]:
        return sorted(
            [
                (ref.remote_head, ref.name)
                for ref in repo.remotes.origin.refs
                if ref.remote_head != "HEAD"
            ],
            key=lambda item: item[0].casefold(),
        )

    @staticmethod
    def collect_files(repo_root: Path, limit: int) -> list[str]:
        results: list[str] = []

        for file_path in sorted(repo_root.rglob("*")):
            if len(results) >= limit:
                break
            if not file_path.is_file() or ".git" in file_path.parts:
                continue

            file_name = file_path.name.lower()
            if not GitService.is_supported_filename(file_path.name):
                continue

            results.append(file_path.relative_to(repo_root).as_posix())

        return results

    @staticmethod
    def is_supported_filename(filename: str) -> bool:
        path = Path(filename)
        return (
            path.suffix.lower() in GitService.DEFAULT_EXTENSIONS
            or path.name.lower() in GitService.SPECIAL_FILENAMES
        )

    @staticmethod
    def repo_name_from_url(repository_url: str) -> str:
        parsed = urlparse(repository_url)
        name = parsed.path.rstrip("/").split("/")[-1]
        if name.endswith(".git"):
            name = name[:-4]
        return name or "repository"

    @staticmethod
    def extract_chunks_for_file(
        full_path: Path,
        rel_path: str,
        chunk_size: int,
        chunk_overlap: int,
        max_chunks: int,
    ) -> list[dict[str, int | str | None]]:
        logical_path = Path(rel_path)
        suffix = logical_path.suffix.lower()
        file_name = logical_path.name.lower()

        if suffix == ".xlsx":
            return GitService._extract_xlsx_chunks(full_path, max_chunks)
        if suffix == ".csv":
            return GitService._extract_csv_chunks(full_path, max_chunks)
        if suffix == ".json":
            chunks = GitService._extract_json_chunks(
                full_path, chunk_size, chunk_overlap, max_chunks
            )
            raw_content = GitService._read_text_file(full_path)
            artifact_type = GitService._classify_artifact_type(
                suffix=suffix,
                file_name=file_name,
                rel_path=rel_path,
                content=raw_content,
            )
            for chunk in chunks:
                chunk["document_type"] = "artifact"
                chunk["artifact_type"] = artifact_type
            return chunks
        if suffix == ".pdf":
            return GitService._extract_pdf_chunks(
                full_path, chunk_size, chunk_overlap, max_chunks
            )
        if suffix == ".docx":
            return GitService._extract_docx_chunks(
                full_path, chunk_size, chunk_overlap, max_chunks
            )
        if suffix == ".drawio" or (suffix == ".xml" and "drawio" in rel_path.lower()):
            return GitService._extract_drawio_chunks(
                full_path, chunk_size, chunk_overlap, max_chunks
            )

        content = GitService._read_text_file(full_path)
        if not content:
            return []

        artifact_type = GitService._classify_artifact_type(
            suffix=suffix,
            file_name=file_name,
            rel_path=rel_path,
            content=content,
        )
        document_type = "code" if artifact_type == "code" else "artifact"
        chunks = GitService._split_text_with_lines(
            content, chunk_size, chunk_overlap, max_chunks
        )

        for chunk in chunks:
            chunk["document_type"] = document_type
            chunk["artifact_type"] = artifact_type
            chunk["tab"] = None
            chunk["page"] = None

        return chunks

    @staticmethod
    def _classify_artifact_type(
        suffix: str,
        file_name: str,
        rel_path: str,
        content: str,
    ) -> str:
        path_lower = rel_path.lower()
        content_lower = content.lower()

        if suffix in {".drawio", ".mmd", ".mermaid"} or "drawio" in path_lower:
            return "architecture"
        if suffix == ".sql":
            return "database"
        if file_name in {"dockerfile", "docker-compose.yml", "docker-compose.yaml"}:
            return "infrastructure"
        if file_name in {
            "package.json",
            "package-lock.json",
            "composer.json",
            "requirements.txt",
            "pyproject.toml",
            "pom.xml",
            "build.gradle",
            "build.gradle.kts",
            "yarn.lock",
            "pnpm-lock.yaml",
            "go.mod",
            "cargo.toml",
            "cargo.lock",
        }:
            return "dependencies"
        if file_name == ".env.example" or suffix in {".toml", ".ini", ".conf", ".properties"}:
            return "configuration"
        if suffix in {".yaml", ".yml"}:
            if any(token in path_lower for token in ["k8s", "kubernetes", "helm", "manifests"]):
                return "infrastructure"
            if all(token in content_lower for token in ["apiversion:", "kind:"]):
                return "infrastructure"
            return "configuration"
        if suffix in {".xlsx", ".csv"}:
            return "data_dictionary"
        if suffix == ".json":
            if any(token in path_lower for token in ["dictionary", "diccionario", "schema", "fields"]):
                return "data_dictionary"
            if file_name == "package.json":
                return "dependencies"
            return "documentation"
        if suffix in {".md", ".txt", ".pdf", ".docx"}:
            return "documentation"
        if suffix in {".py", ".js", ".ts", ".tsx", ".jsx", ".java", ".cs", ".go", ".rs", ".php", ".rb"}:
            return "code"
        return "artifact"

    @staticmethod
    def _read_text_file(file_path: Path) -> str:
        try:
            return file_path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            return ""

    @staticmethod
    def _extract_xlsx_chunks(
        full_path: Path,
        max_chunks: int,
    ) -> list[dict[str, int | str | None]]:
        workbook = load_workbook(full_path, read_only=True, data_only=True)
        chunks: list[dict[str, int | str | None]] = []

        for sheet_name in workbook.sheetnames:
            worksheet = workbook[sheet_name]
            for row_index, row in enumerate(worksheet.iter_rows(values_only=True), start=1):
                if len(chunks) >= max_chunks:
                    return chunks

                values = ["" if cell is None else str(cell).strip() for cell in row]
                text = " | ".join(value for value in values if value)
                if not text:
                    continue

                chunks.append(
                    {
                        "content": text,
                        "line_start": row_index,
                        "line_end": row_index,
                        "document_type": "artifact",
                        "artifact_type": "data_dictionary",
                        "tab": sheet_name,
                        "page": None,
                    }
                )

        return chunks

    @staticmethod
    def _extract_csv_chunks(
        full_path: Path,
        max_chunks: int,
    ) -> list[dict[str, int | str | None]]:
        chunks: list[dict[str, int | str | None]] = []
        try:
            with full_path.open("r", encoding="utf-8", errors="ignore", newline="") as csv_file:
                reader = csv.reader(csv_file)
                for row_index, row in enumerate(reader, start=1):
                    if len(chunks) >= max_chunks:
                        break

                    text = " | ".join(
                        cell.strip() for cell in row if cell and cell.strip()
                    )
                    if not text:
                        continue

                    chunks.append(
                        {
                            "content": text,
                            "line_start": row_index,
                            "line_end": row_index,
                            "document_type": "artifact",
                            "artifact_type": "data_dictionary",
                            "tab": None,
                            "page": None,
                        }
                    )
        except OSError:
            return []

        return chunks

    @staticmethod
    def _extract_json_chunks(
        full_path: Path,
        chunk_size: int,
        chunk_overlap: int,
        max_chunks: int,
    ) -> list[dict[str, int | str | None]]:
        try:
            raw = full_path.read_text(encoding="utf-8", errors="ignore")
            parsed = json.loads(raw)
            normalized = json.dumps(parsed, ensure_ascii=False, indent=2)
        except (OSError, json.JSONDecodeError):
            return []

        chunks = GitService._split_text_with_lines(
            normalized, chunk_size, chunk_overlap, max_chunks
        )
        for chunk in chunks:
            chunk["document_type"] = "artifact"
            chunk["artifact_type"] = "documentation"
            chunk["tab"] = None
            chunk["page"] = None
        return chunks

    @staticmethod
    def _extract_pdf_chunks(
        full_path: Path,
        chunk_size: int,
        chunk_overlap: int,
        max_chunks: int,
    ) -> list[dict[str, int | str | None]]:
        try:
            reader = PdfReader(str(full_path))
        except Exception:
            return []

        chunks: list[dict[str, int | str | None]] = []
        for page_index, page in enumerate(reader.pages, start=1):
            if len(chunks) >= max_chunks:
                break

            text = page.extract_text() or ""
            if not text.strip():
                continue

            page_chunks = GitService._split_text_with_lines(
                text,
                chunk_size,
                chunk_overlap,
                max_chunks - len(chunks),
            )
            for chunk in page_chunks:
                chunk["document_type"] = "artifact"
                chunk["artifact_type"] = "documentation"
                chunk["tab"] = None
                chunk["page"] = page_index
                chunks.append(chunk)

        return chunks

    @staticmethod
    def _extract_docx_chunks(
        full_path: Path,
        chunk_size: int,
        chunk_overlap: int,
        max_chunks: int,
    ) -> list[dict[str, int | str | None]]:
        try:
            document = Document(str(full_path))
            lines: list[str] = []
            for block in document.iter_inner_content():
                if isinstance(block, Table):
                    for row in block.rows:
                        cells = [" ".join(cell.text.split()) for cell in row.cells]
                        if any(cells):
                            lines.append(" | ".join(cells))
                else:
                    text = " ".join(block.text.split())
                    if text:
                        lines.append(text)
        except Exception:
            return []

        chunks = GitService._split_text_with_lines(
            "\n".join(lines), chunk_size, chunk_overlap, max_chunks
        )
        for chunk in chunks:
            chunk["line_start"] = None
            chunk["line_end"] = None
            chunk["document_type"] = "artifact"
            chunk["artifact_type"] = "documentation"
            chunk["tab"] = None
            chunk["page"] = None
        return chunks

    @staticmethod
    def _extract_drawio_chunks(
        full_path: Path,
        chunk_size: int,
        chunk_overlap: int,
        max_chunks: int,
    ) -> list[dict[str, int | str | None]]:
        raw = GitService._read_text_file(full_path)
        if not raw:
            return []

        labels = re.findall(r'value="([^"]+)"', raw)
        text = "\n".join(labels) if labels else raw
        chunks = GitService._split_text_with_lines(
            text, chunk_size, chunk_overlap, max_chunks
        )
        for chunk in chunks:
            chunk["document_type"] = "artifact"
            chunk["artifact_type"] = "architecture"
            chunk["tab"] = None
            chunk["page"] = None
        return chunks

    @staticmethod
    def _split_text_with_lines(
        text: str,
        chunk_size: int,
        chunk_overlap: int,
        max_chunks: int,
    ) -> list[dict[str, int | str]]:
        lines = text.splitlines()
        if not lines:
            return []

        results: list[dict[str, int | str]] = []
        start_index = 0
        overlap_lines = 0 if chunk_overlap == 0 else max(1, chunk_overlap // 120)

        while start_index < len(lines) and len(results) < max_chunks:
            end_index = start_index
            current_size = 0

            while end_index < len(lines):
                current_size += len(lines[end_index]) + 1
                end_index += 1
                if current_size >= chunk_size:
                    break

            chunk_text = "\n".join(lines[start_index:end_index]).strip()
            if chunk_text:
                results.append(
                    {
                        "content": chunk_text,
                        "line_start": start_index + 1,
                        "line_end": end_index,
                    }
                )

            if end_index >= len(lines):
                break
            start_index = max(start_index + 1, end_index - overlap_lines)

        return results
