"""Train the ML risk classifier and print cross-validation results."""

import json
from pathlib import Path

from src.ml_model import train

ROOT = Path(__file__).parent
TRAINING_DATA = ROOT / "evals" / "training_data.json"


def main():
    model, vectorizer = train(str(TRAINING_DATA))

    from sklearn.model_selection import cross_val_score

    with open(TRAINING_DATA, encoding="utf-8") as fh:
        cases = json.load(fh)

    texts = []
    labels = []
    for case in cases:
        entity_count = len(case.get("entities", []))
        enriched = f"{case['text']} __entity_count_{entity_count}__"
        texts.append(enriched)
        labels.append(case["expected_label"])

    X = vectorizer.transform(texts)
    folds = min(5, len(set(labels)))
    scores = cross_val_score(model, X, labels, cv=folds)

    print(f"training_samples={len(cases)}")
    print(f"cv_accuracy={scores.mean():.3f} (+/- {scores.std():.3f})")
    print("train-ok")


if __name__ == "__main__":
    main()
