from typing import Any

from pydantic import BaseModel, Field


class RAGAskRequest(BaseModel):
    query: str
    project_id: str = Field(min_length=1, max_length=120)
    branches: list[str] | None = None
    source: str | list[str] | None = None
    file_paths: list[str] | None = None
    top_k: int = Field(default=8, ge=1, le=20)
    max_new_tokens: int = Field(default=1600, ge=64, le=8000)
    conversation_history: list[dict[str, Any]] = Field(default_factory=list)
    additional_context: str | None = None
    debug: bool = False


class RAGCitation(BaseModel):
    chunk_id: int
    source: str
    similarity: float
    source_type: str = "unknown"
    repository: str | None = None
    document: str | None = None
    file_path: str | None = None
    line_start: int | None = None
    line_end: int | None = None
    page: int | None = None
    tab: str | None = None
    branch: str | None = None
    commit: str | None = None
    artifact_type: str | None = None


class RAGAskResponse(BaseModel):
    answer: str
    citations: list[RAGCitation]
    context_chunks_used: int
    retrieval_query: str
    provider: str
    model: str
    response_time_ms: float = 0.0
    debug_matches: list[dict] | None = None
