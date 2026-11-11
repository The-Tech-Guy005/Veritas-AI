from pydantic_settings import BaseSettings, SettingsConfigDict
from pathlib import Path

class Settings(BaseSettings):
    app_name: str = "Veritas AI Research Agent"
    tavily_api_key: str = ""
    data_dir: str = "./data"
    chroma_collection: str = "veritas_documents"
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    chunk_size: int = 900
    chunk_overlap: int = 150
    max_upload_mb: int = 20
    cors_origins: list[str] = ["*"]

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

settings = Settings()
Path(settings.data_dir).mkdir(parents=True, exist_ok=True)
