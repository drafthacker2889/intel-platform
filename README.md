# Intel Platform

Intel Platform is a polyglot intelligence pipeline that collects web content, sanitizes and enriches text, scores risk, and indexes results for search and investigation.

## What This Repository Delivers

This project runs end-to-end locally or in containers:

1. Crawls source pages with Go over Tor.
2. Cleans and normalizes raw HTML with Rust.
3. Extracts entities and computes risk in Python.
4. Stores searchable artifacts in Elasticsearch.
5. Exposes operations through a React dashboard, gateway, and observability stack.

In one line: this repo turns noisy web data into searchable, risk-scored intelligence artifacts.

## Why This Project Is Strong

Compared to most sample repos, this platform includes:

1. Polyglot service specialization (Go, Rust, Python, TypeScript).
2. Queue-driven decoupling across pipeline stages.
3. Production and observability compose overlays.
4. CI workflows for quality, performance, chaos, and policy checks.
5. Health endpoints and restart/dependency controls.
6. Contributor and security docs.

## Current Stretch Goals

The platform is production-capable and significantly hardened, with these remaining high-bar improvements:

1. ML risk model is trained and evaluated, but needs larger production-labeled data and online adaptation.
2. JWT RBAC is implemented, but external IdP integration (OIDC/SAML) is still a next step.
3. Canary analysis supports error-rate rollback; latency percentile-based rollback can improve signal quality.
4. Elasticsearch schema migration is automated via reindex; zero-downtime cluster-wide rolling migration remains manual.
5. Chaos matrix covers Redis, Elasticsearch, partition, and cascading failures; disk I/O fault injection is still pending.
6. Policy-as-code covers Compose, Kubernetes, and Terraform; runtime admission control is still open.

## Architecture

1. collector-go crawls configured domains over Tor and pushes envelopes (raw_html, source_url, traceparent) to Redis queue RAW_QUEUE_NAME.
2. sanitizer-rust strips HTML, enforces quality thresholds, and writes normalized payloads to SANITIZED_QUEUE_NAME.
3. brain-python extracts entities, scores risk, and indexes documents into Elasticsearch aliases.
4. auth-api issues and verifies JWT tokens and role claims (admin, analyst, viewer).
5. dashboard-ui serves operational status and access routes through the gateway.
6. Kibana and Neo4j are available for search and graph workflows.

## Key Implemented Capabilities

1. Metrics endpoints on collector, sanitizer, and brain services.
2. Runtime counters for processed, dropped, parse fallback, and failures.
3. Dead-letter queues for raw and sanitized stages plus replay tooling.
4. Trace context propagation across services.
5. OpenTelemetry Collector and Tempo integration.
6. Versioned Elasticsearch schema aliases and model-versioned documents.
7. Risk model regression evaluation and ML training pipeline.
8. JWT-based RBAC at the edge via gateway auth_request flow.
9. Blue-green rollout overlay and switch script.
10. Automated canary analysis with auto-rollback.
11. Automated Elasticsearch reindex migration script.
12. Chaos workflows for Redis, Elasticsearch, network partition, and cascading failures.
13. Policy workflows for Compose, Kubernetes, and Terraform.

## Repository Layout

- services/collector-go: Tor crawler and Redis producer.
- services/sanitizer-rust: HTML cleaning and text normalization.
- services/brain-python: enrichment, risk scoring, indexing.
- services/auth-api: JWT auth and role verification.
- services/dashboard-ui: web dashboard.
- infrastructure: nginx gateway, prometheus, grafana, tempo, otel collector configs.
- tests/chaos: reliability failure simulations.
- policy: OPA/Rego rules for compose, kubernetes, terraform.
- scripts: setup, health checks, canary rollout, migration, replay, teardown helpers.

## Quick Start

1. Copy .env.example to .env.
2. Review credentials and environment values.
3. Run: docker compose up --build
4. Open dashboard: http://localhost:3000
5. Open Kibana: http://localhost:5601
6. Open Neo4j Browser: http://localhost:7474

## Production Profile

Start production-style edge routing and auth:

1. Set strong values in .env:
- ELASTIC_PASSWORD
- NEO4J_PASSWORD
- AUTH_SECRET_KEY
- RBAC_ADMIN_PASSWORD
2. Run:
- docker compose -f docker-compose.yml -f docker-compose.prod.yml up --build -d
3. Validate endpoints:
- Gateway health: http://localhost:8080/health
- Brain health: http://localhost:8080/brain/health

### Authentication and RBAC

Gateway routes use JWT role checks via auth-api.

1. Login:
- curl -X POST http://localhost:8080/auth/login -H "Content-Type: application/json" -d '{"username":"admin","password":"admin-secret"}'
2. Use token:
- curl -H "Authorization: Bearer <token>" http://localhost:8080/
3. Create user (admin only):
- curl -X POST -H "Authorization: Bearer <token>" -H "Content-Type: application/json" http://localhost:8080/auth/users -d '{"username":"analyst1","password":"secret","role":"analyst"}'

Route access:

- /: viewer, analyst, admin
- /kibana/: analyst, admin
- /admin/: admin
- /health, /brain/health, /auth/login: public

## Observability Profile

Run with tracing and metrics stack:

- docker compose -f docker-compose.yml -f docker-compose.prod.yml -f docker-compose.observability.yml up -d --build

Endpoints:

- Grafana: http://localhost:3001
- Prometheus: http://localhost:9090
- Tempo: http://localhost:3200
- OTLP ingest: localhost:4317 (gRPC), localhost:4318 (HTTP)

## Deployment and Reliability Operations

Blue-green switch:

- ./scripts/switch_rollout.ps1 -Color green
- ./scripts/switch_rollout.ps1 -Color blue

Canary with auto-rollback:

- python scripts/canary_analysis.py --canary-duration 120 --error-threshold 0.05

Schema migration:

- python scripts/es_migrate.py --dry-run
- python scripts/es_migrate.py --auto

DLQ replay:

- ./scripts/replay_dlq.ps1 -SourceQueue sanitized_text_dlq -TargetQueue sanitized_text -Count 100

## Development Checks

- Go tests: cd services/collector-go && go test ./...
- Rust tests: cd services/sanitizer-rust && cargo test
- Brain tests: cd services/brain-python && python -m unittest discover -s src -p "test_*.py"
- Risk eval: cd services/brain-python && python eval_model.py
- Train ML model: cd services/brain-python && python train_risk_model.py
- UI build: cd services/dashboard-ui && npm install && npm run build
- Compose lint: docker compose -f docker-compose.yml -f docker-compose.prod.yml config

## Performance Gate

Performance gate assets:

1. Workflow: .github/workflows/performance-gate.yml
2. Load profile: tests/perf/gateway-health.js
3. Burn-rate evaluator: scripts/evaluate_burn_rate.py

Burn rate formula:

BR = ER / (1 - SLO)

Where:

- BR = burn rate
- ER = observed error rate
- SLO = target success objective

The gate fails when burn rate exceeds configured thresholds.

## Governance

1. Policy workflow: .github/workflows/policy.yml
2. Chaos workflow: .github/workflows/chaos.yml
3. Compose policy rules: policy/compose/deny.rego
4. Kubernetes policy rules: policy/kubernetes/deny.rego
5. Terraform policy rules: policy/terraform/deny.rego

## Notes

- Elasticsearch security is disabled in default local mode for speed.
- Root-level data directories are for local persistence only.
- Use managed secret storage and network segmentation before public exposure.
