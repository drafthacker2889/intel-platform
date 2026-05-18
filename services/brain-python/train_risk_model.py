"""Train the risk classification model.

Loads the English synthetic dataset (evals/risk_eval_cases.json) and,
if present, the multilingual dataset (evals/multilingual_eval_cases.json),
merges them, featurizes with the shared 12-feature extractor, then trains
and evaluates a RandomForestClassifier.

Usage:
    # Generate data first if not present:
    python generate_synthetic_data.py
    python generate_multilingual_data.py   # optional

    # Then train:
    python train_risk_model.py
"""

import json
import sys
from collections import Counter
from pathlib import Path

import joblib
import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import classification_report
from sklearn.model_selection import StratifiedKFold, cross_val_score, train_test_split
from sklearn.preprocessing import LabelEncoder

ROOT      = Path(__file__).parent
EVALS_DIR = ROOT / "evals"
MODEL_DIR = ROOT / "models"
MODEL_PATH = MODEL_DIR / "risk_model.joblib"

# Ensure the shared featurize module is importable
sys.path.insert(0, str(ROOT / "src"))
from featurize import featurize  # type: ignore[import]  # noqa: E402

LABEL_ORDER = ["LOW", "MEDIUM", "HIGH", "CRITICAL"]


def load_cases(path: Path) -> list:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def build_dataset(cases: list):
    X, y = [], []
    skipped = 0
    for case in cases:
        text     = case.get("text", "")
        entities = case.get("entities", [])
        label    = case.get("expected_label", "")
        if not text or label not in LABEL_ORDER:
            skipped += 1
            continue
        X.append(featurize(text, entities))
        y.append(label)
    if skipped:
        print(f"  Skipped {skipped} malformed cases.")
    return np.array(X, dtype=float), np.array(y)


def main():
    # ── Load datasets ─────────────────────────────────────────────────────────
    en_cases   = load_cases(EVALS_DIR / "risk_eval_cases.json")
    ml_cases   = load_cases(EVALS_DIR / "multilingual_eval_cases.json")

    all_cases  = en_cases + ml_cases
    if not all_cases:
        raise RuntimeError(
            "No training data found. Run generate_synthetic_data.py first."
        )

    print(f"Loaded {len(en_cases)} English + {len(ml_cases)} multilingual cases "
          f"= {len(all_cases)} total.")

    X, y = build_dataset(all_cases)
    print(f"Feature matrix: {X.shape}  (samples × features)")

    label_dist = Counter(y)
    print("\nLabel distribution:")
    for label in LABEL_ORDER:
        count = label_dist.get(label, 0)
        print(f"  {label:10s}: {count:6d} ({100*count/len(y):.1f}%)")

    # ── Train / test split (stratified 80/20) ─────────────────────────────────
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y
    )
    print(f"\nTrain: {len(X_train)}  Test: {len(X_test)}")

    # ── Cross-validation on training set ─────────────────────────────────────
    clf = RandomForestClassifier(
        n_estimators=300,
        max_depth=None,        # let trees grow fully
        min_samples_leaf=2,
        max_features="sqrt",
        class_weight="balanced",
        random_state=42,
        n_jobs=-1,
    )

    min_class = min(Counter(y_train).values())
    k = min(5, min_class)
    if k >= 2:
        skf    = StratifiedKFold(n_splits=k, shuffle=True, random_state=42)
        scores = cross_val_score(clf, X_train, y_train, cv=skf, scoring="f1_macro")
        print(f"\nStratified {k}-fold CV macro-F1: "
              f"{scores.mean():.4f} ± {scores.std():.4f}")

    # ── Final fit on full training set ─────────────────────────────────────────
    clf.fit(X_train, y_train)

    # ── Evaluate on held-out test set ─────────────────────────────────────────
    y_pred = clf.predict(X_test)
    print("\nTest-set classification report:")
    print(classification_report(y_test, y_pred, labels=LABEL_ORDER, zero_division=0))

    train_acc = (clf.predict(X_train) == y_train).mean()
    test_acc  = (y_pred == y_test).mean()
    print(f"Train accuracy: {train_acc:.4f}   Test accuracy: {test_acc:.4f}")

    # ── Feature importance ────────────────────────────────────────────────────
    feature_names = [
        "critical_keywords", "high_keywords", "medium_keywords",
        "entity_count", "text_length_norm",
        "ip_count", "email_count", "url_count", "hash_count",
        "at_count", "urgency_count", "allcaps_count",
    ]
    importances = sorted(
        zip(feature_names, clf.feature_importances_), key=lambda x: -x[1]
    )
    print("\nFeature importances (top 12):")
    for name, imp in importances:
        bar = "█" * int(imp * 50)
        print(f"  {name:25s} {imp:.4f}  {bar}")

    # ── Save ──────────────────────────────────────────────────────────────────
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    joblib.dump(clf, MODEL_PATH)
    print(f"\nModel saved → {MODEL_PATH}")


if __name__ == "__main__":
    main()
