# Queue Contracts

## raw_html

Producer: collector-go
Payload:
{
  "raw_html": "string",
  "source_url": "https://...",
  "collected_at": "RFC3339 timestamp",
  "traceparent": "W3C traceparent"
}

SLO: non-empty `raw_html`, utf-8 compatible, trace context included.

## raw_html_dlq

Producer: collector-go / sanitizer-rust
Payload:
{
  "error": "string",
  "raw_payload": "string",
  "failed_at": "RFC3339 timestamp"
}

Consumer: replay tooling (`scripts/replay_dlq.ps1`)

## sanitized_text

Producer: sanitizer-rust
Payload:
{
  "text": "string",
  "length": 12345,
  "source_url": "https://...",
  "traceparent": "W3C traceparent"
}

Consumer: brain-python
Contract rule: if JSON parse fails, treat payload as plain text for backward compatibility.

## sanitized_text_dlq

Producer: brain-python / sanitizer-rust
Payload:
{
  "error": "string",
  "payload": "string",
  "failed_at": "RFC3339 timestamp",
  "traceparent": "W3C traceparent"
}

Consumer: replay tooling (`scripts/replay_dlq.ps1`)
