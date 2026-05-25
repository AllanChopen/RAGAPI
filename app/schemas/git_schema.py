from pydantic import BaseModel, Field, model_validator


class GitSourceRequest(BaseModel):
    repo_url: str | None = None
    local_path: str | None = None
    branch: str | None = None
    max_files: int = Field(default=200, ge=1, le=5000)
    include_extensions: list[str] = Field(
        default_factory=lambda: [
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
            ".mmd",
            ".mermaid",
            ".drawio",
            ".json",
            ".csv",
            ".yaml",
            ".yml",
            ".xml",
            ".pdf",
            ".xlsx",
        ]
    )

    @model_validator(mode="after")
    def validate_source(self) -> "GitSourceRequest":
        if not self.repo_url and not self.local_path:
            raise ValueError("Provide either repo_url or local_path")

        if self.repo_url and self.local_path:
            raise ValueError("Use only one source: repo_url or local_path")

        return self


class GitCommitSummary(BaseModel):
    hash: str
    author: str
    date: str
    message: str


class GitScanResponse(BaseModel):
    repo_name: str
    source_type: str
    current_branch: str
    latest_commit: GitCommitSummary
    scanned_files_total: int
    sampled_files: list[str]


class GitIngestRequest(GitSourceRequest):
    chunk_size: int = Field(default=1200, ge=200, le=4000)
    chunk_overlap: int = Field(default=150, ge=0, le=1000)
    max_chunks_per_file: int = Field(default=20, ge=1, le=300)

    @model_validator(mode="after")
    def validate_chunking(self) -> "GitIngestRequest":
        if self.chunk_overlap >= self.chunk_size:
            raise ValueError("chunk_overlap must be less than chunk_size")
        return self


class GitIngestResponse(BaseModel):
    repo_name: str
    source_type: str
    current_branch: str
    latest_commit: GitCommitSummary
    files_processed: int
    chunks_inserted: int
