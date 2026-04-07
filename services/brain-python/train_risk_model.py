"""Train a risk classification model from labeled evaluation data.

Reads evals/risk_eval_cases.json (same format used by eval_model.py),
featurizes each case, trains a RandomForest classifier, and saves the
model to models/risk_model.joblib.

Usage:
    python train_risk_model.py
"""

import json
import os
from pathlib import Path

import joblib
import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import cross_val_score

ROOT = Path(__file__).parent
CASES_PATH = ROOT / "evals" / "risk_eval_cases.json"
MODEL_DIR = ROOT / "models"
MODEL_PATH = MODEL_DIR / "risk_model.joblib"

RISK_KEYWORDS = [
    "password", "admin", "login", "secret",
    "confidential", "leaked", "db_pass", "key",
]


def featurize(case):
    text = case["text"].lower()
    entities = case.get("entities", [])
    keyword_hits = sum(1 for w in RISK_KEYWORDS if w in text)
    return [
        keyword_hits,
        len(entities),
        len(text),
        text.count("http"),
        text.count("@"),
    ]


def main():
    with CASES_PATH.open("r", encoding="utf-8") as f:
        cases = json.load(f)

    X = np.array([featurize(c) for c in cases])
    y = np.array([c["expected_label"] for c in cases])

    clf = RandomForestClassifier(
        n_estimators=100,
        max_depth=5,
        random_state=42,
        class_weight="balanced",
    )

    if len(cases) >= 8:
        from collections import Counter
        class_counts = Counter(y)
        min_class = min(class_counts.values())
        k = min(min_class, 3)
        if k >= 2:
            scores = cross_val_score(clf, X, y, cv=k, scoring="accuracy")
            print(f"cross-val accuracy (k={k}): {scores.mean():.3f} ± {scores.std():.3f}")

    clf.fit(X, y)

    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    joblib.dump(clf, MODEL_PATH)
    print(f"Model saved to {MODEL_PATH}")
    print(f"Feature importances: {clf.feature_importances_}")

    preds = clf.predict(X)
    train_acc = (preds == y).mean()
    print(f"Train accuracy: {train_acc:.3f}")


if __name__ == "__main__":
    main()
