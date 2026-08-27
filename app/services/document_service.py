import tempfile
from pathlib import Path

from fastapi import UploadFile
from sqlalchemy.orm import Session

from app.core.settings import settings
from app.models.context_chunk import ContextChunk
from app.schemas.document_schema import DocumentIngestResponse, DocumentIngestSummary
from app.services.embedding_service import EmbeddingService
from app.services.git_service import GitService


class DocumentService:
    @staticmethod
    def ingest_files(
        project_id: str,
        files: list[UploadFile],
        db: Session,
    ) -> DocumentIngestResponse:
        if not files:
            raise ValueError("Debe enviar al menos un archivo")

        summaries: list[DocumentIngestSummary] = []
        total_chunks = 0
        seen_filenames: set[str] = set()

        try:
            for upload in files:
                filename = Path(upload.filename or "uploaded").name
                filename_key = filename.casefold()
                if filename_key in seen_filenames:
                    raise ValueError(f"El archivo '{filename}' está duplicado en la misma solicitud")
                seen_filenames.add(filename_key)
                suffix = Path(filename).suffix.lower()
                if not GitService.is_supported_filename(filename):
                    raise ValueError(f"El archivo '{filename}' tiene un formato no soportado")

                content = upload.file.read()
                if not content:
                    raise ValueError(f"El archivo '{filename}' está vacío")

                with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temp_file:
                    temp_file.write(content)
                    temp_path = Path(temp_file.name)

                try:
                    chunks = GitService.extract_chunks_for_file(
                        full_path=temp_path,
                        rel_path=filename,
                        chunk_size=settings.rag_chunk_size,
                        chunk_overlap=settings.rag_chunk_overlap,
                        max_chunks=settings.rag_document_max_chunks_per_file,
                    )
                finally:
                    temp_path.unlink(missing_ok=True)

                if not chunks:
                    raise ValueError(f"El archivo '{filename}' no pudo procesarse o no contiene texto extraíble")

                embedding_texts = [
                    DocumentService._embedding_text(
                        filename=filename,
                        artifact_type=str(chunk.get("artifact_type") or "document"),
                        content=str(chunk["content"]),
                    )
                    for chunk in chunks
                ]
                embeddings = DocumentService._embed_in_batches(embedding_texts)
                source = f"project:{project_id}:document:{filename}"

                db.query(ContextChunk).filter(
                    ContextChunk.metadata_json["project_id"].astext == project_id,
                    ContextChunk.metadata_json["source_type"].astext == "document",
                    ContextChunk.metadata_json["document"].astext == filename,
                ).delete(synchronize_session=False)

                for index, (chunk_info, embedding) in enumerate(zip(chunks, embeddings)):
                    db.add(
                        ContextChunk(
                            source=source,
                            content=str(chunk_info["content"]),
                            metadata_json={
                                "project_id": project_id,
                                "source_type": "document",
                                "document": filename,
                                "file_name": filename,
                                "file_path": filename,
                                "chunk_index": index,
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

                artifact_type = str(chunks[0].get("artifact_type") or "document")
                summaries.append(
                    DocumentIngestSummary(
                        name=filename,
                        artifact_type=artifact_type,
                        chunks_created=len(chunks),
                    )
                )
                total_chunks += len(chunks)

            db.commit()
            return DocumentIngestResponse(
                project_id=project_id,
                documents=summaries,
                total_chunks=total_chunks,
            )
        except Exception:
            db.rollback()
            raise

    @staticmethod
    def _embedding_text(
        filename: str,
        artifact_type: str,
        content: str,
    ) -> str:
        return "\n".join(
            [
                f"document: {filename}",
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
