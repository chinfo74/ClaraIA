"""
Central configuration for Clara, read from `backend/.env`.

Nothing here is secret: real values live in `backend/.env` (git-ignored) and the
template is `backend/.env.example`. Access settings everywhere via
`get_settings()` so the .env is parsed only once.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent          # .../backend
PROJECT_ROOT = BACKEND_DIR.parent                             # repo root
ADMIN_DIR = PROJECT_ROOT / "admin"
WIDGET_DIR = PROJECT_ROOT / "widget"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(BACKEND_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ── LLM (provider-agnostic, default Mistral for EU residency) ──────────────
    llm_provider: str = "mistral"                 # mistral | (anthropic | openai | ollama later)
    mistral_api_key: str = ""
    # Reliable model for extraction / French writing (ingestion step).
    mistral_model: str = "mistral-medium-latest"
    # Small fast model for the router / Manager (used in step 3).
    mistral_router_model: str = "mistral-small-latest"
    # Local chat model used when LLM_PROVIDER=ollama (free, fully offline).
    ollama_model: str = "mistral-nemo"

    # ── Embeddings (separate provider switch) ──────────────────────────────────
    embed_provider: str = "mistral"               # mistral | ollama
    mistral_embed_model: str = "mistral-embed"
    ollama_base_url: str = "http://localhost:11434"
    ollama_embed_model: str = "nomic-embed-text"

    # ── Vector store ───────────────────────────────────────────────────────────
    chroma_dir: str = str(PROJECT_ROOT / "base_clara")
    chroma_collection: str = "clara_docs"

    # ── Chunking ───────────────────────────────────────────────────────────────
    chunk_size: int = 800
    chunk_overlap: int = 120
    # Hard cap on characters sent to the LLM during extraction (prototype safety).
    max_extract_chars: int = 60_000

    # ── PII guardrail (Presidio, French) ───────────────────────────────────────
    pii_language: str = "fr"
    spacy_model: str = "fr_core_news_md"
    # Privacy-by-design: the raw uploaded file still contains PII. By default it is
    # deleted after ingestion (the cleaned .md is kept). Set true to retain it.
    keep_uploads: bool = False

    # ── Paths (data produced by the ingestion pipeline) ────────────────────────
    data_dir: str = str(BACKEND_DIR / "data")
    cleaned_md_dir: str = str(BACKEND_DIR / "data" / "cleaned_md")
    uploads_dir: str = str(BACKEND_DIR / "data" / "uploads")
    log_file: str = str(BACKEND_DIR / "data" / "clara.jsonl")
    documents_registry: str = str(BACKEND_DIR / "data" / "documents.json")

    # ── Back-office authentication (HTTP Basic) ────────────────────────────────
    admin_user: str = "admin"
    admin_password: str = ""  # doit être défini dans .env pour activer le back-office

    # ── Server ─────────────────────────────────────────────────────────────────
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
    # Ensure runtime directories exist (cheap, idempotent).
    for d in (s.data_dir, s.cleaned_md_dir, s.uploads_dir):
        Path(d).mkdir(parents=True, exist_ok=True)
    return s
