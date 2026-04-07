# Reliability Guardrails

## Chaos

1. `tests/chaos/redis_recovery.sh` validates Redis outage and recovery flow.
2. `.github/workflows/chaos.yml` runs the recovery suite in CI.

## Policy-as-Code

1. `.github/workflows/policy.yml` renders merged Compose manifests.
2. `policy/compose/deny.rego` enforces restart, healthcheck, and port policies.

## Future Expansion

1. Add latency injection through Toxiproxy.
2. Add Elasticsearch corruption and disk-pressure drills.
3. Extend policy coverage to release workflows and infrastructure provisioning.
