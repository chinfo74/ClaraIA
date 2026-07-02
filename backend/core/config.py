from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent
PROJECT_ROOT = BACKEND_DIR.parent
ADMIN_DIR = PROJECT_ROOT / "admin"
WIDGET_DIR = PROJECT_ROOT / "widget"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(BACKEND_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    llm_provider: str = "mistral"
    mistral_api_key: str = ""
    mistral_model: str = "mistral-medium-latest"
    mistral_router_model: str = "mistral-small-latest"
    ollama_model: str = "mistral-nemo"

    embed_provider: str = "mistral"
    mistral_embed_model: str = "mistral-embed"
    ollama_base_url: str = "http://localhost:11434"
    ollama_embed_model: str = "nomic-embed-text"

    chroma_dir: str = str(PROJECT_ROOT / "base_clara")
    chroma_collection: str = "clara_docs"

    chunk_size: int = 800
    chunk_overlap: int = 120
    max_extract_chars: int = 60_000

    pii_language: str = "fr"
    spacy_model: str = "fr_core_news_md"
    keep_uploads: bool = False

    data_dir: str = str(BACKEND_DIR / "data")
    cleaned_md_dir: str = str(BACKEND_DIR / "data" / "cleaned_md")
    uploads_dir: str = str(BACKEND_DIR / "data" / "uploads")
    log_file: str = str(BACKEND_DIR / "data" / "clara.jsonl")
    documents_registry: str = str(BACKEND_DIR / "data" / "documents.json")

    admin_user: str = "admin"
    admin_password: str = ""

    allowed_origins: str = (
        "http://localhost:5173,http://localhost:8080,http://127.0.0.1:5500,"
        "http://localhost:8000"
    )

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.allowed_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    s = Settings()
    for d in (s.data_dir, s.cleaned_md_dir, s.uploads_dir):
        Path(d).mkdir(parents=True, exist_ok=True)
    return s
