from typing import Any

from typing import TypedDict

from pydantic import BaseModel, Field, model_validator

from app.schemas.repository_schema import RepositoryFileChange


class ConversationTurn(TypedDict):
    user: str
    assistant: str
    
class RAGQueryRequest(BaseModel):
    project_id: str = Field(
        min_length=1,
        max_length=120,
        description="Identificador del proyecto cuyo conocimiento indexado se desea consultar.",
    )
    question: str = Field(
        min_length=1,
        description="Pregunta en lenguaje natural que se enviará al RAG.",
    )
    branches: list[str] | None = Field(
        default=None,
        description="Ramas Git a las que se debe restringir la recuperación. Si se omite, se consulta todo el proyecto indexado.",
    )
    document: str | None = Field(
        default=None,
        min_length=1,
        description="Nombre exacto de un documento indexado en el proyecto. Si se omite, se consultan todas las fuentes. No se combina con branches.",
    )
    commit: str | None = Field(
        default=None,
        min_length=7,
        max_length=40,
        pattern=r"^[0-9a-fA-F]+$",
        description="SHA completo o prefijo único de un commit indexado. No se combina con branches ni document.",
    )
    repository: str | None = Field(
        default=None,
        min_length=1,
        description="Nombre del repositorio para desambiguar un commit cuando el proyecto contiene varios repositorios.",
    )
    conversation_history: list[ConversationTurn] = Field(
        default_factory=list,
        description=(
            "Historial opcional de conversaciones anteriores. "
            "Cada elemento contiene la pregunta del usuario y la respuesta anterior del RAG."
        ),
    )
    debug: bool = Field(
        default=False,
        description="Incluye información adicional de recuperación para depuración cuando está activado.",
    )

    @model_validator(mode="after")
    def normalize_branches(self) -> "RAGQueryRequest":
        if self.branches is not None:
            self.branches = list(
                dict.fromkeys(branch.strip() for branch in self.branches if branch.strip())
            )
            if not self.branches:
                self.branches = None
        if self.document is not None:
            self.document = self.document.strip()
            if not self.document:
                raise ValueError("document no puede estar vacío")
        if self.document and self.branches:
            raise ValueError("document y branches no pueden utilizarse juntos")
        if self.commit is not None:
            self.commit = self.commit.lower()
        if self.commit and (self.document or self.branches):
            raise ValueError("commit no puede combinarse con document ni branches")
        if self.repository is not None:
            self.repository = self.repository.strip()
            if not self.repository:
                raise ValueError("repository no puede estar vacío")
            if not self.commit:
                raise ValueError("repository requiere commit")
        return self


class RAGSource(BaseModel):
    chunk_id: int
    source_type: str
    source: str
    repository: str | None = None
    document: str | None = None
    branch: str | None = None
    commit: str | None = None
    file_path: str | None = None
    line_start: int | None = None
    line_end: int | None = None
    page: int | None = None
    tab: str | None = None
    artifact_type: str | None = None
    score: float


class RAGQueryResponse(BaseModel):
    project_id: str
    question: str
    answer: str
    sources: list[RAGSource]
    context_chunks_used: int
    provider: str
    model: str
    response_time_ms: float
    debug_matches: list[dict] | None = None


class RAGCompareRequest(BaseModel):
    project_id: str = Field(
        min_length=1,
        max_length=120,
        description="Identificador del proyecto que contiene las ramas previamente indexadas.",
    )
    repository_url: str = Field(
        min_length=1,
        description="URL HTTPS del repositorio Git que se desea comparar.",
    )
    branch_a: str = Field(
        min_length=1,
        description="Primera rama de la comparación.",
    )
    branch_b: str = Field(
        min_length=1,
        description="Segunda rama de la comparación.",
    )
    question: str = Field(
        default="¿Qué diferencias relevantes existen entre estas dos ramas?",
        min_length=1,
        description="Pregunta que orientará la explicación RAG sobre las diferencias encontradas.",
    )
    debug: bool = Field(
        default=False,
        description="Incluye información adicional de recuperación para depuración cuando está activado.",
    )

    @model_validator(mode="after")
    def validate_branches(self) -> "RAGCompareRequest":
        if self.branch_a == self.branch_b:
            raise ValueError("branch_a y branch_b deben ser diferentes")
        return self


class RAGCompareResponse(BaseModel):
    project_id: str
    repository: str
    branch_a: str
    branch_b: str
    question: str
    answer: str
    changes: list[RepositoryFileChange]
    sources: list[RAGSource]
    context_chunks_used: int
    provider: str
    model: str
    response_time_ms: float
    debug_matches: list[dict] | None = None


class RAGHealthResponse(BaseModel):
    status: str
    database: str
    vector_store: str
    embedding_service: str
    embedding_provider: str
    embedding_model: str
    llm_service: str
    llm_provider: str
    llm_model: str


class RAGMetricsResponse(BaseModel):
    total_queries: int
    successful_queries: int
    failed_queries: int
    average_response_time_ms: float


class RAGIndexDeleteResponse(BaseModel):
    project_id: str
    deleted_chunks: int


class RAGIndexedBranch(BaseModel):
    name: str
    commit: str | None = None
    chunks: int


class RAGIndexedCommit(BaseModel):
    sha: str
    message: str | None = None
    chunks: int


class RAGIndexedRepository(BaseModel):
    name: str
    chunks: int
    branches: list[RAGIndexedBranch]
    commits: list[RAGIndexedCommit] = Field(default_factory=list)


class RAGIndexedDocument(BaseModel):
    name: str
    artifact_type: str | None = None
    chunks: int


class RAGProjectSourcesResponse(BaseModel):
    project_id: str
    repositories: list[RAGIndexedRepository]
    documents: list[RAGIndexedDocument]
    total_chunks: int
