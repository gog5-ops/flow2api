$ErrorActionPreference = "Stop"

$ChromeExe = "C:\Program Files\Google\Chrome\Application\chrome.exe"
$DebugPort = 9224

if (-not (Test-Path $ChromeExe)) {
    throw "Chrome executable not found: $ChromeExe"
}

Write-Host "Starting real Chrome Default profile with remote debugging..." -ForegroundColor Cyan
Write-Host "Chrome: $ChromeExe" -ForegroundColor Green
Write-Host "Profile: Default" -ForegroundColor Green
Write-Host "Debug URL: http://127.0.0.1:$DebugPort" -ForegroundColor Green

Get-Process chrome -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
Start-Sleep -Seconds 2

Start-Process -FilePath $ChromeExe -ArgumentList @(
    "--profile-directory=Default",
    "--remote-debugging-port=$DebugPort",
    "--remote-allow-origins=*",
    "--new-window",
    "https://labs.google/fx/tools/flow"
)
