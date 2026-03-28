param(
    [ValidateSet("Request", "Boot", "Full", "Matrix")]
    [string]$Action = "Request",

    [ValidateSet("image", "video")]
    [string]$Mode = "image",

    [string]$TargetEmail = "kpveoiref@libertystreeteriepa.asia",
    [string]$ProjectId = "c6d7cff5-2977-4825-acbe-e978e4addc65",
    [string]$DisableOtherTokens = "true",
    [string]$ForceBridgeRestart = "false",
    [string]$SkipPluginSync = "false",
    [string]$SkipProjectContextPage = "false",
    [string]$SkipTargetToken = "false",
    [string]$SkipRemoteBrowserMode = "false"
)

$ErrorActionPreference = "Stop"

$ScriptsDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$Root = Split-Path -Parent (Split-Path -Parent $ScriptsDir)
$VMManager = Join-Path $Root "scripts\vm\vm_manager.ps1"
$BridgeScript = Join-Path $Root "scripts\remote_browser\start_remote_browser_bridge.ps1"
$TunnelScript = Join-Path $Root "scripts\remote_browser\start_remote_browser_reverse_tunnel.ps1"
$BridgeOutLog = Join-Path $env:TEMP "flow2api_remote_browser_bridge.out.log"
$BridgeErrLog = Join-Path $env:TEMP "flow2api_remote_browser_bridge.err.log"
$TunnelOutLog = Join-Path $env:TEMP "flow2api_remote_browser_tunnel.out.log"
$TunnelErrLog = Join-Path $env:TEMP "flow2api_remote_browser_tunnel.err.log"
$BridgePort = 8318
$BridgeHealthUrl = "http://127.0.0.1:$BridgePort/health"
$BridgeProfileUrl = "http://127.0.0.1:$BridgePort/api/v1/debug/profile"
$BridgePluginSyncUrl = "http://127.0.0.1:$BridgePort/api/v1/plugin-sync-request"
$ChromeExecutable = "C:\Program Files\Google\Chrome\Application\chrome.exe"
$VMZone = "us-central1-a"
$MaxRepairAttempts = 3
$BridgeProbeCount = 6
$TunnelProbeCount = 6
$ProbeSleepSeconds = 2

function Convert-ToBool {
    param(
        [string]$Value,
        [bool]$Default = $true
    )
    if ($null -eq $Value -or "$Value" -eq "") {
        return $Default
    }
    $normalized = "$Value".Trim().ToLowerInvariant()
    if ($normalized -in @("true", "1", "yes", "on")) { return $true }
    if ($normalized -in @("false", "0", "no", "off")) { return $false }
    return $Default
}

$DisableOtherTokensBool = Convert-ToBool -Value $DisableOtherTokens -Default $true
$ForceBridgeRestartBool = Convert-ToBool -Value $ForceBridgeRestart -Default $false
$SkipPluginSyncBool = Convert-ToBool -Value $SkipPluginSync -Default $false
$SkipProjectContextPageBool = Convert-ToBool -Value $SkipProjectContextPage -Default $false
$SkipTargetTokenBool = Convert-ToBool -Value $SkipTargetToken -Default $false
$SkipRemoteBrowserModeBool = Convert-ToBool -Value $SkipRemoteBrowserMode -Default $false

function Write-State {
    param(
        [Parameter(Mandatory = $true)][string]$State,
        [string]$Detail = ""
    )
    if ($Detail) {
        Write-Host "[$State] $Detail" -ForegroundColor Cyan
    } else {
        Write-Host "[$State]" -ForegroundColor Cyan
    }
}

function Fail-State {
    param(
        [Parameter(Mandatory = $true)][string]$Code,
        [Parameter(Mandatory = $true)][string]$Message
    )
    Write-Host "[failed] $Code - $Message" -ForegroundColor Red
    throw $Message
}

function Invoke-VMManagerAction {
    param(
        [Parameter(Mandatory = $true)][string]$Action,
        [hashtable]$ExtraArgs = @{}
    )

    $args = @(
        "-NoProfile",
        "-ExecutionPolicy", "Bypass",
        "-File", $VMManager,
        "-Action", $Action,
        "-Zone", $VMZone
    )

    foreach ($key in $ExtraArgs.Keys) {
        $value = $ExtraArgs[$key]
        if ($value -is [switch]) {
            if ($value.IsPresent) {
                $args += "-$key"
            }
            continue
        }
        if ($null -ne $value -and "$value" -ne "") {
            $args += "-$key"
            $args += "$value"
        }
    }

    & powershell @args
}

function Test-JsonEndpoint {
    param(
        [Parameter(Mandatory = $true)][string]$Url,
        [int]$TimeoutSec = 5,
        [hashtable]$Headers = @{}
    )

    try {
        $resp = Invoke-WebRequest -UseBasicParsing -Uri $Url -Headers $Headers -TimeoutSec $TimeoutSec
        if (-not $resp.Content) {
            return $null
        }
        return $resp.Content | ConvertFrom-Json
    } catch {
        return $null
    }
}

function Get-BridgeAuthHeaders {
    $apiKeyFile = Join-Path $Root "tools\remote_browser_bridge\bridge_api_key.txt"
    if (-not (Test-Path $apiKeyFile)) {
        $legacyApiKeyFile = Join-Path (Split-Path $Root -Parent) "flow2api_remote_browser_bridge\bridge_api_key.txt"
        if (Test-Path $legacyApiKeyFile) {
            $apiKeyFile = $legacyApiKeyFile
        }
    }
    $apiKey = (Get-Content $apiKeyFile -Raw).Trim()
    return @{ Authorization = "Bearer $apiKey" }
}

function Start-BackgroundScript {
    param(
        [Parameter(Mandatory = $true)][string]$ScriptPath,
        [Parameter(Mandatory = $true)][string]$StdOutLog,
        [Parameter(Mandatory = $true)][string]$StdErrLog
    )

    Start-Process -FilePath "powershell" `
        -ArgumentList @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $ScriptPath) `
        -WindowStyle Hidden `
        -RedirectStandardOutput $StdOutLog `
        -RedirectStandardError $StdErrLog | Out-Null
}

function Stop-ProcessesByPattern {
    param(
        [string[]]$Patterns
    )

    $processes = @()
    try {
        $processes = Get-CimInstance Win32_Process | Where-Object {
            $cmd = $_.CommandLine
            if (-not $cmd) { return $false }
            foreach ($pattern in $Patterns) {
                if ($cmd -like "*$pattern*") {
                    return $true
                }
            }
            return $false
        }
    } catch {
        return
    }

    foreach ($proc in $processes) {
        try {
            Stop-Process -Id $proc.ProcessId -Force -ErrorAction Stop
        } catch {
        }
    }
}

function Stop-ProcessOnPort {
    param(
        [Parameter(Mandatory = $true)][int]$Port
    )

    $connections = Get-NetTCPConnection -LocalAddress 127.0.0.1 -LocalPort $Port -ErrorAction SilentlyContinue
    foreach ($conn in $connections) {
        if ($conn.OwningProcess -and $conn.OwningProcess -gt 0) {
            try {
                Stop-Process -Id $conn.OwningProcess -Force -ErrorAction Stop
            } catch {
            }
        }
    }
}

function Restart-LocalBridge {
    Write-State -State "repair" -Detail "Restarting local bridge"
    Stop-ProcessOnPort -Port $BridgePort
    Stop-ProcessesByPattern -Patterns @(
        "start_flow2api_remote_browser_bridge.ps1",
        "uvicorn app:app --host 127.0.0.1 --port 8318"
    )
    Start-Sleep -Seconds 1
    Start-BackgroundScript -ScriptPath $BridgeScript -StdOutLog $BridgeOutLog -StdErrLog $BridgeErrLog
}

function Ensure-LocalBridge {
    Write-State -State "checking_channel" -Detail "Checking local bridge"
    $health = Test-JsonEndpoint -Url $BridgeHealthUrl
    $profile = $null
    if ($health -and $health.ok) {
        $profile = Test-JsonEndpoint -Url $BridgeProfileUrl -Headers (Get-BridgeAuthHeaders)
    }
    if ($health -and $health.ok -and $profile -and $null -ne $profile.recent_events) {
        Write-Host "Local bridge already healthy." -ForegroundColor Green
        return
    }

    for ($attempt = 1; $attempt -le $MaxRepairAttempts; $attempt++) {
        Write-State -State "repair_attempt" -Detail "Bridge repair attempt $attempt/$MaxRepairAttempts"
        Restart-LocalBridge
        for ($i = 0; $i -lt $BridgeProbeCount; $i++) {
            Write-State -State "probe" -Detail "Bridge probe $($i + 1)/$BridgeProbeCount"
            Start-Sleep -Seconds $ProbeSleepSeconds
            $health = Test-JsonEndpoint -Url $BridgeHealthUrl
            if ($health -and $health.ok) {
                $profile = Test-JsonEndpoint -Url $BridgeProfileUrl -Headers (Get-BridgeAuthHeaders)
            }
            if ($health -and $health.ok -and $profile -and $null -ne $profile.recent_events) {
                Write-Host "Local bridge is healthy." -ForegroundColor Green
                return
            }
        }
    }

    throw "Local bridge failed to start. See $BridgeErrLog"
}

function Test-LocalBridgeReady {
    $health = Test-JsonEndpoint -Url $BridgeHealthUrl
    if (-not ($health -and $health.ok)) {
        return $false
    }
    $profile = Test-JsonEndpoint -Url $BridgeProfileUrl -Headers (Get-BridgeAuthHeaders)
    return [bool]($profile -and $null -ne $profile.recent_events)
}

function Test-RemoteBridgeHealth {
    try {
        $resp = Invoke-VMManagerAction -Action "CheckRemoteBrowserBridgeHealth"
        if ($LASTEXITCODE -ne 0) {
            return $false
        }
        $text = "$resp"
        return ($text -match '"ok"\s*:\s*true')
    } catch {
        return $false
    }
}

function Test-VMTunnelListener {
    try {
        $resp = Invoke-VMManagerAction -Action "CheckRemoteBrowserTunnelListener"
        return ($LASTEXITCODE -eq 0 -and $resp)
    } catch {
        return $false
    }
}

function Test-VMHostProxyListener {
    try {
        $resp = Invoke-VMManagerAction -Action "CheckRemoteBrowserHostProxyListener"
        return ($LASTEXITCODE -eq 0 -and $resp)
    } catch {
        return $false
    }
}

function Test-RemoteBridgeConfig {
    try {
        $resp = Invoke-VMManagerAction -Action "CheckRemoteBrowserBridgeConfig"
        if ($LASTEXITCODE -ne 0) {
            return $false
        }
        $text = "$resp"
        return ($text -match 'api_key_preview')
    } catch {
        return $false
    }
}

function Restart-ReverseTunnel {
    Write-State -State "repair" -Detail "Restarting reverse tunnel"
    Stop-ProcessesByPattern -Patterns @(
        "start_flow2api_remote_browser_reverse_tunnel.ps1",
        "-R 0.0.0.0:8318:127.0.0.1:8318",
        "-R 0.0.0.0:8319:127.0.0.1:8318"
    )
    Start-Sleep -Seconds 1
    Start-BackgroundScript -ScriptPath $TunnelScript -StdOutLog $TunnelOutLog -StdErrLog $TunnelErrLog
}

function Ensure-ReverseTunnel {
    Write-State -State "checking_channel" -Detail "Checking reverse tunnel from VM"
    $null = Invoke-VMManagerAction -Action "SetupRemoteBrowserHostProxy"
    if ((Test-VMTunnelListener) -and (Test-VMHostProxyListener) -and (Test-RemoteBridgeHealth) -and (Test-RemoteBridgeConfig)) {
        Write-Host "Reverse tunnel and host proxy are reachable from VM." -ForegroundColor Green
        return
    }

    for ($attempt = 1; $attempt -le $MaxRepairAttempts; $attempt++) {
        Write-State -State "repair_attempt" -Detail "Tunnel repair attempt $attempt/$MaxRepairAttempts"
        Restart-ReverseTunnel
        for ($i = 0; $i -lt $TunnelProbeCount; $i++) {
            Write-State -State "probe" -Detail "Tunnel probe $($i + 1)/$TunnelProbeCount"
            Start-Sleep -Seconds $ProbeSleepSeconds
            $tunnelOk = Test-VMTunnelListener
            $proxyOk = Test-VMHostProxyListener
            $healthOk = Test-RemoteBridgeHealth
            $configOk = Test-RemoteBridgeConfig
            if ($tunnelOk -and $proxyOk -and $healthOk -and $configOk) {
                Write-Host "Reverse tunnel and host proxy are reachable from VM." -ForegroundColor Green
                return
            }
        }
    }

    Fail-State -Code "failed_vm_bridge_health" -Message "VM tunnel/host proxy/bridge health checks did not all pass."
}

function Test-RemoteBridgeReady {
    $tunnelOk = Test-VMTunnelListener
    $proxyOk = Test-VMHostProxyListener
    $healthOk = Test-RemoteBridgeHealth
    $configOk = Test-RemoteBridgeConfig
    return [bool]($tunnelOk -and $proxyOk -and $healthOk -and $configOk)
}

function Ensure-TargetToken {
    Write-State -State "checking_channel" -Detail "Selecting target token: $TargetEmail"
    $disableValue = if ($DisableOtherTokensBool) { "true" } else { "false" }
    Invoke-VMManagerAction -Action "SelectFlow2APIToken" -ExtraArgs @{
        TargetEmail = $TargetEmail
        DisableOthers = $disableValue
    }
}

function Request-PluginTokenSync {
    Write-State -State "checking_channel" -Detail "Requesting extension session-token sync"
    try {
        Invoke-WebRequest -UseBasicParsing -Method POST -Headers (Get-BridgeAuthHeaders) -Uri $BridgePluginSyncUrl -TimeoutSec 10 | Out-Null
    } catch {
        Fail-State -Code "failed_plugin_sync_request" -Message "Failed to request plugin session-token sync from local bridge."
    }
    Start-Sleep -Seconds 8
}

function Ensure-ProjectContextPage {
    if (-not $ProjectId) {
        return
    }
    $projectUrl = "https://labs.google/fx/tools/flow/project/$ProjectId"
    Write-State -State "checking_channel" -Detail "Opening project context page: $ProjectId"
    if (Test-Path $ChromeExecutable) {
        Start-Process -FilePath $ChromeExecutable -ArgumentList @(
            "--profile-directory=Default",
            $projectUrl
        ) | Out-Null
        Start-Sleep -Seconds 5
    } else {
        Write-State -State "warning" -Detail "Chrome executable not found, skipping project page open"
    }
}

function Invoke-Request {
    Write-State -State "upstream_running" -Detail "Dispatching Flow2API request"
    if ($Mode -eq "video") {
        Write-Host "Running video smoke request..." -ForegroundColor Cyan
        Invoke-VMManagerAction -Action "GenerateFlow2APICatAlienVideo"
    } else {
        Write-Host "Running image smoke request..." -ForegroundColor Cyan
        Invoke-VMManagerAction -Action "SmokeTestFlow2API" -ExtraArgs @{
            ProjectId = $ProjectId
        }
    }
}

function Invoke-MatrixRequest {
    Write-State -State "upstream_running" -Detail "Dispatching Flow2API request matrix"
    $referenceImagePath = Join-Path $Root "output\flow2api\tree-1.png"
    if (-not (Test-Path $referenceImagePath)) {
        $legacyReferenceImagePath = Join-Path (Split-Path $Root -Parent) "output\flow2api\tree-1.png"
        if (Test-Path $legacyReferenceImagePath) {
            $referenceImagePath = $legacyReferenceImagePath
        }
    }
    Invoke-VMManagerAction -Action "SmokeTestFlow2APIMatrix" -ExtraArgs @{
        ProjectId = $ProjectId
        ReferenceImagePath = $referenceImagePath
    }
}

function Ensure-RemoteBrowserMode {
    Write-State -State "checking_channel" -Detail "Ensuring Flow2API remote_browser mode"
    Invoke-VMManagerAction -Action "SetFlow2APIRemoteBrowserMode"
}

function Assert-RequestReady {
    Write-State -State "request_preflight" -Detail "Running lightweight request checks"
    if (-not (Test-LocalBridgeReady)) {
        Fail-State -Code "failed_local_bridge" -Message "Local bridge is not ready. Run with -Action Boot or -Action Full first."
    }
    if (-not (Test-RemoteBridgeReady)) {
        Fail-State -Code "failed_vm_bridge_health" -Message "VM tunnel/host proxy/bridge is not ready. Run with -Action Boot or -Action Full first."
    }
    Write-State -State "channel_ready" -Detail "Existing bridge and tunnel runtime are ready"
}

function Assert-Preflight {
    Write-State -State "preflight" -Detail "Running end-to-end preflight"
    if ($ForceBridgeRestartBool) {
        Write-State -State "repair" -Detail "Force restarting local bridge before preflight"
        Restart-LocalBridge
    }
    Ensure-LocalBridge
    Ensure-ReverseTunnel
    if (-not $SkipRemoteBrowserModeBool) {
        Ensure-RemoteBrowserMode
    } else {
        Write-State -State "preflight" -Detail "Skipping remote_browser mode sync"
    }
    if (-not $SkipPluginSyncBool) {
        Request-PluginTokenSync
    } else {
        Write-State -State "preflight" -Detail "Skipping plugin sync"
    }
    if (-not $SkipProjectContextPageBool) {
        Ensure-ProjectContextPage
    } else {
        Write-State -State "preflight" -Detail "Skipping project context page open"
    }
    if (-not $SkipTargetTokenBool) {
        Ensure-TargetToken
    } else {
        Write-State -State "preflight" -Detail "Skipping target token selection"
    }
    Write-State -State "channel_ready" -Detail "Bridge, tunnel, captcha mode, and target token are ready"
}

switch ($Action) {
    "Boot" {
        Assert-Preflight
    }
    "Request" {
        Assert-RequestReady
        if (-not $SkipPluginSyncBool) {
            Request-PluginTokenSync
        }
        Ensure-ProjectContextPage
        Ensure-TargetToken
        Invoke-Request
    }
    "Full" {
        Assert-Preflight
        Invoke-Request
    }
    "Matrix" {
        Assert-RequestReady
        Request-PluginTokenSync
        Ensure-ProjectContextPage
        Ensure-TargetToken
        Invoke-MatrixRequest
    }
    default {
        Fail-State -Code "failed_invalid_action" -Message "Unsupported action: $Action"
    }
}
