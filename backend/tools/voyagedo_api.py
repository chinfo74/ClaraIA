"""Voyage d'Ô API client. Stations via /mob1, logement via /clara.

Every call returns the API payload or {"erreur": <code>} (graceful degradation).
"""

from __future__ import annotations

import httpx

from ..core.logging import get_logger

logger = get_logger("voyagedo")

MOB1_URL = "https://www.location-cure.net/mob1"
CLARA_URL = "https://www.location-cure.net/clara"
TIMEOUT = 12.0


def _get(path: str, base: str = MOB1_URL):
    url = f"{base}/{path.lstrip('/')}"
    try:
        with httpx.Client(timeout=TIMEOUT) as client:
            resp = client.get(url)
            resp.raise_for_status()
            return resp.json()
    except httpx.TimeoutException:
        return {"erreur": "timeout"}
    except httpx.HTTPStatusError as exc:
        return {"erreur": f"http_{exc.response.status_code}"}
    except Exception as exc:  # noqa: BLE001
        logger.warning("Appel API échoué (%s) : %s", type(exc).__name__, path)
        return {"erreur": "reseau"}


# ── Stations (ville -> StationID) ──────────────────────────────────────────────

_STATIONS_CACHE: list[dict] | None = None


def _stations() -> list[dict]:
    global _STATIONS_CACHE
    if _STATIONS_CACHE is None:
        data = _get("start")
        if isinstance(data, dict) and data.get("Station"):
            _STATIONS_CACHE = data["Station"]
        else:
            return []
    return _STATIONS_CACHE


def station_names() -> list[str]:
    return [s.get("StationCity", "") for s in _stations() if s.get("StationCity")]


def resolve_ville(name: str) -> tuple[int | None, str | None]:
    if not name:
        return (None, None)
    query = name.strip().lower()
    stations = _stations()
    for s in stations:
        if str(s.get("StationCity", "")).strip().lower() == query:
            return (s.get("StationID"), s.get("StationCity"))
    for s in stations:
        city = str(s.get("StationCity", "")).strip().lower()
        if city.startswith(query) or query in city:
            return (s.get("StationID"), s.get("StationCity"))
    return (None, None)


# ── Endpoints logement (/clara) ────────────────────────────────────────────────


def search_logements(ville_id: int | str, start: str, end: str, equip: str = "0"):
    return _get(
        f"recherche/ville/{ville_id}/equip/{equip}/start/{start}/end/{end}",
        base=CLARA_URL,
    )


def get_logement_card(logement_id: int | str):
    return _get(f"fiche/id/{logement_id}", base=CLARA_URL)


def check_availability(advert_id: int | str, start: str, end: str, persons: int):
    return _get(
        f"disponibilite/id/{advert_id}/start/{start}/end/{end}/persons/{persons}",
        base=CLARA_URL,
    )


def make_reservation(advert_id: int | str, start: str, end: str, adults: int, children: int):
    return _get(
        f"reserver/advert_id/{advert_id}/start/{start}/end/{end}"
        f"/adulte/{adults}/enfant/{children}",
        base=CLARA_URL,
    )


def get_accessibility(advert_id: int | str):
    return _get(f"accessibilite/id/{advert_id}", base=CLARA_URL)


def get_proximity(advert_id: int | str):
    return _get(f"proximite/id/{advert_id}", base=CLARA_URL)


def get_equipments(advert_id: int | str):
    return _get(f"equipements/id/{advert_id}", base=CLARA_URL)


def get_bedding(advert_id: int | str):
    return _get(f"couchages/id/{advert_id}", base=CLARA_URL)


def get_pets(advert_id: int | str):
    return _get(f"animaux/id/{advert_id}", base=CLARA_URL)


def get_pricing(advert_id: int | str):
    return _get(f"tarifs/id/{advert_id}", base=CLARA_URL)


def get_reviews(advert_id: int | str):
    return _get(f"avis/id/{advert_id}", base=CLARA_URL)
