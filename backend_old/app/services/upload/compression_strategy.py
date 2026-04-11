from abc import ABC, abstractmethod
from typing import List, Dict, Any
import os

class CompressionStrategy(ABC):
    """
    压缩文件处理策略基类
    
    定义所有压缩格式必须实现的接口
    """
    
    @abstractmethod
    async def extract(self, file_path: str, extract_to: str) -> List[str]:
        """
        解压文件
        
        Args:
            file_path: 压缩文件路径
            extract_to: 解压目标目录
            
        Returns:
            解压后的文件列表 (相对路径)
        """
        pass
    
    @abstractmethod
    def validate(self, file_path: str) -> bool:
        """
        验证文件完整性
        
        Args:
            file_path: 文件路径
            
        Returns:
            是否有效
        """
        pass
    
    @abstractmethod
    def get_file_list(self, file_path: str) -> List[Dict[str, Any]]:
        """
        获取压缩包内文件列表（不解压）
        
        Args:
            file_path: 压缩文件路径
            
        Returns:
            文件列表，包含路径和大小信息
        """
        pass
    
    @property
    @abstractmethod
    def supported_extensions(self) -> List[str]:
        """
        支持的文件扩展名
        
        Returns:
            扩展名列表，如 ['.zip', '.ZIP']
        """
        pass