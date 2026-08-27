from pydantic import BaseModel, Field


class VectorHealthResponse(BaseModel):
    vector_extension_enabled: bool
    context_chunks_table_exists: bool
    embedding_dimensions: int


class VectorSearchRequest(BaseModel):
    query: str
    top_k: int = Field(default=5, ge=1, le=100)
    project_id: str = Field(min_length=1, max_length=120)
    source: str | list[str] | None = None
    branches: list[str] | None = None
    source_types: list[str] | None = None
    file_paths: list[str] | None = None


class VectorSearchResult(BaseModel):
    id: int
    source: str
    content: str
    metadata_json: dict
    similarity: float


class VectorSearchResponse(BaseModel):
    query: str
    top_k: int
    matches: list[VectorSearchResult]
