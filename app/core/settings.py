from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "RAG API"
    api_prefix: str = "/api"
    database_url: str | None = None
    hf_api_token: str | None = None
    hf_model_url: str = "https://router.huggingface.co/v1/chat/completions"
    hf_model_name: str = "Qwen/Qwen2.5-Coder-32B-Instruct"
    embedding_dimensions: int = 1536
    rag_min_similarity: float = 0.05
    rag_memory_turns: int = 6
    mysql_user: str = "root"
    mysql_password: str = "password"
    mysql_host: str = "127.0.0.1"
    mysql_port: int = 3306
    mysql_database: str = "ragdb"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls,
        init_settings,
        env_settings,
        dotenv_settings,
        file_secret_settings,
    ):
        # Prefer project .env values to avoid conflicts with stale global env vars.
        return init_settings, dotenv_settings, env_settings, file_secret_settings

    @property
    def sqlalchemy_database_url(self) -> str:
        if self.database_url:
            return self.database_url

        return (
            f"mysql+pymysql://{self.mysql_user}:{self.mysql_password}"
            f"@{self.mysql_host}:{self.mysql_port}/{self.mysql_database}"
        )


settings = Settings()