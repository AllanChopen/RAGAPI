from pydantic import BaseModel, Field
from typing import List


class VectorHealthResponse(BaseModel):
    vector_extension_enabled: bool
    context_chunks_table_exists: bool
    embedding_dimensions: int


class VectorUpsertRequest(BaseModel):
    source: str
    content: str
    embedding: list[float]
    metadata_json: dict = Field(default_factory=dict)


class VectorUpsertResponse(BaseModel):
    id: int
    source: str
    embedding_dimensions: int


class VectorSearchRequest(BaseModel):
    query: str
    top_k: int = Field(default=5, ge=1, le=50)
    # source can be a single source string, a list of source strings, or None (search all)
    source: str | List[str] | None = None


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
