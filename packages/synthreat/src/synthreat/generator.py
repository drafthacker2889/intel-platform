"""Reproducible synthetic threat-intelligence dataset generation."""

import json
import random
from collections import Counter
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Dict, Iterable, Iterator, List, Optional, Sequence

from . import vocab
from .iocs import embed_iocs, synth_iocs


@dataclass
class Sample:
    """One labeled synthetic document."""

    text: str
    label: str
    language: str
    entities: List[Dict] = field(default_factory=list)
    iocs: Dict[str, List[str]] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)

    def to_training_case(self) -> dict:
        """Return a dict shaped for ``osintlens.ml.train`` (``expected_label`` key)."""
        return {"text": self.text, "entities": self.entities, "expected_label": self.label}


class Dataset:
    """A generated collection of :class:`Sample` with export helpers."""

    def __init__(self, samples: Sequence[Sample]) -> None:
        self._samples: List[Sample] = list(samples)

    def __len__(self) -> int:
        return len(self._samples)

    def __iter__(self) -> Iterator[Sample]:
        return iter(self._samples)

    def __getitem__(self, i):
        return self._samples[i]

    def to_list(self) -> List[dict]:
        return [s.to_dict() for s in self._samples]

    def to_json(self, **kwargs) -> str:
        kwargs.setdefault("ensure_ascii", False)
        kwargs.setdefault("indent", 2)
        return json.dumps(self.to_list(), **kwargs)

    def to_jsonl(self) -> str:
        return "\n".join(json.dumps(s.to_dict(), ensure_ascii=False) for s in self._samples)

    def as_training_data(self) -> List[dict]:
        """Records shaped for ``osintlens.ml.train``."""
        return [s.to_training_case() for s in self._samples]

    def save(self, path, fmt: Optional[str] = None) -> Path:
        """Write to ``path`` as ``.json`` or ``.jsonl`` (inferred from suffix if ``fmt`` omitted)."""
        p = Path(path)
        fmt = fmt or (p.suffix.lstrip(".") or "json")
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(self.to_jsonl() if fmt == "jsonl" else self.to_json(), encoding="utf-8")
        return p

    def stats(self) -> Dict[str, Dict[str, int]]:
        """Counts by language and by label."""
        return {
            "by_language": dict(Counter(s.language for s in self._samples)),
            "by_label": dict(Counter(s.label for s in self._samples)),
            "total": len(self._samples),
            "with_iocs": sum(1 for s in self._samples if s.iocs),
        }


class ThreatDataGenerator:
    """Generate reproducible multilingual threat-intel datasets.

    Parameters
    ----------
    seed:
        Seed for the internal RNG. Pass an int for byte-identical output across
        runs; ``None`` for nondeterministic generation.
    languages:
        Subset of ``("en", "ru", "zh", "de")`` to generate. Defaults to all.
    inject_iocs:
        Fraction ``0.0-1.0`` of samples to enrich with synthetic ground-truth
        indicators (IP/email/sha256/CVE), recorded on ``Sample.iocs``.
    vocab_overrides:
        Optional mapping of vocab attribute name -> replacement, e.g.
        ``{"ACTORS": {...}}`` to swap in your own actor lists.
    """

    def __init__(
        self,
        seed: Optional[int] = None,
        languages: Optional[Sequence[str]] = None,
        inject_iocs: float = 0.0,
        vocab_overrides: Optional[Dict[str, object]] = None,
    ) -> None:
        self._rng = random.Random(seed)
        self.languages = tuple(languages) if languages else vocab.LANGUAGES
        for lang in self.languages:
            if lang not in vocab.LANGUAGES:
                raise ValueError(f"unsupported language {lang!r}; choose from {vocab.LANGUAGES}")
        if not 0.0 <= inject_iocs <= 1.0:
            raise ValueError("inject_iocs must be between 0.0 and 1.0")
        self.inject_iocs = inject_iocs
        self._v = vocab
        self._overrides = vocab_overrides or {}

    def _vget(self, name: str):
        return self._overrides.get(name, getattr(self._v, name))

    def _maybe_inject(self, sample: Sample) -> Sample:
        if self.inject_iocs and self._rng.random() < self.inject_iocs:
            iocs = synth_iocs(self._rng)
            sample.text = embed_iocs(sample.text, sample.language, iocs)
            sample.iocs = iocs
        return sample

    def _critical(self, lang: str) -> Sample:
        actor = self._rng.choice(self._vget("ACTORS")[lang])
        org = self._rng.choice(self._vget("ORGS")[lang])
        phrase = self._rng.choice(self._vget("PHRASES")[lang]["CRITICAL"])
        text = self._rng.choice(self._vget("CRITICAL_TEMPLATES")[lang]).format(
            actor=actor, org=org, phrase=phrase, count=self._rng.randint(50, 500)
        )
        entities = [{"text": actor, "type": "ORG"}, {"text": org, "type": "ORG"}]
        return self._maybe_inject(Sample(text, "CRITICAL", lang, entities))

    def _high(self, lang: str) -> Sample:
        actor = self._rng.choice(self._vget("ACTORS")[lang])
        tech = self._rng.choice(self._vget("TECHS")[lang])
        phrase = self._rng.choice(self._vget("PHRASES")[lang]["HIGH"])
        text = self._rng.choice(self._vget("HIGH_TEMPLATES")[lang]).format(
            actor=actor, phrase=phrase, tech=tech
        )
        entities = [{"text": actor, "type": "ORG"}, {"text": tech, "type": "PRODUCT"}]
        return self._maybe_inject(Sample(text, "HIGH", lang, entities))

    def _medium(self, lang: str) -> Sample:
        org = self._rng.choice(self._vget("ORGS")[lang])
        phrase = self._rng.choice(self._vget("PHRASES")[lang]["MEDIUM"])
        text = self._vget("MEDIUM_PATTERNS")[lang].format(org=org, phrase=phrase)
        return self._maybe_inject(Sample(text, "MEDIUM", lang, [{"text": org, "type": "ORG"}]))

    def _low(self, lang: str) -> Sample:
        phrase = self._rng.choice(self._vget("PHRASES")[lang]["LOW"])
        text = self._vget("LOW_PATTERNS")[lang].format(phrase=phrase)
        return self._maybe_inject(Sample(text, "LOW", lang, []))

    def _counts(self, total: int, distribution: Dict[str, float]) -> Dict[str, int]:
        # CRITICAL/HIGH/MEDIUM via floor; LOW absorbs the remainder for an exact total.
        crit = int(total * distribution["CRITICAL"])
        high = int(total * distribution["HIGH"])
        med = int(total * distribution["MEDIUM"])
        low = total - crit - high - med
        return {"CRITICAL": crit, "HIGH": high, "MEDIUM": med, "LOW": low}

    def generate(
        self,
        samples_per_language: int = 5000,
        distribution: Optional[Dict[str, float]] = None,
        shuffle: bool = True,
    ) -> Dataset:
        """Generate a :class:`Dataset` with ``samples_per_language`` per language."""
        distribution = distribution or self._v.DEFAULT_DISTRIBUTION
        builders = {
            "CRITICAL": self._critical,
            "HIGH": self._high,
            "MEDIUM": self._medium,
            "LOW": self._low,
        }
        samples: List[Sample] = []
        for lang in self.languages:
            counts = self._counts(samples_per_language, distribution)
            for label, n in counts.items():
                build = builders[label]
                samples.extend(build(lang) for _ in range(n))
        if shuffle:
            self._rng.shuffle(samples)
        return Dataset(samples)


def generate(
    samples_per_language: int = 5000,
    seed: Optional[int] = None,
    languages: Optional[Sequence[str]] = None,
    inject_iocs: float = 0.0,
) -> Dataset:
    """Convenience wrapper around :class:`ThreatDataGenerator`."""
    gen = ThreatDataGenerator(seed=seed, languages=languages, inject_iocs=inject_iocs)
    return gen.generate(samples_per_language=samples_per_language)
