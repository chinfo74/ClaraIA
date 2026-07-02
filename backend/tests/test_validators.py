from datetime import date

import pytest

from backend.tools import validators
from backend.tools.validators import parse_date, validate_logement

TODAY = date(2026, 6, 24)


@pytest.fixture
def known_city(monkeypatch):
    monkeypatch.setattr(validators, "resolve_ville", lambda n: (104, "Saint-Paul-lès-Dax"))


def test_parse_date():
    assert parse_date("2026-09-01") == date(2026, 9, 1)
    assert parse_date("01/09/2026") is None
    assert parse_date(None) is None


def test_all_fields_missing():
    v = validate_logement({})
    assert v["ok"] is False
    assert set(v["missing"]) == {"ville", "start_date", "end_date"}


def test_only_dates_missing():
    v = validate_logement({"ville": "Dax"})
    assert v["ok"] is False
    assert "ville" not in v["missing"]
    assert {"start_date", "end_date"} == set(v["missing"])


def test_past_date(known_city):
    v = validate_logement({"ville": "Dax", "start_date": "2020-01-01", "end_date": "2020-01-10"}, today=TODAY)
    assert v["error"] == "date_passee"


def test_incoherent_dates(known_city):
    v = validate_logement({"ville": "Dax", "start_date": "2026-09-21", "end_date": "2026-09-01"}, today=TODAY)
    assert v["error"] == "dates_incoherentes"


def test_bad_date_format(known_city):
    v = validate_logement({"ville": "Dax", "start_date": "01/09/2026", "end_date": "2026-09-21"}, today=TODAY)
    assert v["error"] == "dates_format"


def test_implausible_party_size(known_city):
    v = validate_logement(
        {"ville": "Dax", "start_date": "2026-09-01", "end_date": "2026-09-21", "nb_personnes": 99}, today=TODAY
    )
    assert v["error"] == "nb_personnes"


def test_unknown_city(monkeypatch):
    monkeypatch.setattr(validators, "resolve_ville", lambda n: (None, None))
    v = validate_logement({"ville": "Atlantis", "start_date": "2026-09-01", "end_date": "2026-09-21"}, today=TODAY)
    assert v["error"] == "ville_inconnue"


def test_valid(known_city):
    v = validate_logement(
        {"ville": "Dax", "start_date": "2026-09-01", "end_date": "2026-09-21", "nb_personnes": 2}, today=TODAY
    )
    assert v["ok"] is True
    assert v["ville_id"] == 104
    assert v["ville_canon"] == "Saint-Paul-lès-Dax"
    assert v["nb_personnes"] == 2
    assert v["start"] == "2026-09-01" and v["end"] == "2026-09-21"
