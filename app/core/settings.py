from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "API RAG"
    api_prefix: str = "/api"
    api_v1_prefix: str = "/api/v1"
    database_url: str = "postgresql://postgres:postgres@127.0.0.1:5432/ragdb"

    llm_provider: str = "huggingface"
    llm_timeout_seconds: float = 120.0
    llm_max_output_tokens: int = 1600

    hf_api_token: str | None = None
    hf_model_url: str = "https://router.huggingface.co/v1/chat/completions"
    hf_model_name: str = "Qwen/Qwen2.5-Coder-32B-Instruct"

    openai_api_key: str | None = None
    openai_base_url: str = "https://api.openai.com/v1"
    openai_model_name: str = "gpt-5.4-mini"

    anthropic_api_key: str | None = None
    anthropic_base_url: str = "https://api.anthropic.com/v1"
    anthropic_model_name: str = "claude-sonnet-5"
    anthropic_version: str = "2023-06-01"

    openai_compatible_api_key: str | None = None
    openai_compatible_base_url: str | None = None
    openai_compatible_model_name: str | None = None

    embedding_provider: str = "huggingface"
    embedding_model_name: str = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
    embedding_dimensions: int = 1536
    embedding_batch_size: int = 16
    openai_embedding_model_name: str = "text-embedding-3-small"

    rag_min_similarity: float = 0.15
    rag_memory_turns: int = 6
    rag_default_top_k: int = 8
    rag_candidate_multiplier: int = 4
    rag_chunk_size: int = 1200
    rag_chunk_overlap: int = 150
    rag_repository_max_files: int = 500
    rag_repository_max_chunks_per_file: int = 50
    rag_commit_max_diff_files: int = 50
    rag_commit_max_diff_chunks_per_file: int = 5
    rag_commit_max_patch_chars: int = 20000
    rag_document_max_chunks_per_file: int = 300

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls,
        init_settings,
        env_settings,
        dotenv_settings,
        file_secret_settings,
    ):
        return init_settings, env_settings, dotenv_settings, file_secret_settings

    @property
    def sqlalchemy_database_url(self) -> str:
        return self.database_url

    @property
    def active_llm_model(self) -> str:
        provider = self.llm_provider.strip().lower()
        if provider == "huggingface":
            return self.hf_model_name
        if provider == "openai":
            return self.openai_model_name
        if provider == "anthropic":
            return self.anthropic_model_name
        if provider == "openai_compatible":
            return self.openai_compatible_model_name or ""
        return ""


settings = Settings()
