"""
RAG ingestion pipeline (Step 1).

    upload  ->  parse (PDF/DOCX/TXT)
            ->  LLM extraction (doc type + essential info + first PII removal)
            ->  Presidio guardrail (second PII net, French)
            ->  clean .md (frontmatter + body)
            ->  chunk -> embed -> ChromaDB
            ->  registry + structured logs (counts only, never PII content)

Public entry points:
    ingest_file(file_path, original_filename) -> IngestResult     # full pipeline
    add_document_to_vectorstore(md_path, metadata) -> IngestResult # index an existing .md
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..core.config import get_settings
from ..core.llm_client import embed_texts, get_llm_client
from ..core.logging import get_logger, log_event
from .pii import scrub_pii
from .vectorstore import get_vectorstore

logger = get_logger("ingestion")

DOC_TYPES = ["cgv", "contrat_assurance", "guide_sejour", "faq", "tarifs", "procedure", "autre"]

EXTRACTION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "doc_type": {"type": "string", "enum": DOC_TYPES},
        "summary": {"type": "string"},
        "keywords": {"type": "array", "items": {"type": "string"}},
        "content_md": {"type": "string"},
    },
    "required": ["title", "doc_type", "summary", "keywords", "content_md"],
    "additionalProperties": False,
}

EXTRACTION_SYSTEM = (
    "Tu es un assistant d'ingestion documentaire pour Voyage d'Ô, une agence de "
    "location de logements pour curistes seniors. On te donne le texte brut d'un "
    "document interne. Ta mission :\n"
    "1. Identifier le TYPE de document (doc_type) parmi : cgv, contrat_assurance, "
    "guide_sejour, faq, tarifs, procedure, autre.\n"
    "2. Extraire UNIQUEMENT l'information essentielle, factuelle et réutilisable "
    "pour répondre à des clients (conditions, règles, tarifs, procédures, garanties, "
    "délais...). Reformule proprement en Markdown structuré (titres ##, listes).\n"
    "3. SUPPRIMER toute donnée personnelle ou compromettante : noms et prénoms de "
    "personnes, adresses postales, numéros de téléphone, e-mails, numéros de client/"
    "contrat/sécurité sociale, IBAN, signatures. Ne JAMAIS recopier ces éléments.\n"
    "4. CONSERVER les informations métier non personnelles : noms de villes/stations "
    "thermales, montants, pourcentages, durées, conditions générales.\n"
    "N'invente rien. Si une information n'est pas dans le texte, ne l'ajoute pas. "
    "Réponds en français. content_md ne doit contenir aucune donnée personnelle."
)


@dataclass
class IngestResult:
    document_id: str
    filename: str
    status: str  # "success" | "indexed" | "error"
    doc_type: str = "autre"
    title: str = ""
    summary: str = ""
    keywords: list[str] = field(default_factory=list)
    md_path: str = ""
    n_chunks: int = 0
    pii_removed: int = 0
    pii_breakdown: dict[str, int] = field(default_factory=dict)
    ingested_at: str = ""
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class UnsupportedFileTypeError(ValueError):
    pass


# ── Parsing ────────────────────────────────────────────────────────────────────


def _extract_pdf(path: str) -> str:
    """pdfplumber handles glyph spacing far better than pypdf on real-world PDFs;
    fall back to pypdf if pdfplumber is unavailable or returns nothing."""
    try:
        import pdfplumber

        with pdfplumber.open(path) as pdf:
            text = "\n".join((page.extract_text() or "") for page in pdf.pages)
        if text.strip():
            return text
    except Exception:  # noqa: BLE001
        logger.warning("pdfplumber a échoué, repli sur pypdf")
    from pypdf import PdfReader

    reader = PdfReader(path)
    return "\n".join((page.extract_text() or "") for page in reader.pages)


def extract_text(file_path: str | Path) -> str:
    path = Path(file_path)
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return _extract_pdf(str(path))
    if suffix == ".docx":
        import docx

        document = docx.Document(str(path))
        return "\n".join(p.text for p in document.paragraphs)
    if suffix in (".txt", ".md"):
        return path.read_text(encoding="utf-8", errors="replace")
    raise UnsupportedFileTypeError(
        f"Format non supporté : '{suffix}'. Formats acceptés : PDF, DOCX, TXT."
    )


# ── Chunking (lightweight, no extra dependency) ──────────────────────────────────


def chunk_text(text: str, size: int, overlap: int) -> list[str]:
    text = text.strip()
    if not text:
        return []

    paragraphs = re.split(r"\n\s*\n", text)
    chunks: list[str] = []
    current = ""

    def flush() -> None:
        nonlocal current
        if current.strip():
            chunks.append(current.strip())
        current = ""

    for para in paragraphs:
        para = para.strip()
        if not para:
            continue
        if len(para) > size:
            flush()
            for sentence in re.split(r"(?<=[.!?])\s+", para):
                if len(current) + len(sentence) + 1 <= size:
                    current = f"{current} {sentence}".strip()
                else:
                    flush()
                    current = sentence[:size]
            continue
        if len(current) + len(para) + 2 <= size:
            current = f"{current}\n\n{para}".strip()
        else:
            flush()
            current = para
    flush()

    if overlap > 0 and len(chunks) > 1:
        with_overlap: list[str] = [chunks[0]]
        for i in range(1, len(chunks)):
            tail = chunks[i - 1][-overlap:]
            with_overlap.append(f"{tail}\n{chunks[i]}".strip())
        chunks = with_overlap
    return chunks


# ── Markdown assembly / parsing ──────────────────────────────────────────────────


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "document"


def _build_markdown(
    title: str, doc_type: str, source: str, summary: str, keywords: list[str], content: str
) -> str:
    keywords_line = ", ".join(keywords)
    return (
        "---\n"
        f"title: {title}\n"
        f"doc_type: {doc_type}\n"
        f"source: {source}\n"
        f"ingested_at: {datetime.now(timezone.utc).isoformat()}\n"
        f"keywords: {keywords_line}\n"
        "---\n\n"
        f"# {title}\n\n"
        f"> **Résumé** : {summary}\n\n"
        f"{content}\n"
    )


def _read_md_body(md_path: str | Path) -> str:
    text = Path(md_path).read_text(encoding="utf-8")
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end != -1:
            text = text[end + 4 :]
    return text.strip()


# ── Registry (documents.json) ────────────────────────────────────────────────────


def _load_registry() -> dict[str, dict[str, Any]]:
    path = Path(get_settings().documents_registry)
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def _save_registry(registry: dict[str, dict[str, Any]]) -> None:
    path = Path(get_settings().documents_registry)
    path.write_text(json.dumps(registry, ensure_ascii=False, indent=2), encoding="utf-8")


def list_documents() -> list[dict[str, Any]]:
    docs = list(_load_registry().values())
    docs.sort(key=lambda d: d.get("ingested_at", ""), reverse=True)
    return docs


def get_document(document_id: str) -> dict[str, Any] | None:
    return _load_registry().get(document_id)


# ── Indexing ──────────────────────────────────────────────────────────────────


def add_document_to_vectorstore(md_path: str, metadata: dict[str, Any]) -> IngestResult:
    """Chunk an existing .md, embed it and (re)add it to the vector store."""
    source = metadata.get("source") or Path(md_path).name
    document_id = metadata.get("document_id") or _slugify(Path(md_path).stem)

    body = _read_md_body(md_path)
    settings = get_settings()
    chunks = chunk_text(body, settings.chunk_size, settings.chunk_overlap)
    if not chunks:
        raise ValueError("Aucun contenu exploitable à indexer après nettoyage.")

    embeddings = embed_texts(chunks)
    store = get_vectorstore()
    store.delete_by_source(source)  # avoid duplicates on re-ingestion

    base_meta = {
        "source": source,
        "document_id": document_id,
        "doc_type": metadata.get("doc_type", "autre"),
        "title": metadata.get("title", ""),
    }
    ids = [f"{document_id}::{i}" for i in range(len(chunks))]
    metadatas = [{**base_meta, "chunk": i} for i in range(len(chunks))]
    store.add(ids=ids, texts=chunks, embeddings=embeddings, metadatas=metadatas)

    return IngestResult(
        document_id=document_id,
        filename=source,
        status="indexed",
        doc_type=metadata.get("doc_type", "autre"),
        title=metadata.get("title", ""),
        md_path=str(md_path),
        n_chunks=len(chunks),
        pii_removed=int(metadata.get("pii_removed", 0)),
        pii_breakdown=metadata.get("pii_breakdown", {}),
    )


# ── LLM extraction ──────────────────────────────────────────────────────────────


def _llm_extract(raw_text: str) -> dict[str, Any]:
    client = get_llm_client()
    data = client.complete_json(
        system=EXTRACTION_SYSTEM,
        user=f"Voici le texte brut du document à traiter :\n\n{raw_text}",
        schema=EXTRACTION_SCHEMA,
        schema_name="document_extraction",
    )
    data.setdefault("title", "Document sans titre")
    data.setdefault("doc_type", "autre")
    data.setdefault("summary", "")
    data.setdefault("keywords", [])
    data.setdefault("content_md", "")
    if data["doc_type"] not in DOC_TYPES:
        data["doc_type"] = "autre"
    return data


# ── Full pipeline ────────────────────────────────────────────────────────────────


def ingest_file(file_path: str | Path, original_filename: str) -> IngestResult:
    document_id = _slugify(Path(original_filename).stem)
    started = datetime.now(timezone.utc).isoformat()
    log_event(logger, "ingest.start", document_id=document_id, filename=original_filename)

    try:
        raw_text = extract_text(file_path)
        if not raw_text.strip():
            raise ValueError(
                "Aucun texte extrait (document vide ou scanné sans OCR)."
            )
        log_event(logger, "ingest.parsed", document_id=document_id, chars=len(raw_text))

        settings = get_settings()
        extraction = _llm_extract(raw_text[: settings.max_extract_chars])
        log_event(
            logger, "ingest.extracted", document_id=document_id,
            doc_type=extraction["doc_type"], content_chars=len(extraction["content_md"]),
        )

        # Second PII net (Presidio). Log counts only — never the matched content.
        scrubbed_content = scrub_pii(extraction["content_md"])
        scrubbed_summary = scrub_pii(extraction["summary"])
        scrubbed_title = scrub_pii(extraction["title"])
        breakdown: dict[str, int] = {}
        for part in (scrubbed_content, scrubbed_summary, scrubbed_title):
            for entity, n in part.counts.items():
                breakdown[entity] = breakdown.get(entity, 0) + n
        pii_total = sum(breakdown.values())
        log_event(
            logger, "ingest.pii_scrubbed", document_id=document_id,
            pii_removed=pii_total, breakdown=breakdown,
        )

        md_text = _build_markdown(
            title=scrubbed_title.text.strip() or "Document sans titre",
            doc_type=extraction["doc_type"],
            source=original_filename,
            summary=scrubbed_summary.text.strip(),
            keywords=extraction["keywords"],
            content=scrubbed_content.text.strip(),
        )
        md_path = Path(settings.cleaned_md_dir) / f"{document_id}.md"
        md_path.write_text(md_text, encoding="utf-8")

        result = add_document_to_vectorstore(
            str(md_path),
            metadata={
                "source": original_filename,
                "document_id": document_id,
                "doc_type": extraction["doc_type"],
                "title": scrubbed_title.text.strip(),
                "pii_removed": pii_total,
                "pii_breakdown": breakdown,
            },
        )
        result.status = "success"
        result.summary = scrubbed_summary.text.strip()
        result.keywords = extraction["keywords"]
        result.ingested_at = started

        registry = _load_registry()
        registry[document_id] = result.to_dict()
        _save_registry(registry)

        log_event(
            logger, "ingest.success", document_id=document_id,
            doc_type=result.doc_type, n_chunks=result.n_chunks, pii_removed=pii_total,
            total_in_store=get_vectorstore().count(),
        )
        return result

    except Exception as exc:  # noqa: BLE001 — graceful degradation, surface a clean status
        logger.exception("Echec ingestion document_id=%s", document_id)
        result = IngestResult(
            document_id=document_id,
            filename=original_filename,
            status="error",
            ingested_at=started,
            error=str(exc),
        )
        registry = _load_registry()
        registry[document_id] = result.to_dict()
        _save_registry(registry)
        return result
