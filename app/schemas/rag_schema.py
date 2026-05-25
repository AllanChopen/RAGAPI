from pydantic import BaseModel, Field


class RAGAskRequest(BaseModel):
    query: str
    source: str | None = None
    top_k: int = Field(default=5, ge=1, le=20)
    max_new_tokens: int = Field(default=300, ge=32, le=1200)
    temperature: float = Field(default=0.2, ge=0.0, le=1.5)
    conversation_history: list[dict[str, str]] = Field(default_factory=list)


class RAGCitation(BaseModel):
    chunk_id: int
    source: str
    similarity: float
    file_path: str | None = None
    line_start: int | None = None
    line_end: int | None = None
    tab: str | None = None


class RAGAskResponse(BaseModel):
    answer: str
    citations: list[RAGCitation]
    context_chunks_used: int
    retrieval_query: str
    model: str
