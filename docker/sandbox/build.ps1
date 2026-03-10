# =============================================
# Build sandbox image for Windows (PowerShell)
# =============================================

$ErrorActionPreference = "Stop"

$ImageName = "deepaudit/sandbox"
$ImageTag = "latest"

Write-Host "Building sandbox image: ${ImageName}:${ImageTag}" -ForegroundColor Green

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path

docker build -t "${ImageName}:${ImageTag}" -f "$ScriptDir\Dockerfile" "$ScriptDir"

if ($LASTEXITCODE -ne 0) {
    Write-Host "[ERROR] Build failed" -ForegroundColor Red
    exit $LASTEXITCODE
}

Write-Host "Build complete: ${ImageName}:${ImageTag}" -ForegroundColor Green

# Verify image
Write-Host "Verifying image..." -ForegroundColor Yellow
docker run --rm "${ImageName}:${ImageTag}" python3 --version
docker run --rm "${ImageName}:${ImageTag}" node --version

Write-Host "Sandbox image ready!" -ForegroundColor Green
exit 0
