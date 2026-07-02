from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any

from ..core.config import get_settings

_MASK: dict[str, str] = {
    "PERSON": "[NOM]",
    "PHONE_NUMBER": "[TÉLÉPHONE]",
    "EMAIL_ADDRESS": "[EMAIL]",
    "IBAN_CODE": "[IBAN]",
    "CREDIT_CARD": "[CARTE]",
    "IP_ADDRESS": "[IP]",
    "FR_SSN": "[NUM_SECU]",
    "FR_ADDRESS": "[ADRESSE]",
}
_TARGET_ENTITIES = list(_MASK.keys())


@dataclass
class PiiResult:
    text: str
    counts: dict[str, int] = field(default_factory=dict)

    @property
    def total(self) -> int:
        return sum(self.counts.values())


@lru_cache
def _get_analyzer() -> Any:
    from presidio_analyzer import (
        AnalyzerEngine,
        Pattern,
        PatternRecognizer,
        RecognizerRegistry,
    )
    from presidio_analyzer.nlp_engine import NlpEngineProvider
    from presidio_analyzer.predefined_recognizers import (
        CreditCardRecognizer,
        EmailRecognizer,
        IbanRecognizer,
        IpRecognizer,
        PhoneRecognizer,
        SpacyRecognizer,
    )

    settings = get_settings()
    lang = settings.pii_language

    nlp_configuration = {
        "nlp_engine_name": "spacy",
        "models": [{"lang_code": lang, "model_name": settings.spacy_model}],
        "ner_model_configuration": {
            "model_to_presidio_entity_mapping": {
                "PER": "PERSON",
                "PERSON": "PERSON",
                "LOC": "LOCATION",
                "GPE": "LOCATION",
                "ORG": "ORGANIZATION",
                "MISC": "MISC",
            },
        },
    }
    try:
        nlp_engine = NlpEngineProvider(nlp_configuration=nlp_configuration).create_engine()
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(
            f"Modèle spaCy '{settings.spacy_model}' introuvable. Installez-le avec : "
            f"python -m spacy download {settings.spacy_model}"
        ) from exc

    registry = RecognizerRegistry(supported_languages=[lang])
    registry.add_recognizer(SpacyRecognizer(supported_language=lang))
    registry.add_recognizer(
        EmailRecognizer(
            supported_language=lang,
            context=["email", "courriel", "mail", "adresse électronique"],
        )
    )
    registry.add_recognizer(
        PhoneRecognizer(
            supported_language=lang,
            supported_regions=["FR", "BE", "CH"],
            context=["téléphone", "tel", "tél", "portable", "mobile", "appeler"],
        )
    )
    registry.add_recognizer(IbanRecognizer(supported_language=lang))
    registry.add_recognizer(CreditCardRecognizer(supported_language=lang))
    registry.add_recognizer(IpRecognizer(supported_language=lang))

    registry.add_recognizer(
        PatternRecognizer(
            supported_entity="FR_SSN",
            supported_language=lang,
            patterns=[
                Pattern(
                    name="fr_ssn",
                    regex=r"\b[12]\s?\d{2}\s?\d{2}\s?\d{2}\s?\d{3}\s?\d{3}\s?\d{2}\b",
                    score=0.7,
                )
            ],
        )
    )
    registry.add_recognizer(
        PatternRecognizer(
            supported_entity="FR_ADDRESS",
            supported_language=lang,
            patterns=[
                Pattern(
                    name="fr_address",
                    regex=(
                        r"\b\d{1,4}\s?(?:bis|ter)?\s*,?\s*"
                        r"(?:rue|avenue|av\.?|bd|boulevard|impasse|all[ée]e|chemin|"
                        r"place|quai|route|cours|résidence)\b[^\n.,;]{0,40}"
                    ),
                    score=0.55,
                )
            ],
        )
    )

    return AnalyzerEngine(
        registry=registry, supported_languages=[lang], nlp_engine=nlp_engine
    )


def scrub_pii(text: str) -> PiiResult:
    if not text.strip():
        return PiiResult(text=text, counts={})

    from presidio_anonymizer import AnonymizerEngine
    from presidio_anonymizer.entities import OperatorConfig

    settings = get_settings()
    analyzer = _get_analyzer()
    results = analyzer.analyze(
        text=text, language=settings.pii_language, entities=_TARGET_ENTITIES
    )

    counts: dict[str, int] = {}
    for r in results:
        counts[r.entity_type] = counts.get(r.entity_type, 0) + 1

    operators = {
        entity: OperatorConfig("replace", {"new_value": tag})
        for entity, tag in _MASK.items()
    }
    operators["DEFAULT"] = OperatorConfig("replace", {"new_value": "[CONFIDENTIEL]"})

    anonymized = AnonymizerEngine().anonymize(
        text=text, analyzer_results=results, operators=operators
    )
    return PiiResult(text=anonymized.text, counts=counts)
