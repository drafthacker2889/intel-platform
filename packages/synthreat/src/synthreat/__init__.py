"""synthreat — reproducible synthetic multilingual threat-intel datasets.

Generate labeled EN/RU/ZH/DE threat-intelligence text with risk labels,
entities, and optional ground-truth IOCs — for training and benchmarking
classifiers and indicator extractors.

    >>> import synthreat
    >>> ds = synthreat.generate(samples_per_language=100, seed=42, inject_iocs=0.3)
    >>> ds.stats()["by_label"]
    {'CRITICAL': ..., 'HIGH': ..., 'MEDIUM': ..., 'LOW': ...}
"""

from .generator import Dataset, Sample, ThreatDataGenerator, generate
from .vocab import LABELS, LANGUAGES

__version__ = "0.1.0"

__all__ = [
    "generate",
    "ThreatDataGenerator",
    "Dataset",
    "Sample",
    "LANGUAGES",
    "LABELS",
    "__version__",
]
