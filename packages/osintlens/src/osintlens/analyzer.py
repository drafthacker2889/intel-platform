"""The one-call analysis API.

``Analyzer`` wires together language detection, entity recognition, IOC
extraction, and risk scoring. The module-level :func:`analyze` uses a shared
default analyzer for the common case.
"""

import hashlib
from typing import Optional

from .entities import EntityExtractor
from .iocs import extract_iocs
from .keywords import matched_keywords
from .language import language_info
from .result import AnalysisResult, Language, Risk
from .risk import rule_confidence, score_rules


class Analyzer:
    """Reusable analysis pipeline.

    Parameters
    ----------
    ml_model_path:
        Path to a joblib model for ML risk scoring (needs the ``[ml]`` extra).
        When omitted or unloadable, scoring falls back to rules.
    enable_entities:
        Run spaCy NER (needs the ``[multilingual]`` extra). Defaults to True;
        silently yields no entities if spaCy is not installed.
    """

    def __init__(self, ml_model_path: Optional[str] = None, enable_entities: bool = True) -> None:
        self._entities = EntityExtractor() if enable_entities else None
        self._ml = None
        if ml_model_path:
            from .ml import MLRiskModel

            self._ml = MLRiskModel.load(ml_model_path)

    def analyze(self, text: str) -> AnalysisResult:
        """Analyze ``text`` and return a structured :class:`AnalysisResult`."""
        text = text or ""
        lang = language_info(text)

        entities = []
        if self._entities is not None:
            entities = self._entities.extract(text, lang["code"])

        iocs = extract_iocs(text)

        if self._ml is not None:
            score, label, confidence = self._ml.predict(text, entities)
            backend = "ml"
        else:
            score, label = score_rules(text, entities)
            confidence = rule_confidence(score, label)
            backend = "rules"

        return AnalysisResult(
            language=Language(**lang),
            risk=Risk(label=label, score=score, confidence=confidence, backend=backend),
            iocs=iocs,
            entities=entities,
            matched_keywords=matched_keywords(text.lower()),
            text_sha256=hashlib.sha256(text.encode("utf-8", "replace")).hexdigest(),
        )


_default: Optional[Analyzer] = None


def analyze(text: str) -> AnalysisResult:
    """Analyze ``text`` with a shared default :class:`Analyzer`.

    >>> from osintlens import analyze
    >>> r = analyze("Leaked db_pass for admin@corp.example, C2 at 45.13.2.11")
    >>> r.risk.label
    'CRITICAL'
    """
    global _default
    if _default is None:
        _default = Analyzer()
    return _default.analyze(text)
