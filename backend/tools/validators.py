"""
Deterministic validation of the logement slots (no AI here).

Checks that required fields are present, that dates are well-formed, future and
coherent, that the party size is plausible, and that the city maps to a real
thermal station. Returns a structured verdict the orchestration turns into either
a slot-filling question (missing fields) or a friendly error (invalid values).
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from .voyagedo_api import resolve_ville

REQUIRED_FIELDS = ["ville", "start_date", "end_date"]
MAX_PERSONS = 12


def parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return datetime.strptime(str(value), "%Y-%m-%d").date()
    except ValueError:
        return None


def validate_logement(slots: dict, today: date | None = None) -> dict:
    """Return a verdict dict:
    {ok, missing: [...], error: <code|None>, ville_id, ville_canon, start, end, nb_personnes}
    """
    today = today or date.today()

    missing = [f for f in REQUIRED_FIELDS if not slots.get(f)]
    if missing:
        return {"ok": False, "missing": missing, "error": None}

    start = parse_date(slots.get("start_date"))
    end = parse_date(slots.get("end_date"))
    if not start or not end:
        return {"ok": False, "missing": [], "error": "dates_format"}
    if start < today:
        return {"ok": False, "missing": [], "error": "date_passee"}
    if end <= start:
        return {"ok": False, "missing": [], "error": "dates_incoherentes"}

    nb = slots.get("nb_personnes")
    if nb is not None and (not isinstance(nb, int) or nb < 1 or nb > MAX_PERSONS):
        return {"ok": False, "missing": [], "error": "nb_personnes"}

    ville_id, ville_canon = resolve_ville(slots.get("ville"))
    if ville_id is None:
        return {"ok": False, "missing": [], "error": "ville_inconnue"}

    return {
        "ok": True,
        "missing": [],
        "error": None,
        "ville_id": ville_id,
        "ville_canon": ville_canon,
        "start": slots["start_date"],
        "end": slots["end_date"],
        "nb_personnes": nb,
    }
