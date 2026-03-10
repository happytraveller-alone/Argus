# =============================================
# VulHunter Docker Compose Wrapper for Windows (PowerShell)
# =============================================
# This script provides mirror selection and fallback for Windows environments
# Usage: powershell -ExecutionPolicy Bypass -File scripts\compose-up-with-fallback.ps1 [compose-args]

param(
    [Parameter(ValueFromRemainingArguments=$true)]
    [string[]]$ComposeArgs
)

$ErrorActionPreference = "Stop"

function Log-Info {
    param([string]$Message)
    Write-Host "[INFO] $Message" -ForegroundColor Green
}

function Log-Warn {
    param([string]$Message)
    Write-Host "[WARN] $Message" -ForegroundColor Yellow
}

function Log-Error {
    param([string]$Message)
    Write-Host "[ERROR] $Message" -ForegroundColor Red
}

function Detect-ComposeCommand {
    try {
        $null = docker compose version 2>&1
        if ($LASTEXITCODE -eq 0) {
            return @("docker", "compose")
        }
    } catch {}
    
    try {
        $null = docker-compose --version 2>&1
        if ($LASTEXITCODE -eq 0) {
            return @("docker-compose")
        }
    } catch {}
    
    Log-Error "docker compose or docker-compose not found"
    exit 127
}

function Test-Url {
    param(
        [string]$Url,
        [int]$TimeoutSeconds = 10
    )
    
    try {
        $response = Invoke-WebRequest -Uri $Url -Method Head -TimeoutSec $TimeoutSeconds -UseBasicParsing -ErrorAction Stop
        return $true
    } catch {
        return $false
    }
}

function Measure-UrlLatency {
    param(
        [string]$Url,
        [int]$Attempts = 3,
        [int]$TimeoutSeconds = 10
    )
    
    $latencies = @()
    
    for ($i = 0; $i -lt $Attempts; $i++) {
        try {
            $stopwatch = [System.Diagnostics.Stopwatch]::StartNew()
            $response = Invoke-WebRequest -Uri $Url -Method Head -TimeoutSec $TimeoutSeconds -UseBasicParsing -ErrorAction Stop
            $stopwatch.Stop()
            $latencies += $stopwatch.Elapsed.TotalSeconds
        } catch {
            # Failed attempt, skip
        }
    }
    
    if ($latencies.Count -eq 0) {
        return 9999
    }
    
    $sorted = $latencies | Sort-Object
    $median = if ($sorted.Count % 2 -eq 1) {
        $sorted[[Math]::Floor($sorted.Count / 2)]
    } else {
        ($sorted[$sorted.Count / 2 - 1] + $sorted[$sorted.Count / 2]) / 2
    }
    
    return $median
}

function Rank-Candidates {
    param(
        [string]$Kind,
        [string]$Label,
        [string[]]$Candidates
    )
    
    if ($Candidates.Count -eq 0) {
        return @()
    }
    
    $results = @()
    
    foreach ($candidate in $Candidates) {
        $url = switch ($Kind) {
            "dockerhub" {
                $host = $candidate -replace '/.*$', ''
                if ($host -eq "docker.io" -or $host -eq "index.docker.io") {
                    $host = "registry-1.docker.io"
                }
                "https://$host/v2/"
            }
            "ghcr" {
                "https://$candidate/v2/"
            }
            "npm" {
                "$($candidate.TrimEnd('/'))/--/ping"
            }
            "pypi" {
                if ($candidate -match '/simple/?$') {
                    $candidate
                } else {
                    "$($candidate.TrimEnd('/'))/simple/"
                }
            }
            default {
                $null
            }
        }
        
        if (-not $url) {
            continue
        }
        
        Log-Info "Probing $Label : $candidate"
        $latency = Measure-UrlLatency -Url $url -Attempts 3 -TimeoutSeconds 10
        
        if ($latency -lt 9999) {
            Log-Info "Probe $Label : $candidate median=$([Math]::Round($latency, 3))s url=$url"
        } else {
            Log-Warn "Probe $Label : $candidate failed url=$url"
        }
        
        $results += [PSCustomObject]@{
            Candidate = $candidate
            Latency = $latency
        }
    }
    
    return ($results | Sort-Object Latency | Select-Object -ExpandProperty Candidate)
}

# Detect compose command
$ComposeCmd = Detect-ComposeCommand
Log-Info "Using compose command: $($ComposeCmd -join ' ')"

# Set default compose args
if ($ComposeArgs.Count -eq 0) {
    $ComposeArgs = @("up", "-d", "--build")
}

# Enable BuildKit
$env:DOCKER_BUILDKIT = "1"
$env:COMPOSE_DOCKER_CLI_BUILD = "1"

# Define candidates
$dockerhubCandidates = @(
    "docker.m.daocloud.io/library",
    "docker.1ms.run/library",
    "docker.io/library"
)

$ghcrCandidates = @(
    "ghcr.nju.edu.cn",
    "ghcr.m.daocloud.io",
    "ghcr.io"
)

$npmCandidates = @(
    "https://registry.npmmirror.com",
    "https://registry.npmjs.org"
)

$pypiCandidates = @(
    "https://mirrors.aliyun.com/pypi/simple/",
    "https://pypi.org/simple"
)

# Rank candidates (skip if explicitly set)
Log-Info "Ranking mirror candidates..."

if (-not $env:DOCKERHUB_LIBRARY_MIRROR) {
    $dockerhubRanked = Rank-Candidates -Kind "dockerhub" -Label "dockerhub" -Candidates $dockerhubCandidates
    $env:DOCKERHUB_LIBRARY_MIRROR = $dockerhubRanked[0]
} else {
    Log-Info "Using explicit DOCKERHUB_LIBRARY_MIRROR=$env:DOCKERHUB_LIBRARY_MIRROR"
}

if (-not $env:GHCR_REGISTRY) {
    $ghcrRanked = Rank-Candidates -Kind "ghcr" -Label "ghcr" -Candidates $ghcrCandidates
    $env:GHCR_REGISTRY = $ghcrRanked[0]
} else {
    Log-Info "Using explicit GHCR_REGISTRY=$env:GHCR_REGISTRY"
}

if (-not $env:BACKEND_NPM_REGISTRY_PRIMARY) {
    $npmRanked = Rank-Candidates -Kind "npm" -Label "npm" -Candidates $npmCandidates
    $env:BACKEND_NPM_REGISTRY_PRIMARY = $npmRanked[0]
    $env:BACKEND_NPM_REGISTRY_FALLBACK = if ($npmRanked.Count -gt 1) { $npmRanked[1] } else { $npmRanked[0] }
}

if (-not $env:FRONTEND_NPM_REGISTRY) {
    $env:FRONTEND_NPM_REGISTRY = $env:BACKEND_NPM_REGISTRY_PRIMARY
    $env:FRONTEND_NPM_REGISTRY_FALLBACK = $env:BACKEND_NPM_REGISTRY_FALLBACK
}

if (-not $env:SANDBOX_NPM_REGISTRY_PRIMARY) {
    $env:SANDBOX_NPM_REGISTRY_PRIMARY = $env:BACKEND_NPM_REGISTRY_PRIMARY
    $env:SANDBOX_NPM_REGISTRY_FALLBACK = $env:BACKEND_NPM_REGISTRY_FALLBACK
}

if (-not $env:BACKEND_PYPI_INDEX_PRIMARY) {
    $pypiRanked = Rank-Candidates -Kind "pypi" -Label "pypi" -Candidates $pypiCandidates
    $env:BACKEND_PYPI_INDEX_PRIMARY = $pypiRanked[0]
    $env:BACKEND_PYPI_INDEX_FALLBACK = if ($pypiRanked.Count -gt 1) { $pypiRanked[1] } else { $pypiRanked[0] }
}

if (-not $env:SANDBOX_PYPI_INDEX_PRIMARY) {
    $env:SANDBOX_PYPI_INDEX_PRIMARY = $env:BACKEND_PYPI_INDEX_PRIMARY
    $env:SANDBOX_PYPI_INDEX_FALLBACK = $env:BACKEND_PYPI_INDEX_FALLBACK
}

# Set default values for other variables
if (-not $env:UV_IMAGE) {
    $env:UV_IMAGE = "$($env:GHCR_REGISTRY)/astral-sh/uv:latest"
}

if (-not $env:SANDBOX_BASE_IMAGE) {
    $env:SANDBOX_BASE_IMAGE = "$($env:DOCKERHUB_LIBRARY_MIRROR)/python:3.12-slim"
}

if (-not $env:SANDBOX_IMAGE) {
    $env:SANDBOX_IMAGE = "$($env:GHCR_REGISTRY)/lintsinghua/vulhunter-sandbox:latest"
}

if (-not $env:BACKEND_APT_MIRROR_PRIMARY) {
    $env:BACKEND_APT_MIRROR_PRIMARY = "mirrors.aliyun.com"
    $env:BACKEND_APT_MIRROR_FALLBACK = "deb.debian.org"
}

if (-not $env:BACKEND_APT_SECURITY_PRIMARY) {
    $env:BACKEND_APT_SECURITY_PRIMARY = "mirrors.aliyun.com"
    $env:BACKEND_APT_SECURITY_FALLBACK = "security.debian.org"
}

if (-not $env:SANDBOX_APT_MIRROR_PRIMARY) {
    $env:SANDBOX_APT_MIRROR_PRIMARY = "mirrors.aliyun.com"
    $env:SANDBOX_APT_MIRROR_FALLBACK = "deb.debian.org"
}

if (-not $env:SANDBOX_APT_SECURITY_PRIMARY) {
    $env:SANDBOX_APT_SECURITY_PRIMARY = "mirrors.aliyun.com"
    $env:SANDBOX_APT_SECURITY_FALLBACK = "security.debian.org"
}

# Log selected mirrors
Log-Info "Selected mirrors:"
Log-Info "  DOCKERHUB_LIBRARY_MIRROR=$env:DOCKERHUB_LIBRARY_MIRROR"
Log-Info "  GHCR_REGISTRY=$env:GHCR_REGISTRY"
Log-Info "  UV_IMAGE=$env:UV_IMAGE"
Log-Info "  SANDBOX_BASE_IMAGE=$env:SANDBOX_BASE_IMAGE"
Log-Info "  SANDBOX_IMAGE=$env:SANDBOX_IMAGE"
Log-Info "  BACKEND_NPM_REGISTRY_PRIMARY=$env:BACKEND_NPM_REGISTRY_PRIMARY"
Log-Info "  FRONTEND_NPM_REGISTRY=$env:FRONTEND_NPM_REGISTRY"

# Execute docker compose
Log-Info "Executing: $($ComposeCmd -join ' ') $($ComposeArgs -join ' ')"

$process = Start-Process -FilePath $ComposeCmd[0] -ArgumentList ($ComposeCmd[1..($ComposeCmd.Length-1)] + $ComposeArgs) -NoNewWindow -Wait -PassThru

if ($process.ExitCode -ne 0) {
    Log-Error "Docker compose failed with exit code $($process.ExitCode)"
    exit $process.ExitCode
}

Log-Info "Docker compose completed successfully"
exit 0
