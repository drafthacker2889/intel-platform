import json
import os
import sys


def fail(message: str) -> None:
    print(f"SLO gate failed: {message}")
    sys.exit(1)


def main() -> None:
    if len(sys.argv) < 2:
        fail("usage: python scripts/evaluate_burn_rate.py <k6-summary.json>")

    summary_path = sys.argv[1]
    if not os.path.exists(summary_path):
        fail(f"summary file not found: {summary_path}")

    with open(summary_path, "r", encoding="utf-8") as file:
        data = json.load(file)

    metrics = data.get("metrics", {})
    failed_rate = metrics.get("http_req_failed", {}).get("values", {}).get("rate")
    checks_rate = metrics.get("checks", {}).get("values", {}).get("rate")

    if failed_rate is None:
        if checks_rate is None:
            fail("missing http_req_failed.rate and checks.rate in k6 summary")
        failed_rate = max(0.0, 1.0 - float(checks_rate))

    slo_target = float(os.getenv("SLO_TARGET", "0.999"))
    burn_rate_limit = float(os.getenv("BURN_RATE_LIMIT", "2.0"))
    error_budget = 1.0 - slo_target

    if error_budget <= 0.0:
        fail("SLO_TARGET must be below 1.0")

    burn_rate = float(failed_rate) / error_budget

    print(f"failed_rate={failed_rate:.6f}")
    print(f"slo_target={slo_target:.6f}")
    print(f"error_budget={error_budget:.6f}")
    print(f"burn_rate={burn_rate:.4f}")
    print(f"burn_rate_limit={burn_rate_limit:.4f}")

    if burn_rate > burn_rate_limit:
        fail(f"burn rate {burn_rate:.4f} exceeded limit {burn_rate_limit:.4f}")

    print("SLO gate passed")


if __name__ == "__main__":
    main()
