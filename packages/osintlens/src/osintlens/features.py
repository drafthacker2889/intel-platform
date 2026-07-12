"""Feature vector for risk classification.

The 12-element vector is the input contract shared between the rule engine,
the ML backend, and any model you train yourself. Keep the order stable.
"""

from typing import List, Sequence

from .iocs import _EMAIL_RE, _HASH_RE, _IPV4_RE, _URL_RE
from .keywords import (
    RISK_KEYWORDS_CRITICAL,
    RISK_KEYWORDS_HIGH,
    RISK_KEYWORDS_MEDIUM,
)

FEATURE_NAMES: Sequence[str] = (
    "critical_keyword_hits",
    "high_keyword_hits",
    "medium_keyword_hits",
    "entity_count",
    "text_length_norm",
    "ip_count",
    "email_count",
    "url_count",
    "hash_count",
    "at_count",
    "urgency_count",
    "allcaps_word_count",
)


def featurize(text: str, entities: Sequence) -> List[float]:
    """Return the 12-element feature vector for ``text``.

    ``entities`` only contributes its length, so any sequence works.
    """
    text_lower = text.lower()

    critical_hits = sum(1 for w in RISK_KEYWORDS_CRITICAL if w in text_lower)
    high_hits = sum(1 for w in RISK_KEYWORDS_HIGH if w in text_lower)
    medium_hits = sum(1 for w in RISK_KEYWORDS_MEDIUM if w in text_lower)

    return [
        critical_hits,
        high_hits,
        medium_hits,
        len(entities),
        min(len(text) / 100.0, 100.0),
        len(_IPV4_RE.findall(text)),
        len(_EMAIL_RE.findall(text)),
        len(_URL_RE.findall(text)),
        len(_HASH_RE.findall(text)),
        text.count("@"),
        text.count("!"),
        sum(1 for w in text.split() if w.isupper() and len(w) > 2),
    ]
