import json
from pathlib import Path

from src.main import calculate_risk


ROOT = Path(__file__).parent
CASES_PATH = ROOT / "evals" / "risk_eval_cases.json"
MIN_ACCURACY = 0.9


def load_cases():
    with CASES_PATH.open("r", encoding="utf-8") as file:
        return json.load(file)


def predict(case):
    score, label = calculate_risk(case["text"], case.get("entities", []))
    return {"score": score, "label": label}


def main():
    cases = load_cases()
    total = len(cases)
    correct = 0
    failures = []

    for case in cases:
        prediction = predict(case)
        if prediction["label"] == case["expected_label"]:
            correct += 1
            continue
        failures.append(
            {
                "name": case["name"],
                "expected": case["expected_label"],
                "actual": prediction["label"],
                "score": prediction["score"],
            }
        )

    accuracy = correct / total if total else 0.0
    print(f"cases={total}")
    print(f"correct={correct}")
    print(f"accuracy={accuracy:.3f}")

    if failures:
        print("failures=")
        for failure in failures:
            print(json.dumps(failure))

    if accuracy < MIN_ACCURACY:
        raise SystemExit(f"model evaluation failed: accuracy {accuracy:.3f} < {MIN_ACCURACY:.3f}")

    print("model-eval-ok")


if __name__ == "__main__":
    main()
