from backend.agents.sections import logement
from backend.session.store import Session
from backend.tools import voyagedo_api

_NULLS = {
    "theme": None, "ville": None, "start_date": None, "end_date": None,
    "nb_personnes": None, "equip": None, "advert_id": None, "adults": None,
    "children": None, "confirm": None,
}


def _slots(**over):
    return {**_NULLS, **over}


def test_reservation_requires_explicit_confirmation(monkeypatch):
    calls = []
    monkeypatch.setattr(voyagedo_api, "make_reservation",
                        lambda *a, **k: (calls.append(a), {"ok": True})[1])
    session = Session(session_id="t1")

    monkeypatch.setattr(logement, "_extract_slots", lambda m, s: _slots(
        theme="reservation", advert_id=3727, start_date="2026-09-01",
        end_date="2026-09-21", adults=2, children=0))
    r1 = logement.handle_logement("je veux réserver le 3727", session, "je veux réserver le 3727")
    assert "confirm" in r1["response"].lower()
    assert calls == []
    assert session.state["logement"].get("awaiting_confirmation") is True

    monkeypatch.setattr(logement, "_extract_slots", lambda m, s: _slots())
    r2 = logement.handle_logement("oui", session, "oui")
    assert len(calls) == 1
    assert calls[0] == (3727, "2026-09-01", "2026-09-21", 2, 0)
    assert "confirmée" in r2["response"].lower()


def test_reservation_cancelled_on_no(monkeypatch):
    calls = []
    monkeypatch.setattr(voyagedo_api, "make_reservation",
                        lambda *a, **k: (calls.append(a), {"ok": True})[1])
    session = Session(session_id="t2")

    monkeypatch.setattr(logement, "_extract_slots", lambda m, s: _slots(
        theme="reservation", advert_id=3727, start_date="2026-09-01",
        end_date="2026-09-21", adults=2, children=0))
    logement.handle_logement("réserver le 3727", session, "réserver le 3727")

    monkeypatch.setattr(logement, "_extract_slots", lambda m, s: _slots())
    r = logement.handle_logement("non", session, "non")
    assert calls == []
    assert "rien réservé" in r["response"].lower()
