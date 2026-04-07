# Operations Runbook

## Service Health Endpoints

1. Gateway: /health
2. Brain: /brain/health
3. Collector: http://collector-go:8081/health (internal)
4. UI: /health

## Incident Triage

1. Validate compose health: docker compose ps
2. Inspect logs: docker compose logs --tail=200 <service>
3. Confirm queue movement in Redis.
4. Confirm indexing activity in Elasticsearch.

## Recovery

1. Restart unhealthy service only.
2. If queue backlog is corrupted, snapshot and drain queue.
3. Restore from daily volume backup when corruption is detected.
