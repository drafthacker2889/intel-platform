"""Named-entity recognition.

Requires the ``[multilingual]`` extra (spaCy). Without spaCy installed, entity
extraction returns an empty list and the rest of the pipeline (language, IOCs,
risk) continues to work — IOCs act as a dependency-free entity floor.
"""

import logging
from typing import Dict, List

logger = logging.getLogger("osintlens.entities")

# Per-language spaCy models. Install with e.g. `python -m spacy download en_core_web_sm`.
LANGUAGE_MODELS = {
    "en": "en_core_web_sm",
    "ru": "ru_core_news_sm",
    "zh": "zh_core_web_sm",
    "de": "de_core_news_sm",
}

_LABEL_MAP = {
    "PERSON": "PERSON", "PER": "PERSON",
    "ORG": "ORG", "ORGANIZATION": "ORG",
    "GPE": "LOCATION", "LOC": "LOCATION", "LOCATION": "LOCATION", "FACILITY": "LOCATION",
    "PRODUCT": "PRODUCT",
}

try:  # optional dependency
    import spacy

    _HAS_SPACY = True
except Exception:  # pragma: no cover - exercised only without the extra
    _HAS_SPACY = False


class EntityExtractor:
    """Lazy-loading, multilingual spaCy entity extractor with model caching."""

    MAX_CHARS = 100_000

    def __init__(self) -> None:
        self._models: Dict[str, object] = {}

    @property
    def available(self) -> bool:
        return _HAS_SPACY

    def _model_for(self, lang_code: str):
        if lang_code in self._models:
            return self._models[lang_code]
        name = LANGUAGE_MODELS.get(lang_code, LANGUAGE_MODELS["en"])
        try:
            nlp = spacy.load(name)
        except Exception:
            # Model not downloaded — fall back to a blank pipeline for the language.
            blank = lang_code if lang_code in LANGUAGE_MODELS else "en"
            logger.warning("spaCy model %s unavailable; using blank '%s' pipeline", name, blank)
            nlp = spacy.blank(blank)
        self._models[lang_code] = nlp
        return nlp

    def extract(self, text: str, lang_code: str = "en") -> List[Dict]:
        """Return a list of ``{text, type, start, end, language}`` entities.

        Returns ``[]`` when spaCy is not installed.
        """
        if not _HAS_SPACY:
            return []
        nlp = self._model_for(lang_code)
        try:
            doc = nlp(text[: self.MAX_CHARS])
        except Exception as exc:
            logger.error("entity extraction failed for %s: %s", lang_code, exc)
            return []
        return [
            {
                "text": ent.text,
                "type": _LABEL_MAP.get(ent.label_, "ENTITY"),
                "start": ent.start_char,
                "end": ent.end_char,
                "language": lang_code,
            }
            for ent in doc.ents
        ]
