@echo off
REM =============================================
REM Build sandbox image for Windows
REM =============================================

setlocal

set "IMAGE_NAME=deepaudit/sandbox"
set "IMAGE_TAG=latest"

echo Building sandbox image: %IMAGE_NAME%:%IMAGE_TAG%

docker build -t "%IMAGE_NAME%:%IMAGE_TAG%" -f "%~dp0Dockerfile" "%~dp0"

if %errorlevel% neq 0 (
    echo [ERROR] Build failed
    exit /b %errorlevel%
)

echo Build complete: %IMAGE_NAME%:%IMAGE_TAG%

REM Verify image
echo Verifying image...
docker run --rm "%IMAGE_NAME%:%IMAGE_TAG%" python3 --version
docker run --rm "%IMAGE_NAME%:%IMAGE_TAG%" node --version

echo Sandbox image ready!
exit /b 0
