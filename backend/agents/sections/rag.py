"""
RAG section — answers questions about assurance / conditions from the documents
ingested in step 1 (ChromaDB), instead of handing off to the team.

Flow: retrieve relevant chunks → if nothing relevant, hand off (never guess) →
otherwise synthesize a French answer grounded ONLY on those chunks, with sources.
The query is the pseudonymized message (RGPD: nothing personal leaves to the LLM /
embedding provider).
"""

from __future__ import annotations

from ...core.llm_client import get_llm_client
from ...core.logging import get_logger, log_event
from ...rag.vectorstore import search
from ...session.store import Session
from ..schemas import RAG_MIN_SCORE, RAG_SYSTEM
from ._stubs import handoff

logger = get_logger("rag_section")


def handle_rag(message: str, session: Session, scrubbed_message: str, section: str) -> dict:
    try:
        hits = search(scrubbed_message, n_results=5)
    except Exception:  # noqa: BLE001 — embedding/vector store unavailable
        logger.exception("RAG indisponible (recherche)")
        return handoff(section, message, session)

    top = hits[0].score if hits else 0.0
    relevant = [h for h in hits if h.score >= RAG_MIN_SCORE]
    log_event(
        logger, "rag.retrieve", session_id=session.session_id,
        section=section, hits=len(hits), kept=len(relevant), top_score=round(top, 3),
    )

    if not relevant:
        # No grounding → don't guess, hand off to the team.
        log_event(logger, "rag.no_context", session_id=session.session_id, section=section)
        return handoff(section, message, session)

    context = "\n\n---\n\n".join(h.text for h in relevant)
    sources = sorted({h.metadata.get("source", "") for h in relevant if h.metadata.get("source")})

    try:
        answer = get_llm_client().complete_text(
            RAG_SYSTEM,
            [{"role": "user", "content": f"Contexte :\n{context}\n\nQuestion : {scrubbed_message}"}],
            max_tokens=700,
        )
    except Exception:  # noqa: BLE001 — LLM unavailable
        logger.exception("RAG indisponible (synthèse)")
        return handoff(section, message, session)

    log_event(logger, "rag.answer", session_id=session.session_id, section=section, sources=len(sources))
    return {"response": answer, "section": section, "sources": sources, "actions": []}
