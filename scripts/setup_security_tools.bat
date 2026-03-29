@echo off
:: scripts/setup_security_tools.bat — VulHunter 安全工具安装引导脚本（Windows）
::
:: 用法:
::   双击运行，或在 CMD 中执行: scripts\setup_security_tools.bat
::
:: 说明:
::   此批处理脚本仅作为引导入口，实际安装逻辑由同目录下的
::   setup_security_tools.ps1（PowerShell 增强版）执行。
::   会自动检查 PowerShell 是否可用，并以 Bypass 策略调用 .ps1 脚本。

chcp 65001 >nul 2>&1
title VulHunter 安全工具安装

echo.
echo ╔═══════════════════════════════════════════════════════════════╗
echo ║     VulHunter 安全工具一键安装脚本 (Windows)                 ║
echo ╚═══════════════════════════════════════════════════════════════╝
echo.

:: 检查 PowerShell
where powershell >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo [错误] PowerShell 未找到！
    echo 请确保已安装 Windows PowerShell 5.1 或更高版本
    pause
    exit /b 1
)

:: 获取脚本目录
set SCRIPT_DIR=%~dp0
set PS_SCRIPT=%SCRIPT_DIR%setup_security_tools.ps1

:: 检查 PowerShell 脚本是否存在
if not exist "%PS_SCRIPT%" (
    echo [错误] 找不到 PowerShell 脚本: %PS_SCRIPT%
    pause
    exit /b 1
)

:: 运行 PowerShell 脚本
echo 正在启动 PowerShell 安装脚本...
echo.

powershell -ExecutionPolicy Bypass -File "%PS_SCRIPT%" %*

echo.
echo 按任意键退出...
pause >nul
