import os
import shutil
import json
from typing import List, Dict, Any, Optional
from pathlib import Path
from .compression_factory import CompressionStrategyFactory
from .compression_strategy import CompressionStrategy


class UploadManager:
    """
    统一的上传管理器
    
    负责：
    1. 验证上传的文件
    2. 根据格式选择合适的解压策略
    3. 处理目录上传
    4. 管理文件生命周期
    """
    
    # 支持的最大文件大小：500MB
    MAX_FILE_SIZE = 500 * 1024 * 1024
    
    # 支持的最大目录大小：1GB
    MAX_DIRECTORY_SIZE = 1 * 1024 * 1024 * 1024
    
    @staticmethod
    def validate_file(file_path: str) -> tuple[bool, Optional[str]]:
        """
        验证上传的文件
        
        Returns:
            (is_valid, error_message)
        """
        if not os.path.exists(file_path):
            return False, "文件不存在"
        
        file_size = os.path.getsize(file_path)
        if file_size > UploadManager.MAX_FILE_SIZE:
            return False, f"文件大小超过 {UploadManager.MAX_FILE_SIZE / (1024*1024):.0f}MB 限制"
        
        if file_size == 0:
            return False, "文件为空"
        
        # 检查格式是否支持
        if not CompressionStrategyFactory.is_supported(file_path):
            supported = CompressionStrategyFactory.get_supported_formats()
            return False, f"不支持的文件格式。支持的格式: {', '.join(sorted(supported))}"
        
        # 验证文件完整性
        strategy = CompressionStrategyFactory.get_strategy(file_path)
        if strategy and not strategy.validate(file_path):
            return False, "文件损坏或不完整"
        
        return True, None
    
    @staticmethod
    async def extract_file(
        file_path: str,
        extract_to: str,
        max_files: int = 10000
    ) -> tuple[bool, List[str], Optional[str]]:
        """
        解压文件
        
        Args:
            file_path: 压缩文件路径
            extract_to: 解压目标目录
            max_files: 最大解压文件数限制
            
        Returns:
            (success, file_list, error_message)
        """
        try:
            strategy = CompressionStrategyFactory.get_strategy(file_path)
            if not strategy:
                return False, [], "不支持的文件格式"
            
            # 创建解压目录
            os.makedirs(extract_to, exist_ok=True)
            
            # 执行解压
            extracted_files = await strategy.extract(file_path, extract_to)
            
            # 检查文件数量限制
            if len(extracted_files) > max_files:
                # 清理已解压的文件
                shutil.rmtree(extract_to)
                return False, [], f"解压文件数超过 {max_files} 个限制"
            
            # 检查解压后的大小
            total_size = 0
            for root, dirs, files in os.walk(extract_to):
                for file in files:
                    file_path_full = os.path.join(root, file)
                    total_size += os.path.getsize(file_path_full)
                    if total_size > UploadManager.MAX_DIRECTORY_SIZE:
                        shutil.rmtree(extract_to)
                        return False, [], f"解压后大小超过 {UploadManager.MAX_DIRECTORY_SIZE / (1024*1024*1024):.0f}GB 限制"
            
            return True, extracted_files, None
        
        except Exception as e:
            # 清理失败的解压目录
            if os.path.exists(extract_to):
                shutil.rmtree(extract_to)
            return False, [], f"解压失败: {str(e)}"
    
    @staticmethod
    def get_file_list_preview(
        file_path: str,
        limit: int = 100
    ) -> tuple[bool, List[Dict[str, Any]], Optional[str]]:
        """
        获取压缩文件内的文件列表预览（不解压）
        
        Args:
            file_path: 压缩文件路径
            limit: 返回的最大文件数
            
        Returns:
            (success, file_list, error_message)
        """
        try:
            strategy = CompressionStrategyFactory.get_strategy(file_path)
            if not strategy:
                return False, [], "不支持的文件格式"
            
            file_list = strategy.get_file_list(file_path)
            
            # 只返回前 N 个文件
            if len(file_list) > limit:
                total_files = len(file_list)
                file_list = file_list[:limit]
                file_list.append({
                    'path': f'... 还有 {total_files - limit} 个文件',
                    'size': 0
                })
            
            return True, file_list, None
        
        except Exception as e:
            return False, [], f"获取文件列表失败: {str(e)}"
    
    @staticmethod
    def get_directory_structure(directory: str, max_depth: int = 3) -> Dict[str, Any]:
        """
        获取目录结构信息（用于目录上传预览）
        
        Args:
            directory: 目录路径
            max_depth: 最大遍历深度
            
        Returns:
            目录结构信息
        """
        def scan_dir(path: str, current_depth: int = 0) -> Dict[str, Any]:
            if current_depth >= max_depth:
                return {'name': Path(path).name, 'type': 'directory', 'children': []}
            
            info = {
                'name': Path(path).name,
                'type': 'directory',
                'children': []
            }
            
            try:
                for item in sorted(os.listdir(path)):
                    item_path = os.path.join(path, item)
                    if os.path.isdir(item_path):
                        info['children'].append(scan_dir(item_path, current_depth + 1))
                    else:
                        info['children'].append({
                            'name': item,
                            'type': 'file',
                            'size': os.path.getsize(item_path)
                        })
            except PermissionError:
                pass
            
            return info
        
        return scan_dir(directory)
    
    @staticmethod
    def get_directory_size(directory: str) -> int:
        """计算目录总大小"""
        total = 0
        try:
            for dirpath, dirnames, filenames in os.walk(directory):
                for filename in filenames:
                    filepath = os.path.join(dirpath, filename)
                    try:
                        total += os.path.getsize(filepath)
                    except OSError:
                        pass
        except Exception:
            pass
        return total
