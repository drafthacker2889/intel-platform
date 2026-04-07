param(
  [string]$SourceQueue = "sanitized_text_dlq",
  [string]$TargetQueue = "sanitized_text",
  [int]$Count = 50,
  [string]$RedisContainer = "intel_queue"
)

if ($Count -le 0) {
  Write-Error "Count must be greater than zero"
  exit 1
}

for ($i = 0; $i -lt $Count; $i++) {
  $payload = docker exec $RedisContainer redis-cli RPOP $SourceQueue
  if (-not $payload -or $payload -eq "(nil)") {
    Write-Host "Replay complete. Queue '$SourceQueue' is empty or no more items available."
    break
  }

  docker exec $RedisContainer redis-cli LPUSH $TargetQueue "$payload" | Out-Null
}

Write-Host "DLQ replay attempted from '$SourceQueue' to '$TargetQueue' for up to $Count items."
