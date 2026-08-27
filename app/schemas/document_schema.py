from pydantic import BaseModel


class DocumentIngestSummary(BaseModel):
    name: str
    artifact_type: str
    chunks_created: int


class DocumentIngestResponse(BaseModel):
    project_id: str
    documents: list[DocumentIngestSummary]
    total_chunks: int
