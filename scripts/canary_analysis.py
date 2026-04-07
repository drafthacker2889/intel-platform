"""Automated canary analysis with metrics-based auto-rollback.

Deploys the green (canary) upstream, samples error rate from Prometheus,
and auto-rolls back to blue if the canary exceeds the error threshold.

Usage:
    python scripts/canary_analysis.py --canary-duration 120 --error-threshold 0.05
"""

import argparse
import subprocess
import sys
import time
import urllib.request
import json


PROMETHEUS_URL = "http://localhost:9090"
GATEWAY_HEALTH = "http://localhost:8080/health"


def query_prometheus(query: str) -> float | None:
    url = f"{PROMETHEUS_URL}/api/v1/query?query={urllib.parse.quote(query)}"
    try:
        with urllib.request.urlopen(url, timeout=10) as resp:
            data = json.loads(resp.read())
            results = data.get("data", {}).get("result", [])
            if results:
                return float(results[0]["value"][1])
    except Exception as exc:
        print(f"  Prometheus query failed: {exc}")
    return None


def switch_upstream(color: str):
    print(f"Switching gateway to {color}...")
    subprocess.run(
        ["powershell", "-File", "scripts/switch_rollout.ps1", "-Color", color],
        check=True,
    )


def wait_healthy(url: str, timeout: int = 60):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=5) as resp:
                if resp.status == 200:
                    return True
        except Exception:
            pass
        time.sleep(2)
    return False


import urllib.parse


def run_canary(duration: int, interval: int, error_threshold: float):
    print(f"Canary analysis: {duration}s window, {error_threshold:.1%} error threshold")

    # Step 1: record baseline error rate on blue
    print("Recording baseline (blue)...")
    baseline_errors = query_prometheus(
        'rate(brain_index_failures_total[1m])'
    )
    baseline_processed = query_prometheus(
        'rate(brain_processed_total[1m])'
    )
    baseline_error_rate = 0.0
    if baseline_errors is not None and baseline_processed and baseline_processed > 0:
        baseline_error_rate = baseline_errors / baseline_processed
    print(f"  Baseline error rate: {baseline_error_rate:.4f}")

    # Step 2: switch to green (canary)
    switch_upstream("green")
    if not wait_healthy(GATEWAY_HEALTH):
        print("FAIL: gateway unhealthy after canary switch, rolling back")
        switch_upstream("blue")
        return False

    print(f"Canary live. Sampling every {interval}s for {duration}s...")
    samples = []
    end_time = time.time() + duration

    while time.time() < end_time:
        time.sleep(interval)
        err = query_prometheus('rate(brain_index_failures_total[1m])')
        proc = query_prometheus('rate(brain_processed_total[1m])')
        if err is not None and proc is not None and proc > 0:
            rate = err / proc
        else:
            rate = 0.0
        samples.append(rate)
        print(f"  Sample error rate: {rate:.4f}")

        # Immediate rollback on spike
        if rate > error_threshold * 3:
            print(f"SPIKE detected ({rate:.4f} > {error_threshold * 3:.4f}), immediate rollback")
            switch_upstream("blue")
            return False

    avg_error_rate = sum(samples) / len(samples) if samples else 0.0
    print(f"Average canary error rate: {avg_error_rate:.4f}")

    if avg_error_rate > error_threshold:
        print(f"FAIL: error rate {avg_error_rate:.4f} > threshold {error_threshold:.4f}")
        switch_upstream("blue")
        print("Rolled back to blue.")
        return False

    print("PASS: canary promoted. Green is now active.")
    return True


def main():
    parser = argparse.ArgumentParser(description="Automated canary analysis")
    parser.add_argument("--canary-duration", type=int, default=120, help="Seconds to observe canary")
    parser.add_argument("--sample-interval", type=int, default=15, help="Seconds between metric samples")
    parser.add_argument("--error-threshold", type=float, default=0.05, help="Max acceptable error rate (0-1)")
    args = parser.parse_args()

    success = run_canary(args.canary_duration, args.sample_interval, args.error_threshold)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
