"""Theme `infos_logement`: specific questions answered from the /clara endpoints."""

from backend.agents.sections import logement
from backend.session.store import Session
from backend.tools import voyagedo_api

_NULLS = {
    "theme": None, "ville": None, "start_date": None, "end_date": None,
    "nb_personnes": None, "equip": None, "advert_id": None, "adults": None,
    "children": None, "question": None, "confirm": None,
}


def _slots(**over):
    return {**_NULLS, **over}


def _no_llm(monkeypatch):
    def boom(*a, **k):
        raise AssertionError("the LLM must not be called on the focused info path")
    monkeypatch.setattr(logement, "get_llm_client", boom)


def test_proximity_question_uses_focused_endpoint(monkeypatch):
    _no_llm(monkeypatch)
    summary = "À 800 m des thermes, accessible à pied."
    monkeypatch.setattr(voyagedo_api, "get_proximity",
                        lambda advert_id: {"summary": summary, "distance_meters": 800})
    monkeypatch.setattr(logement, "_extract_slots", lambda m, s: _slots(
        theme="infos_logement", advert_id=3727, question="c'est loin des thermes ?"))

    session = Session(session_id="i1")
    r = logement.handle_logement("c'est loin des thermes ?", session, "c'est loin des thermes ?")
    assert summary in r["response"]
    assert r["section"] == "logement"
    assert session.state["logement"] == {}


def test_equipment_question_answers_yes_no(monkeypatch):
    _no_llm(monkeypatch)
    monkeypatch.setattr(voyagedo_api, "get_equipments",
                        lambda advert_id: {"flags": {"wifi": True, "ascenseur": False}})
    monkeypatch.setattr(logement, "_extract_slots", lambda m, s: _slots(
        theme="infos_logement", advert_id=3727, question="y a-t-il le wifi ?"))

    session = Session(session_id="i2")
    r = logement.handle_logement("y a-t-il le wifi ?", session, "y a-t-il le wifi ?")
    assert "wifi" in r["response"].lower()
    assert r["response"].lower().startswith("oui")


def test_infos_without_reference_asks_for_it(monkeypatch):
    monkeypatch.setattr(logement, "_extract_slots", lambda m, s: _slots(
        theme="infos_logement", question="y a-t-il un ascenseur ?"))
    session = Session(session_id="i3")
    r = logement.handle_logement("y a-t-il un ascenseur ?", session, "y a-t-il un ascenseur ?")
    assert "référence" in r["response"].lower()
    assert session.state.get("pending_section") == "logement"
