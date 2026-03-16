#!/usr/bin/env python3
"""
手动测试 external_tools.py 中的安全工具集合
支持 Opengrep、Bandit、Gitleaks、npm audit、Safety、TruffleHog、OSV-Scanner

使用方法:
    python test_external_tools_manual.py --tool opengrep --path .
    python test_external_tools_manual.py --tool bandit --path .
    python test_external_tools_manual.py --tool gitleaks --path .
    python test_external_tools_manual.py --tool npm_audit --path .
    python test_external_tools_manual.py --tool safety --path .
    python test_external_tools_manual.py --help
"""

import os

import pytest

# This file is a CLI/manual smoke test and depends on external binaries being installed.
# Skip it in the default pytest suite unless explicitly enabled.
if os.environ.get("RUN_EXTERNAL_TOOLS_MANUAL_TESTS") != "1":
    pytest.skip(
        "Set RUN_EXTERNAL_TOOLS_MANUAL_TESTS=1 to run external tools manual tests.",
        allow_module_level=True,
    )

import asyncio
import argparse
import sys
from pathlib import Path

# 添加后端路径
sys.path.insert(0, str(Path(__file__).parent))

# 延迟导入，先检查依赖
def check_dependencies():
    """检查必要的依赖"""
    missing = []
    
    try:
        import pydantic
    except ImportError:
        missing.append("pydantic")
    
    try:
        import pydantic_settings
    except ImportError:
        missing.append("pydantic-settings")
    
    try:
        import fastapi
    except ImportError:
        missing.append("fastapi")
    
    if missing:
        print(f"缺少依赖: {', '.join(missing)}")
        print("\n安装依赖:")
        print("  pip install -r requirements.txt")
        sys.exit(1)

check_dependencies()

# 现在安全地导入
try:
    from app.services.agent.tools.external_tools import (
        OpengrepTool, BanditTool, GitleaksTool, NpmAuditTool,
        SafetyTool, TruffleHogTool, OSVScannerTool
    )
    from app.services.agent.tools.sandbox_tool import SandboxManager
except ModuleNotFoundError as e:
    print(f"导入错误: {e}")
    print("\n确保依赖已安装:")
    print("  pip install -r requirements.txt")
    sys.exit(1)


async def test_opengrep(project_root: str):
    """测试 Opengrep 工具"""
    print("\n" + "="*60)
    print(" 测试 Opengrep 工具")
    print("="*60)
    
    sandbox_manager = SandboxManager()
    
    tool = OpengrepTool(project_root, sandbox_manager)
    
    print(f"工具名称: {tool.name}")
    print(f"工具描述: {tool.description[:200]}...")
    
    # 测试扫描
    print("\n执行扫描...")
    result = await tool.execute(
        target_path=".",
        rules="p/security-audit",
        max_results=10
    )
    
    print(f"执行成功: {result.success}")
    print(f"持续时间: {result.duration_ms}ms")
    print(f"元数据: {result.metadata}")
    print(f"\n结果:\n{result.to_string()[:2000]}")
    
    return result.success


async def test_bandit(project_root: str):
    """测试 Bandit 工具（仅限 Python 项目）"""
    print("\n" + "="*60)
    print("🐍 测试 Bandit 工具")
    print("="*60)
    
    sandbox_manager = SandboxManager()
    tool = BanditTool(project_root, sandbox_manager)
    
    print(f"工具名称: {tool.name}")
    print(f"工具描述: {tool.description[:200]}...")
    
    # 检查是否是 Python 项目
    py_files = list(Path(project_root).rglob("*.py"))
    if not py_files:
        print(" 该项目中未找到 Python 文件，跳过 Bandit 测试")
        return None
    
    print(f"发现 {len(py_files)} 个 Python 文件")
    
    print("\n执行扫描...")
    result = await tool.execute(
        target_path=".",
        severity="medium",
        max_results=10
    )
    
    print(f"执行成功: {result.success}")
    print(f"持续时间: {result.duration_ms}ms")
    print(f"元数据: {result.metadata}")
    print(f"\n结果:\n{result.to_string()[:2000]}")
    
    return result.success


async def test_gitleaks(project_root: str):
    """测试 Gitleaks 工具"""
    print("\n" + "="*60)
    print("🔐 测试 Gitleaks 工具")
    print("="*60)
    
    sandbox_manager = SandboxManager()
    tool = GitleaksTool(project_root, sandbox_manager)
    
    print(f"工具名称: {tool.name}")
    print(f"工具描述: {tool.description[:200]}...")
    
    print("\n执行扫描...")
    result = await tool.execute(
        target_path=".",
        no_git=True,
        max_results=10
    )
    
    print(f"执行成功: {result.success}")
    print(f"持续时间: {result.duration_ms}ms")
    print(f"元数据: {result.metadata}")
    print(f"\n结果:\n{result.to_string()[:2000]}")
    
    return result.success


async def test_npm_audit(project_root: str):
    """测试 npm audit 工具（仅限有 package.json 的项目）"""
    print("\n" + "="*60)
    print("测试 npm audit 工具")
    print("="*60)
    
    # 检查是否有 package.json
    package_json = Path(project_root) / "package.json"
    if not package_json.exists():
        print(" 未找到 package.json，跳过 npm audit 测试")
        return None
    
    sandbox_manager = SandboxManager()
    tool = NpmAuditTool(project_root, sandbox_manager)
    
    print(f"工具名称: {tool.name}")
    print(f"工具描述: {tool.description[:200]}...")
    
    print("\n执行扫描...")
    result = await tool.execute(
        target_path=".",
        production_only=False
    )
    
    print(f"执行成功: {result.success}")
    print(f"持续时间: {result.duration_ms}ms")
    print(f"元数据: {result.metadata}")
    print(f"\n结果:\n{result.to_string()[:2000]}")
    
    return result.success


async def test_safety(project_root: str):
    """测试 Safety 工具（仅限有 requirements.txt 的 Python 项目）"""
    print("\n" + "="*60)
    print("🐍 测试 Safety 工具")
    print("="*60)
    
    # 检查是否有 requirements.txt
    req_file = Path(project_root) / "requirements.txt"
    if not req_file.exists():
        print(" 未找到 requirements.txt，跳过 Safety 测试")
        return None
    
    sandbox_manager = SandboxManager()
    tool = SafetyTool(project_root, sandbox_manager)
    
    print(f"工具名称: {tool.name}")
    print(f"工具描述: {tool.description[:200]}...")
    
    print("\n执行扫描...")
    result = await tool.execute(requirements_file="requirements.txt")
    
    print(f"执行成功: {result.success}")
    print(f"持续时间: {result.duration_ms}ms")
    print(f"元数据: {result.metadata}")
    print(f"\n结果:\n{result.to_string()[:2000]}")
    
    return result.success


async def test_trufflehog(project_root: str):
    """测试 TruffleHog 工具"""
    print("\n" + "="*60)
    print(" 测试 TruffleHog 工具")
    print("="*60)
    
    sandbox_manager = SandboxManager()
    tool = TruffleHogTool(project_root, sandbox_manager)
    
    print(f"工具名称: {tool.name}")
    print(f"工具描述: {tool.description[:200]}...")
    
    print("\n执行扫描...")
    result = await tool.execute(
        target_path=".",
        only_verified=False
    )
    
    print(f"执行成功: {result.success}")
    print(f"持续时间: {result.duration_ms}ms")
    print(f"元数据: {result.metadata}")
    print(f"\n结果:\n{result.to_string()[:2000]}")
    
    return result.success


async def test_osv_scanner(project_root: str):
    """测试 OSV-Scanner 工具"""
    print("\n" + "="*60)
    print("测试 OSV-Scanner 工具")
    print("="*60)
    
    sandbox_manager = SandboxManager()
    tool = OSVScannerTool(project_root, sandbox_manager)
    
    print(f"工具名称: {tool.name}")
    print(f"工具描述: {tool.description[:200]}...")
    
    print("\n执行扫描...")
    result = await tool.execute(target_path=".")
    
    print(f"执行成功: {result.success}")
    print(f"持续时间: {result.duration_ms}ms")
    print(f"元数据: {result.metadata}")
    print(f"\n结果:\n{result.to_string()[:2000]}")
    
    return result.success

async def test_pmd(project_root: str):
    """测试 PMD 工具"""
    print("\n" + "="*60)
    print(" 测试 PMD Java 源码扫描工具")
    print("="*60)
    
    sandbox_manager = SandboxManager()
    
    from app.services.agent.tools.external_tools import PMDTool
    tool = PMDTool(project_root, sandbox_manager)
    
    print(f"工具名称: {tool.name}")
    print(f"工具描述: {tool.description[:200]}...")
    
    print("\n执行扫描...")
    # 使用本仓库内提供的 PMD 规则文件进行测试
    result = await tool.execute(
        target_path=".",
        ruleset="backend/app/db/rules_pmd/HardCodedCryptoKey.xml",
        max_results=30
    )
    
    print(f"执行成功: {result.success}")
    print(f"持续时间: {result.duration_ms}ms")
    print(f"元数据: {result.metadata}")
    print(f"\n结果:\n{result.to_string()[:2000]}")
    
    return result.success

async def test_phpstan(project_root: str):
    """测试 PHPStan 工具"""
    print("\n" + "="*60)
    print(" 测试 PHPStan PHP 静态分析工具")
    print("="*60)
    
    sandbox_manager = SandboxManager()
    
    from app.services.agent.tools.external_tools import PHPStanTool
    tool = PHPStanTool(project_root, sandbox_manager)
    
    print(f"工具名称: {tool.name}")
    print(f"工具描述: {tool.description[:200]}...")
    
    print("\n执行扫描...")
    result = await tool.execute(
        target_path=".",
        level=5,
        max_results=30
    )
    
    print(f"执行成功: {result.success}")
    print(f"持续时间: {result.duration_ms}ms")
    print(f"元数据: {result.metadata}")
    print(f"\n结果:\n{result.to_string()[:2000]}")
    
    return result.success

async def main():
    parser = argparse.ArgumentParser(
        description="手动测试外部安全工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 测试 Opengrep
  python test_external_tools_manual.py --tool opengrep

  # 测试所有工具
  python test_external_tools_manual.py --tool all

  # 测试特定项目路径
  python test_external_tools_manual.py --tool opengrep --path /path/to/project
        """
    )
    
    parser.add_argument(
        "--tool",
        choices=["opengrep", "bandit", "gitleaks", "npm_audit", "safety", "trufflehog", "osv_scanner","pmd","phpstan", "all"],
        default="all",
        help="要测试的工具（默认: all）"
    )
    
    parser.add_argument(
        "--path",
        default=".",
        help="要扫描的项目路径（默认: 当前目录）"
    )
    
    args = parser.parse_args()
    
    project_root = os.path.abspath(args.path)
    
    if not os.path.isdir(project_root):
        print(f"错误: {project_root} 不是一个有效的目录")
        sys.exit(1)
    
    print(f"📍 项目路径: {project_root}")
    
    # 检查 Docker 可用性
    print("\n检查 Docker 可用性...")
    sandbox_manager = SandboxManager()
    await sandbox_manager.initialize()
    
    if not sandbox_manager.is_available:
        print(f"Docker 不可用: {sandbox_manager.get_diagnosis()}")
        print("\n提示: 这些工具需要 Docker 才能运行。请先启动 Docker:")
        print("  docker daemon  # 或使用 Docker Desktop")
        sys.exit(1)
    
    print("Docker 可用")
    
    # 执行测试
    results = {}
    
    try:
        if args.tool in ["all", "opengrep"]:
            results["opengrep"] = await test_opengrep(project_root)
        
        if args.tool in ["all", "bandit"]:
            results["bandit"] = await test_bandit(project_root)
        
        if args.tool in ["all", "gitleaks"]:
            results["gitleaks"] = await test_gitleaks(project_root)
        
        if args.tool in ["all", "npm_audit"]:
            results["npm_audit"] = await test_npm_audit(project_root)
        
        if args.tool in ["all", "safety"]:
            results["safety"] = await test_safety(project_root)
        
        if args.tool in ["all", "trufflehog"]:
            results["trufflehog"] = await test_trufflehog(project_root)
        
        if args.tool in ["all", "osv_scanner"]:
            results["osv_scanner"] = await test_osv_scanner(project_root)

        if args.tool in ["all", "pmd"]:
            results["pmd"] = await test_pmd(project_root)

        if args.tool in ["all", "phpstan"]:
            results["phpstan"] = await test_phpstan(project_root)
        
    except KeyboardInterrupt:
        print("\n\n⏹️  测试被中断")
        sys.exit(0)
    except Exception as e:
        print(f"\n错误: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    
    # 总结
    print("\n" + "="*60)
    print("📊 测试总结")
    print("="*60)
    
    for tool_name, result in results.items():
        if result is None:
            status = "⏭️  跳过 (不适用)"
        elif result is True:
            status = "成功"
        else:
            status = "失败"
        
        print(f"{tool_name:15} {status}")


if __name__ == "__main__":
    asyncio.run(main())
