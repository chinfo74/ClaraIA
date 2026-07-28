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
        "pas isolé", "pas trop isolé", "proche d'une ville", "près d'une ville", "dans une grande ville"
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
        if value not in (None, "", "null", []):
            state[key] = value
    state.update(_detect_filters(message))


def handle_stations(message: str, session: Session, scrubbed_message: str) -> dict:
    state = session.state.setdefault(_STATE_KEY, {})

    try:
        extracted = _extract_slots(scrubbed_message, state)
    except Exception as exc:
        return _reply(_DEGRADED, session)

    _merge_slots(state, extracted, message)

    return _handle_search(state, session)


def _resolve_pathologies(state: dict) -> list:
    raw = state.get("pathologie")
    if isinstance(raw, str):
        names = [raw] if raw else []
    elif isinstance(raw, list):
        names = [n for n in raw if n]
    else:
        names = []
    ids = []
    for name in names:
        patho_id, _ = api.resolve_path(name)
        if patho_id:
            ids.append(patho_id)
    return ids


def _format_results(items: list, session: Session) -> str:
    facts = items[:8]
    user = (
        f"{len(items)} station(s) thermale(s) trouvée(s) selon les critères du client :\n"
        f"{json.dumps(facts, ensure_ascii=False)}\n\n"
        "Rédige la réponse pour le client à partir de ces données uniquement (nom de la "
        "station, ville, pathologies traitées si présentes). Invite-le à demander la fiche "
        "d'une station ou à en comparer plusieurs."
    )
    return get_llm_client().complete_text(FORMAT_SYSTEM, [{"role": "user", "content": user}], max_tokens=700)


def _handle_search(state: dict, session: Session) -> dict:
    ville_query = state.get("ville") or ""

    ville_id, _ = api.resolve_center_ville(ville_query)
    patho_ids = _resolve_pathologies(state)

    if not ville_id and not patho_ids and not any(state.get(k) for k in _FILTER_KEYS):
        return _reply(
            "Pour vous proposer les bonnes stations, dites-moi une ville de référence, "
            "une pathologie, ou vos critères (bord de mer, sans voiture, budget...).",
            session,
        )

    data = api.filter_centers(
        ville_ids=ville_id,
        path_ids=patho_ids,
        near_sea=state.get("near_sea"),
        no_car=state.get("no_car"),
        cheap=state.get("cheap"),
        mount=state.get("mount"),
        in_city=state.get("in_city"),
        big_center=state.get("big_center"),
    )
    
    print(ville_id, patho_ids, state.get("near_sea"), state.get("no_car"), state.get("cheap"), state.get("mount"), state.get("in_city"), state.get("big_center"))
    print(data, len(data))

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
