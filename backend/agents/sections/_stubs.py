"""
Stub sections — for this prototype only `logement` is complete. The others
politely hand the request off to the human team and log the event. They never
guess an answer.
"""

from __future__ import annotations

from ...core.logging import get_logger, log_event
from ...session.store import Session

logger = get_logger("handoff")

_LABELS = {
    "assurance": "votre question d'assurance",
    "proprietaire": "votre demande de propriétaire",
    "stations": "votre question sur les stations thermales et les cures",
    "autre": "votre demande",
}


def handoff(section: str, message: str, session: Session) -> dict:
    label = _LABELS.get(section, "votre demande")
    log_event(logger, "chat.handoff", session_id=session.session_id, section=section)
    response = (
        f"Je transmets {label} à notre équipe, qui pourra vous répondre précisément. "
        "Vous pouvez aussi nous écrire à service.client@voyagedo.fr ou nous appeler. "
        "Puis-je vous aider pour autre chose, par exemple rechercher un logement ?"
    )
    return {
        "response": response,
        "section": section,
        "sources": [],
        "actions": [{"type": "handoff", "section": section}],
        "suggestions": ["Trouver un logement"],
    }
