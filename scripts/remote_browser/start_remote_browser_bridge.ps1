$ErrorActionPreference = "Stop"

$ScriptsDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$Root = Split-Path -Parent (Split-Path -Parent $ScriptsDir)
$BridgeDir = Join-Path $Root "tools\remote_browser_bridge"
$Requirements = Join-Path $BridgeDir "requirements.txt"
$Port = 8318
$ApiKeyFile = Join-Path $BridgeDir "bridge_api_key.txt"
$UvCacheDir = Join-Path $BridgeDir ".uv-cache"

$env:UV_CACHE_DIR = $UvCacheDir

if (-not (Test-Path $ApiKeyFile)) {
    $apiKey = [guid]::NewGuid().ToString("N") + [guid]::NewGuid().ToString("N")
    Set-Content -Path $ApiKeyFile -Value $apiKey -Encoding ascii
} else {
    $apiKey = (Get-Content $ApiKeyFile -Raw).Trim()
}

$env:FLOW2API_ROOT = $Root
$env:REMOTE_BROWSER_API_KEY = $apiKey
$env:REMOTE_BROWSER_CHROME_USER_DATA_DIR = Join-Path $env:LOCALAPPDATA "Google\Chrome\User Data"
$env:REMOTE_BROWSER_CHROME_PROFILE_NAME = "Default"
$env:REMOTE_BROWSER_BACKEND = "chrome_direct"
$env:REMOTE_BROWSER_CHROME_ATTACH_MODE = "attach"

Write-Host "Starting local Flow2API remote browser bridge..." -ForegroundColor Cyan
Write-Host "Bridge URL: http://127.0.0.1:$Port" -ForegroundColor Green
Write-Host "API Key: $apiKey" -ForegroundColor Green
Write-Host "Health: http://127.0.0.1:$Port/health" -ForegroundColor Gray
Write-Host "Chrome profile: $env:REMOTE_BROWSER_CHROME_PROFILE_NAME" -ForegroundColor Gray
Write-Host "Backend: $env:REMOTE_BROWSER_BACKEND" -ForegroundColor Gray
Write-Host "Attach mode: $env:REMOTE_BROWSER_CHROME_ATTACH_MODE" -ForegroundColor Gray

Set-Location $BridgeDir
uv run --with-requirements $Requirements uvicorn app:app --host 127.0.0.1 --port $Port

