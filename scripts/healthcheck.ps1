param(
  [string]$BaseUrl = "http://localhost:8080"
)

$endpoints = @(
  "$BaseUrl/health",
  "$BaseUrl/brain/health"
)

foreach ($url in $endpoints) {
  try {
    $response = Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 10
    Write-Host "OK  $url  ($($response.StatusCode))"
  }
  catch {
    Write-Host "FAIL $url  $($_.Exception.Message)"
    exit 1
  }
}

Write-Host "All health checks passed"
