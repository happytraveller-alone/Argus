#!/usr/bin/env python
"""
测试文件树接口实现
"""
import asyncio
import json
import zipfile
import tempfile
import os
from pathlib import Path
from app.api.v1.endpoints.projects import (
    _build_file_tree_from_zip,
    _build_file_tree_from_repo_files,
    FileTreeNode,
    FileTreeResponse,
)


async def test_build_zip_tree():
    """测试从ZIP构建文件树"""
    print("\n" + "="*60)
    print("测试1: 从ZIP文件构建文件树")
    print("="*60)
    
    # 创建测试ZIP文件
    with tempfile.TemporaryDirectory() as tmpdir:
        zip_path = os.path.join(tmpdir, "test.zip")
        
        # 创建测试文件结构
        test_files = {
            "README.md": b"# Test Project",
            "src/main.py": b"print('hello')",
            "src/utils/helpers.py": b"def help(): pass",
            "src/utils/config.py": b"CONFIG = {}",
            "tests/test_main.py": b"assert True",
            "docs/guide.md": b"# Guide",
            ".gitignore": b"*.pyc",
        }
        
        # 创建ZIP
        with zipfile.ZipFile(zip_path, 'w') as zf:
            for path, content in test_files.items():
                zf.writestr(path, content)
        
        print(f"创建测试ZIP文件: {zip_path}")
        print(f"   包含 {len(test_files)} 个文件")
        
        # 构建树
        loop = asyncio.get_event_loop()
        tree = await loop.run_in_executor(None, _build_file_tree_from_zip, zip_path)
        
        print(f"\n文件树结构:")
        print(f"   根节点: {tree.name} (type={tree.type})")
        print(f"   直接子节点数: {len(tree.children) if tree.children else 0}")
        
        # 检查结构
        if tree.children:
            for child in sorted(tree.children, key=lambda x: x.name):
                prefix = "📁" if child.type == "directory" else ""
                size_info = f" ({child.size} bytes)" if child.size else ""
                print(f"   {prefix} {child.name}{size_info}")
                
                # 如果是目录，显示子文件
                if child.type == "directory" and child.children:
                    for subchild in sorted(child.children, key=lambda x: x.name):
                        subprefix = "📁" if subchild.type == "directory" else ""
                        sub_size = f" ({subchild.size} bytes)" if subchild.size else ""
                        print(f"      {subprefix} {subchild.name}{sub_size}")
        
        # JSON序列化测试
        response = FileTreeResponse(root=tree)
        json_str = response.model_dump_json(indent=2)
        parsed = json.loads(json_str)
        print(f"\nJSON序列化成功，输出大小: {len(json_str)} 字符")
        

async def test_build_repo_tree():
    """测试从仓库文件列表构建文件树"""
    print("\n" + "="*60)
    print("测试2: 从仓库文件列表构建文件树")
    print("="*60)
    
    # 模拟仓库文件列表
    files = [
        {"path": "LICENSE", "size": 1024},
        {"path": "README.md", "size": 2048},
        {"path": "package.json", "size": 512},
        {"path": "src/index.js", "size": 4096},
        {"path": "src/utils/helpers.js", "size": 2048},
        {"path": "src/utils/validators.js", "size": 1536},
        {"path": "src/components/Button.jsx", "size": 3072},
        {"path": "src/components/Input.jsx", "size": 2560},
        {"path": "tests/unit/main.test.js", "size": 5120},
        {"path": "tests/e2e/app.test.js", "size": 4096},
        {"path": "docs/API.md", "size": 8192},
        {"path": "docs/SETUP.md", "size": 3584},
    ]
    
    print(f"创建模拟仓库文件列表: {len(files)} 文件")
    
    # 构建树
    tree = _build_file_tree_from_repo_files(files)
    
    print(f"\n文件树结构:")
    print(f"   根节点: {tree.name} (type={tree.type})")
    print(f"   直接子节点数: {len(tree.children) if tree.children else 0}")
    
    # 显示前几层结构
    def print_tree(node, depth=0):
        if node.children:
            for child in node.children:
                prefix = "  " * depth + ("📁" if child.type == "directory" else "")
                size_info = f" ({child.size} bytes)" if child.size else ""
                print(f"{prefix} {child.name}{size_info}")
                print_tree(child, depth + 1)
    
    print_tree(tree)
    
    # JSON序列化测试
    response = FileTreeResponse(root=tree)
    json_str = response.model_dump_json(indent=2)
    parsed = json.loads(json_str)
    print(f"\nJSON序列化成功，输出大小: {len(json_str)} 字符")
    
    # 验证树的完整性
    assert tree.type == "directory"
    assert len(tree.children) == 6  # LICENSE, README.md, package.json, src, tests, docs
    
    src_dir = next((c for c in tree.children if c.name == "src"), None)
    assert src_dir is not None
    assert src_dir.type == "directory"
    assert len(src_dir.children) == 3  # index.js, utils, components
    
    print("\n树结构验证通过")


async def test_tree_properties():
    """测试树节点的属性和排序"""
    print("\n" + "="*60)
    print("测试3: 树节点属性和排序")
    print("="*60)
    
    files = [
        {"path": "z-file.txt", "size": 100},
        {"path": "a-dir/file1.txt", "size": 50},
        {"path": "a-dir/file2.txt", "size": 75},
        {"path": "b-dir/file1.txt", "size": 60},
    ]
    
    tree = _build_file_tree_from_repo_files(files)
    
    print(f"树节点验证:")
    print(f"   根节点path: '{tree.path}'")
    print(f"   根节点type: {tree.type}")
    
    # 验证排序（目录优先）
    children_names = [c.name for c in tree.children]
    print(f"   子节点排序: {children_names}")
    
    # 确认目录在前
    dirs = [c for c in tree.children if c.type == "directory"]
    files_list = [c for c in tree.children if c.type == "file"]
    assert len(dirs) == 2 and len(files_list) == 1
    assert tree.children[0].type == "directory"
    assert tree.children[-1].type == "file"
    
    print(f"   ✓ 排序验证通过（目录优先，然后按字母排序）")


async def main():
    """运行所有测试"""
    print("\n" + "🧪 开始测试文件树实现".center(60))
    
    try:
        await test_build_zip_tree()
        await test_build_repo_tree()
        await test_tree_properties()
        
        print("\n" + "="*60)
        print("所有测试通过！".center(60))
        print("="*60 + "\n")
        
    except Exception as e:
        print(f"\n测试失败: {e}")
        import traceback
        traceback.print_exc()
        exit(1)


if __name__ == "__main__":
    asyncio.run(main())
