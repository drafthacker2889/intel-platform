# Security Policy

## Supported Scope

This project is currently a local-development intelligence pipeline. Treat all credentials as sensitive even in dev mode.

## Reporting a Vulnerability

1. Do not open public issues for security vulnerabilities.
2. Send a private report with reproduction steps, impact, and suggested fix.
3. Rotate any exposed credentials immediately.

## Hardening Priorities

- Enable Elasticsearch and Kibana authentication for non-local environments.
- Restrict exposed ports to trusted networks.
- Store secrets in a secret manager, not `.env`.
- Add signed image publishing and dependency scanning.
