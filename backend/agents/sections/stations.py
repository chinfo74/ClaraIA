from __future__ import annotations

import re

from ...core.logging import get_logger, log_event
from ...session.store import Session
from ...tools import voyagedo_api as api

logger = get_logger("stations")

_STATE_KEY = "stations"

def _reply(text: str, session: Session, **extra) -> dict:
    out = {"response": text, "section": "stations", "sources": [], "actions": []}
    out.update(extra)
    return out


def handle_stations(message: str, session: Session, scrubbed_message: str) -> dict:
    log_event(logger, "stations.request", session_id=session.session_id)

    response = (
        "Test Station/centre thermales"
    )

    return _reply(response, session, suggestions=["Voir les stations thermales", "Demander un centre thermal"])