from __future__ import annotations

from ..core.llm_client import get_llm_client
from ..core.logging import get_logger, log_event
from ..rag.pii import scrub_pii
from ..session.store import Session
from .schemas import (
    CLASSIFY_SCHEMA,
    CLASSIFY_SYSTEM,
    CONFIDENCE_THRESHOLD,
    RAG_SECTIONS,
    SECTIONS,
)
from .sections._stubs import handoff
from .sections.logement import handle_logement
from .sections.rag import handle_rag

logger = get_logger("manager")

_GREETINGS = ("bonjour", "bonsoir", "salut", "coucou", "hello", "bonne journée")
_THANKS = ("merci", "je vous remercie")
_BYE = ("au revoir", "à bientôt", "bonne soirée")

STARTER_SUGGESTIONS = ["Trouver un logement", "Une question sur l'assurance", "Le déroulement du séjour"]


def _smalltalk(message: str) -> tuple[str, list[str]] | None:
    t = message.lower().strip()
    if any(g in t for g in _GREETINGS) and len(t) < 40:
        return (
            "Bonjour et bienvenue chez Voyage d'Ô ! Je suis Clara. "
            "Je peux vous aider à trouver un logement pour votre cure. Que recherchez-vous ?",
            STARTER_SUGGESTIONS,
        )
    if any(g in t for g in _THANKS):
        return ("Avec plaisir ! Puis-je vous aider pour autre chose ?", STARTER_SUGGESTIONS)
    if any(g in t for g in _BYE):
        return ("Je vous souhaite une très belle journée. À bientôt !", [])
    return None


def classify(message: str) -> dict:
    client = get_llm_client()
    data = client.complete_json(
        system=CLASSIFY_SYSTEM, user=message,
        schema=CLASSIFY_SCHEMA, schema_name="routing",
    )
    section = data.get("section", "autre")
    if section not in SECTIONS:
        section = "autre"
    try:
        confidence = float(data.get("confidence", 0) or 0)
    except (TypeError, ValueError):
        confidence = 0.0
    return {"section": section, "confidence": confidence}


def handle(message: str, session: Session) -> dict:
    scrubbed = scrub_pii(message)
    if scrubbed.total:
        log_event(logger, "chat.pii_pseudonymized", session_id=session.session_id, count=scrubbed.total)
    scrubbed_message = scrubbed.text

    chitchat = _smalltalk(message)
    if chitchat:
        reply, suggestions = chitchat
        log_event(logger, "chat.smalltalk", session_id=session.session_id)
        return {"response": reply, "section": "conversation", "sources": [],
                "actions": [], "suggestions": suggestions}

    if session.state.get("pending_section") == "logement":
        log_event(logger, "chat.classify", session_id=session.session_id,
                  section="logement", confidence=1.0, reason="slot_filling")
        return handle_logement(message, session, scrubbed_message)

    result = classify(scrubbed_message)
    section, confidence = result["section"], result["confidence"]
    log_event(logger, "chat.classify", session_id=session.session_id,
              section=section, confidence=round(confidence, 2))

    if confidence < CONFIDENCE_THRESHOLD:
        return handoff("autre", message, session)
    if section == "logement":
        return handle_logement(message, session, scrubbed_message)
    if section in RAG_SECTIONS:
        return handle_rag(message, session, scrubbed_message, section)
    return handoff(section, message, session)
