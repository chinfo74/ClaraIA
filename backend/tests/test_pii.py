"""
PII guardrail tests (Presidio, French).

Skipped automatically if Presidio or the French spaCy model is not installed.
These cover the core acceptance criterion of step 1: a name and a phone number
must be removed — while thermal town names must be preserved.
"""

import pytest

pytest.importorskip("presidio_analyzer")
pytest.importorskip("presidio_anonymizer")

from backend.rag.pii import scrub_pii  # noqa: E402

try:
    scrub_pii("amorce")  # triggers spaCy model load; skip cleanly if missing
except RuntimeError as exc:
    pytest.skip(f"Modèle spaCy FR indisponible : {exc}", allow_module_level=True)


def test_name_and_phone_and_email_are_removed():
    text = (
        "Bonjour, je m'appelle Jean Dupont. Vous pouvez me joindre au "
        "06 12 34 56 78 ou par mail à jean.dupont@example.com."
    )
    result = scrub_pii(text)
    assert "Jean Dupont" not in result.text
    assert "06 12 34 56 78" not in result.text
    assert "jean.dupont@example.com" not in result.text
    assert result.counts.get("PERSON", 0) >= 1
    assert result.counts.get("PHONE_NUMBER", 0) >= 1
    assert result.counts.get("EMAIL_ADDRESS", 0) >= 1
    assert result.total >= 3


def test_thermal_town_name_is_preserved():
    text = "La cure thermale à Dax dure 21 jours et coûte 350 euros."
    result = scrub_pii(text)
    assert "Dax" in result.text
    assert "21 jours" in result.text


def test_counts_never_leak_content():
    # The result exposes counts per type, not the matched strings.
    result = scrub_pii("Appelez Marie Martin au 07 98 76 54 32.")
    assert all(isinstance(v, int) for v in result.counts.values())
