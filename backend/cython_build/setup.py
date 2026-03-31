"""
Cython 编译脚本 - 将 backend/app/ 下可编译的 Python 模块编译为 .so 扩展

策略：排除法（排除已知不可编译的文件，其余全量编译）

使用方式：
    cd /build
    python cython_build/setup.py build_ext --build-lib /build/compiled --build-temp /build/tmp
"""

import fnmatch
import os
from pathlib import Path

from Cython.Build import cythonize
from Cython.Compiler import Options
from setuptools import setup

# ── 编译器全局选项 ──────────────────────────────────────────
Options.docstrings = False   # 剥除 docstring，减小 .so 体积
Options.annotate = False     # 不生成 HTML 注解文件

# ── 不编译的文件/目录模式（相对于 app/ 根目录）───────────────
# 规则：如果 rel_path 或 basename 匹配任意模式，则排除
EXCLUDE_PATTERNS = [
    # Python 包标识文件（保持包注册）
    "__init__.py",
    # 应用入口点（CMD 直接引用）
    "main.py",
    "runtime/container_startup.py",
    # 启动器脚本（COPY --chmod=755 可执行文件，不能编译为 .so）
    "runtime/launchers/*.py",
    # Alembic migration baseline（Alembic 解析时要求源文件）
    "db/schema_snapshots/*.py",
    # 补丁文件（非应用代码）
    "db/patches/*.py",
]

APP_DIR = Path(__file__).resolve().parent.parent / "app"


def should_exclude(rel_path: str) -> bool:
    """判断文件是否应排除编译（相对于 app/ 的路径）"""
    basename = Path(rel_path).name
    for pattern in EXCLUDE_PATTERNS:
        # 精确路径匹配（包含目录分隔符的模式）
        if fnmatch.fnmatch(rel_path, pattern):
            return True
        # 文件名匹配（不含目录分隔符的模式）
        if "/" not in pattern and fnmatch.fnmatch(basename, pattern):
            return True
    return False


def collect_modules() -> list[str]:
    """收集所有待编译的 Python 文件路径（绝对路径）"""
    all_py = sorted(APP_DIR.rglob("*.py"))
    result = []
    excluded = []

    for f in all_py:
        rel = str(f.relative_to(APP_DIR))
        if should_exclude(rel):
            excluded.append(rel)
        else:
            result.append(str(f))

    print(f"[Cython] 待编译模块数: {len(result)}, 排除模块数: {len(excluded)}")
    if excluded:
        print("[Cython] 排除列表（前20条）:")
        for e in excluded[:20]:
            print(f"  - {e}")
    return result


ext_modules = cythonize(
    collect_modules(),
    compiler_directives={
        "language_level": "3",
        "embedsignature": False,     # 不在 .so 中嵌入 docstring 签名
        "annotation_typing": False,  # 关键：忽略类型注解中的 Cython C 类型
                                     # （避免与 Pydantic v2 / dataclass / SQLAlchemy 冲突）
        "cdivision": False,          # 保持 Python 语义的整除
        "boundscheck": True,         # 保持 Python 语义的边界检查
        "wraparound": True,          # 保持 Python 的负索引语义
    },
    nthreads=os.cpu_count() or 4,
    quiet=False,
    include_path=[str(APP_DIR.parent)],  # 允许 cimport app.*
)

setup(
    name="vulhunter-backend-compiled",
    ext_modules=ext_modules,
)
