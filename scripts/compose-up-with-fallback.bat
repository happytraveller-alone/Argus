@echo off
:: scripts/compose-up-with-fallback.bat — Windows docker compose 简易包装脚本
::
:: 用法:
::   scripts\compose-up-with-fallback.bat              — 等效于 docker compose up -d
::   scripts\compose-up-with-fallback.bat up           — 前台启动
::   scripts\compose-up-with-fallback.bat down         — 停止并移除容器
::
:: 说明:
::   此脚本为 Windows CMD 用户提供基础的国内镜像源预设，无镜像探测能力。
::   如需镜像源自动探测与故障转移，请使用 PowerShell 版本:
::     powershell -ExecutionPolicy Bypass -File scripts\compose-up-with-fallback.ps1
::
:: 预设镜像源（可通过同名环境变量覆盖）:
::   DOCKERHUB_LIBRARY_MIRROR  — docker.m.daocloud.io/library
::   GHCR_REGISTRY             — ghcr.io
::   VULHUNTER_IMAGE_NAMESPACE — backend/frontend/runner/sandbox 默认命名空间
::   NEXUS_WEB_IMAGE_NAMESPACE — nexus-web 默认命名空间
::   FRONTEND_NPM_REGISTRY     — https://registry.npmmirror.com
::   BACKEND_PYPI_INDEX_PRIMARY — https://mirrors.aliyun.com/pypi/simple/

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
    set "COMPOSE_ARGS=up -d"
) else (
    set "COMPOSE_ARGS=%*"
)

REM Enable BuildKit
set "DOCKER_BUILDKIT=1"
set "COMPOSE_DOCKER_CLI_BUILD=1"

REM Set default mirrors (China mirrors for better connectivity)
if not defined DOCKERHUB_LIBRARY_MIRROR set "DOCKERHUB_LIBRARY_MIRROR=docker.m.daocloud.io/library"
if not defined GHCR_REGISTRY set "GHCR_REGISTRY=ghcr.io"
if not defined VULHUNTER_IMAGE_NAMESPACE set "VULHUNTER_IMAGE_NAMESPACE=unbengable12"
if not defined NEXUS_WEB_IMAGE_NAMESPACE set "NEXUS_WEB_IMAGE_NAMESPACE=unbengable12"
if not defined VULHUNTER_IMAGE_TAG set "VULHUNTER_IMAGE_TAG=latest"
if not defined NEXUS_WEB_IMAGE_TAG set "NEXUS_WEB_IMAGE_TAG=latest"
if not defined UV_IMAGE set "UV_IMAGE=%GHCR_REGISTRY%/astral-sh/uv:latest"
if not defined SANDBOX_BASE_IMAGE set "SANDBOX_BASE_IMAGE=%DOCKERHUB_LIBRARY_MIRROR%/python:3.11-slim"
if not defined SANDBOX_IMAGE set "SANDBOX_IMAGE=%GHCR_REGISTRY%/%VULHUNTER_IMAGE_NAMESPACE%/vulhunter-sandbox:%VULHUNTER_IMAGE_TAG%"
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
echo [INFO] VULHUNTER_IMAGE_NAMESPACE=%VULHUNTER_IMAGE_NAMESPACE%
echo [INFO] NEXUS_WEB_IMAGE_NAMESPACE=%NEXUS_WEB_IMAGE_NAMESPACE%
echo [INFO] VULHUNTER_IMAGE_TAG=%VULHUNTER_IMAGE_TAG%
echo [INFO] NEXUS_WEB_IMAGE_TAG=%NEXUS_WEB_IMAGE_TAG%
echo [INFO] UV_IMAGE=%UV_IMAGE%
echo [INFO] SANDBOX_BASE_IMAGE=%SANDBOX_BASE_IMAGE%
echo [INFO] SANDBOX_IMAGE=%SANDBOX_IMAGE%
if defined BACKEND_IMAGE (
    echo [INFO] BACKEND_IMAGE_RESOLVED=%BACKEND_IMAGE%
) else (
    echo [INFO] BACKEND_IMAGE_RESOLVED=%GHCR_REGISTRY%/%VULHUNTER_IMAGE_NAMESPACE%/vulhunter-backend:%VULHUNTER_IMAGE_TAG%
)
if defined FRONTEND_IMAGE (
    echo [INFO] FRONTEND_IMAGE_RESOLVED=%FRONTEND_IMAGE%
) else (
    echo [INFO] FRONTEND_IMAGE_RESOLVED=%GHCR_REGISTRY%/%VULHUNTER_IMAGE_NAMESPACE%/vulhunter-frontend:%VULHUNTER_IMAGE_TAG%
)
if defined NEXUS_WEB_IMAGE (
    echo [INFO] NEXUS_WEB_IMAGE_RESOLVED=%NEXUS_WEB_IMAGE%
) else (
    echo [INFO] NEXUS_WEB_IMAGE_RESOLVED=%GHCR_REGISTRY%/%NEXUS_WEB_IMAGE_NAMESPACE%/nexus-web:%NEXUS_WEB_IMAGE_TAG%
)
echo [WARN] GHCR host rewrite does not bypass private package permissions; default remote mode expects anonymous pull access or an explicit full image override.

REM Execute docker compose
echo [INFO] Executing: %COMPOSE_CMD% %COMPOSE_ARGS%
%COMPOSE_CMD% %COMPOSE_ARGS%

if %errorlevel% neq 0 (
    echo [ERROR] Docker compose failed with exit code %errorlevel%
    echo [ERROR] anonymous GHCR pull failed or the image namespace/tag is incorrect
    echo [INFO] For advanced mirror selection and automatic fallback, use PowerShell version:
    echo [INFO]   powershell -ExecutionPolicy Bypass -File scripts\compose-up-with-fallback.ps1
    exit /b %errorlevel%
)

echo [INFO] Docker compose completed successfully
exit /b 0
