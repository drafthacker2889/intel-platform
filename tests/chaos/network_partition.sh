#!/usr/bin/env bash
# Chaos test: Network partition between collector and Redis
# Simulates connectivity loss via iptables-style docker network disconnect
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT_DIR"

COMPOSE_FILES=(
  -f docker-compose.yml
  -f docker-compose.prod.yml
  -f docker-compose.observability.yml
)

cleanup() {
  # Reconnect before teardown
  docker network connect intel-platform_intel_net intel_collector 2>/dev/null || true
  docker compose "${COMPOSE_FILES[@]}" down -v
}
trap cleanup EXIT

docker compose "${COMPOSE_FILES[@]}" up -d --build

for _ in $(seq 1 90); do
  if curl -fsS http://localhost:8080/health >/dev/null 2>&1; then
    break
  fi
  sleep 2
done

echo "Stack healthy. Disconnecting collector from network..."
docker network disconnect intel-platform_intel_net intel_collector

sleep 8

echo "Health endpoints should still serve (collector isolated, others fine)..."
curl -fsS http://localhost:8080/health >/dev/null
curl -fsS http://localhost:8080/brain/health >/dev/null

echo "Reconnecting collector..."
docker network connect intel-platform_intel_net intel_collector

sleep 5

echo "Verifying full stack health..."
curl -fsS http://localhost:8080/health >/dev/null

echo chaos-network-partition-ok
