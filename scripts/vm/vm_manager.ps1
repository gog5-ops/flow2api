# d:\aitools\gcpvm\vm_manager.ps1
# GCVM VM 统一管理脚本
# 用法: .\vm_manager.ps1 -Action <ActionName>

param (
    [Parameter(Mandatory=$true)]
    [ValidateSet("Discover", "Status", "CPU", "ChromeDebugInfo", "ChromeDebugAccess", "StartChromeDebugTunnel", "SetupHeadedChromeRemote", "StartChromeWebTunnel", "DeployFlow2APITokenUpdater", "CheckFlow2APITokenSync", "InspectFlow2APITokenState", "SyncFlow2APITokenManager", "SyncFlow2APIProjectBoundRuntime", "RefreshFlow2APIToken", "EnableFlow2APITokens", "SelectFlow2APIToken", "SetFlow2APIPersonalMode", "SetFlow2APIRemoteBrowserMode", "SetupRemoteBrowserHostProxy", "DisableRemoteBrowserHostProxy", "CheckRemoteBrowserTunnelListener", "CheckRemoteBrowserHostProxyListener", "CheckRemoteBrowserBridgeHealth", "CheckRemoteBrowserBridgeConfig", "CheckRemoteBrowserBridge", "SmokeTestFlow2API", "SmokeTestFlow2APIImg2Img", "SmokeTestFlow2APIVideo", "SmokeTestFlow2APIMatrix", "GenerateFlow2APITreeImages", "GenerateFlow2APICatAlienVideo", "HTTPCheck", "CheckFlow2API", "CheckFlow2APIEgress", "ConfigureFlow2APIResidentialProxy", "GetFlow2APIPluginConfig", "GetFlow2APIProviderConfig", "Connect", "InstallChrome", "SetupProxy", "DeployOpenClaw", "StartOpenClaw", "FixUIAuth", "SetupBackup", "BackupManual", "DeploySub2API", "DeployFlow2API", "RestartGrok", "RestartSub")]
    [string]$Action,

    [string]$Project = "sfanime",
    [string]$Zone,
    [string]$Instance = "grok2api-vm",
    [string]$Flow2APIRepo = "https://github.com/gog5-ops/flow2api.git",
    [string]$Flow2APIDir = "/opt/flow2api",
    [string]$ProjectId = "",
    [string]$ReferenceImagePath = "d:\aitools\output\flow2api\tree-1.png",
    [string]$ResidentialHttpProxy = "http://127.0.0.1:10809",
    [string]$Flow2APIResidentialHttpProxy = "http://172.21.0.1:10809",
    [string]$Flow2APIRemoteBrowserBaseUrl = "",
    [int]$LocalChromeDebugPort = 9223,
    [int]$LocalChromeWebPort = 6081,
    [string]$TargetEmail = "",
    [string]$DisableOthers = "true"
)

# --- 预处理: 若未显式提供 Zone，则自动发现实例所在区 ---
function Resolve-VMZone {
    if ($Zone) {
        return $Zone
    }

    Write-Host "Discovering zone for $Instance in project $Project..." -ForegroundColor DarkCyan
    $resolvedZone = gcloud compute instances list `
        --project=$Project `
        --filter="name=('${Instance}')" `
        --format="value(zone.basename())"

    if (-not $resolvedZone) {
        throw "Unable to determine zone for instance '$Instance' in project '$Project'."
    }

    $script:Zone = ($resolvedZone | Select-Object -First 1).Trim()
    Write-Host "Resolved zone: $script:Zone" -ForegroundColor Green
    return $script:Zone
}

# --- 核心 SSH 执行函数 ---
function Invoke-VMCommand {
    param ([string]$Command)
    Resolve-VMZone | Out-Null
    Write-Host "Executing on VM: $Command" -ForegroundColor Gray
    gcloud compute ssh $Instance --zone=$Zone --project=$Project --command="$Command"
}

function Invoke-VMInteractiveSSH {
    Resolve-VMZone | Out-Null
    Write-Host "Connecting to $Instance in $Zone..." -ForegroundColor Cyan
    gcloud compute ssh $Instance --zone=$Zone --project=$Project
}

function Show-VMDiscovery {
    $resolvedZone = Resolve-VMZone
    gcloud compute instances list `
        --project=$Project `
        --filter="name=('${Instance}')" `
        --format="table(name,zone.basename(),status,networkInterfaces[0].networkIP,networkInterfaces[0].accessConfigs[0].natIP)"
}

function Get-VMNatIP {
    Resolve-VMZone | Out-Null
    $natIp = gcloud compute instances list `
        --project=$Project `
        --filter="name=('${Instance}')" `
        --format="value(networkInterfaces[0].accessConfigs[0].natIP)"
    if (-not $natIp) {
        throw "Unable to determine NAT IP for instance '$Instance'."
    }
    return ($natIp | Select-Object -First 1).Trim()
}

function Get-VMInternalIP {
    Resolve-VMZone | Out-Null
    $internalIp = gcloud compute instances list `
        --project=$Project `
        --filter="name=('${Instance}')" `
        --format="value(networkInterfaces[0].networkIP)"
    if (-not $internalIp) {
        throw "Unable to determine internal IP for instance '$Instance'."
    }
    return ($internalIp | Select-Object -First 1).Trim()
}

# --- 1. 查看状态 ---
function Get-VMStatus {
    Write-Host "--- Instance ---" -ForegroundColor Cyan
    Invoke-VMCommand "hostname && whoami && uptime"

    Write-Host "--- Docker Containers ---" -ForegroundColor Cyan
    Invoke-VMCommand "sudo docker ps --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'"
    
    Write-Host "`n--- Systemd Services (V2Ray/OpenClaw) ---" -ForegroundColor Cyan
    Invoke-VMCommand "sudo systemctl status v2ray openclaw --no-pager | grep -E 'Active:|Loaded:'"
    
    Write-Host "`n--- System Processes (Proxy/Chrome) ---" -ForegroundColor Cyan
    Invoke-VMCommand "ps aux | grep -E 'chrome|v2ray|gost' | grep -v grep || echo 'None running.'"
    
    Write-Host "`n--- Crontab (Backup) ---" -ForegroundColor Cyan
    Invoke-VMCommand "crontab -l || echo 'No crontab found.'"

    Write-Host "`n--- Storage (/opt) ---" -ForegroundColor Cyan
    Invoke-VMCommand "df -h /opt"
}

function Get-VMCPU {
    Write-Host "--- CPU Summary ---" -ForegroundColor Cyan
    Invoke-VMCommand "nproc && echo '---' && uptime && echo '---' && top -bn1 | head -n 5"

    Write-Host "`n--- Top CPU Processes ---" -ForegroundColor Cyan
    Invoke-VMCommand "ps -eo pid,ppid,cmd,%mem,%cpu --sort=-%cpu | head -n 12"
}

function Get-ChromeDebugInfo {
    Write-Host "--- Chrome Service ---" -ForegroundColor Cyan
    Invoke-VMCommand "sudo systemctl status google-chrome --no-pager | grep -E 'Active:|Loaded:'"

    Write-Host "`n--- Chrome Debug Version ---" -ForegroundColor Cyan
    Invoke-VMCommand "curl -fsS http://127.0.0.1:9222/json/version"

    Write-Host "`n--- Chrome Debug Targets ---" -ForegroundColor Cyan
    Invoke-VMCommand "curl -fsS http://127.0.0.1:9222/json/list | head -c 1200 && echo"
}

function Get-ChromeDebugAccess {
    Resolve-VMZone | Out-Null
    Write-Host "--- VM 9222 Listener ---" -ForegroundColor Cyan
    Invoke-VMCommand "sudo ss -lntp | grep 9222 || echo 'No 9222 listener'"

    Write-Host "`n--- Instance Tags ---" -ForegroundColor Cyan
    gcloud compute instances describe $Instance --zone=$Zone --project=$Project --format="value(tags.items)"

    Write-Host "`n--- Firewall Rules with 9222 ---" -ForegroundColor Cyan
    gcloud compute firewall-rules list --project=$Project --filter="allowed.tcp:9222" --format="table(name,sourceRanges.list():label=SRC,targetTags.list():label=TAGS,allowed[].map().firewall_rule().list():label=ALLOW)"
}

function Start-ChromeDebugTunnel {
    Resolve-VMZone | Out-Null
    Write-Host "Starting local tunnel 127.0.0.1:$LocalChromeDebugPort -> ${Instance}:127.0.0.1:9222" -ForegroundColor Yellow
    $gcloudCmd = "C:\Program Files (x86)\Google\Cloud SDK\google-cloud-sdk\bin\gcloud.cmd"
    $stdoutFile = Join-Path $env:TEMP "vm_chrome_tunnel_stdout.log"
    $stderrFile = Join-Path $env:TEMP "vm_chrome_tunnel_stderr.log"

    $existing = Get-NetTCPConnection -LocalAddress 127.0.0.1 -LocalPort $LocalChromeDebugPort -ErrorAction SilentlyContinue
    if ($existing) {
        Write-Host "Local port $LocalChromeDebugPort is already in use. Reusing existing listener." -ForegroundColor Green
    } else {
        $args = @(
            "compute",
            "ssh",
            $Instance,
            "--zone=$Zone",
            "--project=$Project",
            "--",
            "-N",
            "-L",
            "127.0.0.1:$LocalChromeDebugPort`:127.0.0.1:9222"
        )
        $proc = Start-Process -FilePath $gcloudCmd -ArgumentList $args -WindowStyle Hidden -RedirectStandardOutput $stdoutFile -RedirectStandardError $stderrFile -PassThru
        Start-Sleep -Seconds 5
        Write-Host "Tunnel process started. PID: $($proc.Id)" -ForegroundColor Green
    }

    Write-Host "`n--- Local Chrome Debug Version ---" -ForegroundColor Cyan
    try {
        $version = Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:$LocalChromeDebugPort/json/version" -TimeoutSec 5
        $version.Content
    } catch {
        Write-Warning "Failed to reach local tunnel on port ${LocalChromeDebugPort}: $($_.Exception.Message)"

        $natIp = Get-VMNatIP
        Write-Host "`n--- Direct Public Chrome Debug Version ---" -ForegroundColor Cyan
        try {
            $publicVersion = Invoke-WebRequest -UseBasicParsing -Uri "http://$natIp`:9222/json/version" -TimeoutSec 5
            $publicVersion.Content
            Write-Host "`nPublic CDP endpoint is reachable from this machine." -ForegroundColor Green
            Write-Host "Use these URLs directly if you prefer:" -ForegroundColor Cyan
            Write-Host "  http://$natIp`:9222/json/version"
            Write-Host "  http://$natIp`:9222/json/list"
            Write-Host "  chrome://inspect/#devices  (add $natIp`:9222)" -ForegroundColor Gray
        } catch {
            if (Test-Path $stderrFile) {
                Write-Host "`n--- Tunnel stderr tail ---" -ForegroundColor Cyan
                Get-Content $stderrFile -Tail 20
            }
            Write-Error "Public CDP endpoint is also unreachable: $($_.Exception.Message)"
        }
    }

    Write-Host "`nYou can now use these local URLs:" -ForegroundColor Cyan
    Write-Host "  http://127.0.0.1:$LocalChromeDebugPort/json/version"
    Write-Host "  http://127.0.0.1:$LocalChromeDebugPort/json/list"
    Write-Host "  chrome://inspect/#devices  (add 127.0.0.1:$LocalChromeDebugPort)" -ForegroundColor Gray
}

function Deploy-Flow2APITokenUpdater {
    Write-Host "Deploying Flow2API-Token-Updater to VM..." -ForegroundColor Yellow
    Resolve-VMZone | Out-Null
    Invoke-VMCommand "sudo rm -rf /opt/Flow2API-Token-Updater && sudo mkdir -p /opt/Flow2API-Token-Updater && sudo chown -R `$(id -un):`$(id -gn) /opt/Flow2API-Token-Updater"
    gcloud compute scp --recurse "d:\aitools\Flow2API-Token-Updater\*" "${Instance}:/opt/Flow2API-Token-Updater" --zone=$Zone --project=$Project
    gcloud compute scp "d:\aitools\gcpvm\flow2api_prepare_token_updater_vm.py" "${Instance}:/tmp/flow2api_prepare_token_updater_vm.py" --zone=$Zone --project=$Project
    Invoke-VMCommand "python3 /tmp/flow2api_prepare_token_updater_vm.py http://127.0.0.1:38000 admin admin /opt/Flow2API-Token-Updater 360"
    Invoke-VMCommand "ls -la /opt/Flow2API-Token-Updater | head -n 20"
}

function Setup-HeadedChromeRemote {
    Write-Host "Setting up headed Chrome remote stack on VM..." -ForegroundColor Yellow
    Resolve-VMZone | Out-Null
    gcloud compute scp "d:\aitools\gcpvm\setup_headed_chrome_remote.sh" "${Instance}:/tmp/setup_headed_chrome_remote.sh" --zone=$Zone --project=$Project
    Invoke-VMCommand "chmod +x /tmp/setup_headed_chrome_remote.sh && sudo bash /tmp/setup_headed_chrome_remote.sh"
}

function Start-ChromeWebTunnel {
    Resolve-VMZone | Out-Null
    Write-Host "Starting local noVNC tunnel 127.0.0.1:$LocalChromeWebPort -> ${Instance}:127.0.0.1:6080" -ForegroundColor Yellow
    $gcloudCmd = "C:\Program Files (x86)\Google\Cloud SDK\google-cloud-sdk\bin\gcloud.cmd"
    $stdoutFile = Join-Path $env:TEMP "vm_chrome_web_tunnel_stdout.log"
    $stderrFile = Join-Path $env:TEMP "vm_chrome_web_tunnel_stderr.log"

    $existing = Get-NetTCPConnection -LocalAddress 127.0.0.1 -LocalPort $LocalChromeWebPort -ErrorAction SilentlyContinue
    if ($existing) {
        Write-Host "Local web port $LocalChromeWebPort is already in use. Reusing existing listener." -ForegroundColor Green
    } else {
        $args = @(
            "compute",
            "ssh",
            $Instance,
            "--zone=$Zone",
            "--project=$Project",
            "--",
            "-N",
            "-L",
            "127.0.0.1:$LocalChromeWebPort`:127.0.0.1:6080"
        )
        $proc = Start-Process -FilePath $gcloudCmd -ArgumentList $args -WindowStyle Hidden -RedirectStandardOutput $stdoutFile -RedirectStandardError $stderrFile -PassThru
        Start-Sleep -Seconds 5
        Write-Host "Web tunnel process started. PID: $($proc.Id)" -ForegroundColor Green
    }

    try {
        $resp = Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:$LocalChromeWebPort/vnc.html" -TimeoutSec 5
        Write-Host "noVNC is reachable locally." -ForegroundColor Green
        Write-Host "Open this URL in your local browser:" -ForegroundColor Cyan
        Write-Host "  http://127.0.0.1:$LocalChromeWebPort/vnc.html"
    } catch {
        if (Test-Path $stderrFile) {
            Write-Host "`n--- Web tunnel stderr tail ---" -ForegroundColor Cyan
            Get-Content $stderrFile -Tail 20
        }
        Write-Error "Failed to reach local noVNC tunnel on port ${LocalChromeWebPort}: $($_.Exception.Message)"
    }
}

function Invoke-HTTPCheck {
    $probeCommand = @'
echo "[grok2api]"
curl -fsS http://127.0.0.1:8000/v1/models | head -c 400
echo
echo
echo "[sub2api]"
curl -fsS http://127.0.0.1:8001/ | head -c 400
echo
'@
    Invoke-VMCommand $probeCommand.Trim()
}

function Check-Flow2API {
    Write-Host "--- Flow2API Container ---" -ForegroundColor Cyan
    Invoke-VMCommand "sudo docker ps --filter name=flow2api --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'"

    Write-Host "`n--- Flow2API HTTP Probe ---" -ForegroundColor Cyan
    Invoke-VMCommand "curl -fsS http://127.0.0.1:38000/ | head -c 300 && echo"
}

function Check-Flow2APIEgress {
    Write-Host "--- Host Public IP ---" -ForegroundColor Cyan
    Invoke-VMCommand "curl -fsS https://api.ipify.org && echo"

    Write-Host "`n--- Flow2API Container Public IP ---" -ForegroundColor Cyan
    Invoke-VMCommand "sudo docker run --rm --network container:flow2api curlimages/curl:8.12.1 -sS https://api.ipify.org && echo"

    Write-Host "`n--- flow2api setting.toml [proxy] ---" -ForegroundColor Cyan
    Invoke-VMCommand "sudo awk '/^\[proxy\]/{flag=1; print; next} /^\[/{if(flag){exit}} flag{print}' /opt/flow2api/config/setting.toml"

    Write-Host "`n--- flow2api DB proxy/captcha/token proxy ---" -ForegroundColor Cyan
    Invoke-VMCommand "if [ -f /opt/flow2api/data/flow.db ]; then echo '[proxy_config]'; sudo docker run --rm -v /opt/flow2api/data:/data keinos/sqlite3:latest sqlite3 /data/flow.db 'select enabled,proxy_url,media_proxy_enabled,media_proxy_url from proxy_config limit 1;'; else echo 'flow.db not found'; fi"
    Invoke-VMCommand "if [ -f /opt/flow2api/data/flow.db ]; then echo '[captcha_config]'; sudo docker run --rm -v /opt/flow2api/data:/data keinos/sqlite3:latest sqlite3 /data/flow.db 'select captcha_method,browser_proxy_enabled,browser_proxy_url from captcha_config limit 1;'; fi"
    Invoke-VMCommand "if [ -f /opt/flow2api/data/flow.db ]; then echo '[tokens_count]'; sudo docker run --rm -v /opt/flow2api/data:/data keinos/sqlite3:latest sqlite3 /data/flow.db 'select count(*) from tokens;'; echo '[tokens_preview]'; sudo docker run --rm -v /opt/flow2api/data:/data keinos/sqlite3:latest sqlite3 /data/flow.db 'select id,email,is_active,captcha_proxy_url from tokens order by id limit 20;'; fi"

    Write-Host "`n--- Public IP ASN/Org (Host) ---" -ForegroundColor Cyan
    Invoke-VMCommand "curl -fsS https://ipinfo.io/json | head -c 600 && echo"
}

function Configure-Flow2APIResidentialProxy {
    Write-Host "Configuring Flow2API to use the residential proxy..." -ForegroundColor Yellow
    Invoke-VMCommand "test -f $Flow2APIDir/data/flow.db"
    gcloud compute scp "d:\aitools\gcpvm\flow2api_set_proxy_via_admin.py" "${Instance}:/tmp/flow2api_set_proxy_via_admin.py" --zone=$Zone --project=$Project
    Invoke-VMCommand "python3 /tmp/flow2api_set_proxy_via_admin.py http://127.0.0.1:38000 admin admin $Flow2APIResidentialHttpProxy"
    Invoke-VMCommand "echo '[host_proxy_exit_ip]' && curl -fsS -x $ResidentialHttpProxy https://api.ipify.org && echo"
    Invoke-VMCommand "echo '[container_proxy_exit_ip]' && sudo docker run --rm --network container:flow2api curlimages/curl:8.12.1 -x $Flow2APIResidentialHttpProxy -sS https://api.ipify.org && echo"
}

function Get-Flow2APIPluginConfig {
    Write-Host "Fetching Flow2API plugin config..." -ForegroundColor Yellow
    Resolve-VMZone | Out-Null
    gcloud compute scp "d:\aitools\gcpvm\flow2api_get_plugin_config.py" "${Instance}:/tmp/flow2api_get_plugin_config.py" --zone=$Zone --project=$Project
    Invoke-VMCommand "python3 /tmp/flow2api_get_plugin_config.py http://127.0.0.1:38000 admin admin"
}

function Get-Flow2APIProviderConfig {
    Write-Host "Fetching Flow2API provider config..." -ForegroundColor Yellow
    Resolve-VMZone | Out-Null
    $natIp = Get-VMNatIP
    $publicBaseUrl = "http://${natIp}:38000"
    gcloud compute scp "d:\aitools\flow2api\scripts\vm\flow2api_get_provider_config.py" "${Instance}:/tmp/flow2api_get_provider_config.py" --zone=$Zone --project=$Project
    Invoke-VMCommand "cd $Flow2APIDir && python3 /tmp/flow2api_get_provider_config.py http://127.0.0.1:38000 admin admin $publicBaseUrl"
}

function Check-Flow2APITokenSync {
    Write-Host "Checking Flow2API token sync status..." -ForegroundColor Yellow
    Resolve-VMZone | Out-Null
    gcloud compute scp "d:\aitools\gcpvm\flow2api_check_token_sync.py" "${Instance}:/tmp/flow2api_check_token_sync.py" --zone=$Zone --project=$Project
    Invoke-VMCommand "python3 /tmp/flow2api_check_token_sync.py http://127.0.0.1:38000 admin admin"
}

function Inspect-Flow2APITokenState {
    Write-Host "Inspecting detailed Flow2API token state..." -ForegroundColor Yellow
    Resolve-VMZone | Out-Null
    gcloud compute scp "d:\aitools\gcpvm\flow2api_inspect_token_state.py" "${Instance}:/tmp/flow2api_inspect_token_state.py" --zone=$Zone --project=$Project
    Invoke-VMCommand "python3 /tmp/flow2api_inspect_token_state.py http://127.0.0.1:38000 admin admin /opt/flow2api/data/flow.db"
}

function Sync-Flow2APITokenManager {
    Write-Host "Syncing local token_manager.py to VM Flow2API app..." -ForegroundColor Yellow
    Resolve-VMZone | Out-Null
    gcloud compute scp "d:\aitools\flow2api\src\services\token_manager.py" "${Instance}:/tmp/token_manager.py" --zone=$Zone --project=$Project
    Invoke-VMCommand "sudo docker cp /tmp/token_manager.py flow2api:/app/src/services/token_manager.py && sudo docker restart flow2api"
}

function Sync-Flow2APIProjectBoundRuntime {
    Write-Host "Syncing project-bound Flow2API runtime files to VM container..." -ForegroundColor Yellow
    Resolve-VMZone | Out-Null
    gcloud compute scp "d:\aitools\flow2api\src\services\token_manager.py" "${Instance}:/tmp/token_manager.py" --zone=$Zone --project=$Project
    gcloud compute scp "d:\aitools\flow2api\src\core\models.py" "${Instance}:/tmp/models.py" --zone=$Zone --project=$Project
    gcloud compute scp "d:\aitools\flow2api\src\api\routes.py" "${Instance}:/tmp/routes.py" --zone=$Zone --project=$Project
    gcloud compute scp "d:\aitools\flow2api\src\services\generation_handler.py" "${Instance}:/tmp/generation_handler.py" --zone=$Zone --project=$Project
    Invoke-VMCommand "sudo docker cp /tmp/token_manager.py flow2api:/app/src/services/token_manager.py && sudo docker cp /tmp/models.py flow2api:/app/src/core/models.py && sudo docker cp /tmp/routes.py flow2api:/app/src/api/routes.py && sudo docker cp /tmp/generation_handler.py flow2api:/app/src/services/generation_handler.py && sudo docker restart flow2api"
}

function Refresh-Flow2APIToken {
    if (-not $TargetEmail) {
        throw "TargetEmail is required for RefreshFlow2APIToken."
    }
    Write-Host "Refreshing Flow2API token via stored ST: $TargetEmail" -ForegroundColor Yellow
    Resolve-VMZone | Out-Null
    gcloud compute scp "d:\aitools\gcpvm\flow2api_refresh_token.py" "${Instance}:/tmp/flow2api_refresh_token.py" --zone=$Zone --project=$Project
    Invoke-VMCommand "python3 /tmp/flow2api_refresh_token.py http://127.0.0.1:38000 admin admin '$TargetEmail'"
}

function Enable-Flow2APITokens {
    Write-Host "Enabling Flow2API tokens..." -ForegroundColor Yellow
    Resolve-VMZone | Out-Null
    gcloud compute scp "d:\aitools\gcpvm\flow2api_enable_tokens.py" "${Instance}:/tmp/flow2api_enable_tokens.py" --zone=$Zone --project=$Project
    Invoke-VMCommand "python3 /tmp/flow2api_enable_tokens.py http://127.0.0.1:38000 admin admin"
}

function Select-Flow2APIToken {
    if (-not $TargetEmail) {
        throw "TargetEmail is required for SelectFlow2APIToken."
    }
    Write-Host "Selecting Flow2API token: $TargetEmail" -ForegroundColor Yellow
    Resolve-VMZone | Out-Null
    gcloud compute scp "d:\aitools\gcpvm\flow2api_select_token.py" "${Instance}:/tmp/flow2api_select_token.py" --zone=$Zone --project=$Project
    Invoke-VMCommand "python3 /tmp/flow2api_select_token.py http://127.0.0.1:38000 admin admin '$TargetEmail' '$DisableOthers'"
}

function Smoke-TestFlow2API {
    Write-Host "Running Flow2API smoke test..." -ForegroundColor Yellow
    Resolve-VMZone | Out-Null
    gcloud compute scp "d:\aitools\gcpvm\flow2api_smoke_test.py" "${Instance}:/tmp/flow2api_smoke_test.py" --zone=$Zone --project=$Project
    Invoke-VMCommand "python3 /tmp/flow2api_smoke_test.py http://127.0.0.1:38000 admin admin '$ProjectId'"
}

function Smoke-TestFlow2APIImg2Img {
    Write-Host "Running Flow2API img2img smoke test..." -ForegroundColor Yellow
    Resolve-VMZone | Out-Null
    gcloud compute scp "d:\aitools\gcpvm\flow2api_img2img_smoke_test.py" "${Instance}:/tmp/flow2api_img2img_smoke_test.py" --zone=$Zone --project=$Project
    gcloud compute scp "$ReferenceImagePath" "${Instance}:/tmp/flow2api_img2img_ref.png" --zone=$Zone --project=$Project
    Invoke-VMCommand "python3 /tmp/flow2api_img2img_smoke_test.py http://127.0.0.1:38000 admin admin '$ProjectId' /tmp/flow2api_img2img_ref.png"
}

function Smoke-TestFlow2APIVideo {
    Write-Host "Running Flow2API video smoke test..." -ForegroundColor Yellow
    Resolve-VMZone | Out-Null
    gcloud compute scp "d:\aitools\gcpvm\flow2api_video_smoke_test.py" "${Instance}:/tmp/flow2api_video_smoke_test.py" --zone=$Zone --project=$Project
    Invoke-VMCommand "python3 /tmp/flow2api_video_smoke_test.py http://127.0.0.1:38000 admin admin"
}

function Smoke-TestFlow2APIMatrix {
    Write-Host "Running Flow2API request-mode matrix smoke test..." -ForegroundColor Yellow
    Resolve-VMZone | Out-Null
    gcloud compute scp "d:\aitools\flow2api\scripts\vm\flow2api_matrix_smoke_test.py" "${Instance}:/tmp/flow2api_matrix_smoke_test.py" --zone=$Zone --project=$Project
    gcloud compute scp "$ReferenceImagePath" "${Instance}:/tmp/flow2api_matrix_ref.png" --zone=$Zone --project=$Project
    Invoke-VMCommand "python3 /tmp/flow2api_matrix_smoke_test.py http://127.0.0.1:38000 admin admin '$ProjectId' /tmp/flow2api_matrix_ref.png"
}

function Generate-Flow2APITreeImages {
    Write-Host "Generating 3 tree images via Flow2API..." -ForegroundColor Yellow
    Resolve-VMZone | Out-Null
    gcloud compute scp "d:\aitools\gcpvm\flow2api_generate_images.py" "${Instance}:/tmp/flow2api_generate_images.py" --zone=$Zone --project=$Project
    Invoke-VMCommand "python3 /tmp/flow2api_generate_images.py http://127.0.0.1:38000 admin admin 3 '一棵巨大的大树，细节丰富，摄影感强，白天自然光。' 'gemini-3.1-flash-image-square' '/tmp/flow2api_tree_images'"
    gcloud compute scp "${Instance}:/tmp/flow2api_tree_images/*" "d:\aitools\output\flow2api\" --zone=$Zone --project=$Project
}

function Generate-Flow2APICatAlienVideo {
    Write-Host "Generating cat-meets-alien video via Flow2API..." -ForegroundColor Yellow
    Resolve-VMZone | Out-Null
    gcloud compute scp "d:\aitools\gcpvm\flow2api_generate_video.py" "${Instance}:/tmp/flow2api_generate_video.py" --zone=$Zone --project=$Project
    Invoke-VMCommand "python3 /tmp/flow2api_generate_video.py http://127.0.0.1:38000 admin admin '一只猫在夜晚的草地上遇到一个发光的外星人，电影感镜头，真实摄影风格，氛围神秘但可爱。' 'veo_3_1_t2v_fast_landscape' '/tmp/flow2api_video_output'"
    gcloud compute scp "${Instance}:/tmp/flow2api_video_output/*" "d:\aitools\output\flow2api\" --zone=$Zone --project=$Project
}

function Set-Flow2APIPersonalMode {
    Write-Host "Switching Flow2API captcha mode to personal..." -ForegroundColor Yellow
    Resolve-VMZone | Out-Null
    gcloud compute scp "d:\aitools\gcpvm\flow2api_set_captcha_mode.py" "${Instance}:/tmp/flow2api_set_captcha_mode.py" --zone=$Zone --project=$Project
    Invoke-VMCommand "python3 /tmp/flow2api_set_captcha_mode.py http://127.0.0.1:38000 admin admin personal"
}

function Set-Flow2APIRemoteBrowserMode {
    Write-Host "Switching Flow2API captcha mode to remote_browser..." -ForegroundColor Yellow
    Resolve-VMZone | Out-Null
    $remoteBrowserBaseUrl = $Flow2APIRemoteBrowserBaseUrl
    if (-not $remoteBrowserBaseUrl) {
        $internalIp = Get-VMInternalIP
        $remoteBrowserBaseUrl = "http://${internalIp}:8319"
    }
    $remoteBrowserApiKey = $env:FLOW2API_REMOTE_BROWSER_API_KEY
    if (-not $remoteBrowserApiKey) {
        $localApiKeyFiles = @(
            "d:\aitools\flow2api\tools\remote_browser_bridge\bridge_api_key.txt",
            "d:\aitools\flow2api_remote_browser_bridge\bridge_api_key.txt"
        )
        foreach ($localApiKeyFile in $localApiKeyFiles) {
            if (Test-Path $localApiKeyFile) {
                $remoteBrowserApiKey = (Get-Content $localApiKeyFile -Raw).Trim()
                if ($remoteBrowserApiKey) { break }
            }
        }
    }
    if (-not $remoteBrowserApiKey) {
        throw "FLOW2API_REMOTE_BROWSER_API_KEY is not set and local bridge_api_key.txt was not found."
    }
    gcloud compute scp "d:\aitools\gcpvm\flow2api_set_remote_browser_mode.py" "${Instance}:/tmp/flow2api_set_remote_browser_mode.py" --zone=$Zone --project=$Project
    Invoke-VMCommand "python3 /tmp/flow2api_set_remote_browser_mode.py http://127.0.0.1:38000 admin admin $remoteBrowserBaseUrl $remoteBrowserApiKey 120"
}

function Setup-RemoteBrowserHostProxy {
    Write-Host "Setting up remote-browser host proxy on VM..." -ForegroundColor Yellow
    Resolve-VMZone | Out-Null
    gcloud compute scp "d:\aitools\gcpvm\setup_remote_browser_host_proxy.sh" "${Instance}:/tmp/setup_remote_browser_host_proxy.sh" --zone=$Zone --project=$Project
    Invoke-VMCommand "chmod +x /tmp/setup_remote_browser_host_proxy.sh && sudo bash /tmp/setup_remote_browser_host_proxy.sh"
}

function Disable-RemoteBrowserHostProxy {
    Write-Host "Disabling remote-browser host proxy on VM..." -ForegroundColor Yellow
    Resolve-VMZone | Out-Null
    Invoke-VMCommand "sudo systemctl stop remote-browser-host-proxy || true && sudo systemctl disable remote-browser-host-proxy || true"
}

function Check-RemoteBrowserTunnelListener {
    Write-Host "Checking remote-browser tunnel listener on VM..." -ForegroundColor Yellow
    Invoke-VMCommand "sudo bash -lc 'ss -lnt | grep ""127.0.0.1:8318"" >/dev/null || (echo NO_TUNNEL_8318 && exit 1)'"
}

function Check-RemoteBrowserHostProxyListener {
    Write-Host "Checking remote-browser host proxy listener on VM..." -ForegroundColor Yellow
    Invoke-VMCommand "sudo bash -lc 'systemctl is-active remote-browser-host-proxy >/dev/null 2>&1 && ss -lnt | grep "":8319"" >/dev/null || (echo NO_HOST_PROXY_8319 && exit 1)'"
}

function Check-RemoteBrowserBridgeHealth {
    Write-Host "Checking remote-browser bridge health from VM..." -ForegroundColor Yellow
    $internalIp = Get-VMInternalIP
    Invoke-VMCommand "curl -fsS --max-time 10 http://${internalIp}:8319/health"
}

function Check-RemoteBrowserBridgeConfig {
    Write-Host "Checking remote-browser bridge config endpoint from VM..." -ForegroundColor Yellow
    $internalIp = Get-VMInternalIP
    $remoteBrowserApiKey = $env:FLOW2API_REMOTE_BROWSER_API_KEY
    if (-not $remoteBrowserApiKey) {
        $localApiKeyFiles = @(
            "d:\aitools\flow2api\tools\remote_browser_bridge\bridge_api_key.txt",
            "d:\aitools\flow2api_remote_browser_bridge\bridge_api_key.txt"
        )
        foreach ($localApiKeyFile in $localApiKeyFiles) {
            if (Test-Path $localApiKeyFile) {
                $remoteBrowserApiKey = (Get-Content $localApiKeyFile -Raw).Trim()
                if ($remoteBrowserApiKey) { break }
            }
        }
    }
    if (-not $remoteBrowserApiKey) {
        throw "FLOW2API_REMOTE_BROWSER_API_KEY is not set and local bridge_api_key.txt was not found."
    }
    Invoke-VMCommand "python3 - <<'PY'
import urllib.request

url = 'http://$internalIp`:8319/api/v1/config'
try:
    req = urllib.request.Request(url, headers={'Authorization': 'Bearer $remoteBrowserApiKey'})
    with urllib.request.urlopen(req, timeout=10) as resp:
        print(resp.read().decode('utf-8'))
except Exception as exc:
    raise SystemExit(str(exc))
PY"
}

function Check-RemoteBrowserBridge {
    Write-Host "Checking remote-browser bridge from VM..." -ForegroundColor Yellow
    $internalIp = Get-VMInternalIP
    $remoteBrowserApiKey = $env:FLOW2API_REMOTE_BROWSER_API_KEY
    if (-not $remoteBrowserApiKey) {
        $localApiKeyFiles = @(
            "d:\aitools\flow2api\tools\remote_browser_bridge\bridge_api_key.txt",
            "d:\aitools\flow2api_remote_browser_bridge\bridge_api_key.txt"
        )
        foreach ($localApiKeyFile in $localApiKeyFiles) {
            if (Test-Path $localApiKeyFile) {
                $remoteBrowserApiKey = (Get-Content $localApiKeyFile -Raw).Trim()
                if ($remoteBrowserApiKey) { break }
            }
        }
    }
    if (-not $remoteBrowserApiKey) {
        throw "FLOW2API_REMOTE_BROWSER_API_KEY is not set and local bridge_api_key.txt was not found."
    }
    Invoke-VMCommand "python3 - <<'PY'
import json
import urllib.request

url = 'http://$internalIp`:8319/api/v1/debug/profile'
try:
    req = urllib.request.Request(url, headers={'Authorization': 'Bearer $remoteBrowserApiKey'})
    with urllib.request.urlopen(req, timeout=10) as resp:
        print(resp.read().decode('utf-8'))
except Exception as exc:
    raise SystemExit(str(exc))
PY"
}

# --- 2. 部署 Chrome ---
function Install-Chrome {
    Write-Host "Deploying Chrome installation script..." -ForegroundColor Yellow
    # 假设本地有 install_chrome.sh
    gcloud compute scp "d:\sfanix\install_chrome.sh" "${Instance}:/tmp/install_chrome.sh" --zone=$Zone --project=$Project
    Invoke-VMCommand "sudo bash /tmp/install_chrome.sh"
}

# --- 3. 部署 V2Ray (住宅代理桥接) ---
function Setup-V2Ray {
    Write-Host "Deploying V2Ray setup script..." -ForegroundColor Yellow
    gcloud compute scp "d:\aitools\gcpvm\setup_v2ray.bash" "${Instance}:/tmp/setup_v2ray.bash" --zone=$Zone --project=$Project
    Invoke-VMCommand "sudo bash /tmp/setup_v2ray.bash"
}

# --- 4. 部署 OpenClaw (裸机安装) ---
function Deploy-OpenClaw {
    Write-Host "Deploying OpenClaw setup script..." -ForegroundColor Yellow
    gcloud compute scp "d:\aitools\gcpvm\setup_openclaw.bash" "${Instance}:/tmp/setup_openclaw.bash" --zone=$Zone --project=$Project
    Invoke-VMCommand "bash /tmp/setup_openclaw.bash"
}

# --- 5. 启动 OpenClaw 服务 ---
function Start-OpenClaw {
    Write-Host "Deploying OpenClaw start script..." -ForegroundColor Yellow
    gcloud compute scp "d:\aitools\gcpvm\start_openclaw.bash" "${Instance}:/tmp/start_openclaw.bash" --zone=$Zone --project=$Project
    Invoke-VMCommand "sudo bash /tmp/start_openclaw.bash"
}

# --- 6. 修复 UI 认证 (允许公网访问) ---
function Fix-UIAuth {
    Write-Host "Deploying UI Auth fix script..." -ForegroundColor Yellow
    gcloud compute scp "d:\aitools\gcpvm\fix_ui_auth.bash" "${Instance}:/tmp/fix_ui_auth.bash" --zone=$Zone --project=$Project
    Invoke-VMCommand "sudo bash /tmp/fix_ui_auth.bash"
}

# --- 7. 设置备份任务 (GCS + Cron) ---
function Setup-Backup {
    Write-Host "Deploying backup script and setting up cron..." -ForegroundColor Yellow
    gcloud compute scp "d:\aitools\gcpvm\backup_system.bash" "${Instance}:/tmp/backup_system.bash" --zone=$Zone --project=$Project
    Invoke-VMCommand "sudo mv /tmp/backup_system.bash /usr/local/bin/vm_backup && sudo chmod +x /usr/local/bin/vm_backup"
    
    # 添加每日凌晨 3 点运行的 cron 任务
    Invoke-VMCommand "(crontab -l 2>/dev/null; echo \"0 3 * * * /usr/local/bin/vm_backup\") | crontab -"
    Write-Host "Cron job scheduled: Daily at 03:00 VM time." -ForegroundColor Green
}

# --- 8. 手动执行即时备份 ---
function Backup-Manual {
    Write-Host "Triggering manual backup on VM..." -ForegroundColor Yellow
    Invoke-VMCommand "sudo /usr/local/bin/vm_backup"
}

# --- 9. 部署 Sub2API ---
function Deploy-Sub2API {
    Write-Host "Deploying Sub2API deployment script..." -ForegroundColor Yellow
    gcloud compute scp "d:\aitools\gcpvm\redeploy_sub2api.bash" "${Instance}:/tmp/redeploy_sub2api.bash" --zone=$Zone --project=$Project
    Invoke-VMCommand "sudo bash /tmp/redeploy_sub2api.bash"
}

function Deploy-Flow2API {
    Write-Host "Deploying Flow2API..." -ForegroundColor Yellow
    $deployCommand = @"
set -e
if [ ! -d "$Flow2APIDir/.git" ]; then
  sudo git clone "$Flow2APIRepo" "$Flow2APIDir"
else
  cd "$Flow2APIDir"
  sudo git pull --ff-only
fi

cd "$Flow2APIDir"
if [ ! -f config/setting.toml ] && [ -f config/setting_example.toml ]; then
  sudo cp config/setting_example.toml config/setting.toml
fi

sudo mkdir -p data tmp
sudo docker compose down || true
sudo docker compose up -d
sudo docker ps --filter name=flow2api --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'
"@
    Invoke-VMCommand $deployCommand.Trim()
}

# --- 10. 重启 Grok2API ---
function Restart-Grok {
    Write-Host "Restarting Grok2API via Docker Compose..." -ForegroundColor Yellow
    Invoke-VMCommand "cd /opt/grok2api && sudo docker compose restart"
}

# --- 11. 重启 Sub2API ---
function Restart-Sub {
    Write-Host "Restarting Sub2API via Docker Compose..." -ForegroundColor Yellow
    Invoke-VMCommand "cd /opt/sub2api/deploy && sudo docker compose restart"
}

# --- 5. 连接 VM (原生显示) ---
function Connect-VM {
    Invoke-VMInteractiveSSH
}

# --- 主逻辑切换 ---
switch ($Action) {
    "Discover"     { Show-VMDiscovery }
    "Status"       { Get-VMStatus }
    "CPU"          { Get-VMCPU }
    "ChromeDebugInfo" { Get-ChromeDebugInfo }
    "ChromeDebugAccess" { Get-ChromeDebugAccess }
    "StartChromeDebugTunnel" { Start-ChromeDebugTunnel }
    "SetupHeadedChromeRemote" { Setup-HeadedChromeRemote }
    "StartChromeWebTunnel" { Start-ChromeWebTunnel }
    "DeployFlow2APITokenUpdater" { Deploy-Flow2APITokenUpdater }
    "CheckFlow2APITokenSync" { Check-Flow2APITokenSync }
    "InspectFlow2APITokenState" { Inspect-Flow2APITokenState }
    "SyncFlow2APITokenManager" { Sync-Flow2APITokenManager }
    "SyncFlow2APIProjectBoundRuntime" { Sync-Flow2APIProjectBoundRuntime }
    "RefreshFlow2APIToken" { Refresh-Flow2APIToken }
    "EnableFlow2APITokens" { Enable-Flow2APITokens }
    "SelectFlow2APIToken" { Select-Flow2APIToken }
    "SetFlow2APIPersonalMode" { Set-Flow2APIPersonalMode }
    "SetFlow2APIRemoteBrowserMode" { Set-Flow2APIRemoteBrowserMode }
    "SetupRemoteBrowserHostProxy" { Setup-RemoteBrowserHostProxy }
    "DisableRemoteBrowserHostProxy" { Disable-RemoteBrowserHostProxy }
    "CheckRemoteBrowserTunnelListener" { Check-RemoteBrowserTunnelListener }
    "CheckRemoteBrowserHostProxyListener" { Check-RemoteBrowserHostProxyListener }
    "CheckRemoteBrowserBridgeHealth" { Check-RemoteBrowserBridgeHealth }
    "CheckRemoteBrowserBridgeConfig" { Check-RemoteBrowserBridgeConfig }
    "CheckRemoteBrowserBridge" { Check-RemoteBrowserBridge }
    "SmokeTestFlow2API" { Smoke-TestFlow2API }
    "SmokeTestFlow2APIImg2Img" { Smoke-TestFlow2APIImg2Img }
    "SmokeTestFlow2APIVideo" { Smoke-TestFlow2APIVideo }
    "SmokeTestFlow2APIMatrix" { Smoke-TestFlow2APIMatrix }
    "GenerateFlow2APITreeImages" { Generate-Flow2APITreeImages }
    "GenerateFlow2APICatAlienVideo" { Generate-Flow2APICatAlienVideo }
    "HTTPCheck"    { Invoke-HTTPCheck }
    "CheckFlow2API" { Check-Flow2API }
    "CheckFlow2APIEgress" { Check-Flow2APIEgress }
    "ConfigureFlow2APIResidentialProxy" { Configure-Flow2APIResidentialProxy }
    "GetFlow2APIPluginConfig" { Get-Flow2APIPluginConfig }
    "GetFlow2APIProviderConfig" { Get-Flow2APIProviderConfig }
    "Connect"      { Connect-VM }
    "InstallChrome" { Install-Chrome }
    "SetupProxy"   { Setup-V2Ray }
    "DeployOpenClaw" { Deploy-OpenClaw }
    "StartOpenClaw" { Start-OpenClaw }
    "FixUIAuth"    { Fix-UIAuth }
    "SetupBackup"  { Setup-Backup }
    "BackupManual" { Backup-Manual }
    "DeploySub2API" { Deploy-Sub2API }
    "DeployFlow2API" { Deploy-Flow2API }
    "RestartGrok"  { Restart-Grok }
    "RestartSub"   { Restart-Sub }
    Default { Write-Error "Action $Action not implemented yet." }
}
