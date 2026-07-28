from __future__ import annotations

import httpx

from ..core.logging import get_logger

logger = get_logger("voyagedo")

MOB1_URL = "https://www.location-cure.net/mob1"
CLARA_URL = "https://www.location-cure.net/clara"
CLARALOG_URL = "http://localhost:8888/claralog"
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

_PATHOLOGIE_CACHE: list[dict] | None = None

def _pathologie() -> list[dict]:
    global _PATHOLOGIE_CACHE
    if _PATHOLOGIE_CACHE is None:
        data = _get("pathologie", base=CLARALOG_URL)
        _PATHOLOGIE_CACHE = data if isinstance(data, list) else []
    return _PATHOLOGIE_CACHE


def pathologie_names() -> list[str]:
    return [p.get("name", "") for p in _pathologie() if p.get("name")]


def resolve_path(name: str) -> tuple[int | None, str | None]:
    if not name:
        return (None, None)
    query = name.strip().lower()
    pathologies = _pathologie()
    for p in pathologies:
        if str(p.get("name", "")).strip().lower() == query:
            return (p.get("sointher_id"), p.get("name"))
    for p in pathologies:
        patho = str(p.get("name", "")).strip().lower()
        if patho.startswith(query) or query in patho:
            return (p.get("sointher_id"), p.get("name"))
    return (None, None)


_CENTERS_CACHE: list[dict] | None = None


def _centers() -> list[dict]:
    global _CENTERS_CACHE
    if _CENTERS_CACHE is None:
        data = filter_centers()
        _CENTERS_CACHE = data if isinstance(data, list) else []
    return _CENTERS_CACHE


def resolve_center_ville(name: str) -> tuple[int | None, str | None]:
    if not name:
        return (None, None)
    query = name.strip().lower()
    centers = _centers()
    for c in centers:
        if str(c.get("city_name", "")).strip().lower() == query:
            return (c.get("city_id"), c.get("city_name"))
    for c in centers:
        city = str(c.get("city_name", "")).strip().lower()
        if city.startswith(query) or query in city:
            return (c.get("city_id"), c.get("city_name"))
    return (None, None)

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



def get_centers():
    return _get("centers", base=CLARALOG_URL)


def get_center_card(center_id: int | str):
    return _get(f"centercard/id/{center_id}", base=CLARALOG_URL)


def filter_centers(
    ville_ids=None,
    path_ids=None,
    latitude=None,
    longitude=None,
    radius=None,
    near_sea=None,
    no_car=None,
    cheap=None,
    mount=None,
    in_city=None,
    big_center=None,
):
    parts = ["filtercenter"]

    def add(key: str, value) -> None:
        if value in (None, "", [], ()):
            return
        if isinstance(value, (list, tuple)):
            value = "-".join(str(v) for v in value)
        parts.extend([key, str(value)])

    add("ville", ville_ids)
    add("path", path_ids)
    add("latitude", latitude)
    add("longitude", longitude)
    add("radius", radius)
    add("nearsea", near_sea)
    add("nocar", no_car)
    add("cheap", cheap)
    add("mount", mount)
    add("incity", in_city)
    add("bigcenter", big_center)
    return _get("/".join(parts), base=CLARALOG_URL)