# Deployment Strategy

## Production Edge

1. Gateway authentication is enforced in production mode.
2. Internal data services stay off public host ports in the production overlay.
3. Health routes remain available for operational checks.

## Blue-Green Rollout

1. Base service `dashboard-ui` acts as blue.
2. `dashboard-ui-green` is added by `docker-compose.rollout.yml`.
3. Gateway upstream selection is controlled by `ACTIVE_UI_UPSTREAM`.
4. Use `scripts/switch_rollout.ps1` to flip traffic.

## Rollback

1. Switch gateway back to blue.
2. Verify `/health` and `/brain/health`.
3. Remove the green candidate if needed.
