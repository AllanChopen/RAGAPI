import re

from pydantic import BaseModel, Field, field_validator, model_validator


class RepositoryBranchesRequest(BaseModel):
    repository_url: str = Field(
        min_length=1,
        description="URL HTTPS del repositorio Git que se desea consultar.",
    )


class RepositoryBranchInfo(BaseModel):
    name: str
    commit: str
    default: bool = False


class RepositoryBranchesResponse(BaseModel):
    repository: str
    default_branch: str | None = None
    branches: list[RepositoryBranchInfo]


class RepositoryCommitsRequest(BaseModel):
    repository_url: str = Field(min_length=1, description="URL del repositorio Git.")
    branch: str | None = Field(default=None, description="Rama a consultar. Por defecto usa HEAD.")
    limit: int = Field(default=20, ge=1, le=100)


class RepositoryCommitInfo(BaseModel):
    sha: str
    message: str
    authored_at: str


class RepositoryCommitsResponse(BaseModel):
    repository: str
    branch: str
    commits: list[RepositoryCommitInfo]


class RepositoryCommitIngestRequest(BaseModel):
    project_id: str = Field(min_length=1, max_length=120)
    repository_url: str = Field(min_length=1)
    commits: list[str] = Field(min_length=1, max_length=10)

    @field_validator("commits")
    @classmethod
    def validate_commits(cls, commits: list[str]) -> list[str]:
        normalized = list(dict.fromkeys(commit.strip().lower() for commit in commits))
        if any(not re.fullmatch(r"[0-9a-f]{7,40}", commit) for commit in normalized):
            raise ValueError("Cada commit debe ser un SHA hexadecimal de 7 a 40 caracteres")
        return normalized


class RepositoryCommitIngestSummary(BaseModel):
    sha: str
    message: str
    files_processed: int
    chunks_created: int


class RepositoryCommitIngestResponse(BaseModel):
    project_id: str
    repository: str
    commits: list[RepositoryCommitIngestSummary]
    total_files: int
    total_chunks: int


class RepositoryIngestRequest(BaseModel):
    project_id: str = Field(
        min_length=1,
        max_length=120,
        description="Identificador externo del proyecto utilizado para aislar su conocimiento RAG.",
    )
    repository_url: str = Field(
        min_length=1,
        description="URL HTTPS del repositorio Git que se desea indexar.",
    )
    branches: list[str] | None = Field(
        default=None,
        description="Ramas que se desean indexar. Si se omite, se indexan todas las ramas remotas detectadas.",
    )

    @model_validator(mode="after")
    def normalize_branches(self) -> "RepositoryIngestRequest":
        if self.branches is not None:
            self.branches = list(
                dict.fromkeys(branch.strip() for branch in self.branches if branch.strip())
            )
            if not self.branches:
                self.branches = None
        return self


class RepositoryBranchIngestSummary(BaseModel):
    name: str
    commit: str
    files_processed: int
    chunks_created: int


class RepositoryIngestResponse(BaseModel):
    project_id: str
    repository: str
    branches: list[RepositoryBranchIngestSummary]
    total_files: int
    total_chunks: int


class RepositoryFileChange(BaseModel):
    status: str
    path: str
    previous_path: str | None = None
