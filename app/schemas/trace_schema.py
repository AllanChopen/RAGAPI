from pydantic import BaseModel, Field


class DataDictionaryIngestRequest(BaseModel):
    file_path: str
    dictionary_name: str
    sheet_name: str | None = None
    max_rows: int = Field(default=5000, ge=1, le=50000)


class DataDictionaryIngestResponse(BaseModel):
    dictionary_name: str
    sheets_processed: int
    fields_ingested: int


class FieldUsageTraceRequest(BaseModel):
    field_name: str
    dictionary_name: str
    top_k: int = Field(default=20, ge=1, le=200)


class FieldUsageMatch(BaseModel):
    source: str
    file_path: str
    line_start: int
    line_end: int
    similarity: float
    snippet: str


class FieldUsageTraceResponse(BaseModel):
    field_name: str
    dictionary_name: str
    dictionary_tab: str | None = None
    dictionary_row: int | None = None
    dictionary_definition: str | None = None
    matches: list[FieldUsageMatch]
