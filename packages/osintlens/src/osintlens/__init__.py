"""osintlens — multilingual OSINT analysis in a single call.

Language detection, IOC extraction, entity recognition, and explainable risk
scoring, with a pure-Python core and optional ML / spaCy backends.

    >>> import osintlens as ol
    >>> result = ol.analyze("Leaked db_pass for admin@corp.example, C2 at 45.13.2.11")
    >>> result.risk.label
    'CRITICAL'
    >>> result.iocs["email"]
    ['admin@corp.example']
"""

from .analyzer import Analyzer, analyze
from .features import FEATURE_NAMES, featurize
from .iocs import extract_iocs
from .result import AnalysisResult, Language, Risk
from .risk import LABELS, score_rules

__version__ = "0.1.0"

__all__ = [
    "analyze",
    "Analyzer",
    "AnalysisResult",
    "Language",
    "Risk",
    "extract_iocs",
    "featurize",
    "FEATURE_NAMES",
    "score_rules",
    "LABELS",
    "__version__",
]
