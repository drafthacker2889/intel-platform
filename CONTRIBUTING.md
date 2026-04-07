# Contributing

## Branching

1. Create a feature branch from `main`.
2. Keep commits focused by service or concern.
3. Open a pull request with test evidence.

## Pull Request Checklist

1. `docker compose config` succeeds.
2. Service-level tests pass.
3. No credentials are committed.
4. Docs and `.env.example` are updated for config changes.

## Coding Guidelines

- Prefer environment variables over hardcoded connection details.
- Add tests for parser or sanitizer behavior changes.
- Keep queue payloads backwards-compatible when possible.
