"""Machine-learned risk classifier using TF-IDF + Logistic Regression.

Provides predict() as a drop-in replacement for the rule-based calculate_risk().
Falls back gracefully when scikit-learn is not installed or no trained model exists.
"""

import json
import os
from pathlib import Path

MODEL_DIR = Path(__file__).parent.parent / "models"
MODEL_FILE = MODEL_DIR / "risk_classifier.joblib"
VECTORIZER_FILE = MODEL_DIR / "tfidf_vectorizer.joblib"

_model = None
_vectorizer = None
_ml_available = False


def _lazy_imports():
    try:
        import joblib
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.linear_model import LogisticRegression
        return joblib, TfidfVectorizer, LogisticRegression
    except ImportError:
        return None, None, None


def load_model():
    """Load a previously trained model from disk. Returns True on success."""
    global _model, _vectorizer, _ml_available

    joblib, _, _ = _lazy_imports()
    if joblib is None:
        return False
    if not MODEL_FILE.exists() or not VECTORIZER_FILE.exists():
        return False
    try:
        _model = joblib.load(MODEL_FILE)
        _vectorizer = joblib.load(VECTORIZER_FILE)
        _ml_available = True
        return True
    except Exception as exc:
        print(f"ML model load failed: {exc}")
        _ml_available = False
        return False


def predict(text, entities):
    """Predict risk using the ML model.

    Returns (confidence_pct, label) or None if ML is unavailable.
    """
    if not _ml_available or _model is None or _vectorizer is None:
        return None

    enriched = f"{text} __entity_count_{len(entities)}__"
    features = _vectorizer.transform([enriched])
    label = _model.predict(features)[0]
    probabilities = _model.predict_proba(features)[0]
    confidence = int(max(probabilities) * 100)
    return confidence, label


def is_available():
    return _ml_available


def train(training_data_path, output_dir=None):
    """Train a new model from labeled JSON and save artifacts."""
    joblib, TfidfVectorizer, LogisticRegression = _lazy_imports()
    if joblib is None:
        raise ImportError("scikit-learn and joblib are required for training")

    with open(training_data_path, encoding="utf-8") as fh:
        cases = json.load(fh)

    texts = []
    labels = []
    for case in cases:
        entity_count = len(case.get("entities", []))
        enriched = f"{case['text']} __entity_count_{entity_count}__"
        texts.append(enriched)
        labels.append(case["expected_label"])

    vectorizer = TfidfVectorizer(
        max_features=5000,
        ngram_range=(1, 2),
        sublinear_tf=True,
    )
    X = vectorizer.fit_transform(texts)

    model = LogisticRegression(
        max_iter=1000,
        multi_class="multinomial",
        C=1.0,
        class_weight="balanced",
    )
    model.fit(X, labels)

    save_dir = Path(output_dir) if output_dir else MODEL_DIR
    save_dir.mkdir(parents=True, exist_ok=True)
    joblib.dump(model, save_dir / "risk_classifier.joblib")
    joblib.dump(vectorizer, save_dir / "tfidf_vectorizer.joblib")

    return model, vectorizer
