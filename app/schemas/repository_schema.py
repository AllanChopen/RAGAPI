from pydantic import BaseModel, Field, model_validator


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
