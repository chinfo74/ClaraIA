from __future__ import annotations

import json

from ...core.llm_client import get_llm_client
from ...core.logging import get_logger, log_event
from ...session.store import Session
from ...tools import voyagedo_api as api
from ...tools.validators import parse_date, validate_logement
from ..schemas import (
    FORMAT_SYSTEM,
    LOGEMENT_EXTRACT_SYSTEM,
    LOGEMENT_INFO_SYSTEM,
    LOGEMENT_SCHEMA,
)

logger = get_logger("logement")

_SLOT_KEYS = (
    "theme", "ville", "start_date", "end_date", "nb_personnes",
    "equip", "advert_id", "adults", "children", "question",
)
_THEMES = (
    "recherche_logement", "details_logement", "infos_logement",
    "disponibilite", "reservation",
)

_FIELD_QUESTIONS = {
    "ville": "dans quelle ville thermale souhaitez-vous séjourner",
    "start_date": "à quelle date souhaitez-vous arriver",
    "end_date": "jusqu'à quelle date",
}
_ERROR_MESSAGES = {
    "dates_format": "Je n'ai pas bien compris les dates. Pouvez-vous me les redonner, par exemple « du 1er au 21 septembre » ?",
    "date_passee": "La date d'arrivée est déjà passée. Pourriez-vous m'indiquer des dates à venir ?",
    "dates_incoherentes": "La date de départ doit être après la date d'arrivée. Pouvez-vous vérifier vos dates ?",
    "nb_personnes": "Le nombre de personnes me semble inhabituel. Pour combien de personnes recherchez-vous un logement ?",
}
_DEGRADED = (
    "Je vérifie auprès de notre système, mais il ne répond pas à l'instant. Notre équipe "
    "va s'en occuper et vous recontacter rapidement. Vous pouvez aussi écrire à "
    "service.client@voyagedo.fr."
)
_AFFIRM = ("oui", "confirme", "d'accord", "ok", "c'est bon", "réserv", "parfait", "valide")
_NEGATIVE = ("non", "annul", "laisse tomber", "pas maintenant", "plus tard", "renonce")


def _is_affirmative(msg: str) -> bool:
    t = msg.lower()
    return any(w in t for w in _AFFIRM)


def _is_negative(msg: str) -> bool:
    t = msg.lower()
    return any(w in t for w in _NEGATIVE)


def _join(items: list[str]) -> str:
    if len(items) > 1:
        return ", ".join(items[:-1]) + " et " + items[-1]
    return items[0] if items else ""


def _reply(text: str, session: Session, **extra) -> dict:
    out = {"response": text, "section": "logement", "sources": [], "actions": []}
    out.update(extra)
    return out


def _reset(session: Session) -> None:
    session.state["logement"] = {}
    session.state.pop("pending_section", None)


def _extract_slots(message: str, state: dict) -> dict:
    client = get_llm_client()
    user = (
        f"Message du client : {message}\n\n"
        f"Informations déjà connues : {json.dumps(state, ensure_ascii=False)}"
    )
    return client.complete_json(
        system=LOGEMENT_EXTRACT_SYSTEM, user=user,
        schema=LOGEMENT_SCHEMA, schema_name="logement_slots",
    )


def handle_logement(message: str, session: Session, scrubbed_message: str) -> dict:
    state = session.state.setdefault("logement", {})
    extracted = _extract_slots(scrubbed_message, state)
    for key in _SLOT_KEYS:
        value = extracted.get(key)
        if value not in (None, "", "null"):
            state[key] = value
    theme = state.get("theme") if state.get("theme") in _THEMES else "recherche_logement"
    confirm = bool(extracted.get("confirm")) or _is_affirmative(message)
    log_event(
        logger, "logement.slots", session_id=session.session_id, theme=theme,
        filled=[k for k in _SLOT_KEYS if state.get(k)],
    )

    if theme == "details_logement":
        return _handle_details(state, session)
    if theme == "infos_logement":
        return _handle_infos(state, session)
    if theme == "disponibilite":
        return _handle_availability(state, session)
    if theme == "reservation":
        return _handle_reservation(state, session, message, confirm)
    return _handle_search(state, session)


def _format_results(items: list, verdict: dict) -> str:
    lines = []
    for it in items[:8]:
        lines.append(
            f"- {it.get('title', 'Logement')} (réf. {it.get('advert_id', '?')}), "
            f"tarif curiste {it.get('tarif_curiste', '?')} €, à {it.get('city', '')}"
        )
    summary = "\n".join(lines)
    user = (
        f"Ville : {verdict['ville_canon']}, séjour du {verdict['start']} au {verdict['end']}. "
        f"{len(items)} logement(s) disponible(s) :\n{summary}\n\n"
        "Rédige la réponse pour le client (titre, référence, tarif curiste de chaque logement). "
        "Invite-le à demander les détails, la disponibilité ou à réserver une référence."
    )
    return get_llm_client().complete_text(FORMAT_SYSTEM, [{"role": "user", "content": user}], max_tokens=700)


def _handle_search(state: dict, session: Session) -> dict:
    verdict = validate_logement(state)
    if verdict.get("missing"):
        session.state["pending_section"] = "logement"
        questions = [_FIELD_QUESTIONS[f] for f in verdict["missing"] if f in _FIELD_QUESTIONS]
        log_event(logger, "logement.slot_filling", session_id=session.session_id, missing=verdict["missing"])
        return _reply(
            f"Avec plaisir, je vais vous aider à trouver un logement. Pour cela, pouvez-vous me dire {_join(questions)} ?",
            session,
        )
    if not verdict["ok"]:
        session.state["pending_section"] = "logement"
        log_event(logger, "logement.invalid", session_id=session.session_id, error=verdict["error"])
        msg = _ERROR_MESSAGES.get(verdict["error"])
        if verdict["error"] == "ville_inconnue":
            msg = (
                f"Je ne trouve pas « {state.get('ville')} » parmi nos stations thermales. "
                "Pouvez-vous vérifier le nom de la ville ?"
            )
        return _reply(msg or "Pouvez-vous préciser votre demande ?", session)

    data = api.search_logements(verdict["ville_id"], verdict["start"], verdict["end"], state.get("equip") or "0")
    failed = isinstance(data, dict) and "erreur" in data
    items = data if isinstance(data, list) else []
    log_event(
        logger, "logement.api", session_id=session.session_id, endpoint="search",
        status="erreur" if failed else "ok", count=len(items), ville=verdict["ville_canon"],
    )
    session.state.pop("pending_section", None)
    if failed:
        return _reply(_DEGRADED, session)
    if not items:
        return _reply(
            f"Je n'ai pas trouvé de logement disponible à {verdict['ville_canon']} pour ces dates. "
            "Souhaitez-vous essayer d'autres dates ou une autre ville ?",
            session,
        )
    return _reply(
        _format_results(items, verdict), session,
        actions=[{"type": "logements", "count": len(items)}],
        suggestions=["Vérifier une disponibilité", "Voir les détails d'un logement"],
    )


def _format_card(card: dict) -> str:
    lines = [card.get("title", "Logement")]
    loc = ", ".join(str(x) for x in (card.get("city"), card.get("zipcode")) if x)
    if loc:
        lines.append(f"Lieu : {loc}")
    if card.get("type"):
        lines.append(f"Type : {card['type']}")
    if card.get("tarif_curiste"):
        lines.append(f"Tarif curiste : {card['tarif_curiste']} €")
    desc = (card.get("description") or "").strip()
    if desc:
        lines += ["", desc[:350] + ("…" if len(desc) > 350 else "")]
    equip = card.get("equip")
    if isinstance(equip, list) and equip and equip[0].get("equipment_names"):
        lines += ["", "Équipements : " + equip[0]["equipment_names"][:200]]
    lines += ["", f"Souhaitez-vous vérifier les disponibilités ou réserver la référence {card.get('advert_id')} ?"]
    return "\n".join(lines)


def _handle_details(state: dict, session: Session) -> dict:
    advert_id = state.get("advert_id")
    if not advert_id:
        session.state["pending_section"] = "logement"
        return _reply("Bien sûr. Quelle est la référence du logement (par exemple 3727) ?", session)
    card = api.get_logement_card(advert_id)
    ok = isinstance(card, dict) and "erreur" not in card and card.get("title")
    log_event(logger, "logement.api", session_id=session.session_id, endpoint="fiche",
              status="ok" if ok else "erreur", advert_id=advert_id)
    _reset(session)
    if not ok:
        return _reply(
            f"Je n'ai pas trouvé de logement avec la référence {advert_id}. Pouvez-vous vérifier ce numéro ?",
            session,
        )
    return _reply(_format_card(card), session, actions=[{"type": "logement_card", "advert_id": advert_id}])


_INFO_INTENTS = {
    "accessibilite": (
        "ascenseur", "étage", "etage", "escalier", "marche", "plain-pied", "plain pied",
        "rez-de-chaussée", "rez de chaussee", "accessib", "fauteuil", "mobilité", "mobilite",
    ),
    "proximite": (
        "therme", "thermal", "thermes", "distance", "loin", "près", "pres", "proche",
        "navette", "à pied", "a pied",
    ),
    "animaux": ("chien", "chat", "animal", "animaux", "compagnie"),
    "equipements": (
        "wifi", "internet", "lave-linge", "lave linge", "machine à laver", "laver",
        "lave-vaisselle", "vaisselle", "clim", "parking", "garage", "douche", "baignoire",
        "bain", "terrasse", "balcon", "équipement", "equipement",
    ),
}
_INFO_SUGGESTIONS = ["Vérifier une disponibilité", "Voir la fiche complète"]

_EQUIP_LABELS = {
    "wifi": "le wifi", "lave_linge": "un lave-linge", "lave_vaisselle": "un lave-vaisselle",
    "douche": "une douche", "baignoire": "une baignoire", "climatisation": "la climatisation",
    "ascenseur": "un ascenseur", "terrasse": "une terrasse", "garage": "un garage",
    "parking_prive": "un parking privé", "parking_couvert": "un parking couvert",
    "parking_public": "un parking public", "mobilier_jardin": "du mobilier de jardin",
}
_EQUIP_KEYWORDS = {
    "wifi": ("wifi", "internet"),
    "lave_linge": ("lave-linge", "lave linge", "machine à laver", "laver"),
    "lave_vaisselle": ("lave-vaisselle", "vaisselle"),
    "douche": ("douche",),
    "baignoire": ("baignoire", "bain"),
    "climatisation": ("clim",),
    "ascenseur": ("ascenseur",),
    "terrasse": ("terrasse", "balcon"),
    "garage": ("garage",),
    "parking_prive": ("parking",),
}


def _ok(data) -> bool:
    return isinstance(data, dict) and "erreur" not in data


def _format_equipments(data: dict, q: str) -> str:
    flags = data.get("flags") or {}
    targeted = [k for k, kws in _EQUIP_KEYWORDS.items() if any(kw in q for kw in kws)]
    if targeted:
        present = [_EQUIP_LABELS[k] for k in targeted if flags.get(k)]
        absent = [_EQUIP_LABELS[k] for k in targeted if not flags.get(k)]
        parts = []
        if present:
            parts.append("Oui, ce logement a " + _join(present) + ".")
        if absent:
            verb = "ne sont pas indiqués" if len(absent) > 1 else "n'est pas indiqué"
            parts.append(
                _join(absent).capitalize() + " " + verb + " ; "
                "n'hésitez pas à le confirmer avec notre équipe."
            )
        return " ".join(parts)
    present = [label for key, label in _EQUIP_LABELS.items() if flags.get(key)]
    if present:
        return "Ce logement propose notamment : " + _join(present) + "."
    return "Je n'ai pas le détail des équipements pour ce logement pour le moment."


def _focused_info(advert_id, q: str) -> str | None:
    if any(k in q for k in _INFO_INTENTS["accessibilite"]):
        data = api.get_accessibility(advert_id)
        if _ok(data) and data.get("summary"):
            return data["summary"]
    if any(k in q for k in _INFO_INTENTS["proximite"]):
        data = api.get_proximity(advert_id)
        if _ok(data) and data.get("summary"):
            return data["summary"]
    if any(k in q for k in _INFO_INTENTS["animaux"]):
        data = api.get_pets(advert_id)
        if _ok(data) and data.get("summary"):
            return data["summary"]
    if any(k in q for k in _INFO_INTENTS["equipements"]):
        data = api.get_equipments(advert_id)
        if _ok(data) and isinstance(data.get("flags"), dict):
            return _format_equipments(data, q)
    return None


def _card_facts(card: dict) -> dict:
    facts = {
        "titre": card.get("title"),
        "type": card.get("type"),
        "ville": card.get("city"),
        "code_postal": card.get("zipcode"),
        "tarif_curiste_min": card.get("tarif_curiste"),
        "tarif_curiste_max": card.get("tarif_curistes_max"),
        "description": (card.get("description") or "")[:800],
        "etage": card.get("infoFloor"),
        "distances": card.get("activity"),
        "couchages": card.get("bedding"),
        "options": card.get("options"),
        "note_globale": card.get("moyenne_total"),
    }
    equip = card.get("equip")
    if isinstance(equip, list) and equip:
        facts["equipements"] = equip[0].get("equipment_names")
        facts["divers"] = equip[0].get("various_name")
    return {k: v for k, v in facts.items() if v not in (None, "", [], {})}


def _answer_from_card(card: dict, question: str) -> str:
    user = (
        f"Question du client : {question or 'Présente brièvement ce logement.'}\n\n"
        "Données du logement (réponds uniquement à partir d'elles) :\n"
        f"{json.dumps(_card_facts(card), ensure_ascii=False)}"
    )
    return get_llm_client().complete_text(
        LOGEMENT_INFO_SYSTEM, [{"role": "user", "content": user}], max_tokens=500
    )


def _handle_infos(state: dict, session: Session) -> dict:
    advert_id = state.get("advert_id")
    question = (state.get("question") or "").strip()
    if not advert_id:
        session.state["pending_section"] = "logement"
        return _reply(
            "Bien sûr. De quel logement parlez-vous ? Indiquez-moi sa référence (par exemple 3727).",
            session,
        )
    q = question.lower()

    focused = _focused_info(advert_id, q)
    if focused is not None:
        log_event(logger, "logement.api", session_id=session.session_id, endpoint="infos",
                  status="ok", advert_id=advert_id, mode="focused")
        _reset(session)
        return _reply(focused, session, suggestions=_INFO_SUGGESTIONS,
                      actions=[{"type": "logement_info", "advert_id": advert_id}])

    card = api.get_logement_card(advert_id)
    ok = _ok(card) and card.get("title")
    log_event(logger, "logement.api", session_id=session.session_id, endpoint="fiche",
              status="ok" if ok else "erreur", advert_id=advert_id, mode="grounded")
    _reset(session)
    if not ok:
        if isinstance(card, dict) and "erreur" in card:
            return _reply(_DEGRADED, session)
        return _reply(
            f"Je n'ai pas trouvé de logement avec la référence {advert_id}. Pouvez-vous vérifier ce numéro ?",
            session,
        )
    return _reply(_answer_from_card(card, question), session, suggestions=_INFO_SUGGESTIONS,
                  actions=[{"type": "logement_info", "advert_id": advert_id}])


def _format_availability(av: dict, advert_id) -> str:
    msg = f"Bonne nouvelle : le logement réf. {advert_id} est disponible"
    if av.get("start") and av.get("end"):
        msg += f" du {av['start']} au {av['end']}"
    if av.get("price"):
        msg += f". Tarif total : {av['price']} €"
    details = av.get("details") if isinstance(av.get("details"), dict) else {}
    if details.get("nb_days_to_book"):
        msg += f" pour {details['nb_days_to_book']} nuits"
    return msg + ".\n\nSouhaitez-vous le réserver ?"


def _handle_availability(state: dict, session: Session) -> dict:
    advert_id, start, end = state.get("advert_id"), state.get("start_date"), state.get("end_date")
    persons = state.get("nb_personnes") or 1
    missing = []
    if not advert_id:
        missing.append("la référence du logement")
    if not start:
        missing.append("la date d'arrivée")
    if not end:
        missing.append("la date de départ")
    if missing:
        session.state["pending_section"] = "logement"
        return _reply(f"Pour vérifier la disponibilité, j'ai besoin de {_join(missing)}.", session)

    ds, de = parse_date(start), parse_date(end)
    if not ds or not de or de <= ds:
        session.state["pending_section"] = "logement"
        return _reply(_ERROR_MESSAGES["dates_incoherentes"], session)

    av = api.check_availability(advert_id, start, end, persons)
    api_error = isinstance(av, dict) and "erreur" in av
    available = isinstance(av, dict) and av.get("available") is True
    log_event(logger, "logement.api", session_id=session.session_id, endpoint="disponibilite",
              status="erreur" if api_error else "ok", available=available, advert_id=advert_id)

    if api_error:
        _reset(session)
        return _reply(_DEGRADED, session)
    if available:
        _reset(session)
        return _reply(_format_availability(av, advert_id), session,
                      actions=[{"type": "availability", "advert_id": advert_id, "available": True}],
                      suggestions=["Réserver ce logement", "Voir un autre logement"])

    alt_txt = ""
    alts = av.get("alternatives") if isinstance(av, dict) else None
    if isinstance(alts, list) and alts:
        lines = [
            f"- {a.get('title')} (réf. {a.get('advert_id')}), {a.get('price')} €"
            for a in alts[:5]
        ]
        alt_txt = "\n\nVoici d'autres logements disponibles pour ces dates :\n" + "\n".join(lines)
    _reset(session)
    extra = {"suggestions": ["Voir un autre logement", "Essayer d'autres dates"]} if alt_txt else {}
    return _reply(
        f"Le logement réf. {advert_id} n'est pas disponible du {start} au {end}.{alt_txt}",
        session,
        **extra,
    )


def _handle_reservation(state: dict, session: Session, message: str, confirm: bool) -> dict:
    advert_id, start, end = state.get("advert_id"), state.get("start_date"), state.get("end_date")
    adults = state.get("adults") or state.get("nb_personnes") or 1
    children = state.get("children") or 0

    missing = []
    if not advert_id:
        missing.append("la référence du logement")
    if not start:
        missing.append("la date d'arrivée")
    if not end:
        missing.append("la date de départ")
    if missing:
        session.state["pending_section"] = "logement"
        return _reply(f"Pour préparer la réservation, j'ai besoin de {_join(missing)}.", session)

    if state.get("awaiting_confirmation"):
        if _is_negative(message) and not confirm:
            _reset(session)
            return _reply("Pas de souci, je n'ai rien réservé. Puis-je vous aider autrement ?", session)
        if not confirm:
            session.state["pending_section"] = "logement"
            return _reply(
                "Souhaitez-vous confirmer cette réservation ? Répondez « oui » pour valider, ou « non » pour annuler.",
                session, suggestions=["Oui", "Non"],
            )
        data = api.make_reservation(advert_id, start, end, adults, children)
        ok = bool(data) and not (isinstance(data, dict) and "erreur" in data)
        log_event(logger, "logement.api", session_id=session.session_id, endpoint="reserver",
                  status="ok" if ok else "erreur", advert_id=advert_id)
        _reset(session)
        if not ok:
            return _reply(
                "La réservation n'a pas pu être finalisée. Notre équipe va vous recontacter — "
                "vous pouvez aussi écrire à service.client@voyagedo.fr.",
                session,
            )
        return _reply(
            "Votre réservation est confirmée. Vous recevrez votre contrat par e-mail. "
            "Le solde sera à régler 30 jours avant votre arrivée.",
            session, actions=[{"type": "reservation", "advert_id": advert_id}],
        )

    state["awaiting_confirmation"] = True
    session.state["pending_section"] = "logement"
    return _reply(
        f"Vous souhaitez réserver le logement réf. {advert_id}, du {start} au {end}, "
        f"pour {adults} adulte(s) et {children} enfant(s). "
        "Confirmez-vous cette réservation ? Répondez « oui » pour valider.",
        session, suggestions=["Oui, je confirme", "Non, annuler"],
    )
