"""Rule-based risk scoring.

Deterministic, dependency-free, and explainable. The ML backend in
``osintlens.ml`` is an optional drop-in that shares the same output shape.
"""

from typing import Sequence, Tuple

from .keywords import AUTH_CONTEXT_TERMS, RISK_KEYWORDS

LABELS = ("LOW", "MEDIUM", "HIGH", "CRITICAL")
LABEL_TO_SCORE = {"LOW": 0, "MEDIUM": 10, "HIGH": 30, "CRITICAL": 60}


def score_rules(text: str, entities: Sequence) -> Tuple[int, str]:
    """Return ``(score, label)`` for ``text`` using the rule engine.

    Scoring:
      * +10 per critical/high risk keyword present
      * +5 per extracted entity
      * +10 if a keyword co-occurs with an authentication term
      * +10 if four or more keywords are present
    Bands: >=50 CRITICAL, >=20 HIGH, >0 MEDIUM, else LOW.
    """
    text_lower = text.lower()
    keyword_hits = sum(1 for w in RISK_KEYWORDS if w in text_lower)
    score = keyword_hits * 10 + len(entities) * 5

    if keyword_hits > 0 and any(t in text_lower for t in AUTH_CONTEXT_TERMS):
        score += 10
    if keyword_hits >= 4:
        score += 10

    if score >= 50:
        label = "CRITICAL"
    elif score >= 20:
        label = "HIGH"
    elif score > 0:
        label = "MEDIUM"
    else:
        label = "LOW"
    return score, label


def rule_confidence(score: int, label: str) -> int:
    """Heuristic 0-100 confidence for a rule-based verdict.

    Rules are deterministic, so this reflects how firmly the score sits in its
    band rather than a calibrated probability. For calibrated confidence, use
    the ML backend.
    """
    if label == "LOW":
        return 60
    return min(95, 50 + score)
