param(
    [ValidateSet("InstallDeps", "UnitTests", "CI")]
    [string]$Action = "UnitTests"
)

$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot

function Invoke-Checked {
    param(
        [Parameter(Mandatory = $true)]
        [string]$FilePath,
        [string[]]$Arguments = @()
    )

    & $FilePath @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Command failed with exit code ${LASTEXITCODE}: $FilePath $($Arguments -join ' ')"
    }
}

Push-Location $Root
try {
    switch ($Action) {
        "InstallDeps" {
            Invoke-Checked -FilePath "python" -Arguments @("-m", "pip", "install", "--upgrade", "pip")
            Invoke-Checked -FilePath "python" -Arguments @("-m", "pip", "install", "-r", "requirements.txt")
        }
        "UnitTests" {
            Invoke-Checked -FilePath "python" -Arguments @("-m", "pytest", "tests/unit", "-v")
        }
        "CI" {
            Invoke-Checked -FilePath "python" -Arguments @("-m", "pip", "install", "--upgrade", "pip")
            Invoke-Checked -FilePath "python" -Arguments @("-m", "pip", "install", "-r", "requirements.txt")
            Invoke-Checked -FilePath "python" -Arguments @("-m", "pytest", "tests/unit", "-v")
        }
    }
}
finally {
    Pop-Location
}
