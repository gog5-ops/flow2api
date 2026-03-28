$ErrorActionPreference = "Stop"

$GcloudCmd = "C:\Program Files (x86)\Google\Cloud SDK\google-cloud-sdk\bin\gcloud.cmd"
$Project = "sfanime"
$Zone = "us-central1-a"
$Instance = "grok2api-vm"
$LocalPort = 8318
$RemotePort = 8318

Write-Host "Starting reverse tunnel for local remote-browser bridge..." -ForegroundColor Cyan
Write-Host "Local service: 127.0.0.1:$LocalPort" -ForegroundColor Green
Write-Host "VM listener request: 0.0.0.0:$RemotePort" -ForegroundColor Green

& $GcloudCmd compute ssh $Instance --zone=$Zone --project=$Project -- -N -R "0.0.0.0:$RemotePort`:127.0.0.1:$LocalPort"
