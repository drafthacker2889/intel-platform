$timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$backupRoot = Join-Path $PSScriptRoot "..\backups\$timestamp"
New-Item -ItemType Directory -Path $backupRoot -Force | Out-Null

Copy-Item -Recurse -Force "$PSScriptRoot\..\es_data" (Join-Path $backupRoot "es_data")
Copy-Item -Recurse -Force "$PSScriptRoot\..\neo4j_data" (Join-Path $backupRoot "neo4j_data")
Copy-Item -Recurse -Force "$PSScriptRoot\..\redis_data" (Join-Path $backupRoot "redis_data")

Write-Host "Backup complete: $backupRoot"
