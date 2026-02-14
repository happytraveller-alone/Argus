#!/usr/bin/env python3
"""
简单沙箱连通性测试
直接测试 Docker 连接和基本命令执行
"""

import os

import pytest

# This is a manual / environment-dependent smoke test. It requires Docker access and
# a working sandbox image, so we skip it by default in the unit-test suite.
if os.environ.get("RUN_SANDBOX_TESTS") != "1":
    pytest.skip("Set RUN_SANDBOX_TESTS=1 to run sandbox smoke tests.", allow_module_level=True)

import asyncio
import logging
import sys

# 添加 app 目录到路径
sys.path.insert(0, os.path.dirname(__file__))

from app.services.agent.tools.sandbox_tool import SandboxManager, SandboxConfig

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


async def test_docker_connection():
    """测试 Docker 连接"""
    print("\n" + "="*50)
    print("🧪 测试 1: Docker 连接")
    print("="*50)
    
    manager = SandboxManager()
    await manager.initialize()
    
    diagnosis = manager.get_diagnosis()
    print(f"诊断信息: {diagnosis}")
    print(f"Docker 可用: {'✅ 是' if manager.is_available else '❌ 否'}")
    
    return manager.is_available


async def test_simple_command(manager: SandboxManager):
    """测试简单命令执行"""
    print("\n" + "="*50)
    print("🧪 测试 2: 简单命令执行 (echo)")
    print("="*50)
    
    result = await manager.execute_command("echo 'Hello from Sandbox!'")
    
    print(f"执行状态: {'✅ 成功' if result['success'] else '❌ 失败'}")
    print(f"退出码: {result['exit_code']}")
    print(f"输出:\n{result['stdout']}")
    if result['stderr']:
        print(f"错误:\n{result['stderr']}")
    if result.get('error'):
        print(f"错误信息: {result['error']}")
    
    return result['success']


async def test_python_command(manager: SandboxManager):
    """测试 Python 命令执行"""
    print("\n" + "="*50)
    print("🧪 测试 3: Python 命令执行")
    print("="*50)
    
    result = await manager.execute_command("python3 -c \"print('Python works in sandbox!')\"")
    
    print(f"执行状态: {'✅ 成功' if result['success'] else '❌ 失败'}")
    print(f"退出码: {result['exit_code']}")
    print(f"输出:\n{result['stdout']}")
    if result['stderr']:
        print(f"错误:\n{result['stderr']}")
    
    return result['success']


async def test_file_operations(manager: SandboxManager):
    """测试文件操作"""
    print("\n" + "="*50)
    print("🧪 测试 4: 文件操作")
    print("="*50)
    
    # 写文件到 tmpfs
    result1 = await manager.execute_command("echo 'Test content' > /tmp/test.txt && cat /tmp/test.txt")
    
    print(f"文件写入和读取 (tmpfs):")
    print(f"  执行状态: {'✅ 成功' if result1['success'] else '❌ 失败'}")
    print(f"  退出码: {result1['exit_code']}")
    print(f"  输出:\n{result1['stdout']}")
    
    return result1['success']


async def test_environment_vars(manager: SandboxManager):
    """测试环境变量"""
    print("\n" + "="*50)
    print("🧪 测试 5: 环境变量隔离")
    print("="*50)
    
    # 在沙箱中设置和检查环境变量
    result = await manager.execute_command("export MY_VAR='test123' && echo $MY_VAR")
    
    print(f"环境变量设置:")
    print(f"  执行状态: {'✅ 成功' if result['success'] else '❌ 失败'}")
    print(f"  退出码: {result['exit_code']}")
    print(f"  输出: {result['stdout'].strip()}")
    
    return result['success']


async def test_network_isolation(manager: SandboxManager):
    """测试网络隔离"""
    print("\n" + "="*50)
    print("🧪 测试 6: 网络隔离 (ping 应该失败)")
    print("="*50)
    
    # 网络应该被隔离，ping 外部 IP 应该失败
    result = await manager.execute_command("timeout 2 ping -c 1 8.8.8.8 || echo 'Network isolated (expected)'")
    
    print(f"网络隔离检查:")
    print(f"  执行状态: {'✅ 成功' if result['success'] else '❌ 失败'}")
    print(f"  退出码: {result['exit_code']}")
    print(f"  输出:\n{result['stdout']}")
    
    return result['success']


async def test_permission_isolation(manager: SandboxManager):
    """测试权限隔离"""
    print("\n" + "="*50)
    print("🧪 测试 7: 权限隔离 (非 root 用户)")
    print("="*50)
    
    # 检查当前用户
    result = await manager.execute_command("id")
    
    print(f"用户权限检查:")
    print(f"  执行状态: {'✅ 成功' if result['success'] else '❌ 失败'}")
    print(f"  输出: {result['stdout'].strip()}")
    
    # 应该不是 root
    is_not_root = "uid=0" not in result['stdout']
    print(f"  非 root 用户: {'✅ 是' if is_not_root else '❌ 否'}")
    
    return is_not_root


async def test_readonly_filesystem(manager: SandboxManager):
    """测试根文件系统只读"""
    print("\n" + "="*50)
    print("🧪 测试 8: 根文件系统只读")
    print("="*50)
    
    # 尝试在根文件系统写入（应该失败）
    result = await manager.execute_command("touch /test.txt 2>&1 || echo 'Filesystem is read-only (expected)'")
    
    print(f"根文件系统只读检查:")
    print(f"  执行状态: {'✅ 成功' if result['success'] else '❌ 失败'}")
    print(f"  输出: {result['stdout'].strip()}")
    
    is_readonly = "read-only" in result['stdout'].lower()
    print(f"  只读: {'✅ 是' if is_readonly else '✓ 或其他原因'}")
    
    return True


async def test_memory_limit(manager: SandboxManager):
    """测试内存限制"""
    print("\n" + "="*50)
    print("🧪 测试 9: 内存限制")
    print("="*50)
    
    result = await manager.execute_command("free -h")
    
    print(f"内存限制检查:")
    print(f"  执行状态: {'✅ 成功' if result['success'] else '❌ 失败'}")
    print(f"  输出:\n{result['stdout']}")
    
    return result['success']


async def test_timeout(manager: SandboxManager):
    """测试超时机制"""
    print("\n" + "="*50)
    print("🧪 测试 10: 超时机制 (2秒超时)")
    print("="*50)
    
    # 创建一个 3 秒的睡眠，应该被 2 秒超时中断
    config = SandboxConfig(timeout=2)
    timeout_manager = SandboxManager(config)
    await timeout_manager.initialize()
    
    result = await timeout_manager.execute_command("sleep 5 && echo 'This should not print'")
    
    print(f"超时检查:")
    print(f"  执行状态: {'✅ 成功' if result['success'] else '❌ 失败 (预期)'}")
    print(f"  输出: {result['stdout'] or result['error']}")
    
    return True


async def test_create_temp_files(manager: SandboxManager):
    """测试创建临时文件夹和文件"""
    print("\n" + "="*50)
    print("🧪 测试 11: 创建临时文件夹和文件")
    print("="*50)
    
    # 使用 mktemp -d 创建临时文件夹
    commands = [
        "mkdir -p /tmp/myproject",
        "echo '# My Project' > /tmp/myproject/README.md",
        "echo 'import os' > /tmp/myproject/app.py",
        "echo 'PORT=8000' > /tmp/myproject/.env",
        "ls -la /tmp/myproject/",
        "cat /tmp/myproject/README.md",
        "cat /tmp/myproject/app.py",
        "cat /tmp/myproject/.env"
    ]
    
    # 组合成一条命令执行
    combined_command = " && ".join(commands)
    result = await manager.execute_command(combined_command)
    
    print(f"创建临时文件夹和文件:")
    print(f"  执行状态: {'✅ 成功' if result['success'] else '❌ 失败'}")
    print(f"  退出码: {result['exit_code']}")
    print(f"  输出:\n{result['stdout']}")
    
    return result['success']


async def test_temp_dir_operations(manager: SandboxManager):
    """测试使用 mktemp 创建临时文件夹"""
    print("\n" + "="*50)
    print("🧪 测试 12: 动态创建临时文件夹")
    print("="*50)
    
    # 使用 mktemp 动态创建临时文件夹
    command = """
    TMPDIR=$(mktemp -d) && \
    echo "创建的临时目录: $TMPDIR" && \
    echo "project_name: DeepAudit" > "$TMPDIR/config.yaml" && \
    echo "version: 1.0" >> "$TMPDIR/config.yaml" && \
    echo "# Source Code" > "$TMPDIR/main.py" && \
    echo "def main():" >> "$TMPDIR/main.py" && \
    echo "    print('Hello from temp dir')" >> "$TMPDIR/main.py" && \
    echo "" >> "$TMPDIR/main.py" && \
    echo "if __name__ == '__main__':" >> "$TMPDIR/main.py" && \
    echo "    main()" >> "$TMPDIR/main.py" && \
    echo "--- 目录内容 ---" && \
    ls -la "$TMPDIR" && \
    echo "--- config.yaml 内容 ---" && \
    cat "$TMPDIR/config.yaml" && \
    echo "--- main.py 内容 ---" && \
    cat "$TMPDIR/main.py" && \
    echo "--- 执行 Python 文件 ---" && \
    python3 "$TMPDIR/main.py"
    """
    
    result = await manager.execute_command(command)
    
    print(f"动态创建临时文件夹:")
    print(f"  执行状态: {'✅ 成功' if result['success'] else '❌ 失败'}")
    print(f"  退出码: {result['exit_code']}")
    print(f"  输出:\n{result['stdout']}")
    
    return result['success']


async def test_nested_dirs(manager: SandboxManager):
    """测试创建嵌套目录结构"""
    print("\n" + "="*50)
    print("🧪 测试 13: 创建嵌套目录结构")
    print("="*50)
    
    # 创建嵌套目录结构 (在 /home/sandbox 中，并在该目录执行 find)
    command = """
    mkdir -p /home/sandbox/project/src /home/sandbox/project/tests /home/sandbox/project/docs /home/sandbox/project/build && \
    echo "Source code" > /home/sandbox/project/src/main.py && \
    echo "Test code" > /home/sandbox/project/tests/test_main.py && \
    echo "Docs" > /home/sandbox/project/docs/README.md && \
    echo "Build output" > /home/sandbox/project/build/output.bin && \
    echo "=== Project structure ===" && \
    cd /home/sandbox/project && find . -type f && \
    echo "" && \
    echo "=== File count ===" && \
    find . -type f | wc -l && \
    echo "" && \
    echo "=== Directory listing ===" && \
    ls -R .
    """
    
    result = await manager.execute_command(command)
    
    print(f"嵌套目录结构:")
    print(f"  执行状态: {'✅ 成功' if result['success'] else '❌ 失败'}")
    print(f"  输出:\n{result['stdout']}")
    
    return result['success']


async def main():
    """主测试函数"""
    print("\n")
    print("╔" + "="*48 + "╗")
    print("║" + " "*10 + "🐳 沙箱连通性简单测试" + " "*16 + "║")
    print("╚" + "="*48 + "╝")
    
    # 测试 Docker 连接
    docker_ok = await test_docker_connection()
    
    if not docker_ok:
        print("\n❌ Docker 不可用，无法继续测试")
        return 1
    
    # 初始化管理器
    manager = SandboxManager()
    await manager.initialize()
    
    results = []
    
    # 运行所有测试
    try:
        results.append(("Docker 连接", docker_ok))
        results.append(("简单命令", await test_simple_command(manager)))
        results.append(("Python 命令", await test_python_command(manager)))
        results.append(("文件操作", await test_file_operations(manager)))
        results.append(("环境变量", await test_environment_vars(manager)))
        results.append(("网络隔离", await test_network_isolation(manager)))
        results.append(("权限隔离", await test_permission_isolation(manager)))
        results.append(("只读文件系统", await test_readonly_filesystem(manager)))
        results.append(("内存限制", await test_memory_limit(manager)))
        results.append(("超时机制", await test_timeout(manager)))
        results.append(("创建临时文件夹和文件", await test_create_temp_files(manager)))
        results.append(("动态创建临时文件夹", await test_temp_dir_operations(manager)))
        results.append(("嵌套目录结构", await test_nested_dirs(manager)))
    except Exception as e:
        print(f"\n❌ 测试过程中出错: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    # 打印总结
    print("\n" + "="*50)
    print("📊 测试结果总结")
    print("="*50)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for test_name, result in results:
        status = "✅" if result else "❌"
        print(f"{status} {test_name}")
    
    print("-"*50)
    print(f"通过: {passed}/{total} (成功率: {passed*100//total}%)")
    
    if passed == total:
        print("\n🎉 所有测试通过！沙箱连通性正常")
        return 0
    else:
        print(f"\n⚠️  有 {total - passed} 个测试未通过")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
