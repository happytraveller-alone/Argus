from typing import Optional
from pathlib import Path
from .compression_strategy import CompressionStrategy
from .compression_handlers import (
    ZipCompressionStrategy,
    TarCompressionStrategy,
    TarGzCompressionStrategy,
    TarBz2CompressionStrategy,
    SevenZCompressionStrategy,
    RarCompressionStrategy,
)


class CompressionStrategyFactory:
    """
    工厂类：根据文件扩展名返回对应的处理策略
    
    使用单例模式管理所有策略
    """
    
    _strategies = {
        '.zip': ZipCompressionStrategy(),
        '.ZIP': ZipCompressionStrategy(),
        '.tar': TarCompressionStrategy(),
        '.tar.gz': TarGzCompressionStrategy(),
        '.tgz': TarGzCompressionStrategy(),
        '.tar.gzip': TarGzCompressionStrategy(),
        '.tar.bz2': TarBz2CompressionStrategy(),
        '.tbz': TarBz2CompressionStrategy(),
        '.tbz2': TarBz2CompressionStrategy(),
        '.7z': SevenZCompressionStrategy(),
        '.rar': RarCompressionStrategy(),
    }
    
    @classmethod
    def get_strategy(self, file_path: str) -> Optional[CompressionStrategy]:
        """
        根据文件路径获取对应的策略
        
        Args:
            file_path: 文件路径
            
        Returns:
            策略实例，如果不支持则返回 None
        """
        path = Path(file_path)
        
        # 检查 .tar.gz / .tar.bz2 等复合扩展名
        if path.suffix in ['.gz', '.bz2', '.gzip']:
            compound_ext = path.suffixes[-2:] if len(path.suffixes) >= 2 else None
            if compound_ext:
                compound_ext_str = ''.join(compound_ext)
                if compound_ext_str in self._strategies:
                    return self._strategies[compound_ext_str]
        
        # 检查单一扩展名
        suffix = path.suffix
        return self._strategies.get(suffix)
    
    @classmethod
    def is_supported(cls, file_path: str) -> bool:
        """检查文件格式是否支持"""
        return cls.get_strategy(file_path) is not None
    
    @classmethod
    def get_supported_formats(cls) -> set:
        """获取所有支持的格式"""
        return set(cls._strategies.keys())
    
    @classmethod
    def register_strategy(cls, extension: str, strategy: CompressionStrategy):
        """
        注册新的策略（用于扩展）
        
        Args:
            extension: 文件扩展名，如 '.zip'
            strategy: 策略实例
        """
        cls._strategies[extension] = strategy