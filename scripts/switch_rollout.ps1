param(
  [ValidateSet("blue", "green")]
  [string]$Color = "blue"
)

$target = if ($Color -eq "green") { "dashboard-ui-green:80" } else { "dashboard-ui:80" }
$env:ACTIVE_UI_UPSTREAM = $target

docker compose -f .\docker-compose.yml -f .\docker-compose.prod.yml -f .\docker-compose.rollout.yml up -d gateway

Write-Host "Gateway switched to $Color deployment ($target)."
