import json
from pathlib import Path
from types import SimpleNamespace

import pytest

pytest.importorskip("presidio_analyzer")
pytest.importorskip("presidio_anonymizer")

from backend.rag import ingestion  # noqa: E402

try:
    ingestion.scrub_pii("amorce")
except RuntimeError as exc:
    pytest.skip(f"Modèle spaCy FR indisponible : {exc}", allow_module_level=True)


class _FakeLLM:
    def complete_json(self, system, user, schema, schema_name="output"):
        return {
            "title": "Conditions de réservation",
            "doc_type": "cgv",
            "summary": "Conditions de réservation et d'annulation.",
            "keywords": ["réservation", "annulation", "acompte"],
            "content_md": (
                "## Réservation\n"
                "Un acompte de 30% est demandé à la réservation.\n\n"
                "## Contact resté par erreur\n"
                "Pour toute question, contactez Paul Durand au 06 11 22 33 44."
            ),
        }


class _FakeStore:
    def __init__(self):
        self.items: dict[str, dict] = {}

    def delete_by_source(self, source):
        removed = [k for k, v in self.items.items() if v["meta"].get("source") == source]
        for k in removed:
            del self.items[k]
        return len(removed)

    def add(self, ids, texts, embeddings, metadatas):
        for i, t, m in zip(ids, texts, metadatas):
            self.items[i] = {"text": t, "meta": m}

    def count(self):
        return len(self.items)


def test_pipeline_removes_residual_pii_and_indexes(tmp_path, monkeypatch):
    fake_settings = SimpleNamespace(
        cleaned_md_dir=str(tmp_path / "md"),
        documents_registry=str(tmp_path / "documents.json"),
        chunk_size=400,
        chunk_overlap=60,
        max_extract_chars=60_000,
    )
    Path(fake_settings.cleaned_md_dir).mkdir(parents=True, exist_ok=True)

    store = _FakeStore()
    monkeypatch.setattr(ingestion, "get_settings", lambda: fake_settings)
    monkeypatch.setattr(ingestion, "get_llm_client", lambda: _FakeLLM())
    monkeypatch.setattr(ingestion, "embed_texts", lambda texts: [[0.1, 0.2, 0.3] for _ in texts])
    monkeypatch.setattr(ingestion, "get_vectorstore", lambda: store)

    src = tmp_path / "cgv.txt"
    src.write_text("Texte brut du document (le LLM est simulé).", encoding="utf-8")

    result = ingestion.ingest_file(str(src), "cgv.txt")

    assert result.status == "success"
    assert result.doc_type == "cgv"
    assert result.n_chunks >= 1

    md = Path(result.md_path).read_text(encoding="utf-8")
    assert "Paul Durand" not in md
    assert "06 11 22 33 44" not in md
    assert result.pii_removed >= 2
    assert "acompte" in md
    assert store.count() == result.n_chunks

    registry = json.loads(Path(fake_settings.documents_registry).read_text(encoding="utf-8"))
    assert registry["cgv"]["status"] == "success"
