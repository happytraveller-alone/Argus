@echo off
REM =============================================
REM VulHunter Docker Compose Wrapper for Windows
REM =============================================
REM This script provides basic docker compose execution for Windows
REM For advanced mirror selection and fallback, use PowerShell version

setlocal enabledelayedexpansion

REM Detect docker compose command
docker compose version >nul 2>&1
if %errorlevel% equ 0 (
    set "COMPOSE_CMD=docker compose"
    goto :compose_found
)

docker-compose --version >nul 2>&1
if %errorlevel% equ 0 (
    set "COMPOSE_CMD=docker-compose"
    goto :compose_found
)

echo [ERROR] docker compose or docker-compose not found
exit /b 127

:compose_found
echo [INFO] Using compose command: %COMPOSE_CMD%

REM Set default compose args
if "%~1"=="" (
    set "COMPOSE_ARGS=up -d --build"
) else (
    set "COMPOSE_ARGS=%*"
)

REM Enable BuildKit
set "DOCKER_BUILDKIT=1"
set "COMPOSE_DOCKER_CLI_BUILD=1"

REM Set default mirrors (China mirrors for better connectivity)
if not defined DOCKERHUB_LIBRARY_MIRROR set "DOCKERHUB_LIBRARY_MIRROR=docker.m.daocloud.io/library"
if not defined GHCR_REGISTRY set "GHCR_REGISTRY=ghcr.nju.edu.cn"
if not defined UV_IMAGE set "UV_IMAGE=%GHCR_REGISTRY%/astral-sh/uv:latest"
if not defined SANDBOX_BASE_IMAGE set "SANDBOX_BASE_IMAGE=%DOCKERHUB_LIBRARY_MIRROR%/python:3.12-slim"
if not defined SANDBOX_IMAGE set "SANDBOX_IMAGE=%GHCR_REGISTRY%/lintsinghua/vulhunter-sandbox:latest"
if not defined BACKEND_NPM_REGISTRY_PRIMARY set "BACKEND_NPM_REGISTRY_PRIMARY=https://registry.npmmirror.com"
if not defined BACKEND_NPM_REGISTRY_FALLBACK set "BACKEND_NPM_REGISTRY_FALLBACK=https://registry.npmjs.org"
if not defined FRONTEND_NPM_REGISTRY set "FRONTEND_NPM_REGISTRY=https://registry.npmmirror.com"
if not defined FRONTEND_NPM_REGISTRY_FALLBACK set "FRONTEND_NPM_REGISTRY_FALLBACK=https://registry.npmjs.org"
if not defined BACKEND_PYPI_INDEX_PRIMARY set "BACKEND_PYPI_INDEX_PRIMARY=https://mirrors.aliyun.com/pypi/simple/"
if not defined BACKEND_PYPI_INDEX_FALLBACK set "BACKEND_PYPI_INDEX_FALLBACK=https://pypi.org/simple"
if not defined SANDBOX_PYPI_INDEX_PRIMARY set "SANDBOX_PYPI_INDEX_PRIMARY=https://mirrors.aliyun.com/pypi/simple/"
if not defined SANDBOX_PYPI_INDEX_FALLBACK set "SANDBOX_PYPI_INDEX_FALLBACK=https://pypi.org/simple"
if not defined BACKEND_APT_MIRROR_PRIMARY set "BACKEND_APT_MIRROR_PRIMARY=mirrors.aliyun.com"
if not defined BACKEND_APT_SECURITY_PRIMARY set "BACKEND_APT_SECURITY_PRIMARY=mirrors.aliyun.com"
if not defined SANDBOX_APT_MIRROR_PRIMARY set "SANDBOX_APT_MIRROR_PRIMARY=mirrors.aliyun.com"
if not defined SANDBOX_APT_SECURITY_PRIMARY set "SANDBOX_APT_SECURITY_PRIMARY=mirrors.aliyun.com"
if not defined SANDBOX_NPM_REGISTRY_PRIMARY set "SANDBOX_NPM_REGISTRY_PRIMARY=https://registry.npmmirror.com"
if not defined SANDBOX_NPM_REGISTRY_FALLBACK set "SANDBOX_NPM_REGISTRY_FALLBACK=https://registry.npmjs.org"

echo [INFO] DOCKERHUB_LIBRARY_MIRROR=%DOCKERHUB_LIBRARY_MIRROR%
echo [INFO] GHCR_REGISTRY=%GHCR_REGISTRY%
echo [INFO] UV_IMAGE=%UV_IMAGE%
echo [INFO] SANDBOX_BASE_IMAGE=%SANDBOX_BASE_IMAGE%
echo [INFO] SANDBOX_IMAGE=%SANDBOX_IMAGE%

REM Execute docker compose
echo [INFO] Executing: %COMPOSE_CMD% %COMPOSE_ARGS%
%COMPOSE_CMD% %COMPOSE_ARGS%

if %errorlevel% neq 0 (
    echo [ERROR] Docker compose failed with exit code %errorlevel%
    echo [INFO] For advanced mirror selection and automatic fallback, use PowerShell version:
    echo [INFO]   powershell -ExecutionPolicy Bypass -File scripts\compose-up-with-fallback.ps1
    exit /b %errorlevel%
)

echo [INFO] Docker compose completed successfully
exit /b 0
