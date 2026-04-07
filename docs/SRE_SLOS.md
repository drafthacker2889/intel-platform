# SLOs

## Availability SLO

1. Pipeline availability: 99.9% monthly for collector, sanitizer, brain.
2. Dashboard availability: 99.95% monthly via gateway.

## Latency SLO

1. P95 end-to-end ingest to index under 120 seconds.
2. P95 UI response under 350 ms for dashboard route.

## Error Budget Policy

1. If monthly budget burn exceeds 50% in first 10 days, freeze feature releases.
2. Prioritize reliability and rollback automation until burn stabilizes.
