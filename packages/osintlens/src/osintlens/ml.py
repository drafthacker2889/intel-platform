"""Optional machine-learned risk backend (the ``[ml]`` extra).

Trains / loads a scikit-learn classifier over the 12-element feature vector
from :mod:`osintlens.features`. Degrades to ``None`` when scikit-learn/joblib
are absent or no model file is provided, letting the caller fall back to rules.
"""

from pathlib import Path
from typing import Optional, Sequence, Tuple

from .features import featurize
from .risk import LABEL_TO_SCORE


def _lazy_imports():
    try:
        import joblib
        import numpy as np

        return joblib, np
    except Exception:
        return None, None


class MLRiskModel:
    """Wraps a trained sklearn estimator that predicts a risk label."""

    def __init__(self, estimator) -> None:
        self._estimator = estimator

    @classmethod
    def load(cls, model_path) -> Optional["MLRiskModel"]:
        """Load a joblib-serialized estimator. Returns ``None`` on any failure."""
        joblib, _ = _lazy_imports()
        if joblib is None:
            return None
        path = Path(model_path)
        if not path.exists():
            return None
        try:
            return cls(joblib.load(path))
        except Exception:
            return None

    def predict(self, text: str, entities: Sequence) -> Tuple[int, str, int]:
        """Return ``(score, label, confidence)``.

        Confidence is the model's max class probability when available,
        otherwise a fixed 75.
        """
        _, np = _lazy_imports()
        features = np.array([featurize(text, entities)])
        label = str(self._estimator.predict(features)[0])
        confidence = 75
        if hasattr(self._estimator, "predict_proba"):
            proba = self._estimator.predict_proba(features)[0]
            confidence = int(max(proba) * 100)
        return LABEL_TO_SCORE.get(label, 0), label, confidence


def train(labeled_cases, output_path):
    """Train a classifier from labeled cases and persist it with joblib.

    ``labeled_cases`` is an iterable of ``{"text": str, "entities": list,
    "expected_label": str}``. Returns the fitted estimator.
    """
    joblib, np = _lazy_imports()
    if joblib is None:
        raise ImportError("scikit-learn and joblib are required to train; install osintlens[ml]")
    from sklearn.ensemble import RandomForestClassifier

    X, y = [], []
    for case in labeled_cases:
        X.append(featurize(case["text"], case.get("entities", [])))
        y.append(case["expected_label"])

    model = RandomForestClassifier(n_estimators=200, class_weight="balanced", random_state=0)
    model.fit(np.array(X), y)

    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(model, out)
    return model
