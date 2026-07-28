from __future__ import annotations

import json

from ...core.llm_client import get_llm_client
from ...core.logging import get_logger, log_event
from ...session.store import Session
from ...tools import voyagedo_api as api
from ..schemas import FORMAT_SYSTEM, STATIONS_EXTRACT_SYSTEM, STATIONS_SCHEMA

logger = get_logger("stations")

_STATE_KEY = "stations"
_SLOT_KEYS = ("theme", "ville", "pathologie", "station_nom", "question", "comparaison")
_FILTER_KEYS = ("near_sea", "no_car", "cheap", "mount", "in_city", "big_center")

_FILTER_KEYWORDS = {
    "near_sea": ("bord de mer", "près de la mer", "proche de la mer", "littoral", "océan", "mer"),
    "no_car": ("sans voiture", "pas de voiture", "sans véhicule", "accessible en train", "à pied de la gare"),
    "cheap": ("pas cher", "pas chère", "économique", "petit budget", "prix bas", "abordable", "moins cher"),
    "mount": ("montagne", "en altitude"),
    "in_city": (
        "près d'une grande ville", "proche d'une grande ville", "à côté d'une grande ville",
        "pas isolé", "pas trop isolé", "proche d'une ville", "près d'une ville",
    ),
    "big_center": ("grand centre", "grande station", "gros centre", "beaucoup de curistes"),
}

_DEGRADED = (
    "Je vérifie auprès de notre système, mais il ne répond pas à l'instant. Notre équipe "
    "va s'en occuper et vous recontacter rapidement. Vous pouvez aussi écrire à "
    "service.client@voyagedo.fr."
)


def _detect_filters(message: str) -> dict:
    q = message.lower()
    return {key: True for key, keywords in _FILTER_KEYWORDS.items() if any(kw in q for kw in keywords)}


def _reply(text: str, session: Session, **extra) -> dict:
    out = {"response": text, "section": "stations", "sources": [], "actions": []}
    out.update(extra)
    return out


def _extract_slots(message: str, state: dict) -> dict:
    client = get_llm_client()
    user = (
        f"Message du client : {message}\n\n"
        f"Informations déjà connues : {json.dumps(state, ensure_ascii=False)}"
    )
    return client.complete_json(
        system=STATIONS_EXTRACT_SYSTEM, user=user,
        schema=STATIONS_SCHEMA, schema_name="stations_slots",
    )


def _merge_slots(state: dict, extracted: dict, message: str) -> None:
    for key in _SLOT_KEYS:
        value = extracted.get(key)
        if value not in (None, "", "null"):
            state[key] = value
    state.update(_detect_filters(message))


def handle_stations(message: str, session: Session, scrubbed_message: str) -> dict:
    state = session.state.setdefault(_STATE_KEY, {})

    try:
        extracted = _extract_slots(scrubbed_message, state)
    except Exception as exc:
        logger.warning("Extraction des critères stations indisponible : %s", exc)
        return _reply(_DEGRADED, session)

    _merge_slots(state, extracted, message)

    return _handle_search(state, session)


def _format_center(center: dict) -> str:
    return "details center"


def _format_results(items: list, session: Session) -> str:
    return "TEST TEST"


def _handle_search(state: dict, session: Session) -> dict:
    ville_id, _ = api.resolve_center_ville(state.get("ville") or "")
    patho_id, _ = api.resolve_path(state.get("pathologie") or "")

    data = api.filter_centers(
        ville_ids=ville_id,
        path_ids=patho_id,
        near_sea=state.get("near_sea"),
        no_car=state.get("no_car"),
        cheap=state.get("cheap"),
        mount=state.get("mount"),
        in_city=state.get("in_city"),
        big_center=state.get("big_center"),
    )

    failed = isinstance(data, dict) and "erreur" in data
    items = data if isinstance(data, list) else []

    if failed:
        return _reply(_DEGRADED, session)
    if not items:
        return _reply(
            "Je n'ai pas trouvé de station thermale correspondant à ces critères. "
            "Souhaitez-vous élargir la recherche (autre ville, ou sans certains critères) ?",
            session,
        )
    return _reply(
        _format_results(items, session),
        session,
        actions=[{"type": "stations", "count": len(items)}],
        suggestions=["Voir la fiche d'une station", "Comparer des stations"],
    )
