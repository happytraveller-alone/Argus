import zipfile
import tarfile
import os
from typing import List, Dict, Any, Optional
from pathlib import Path
from .compression_strategy import CompressionStrategy


def _preserve_tarinfo(
    tarinfo: tarfile.TarInfo,
    path: str,
) -> Optional[tarfile.TarInfo]:
    """
    Tar extraction filter.

    Python 3.12+ passes both `(tarinfo, path)` into the callback.
    Prefer the stdlib data filter when available for safer extraction,
    while keeping backward compatibility.
    """
    data_filter = getattr(tarfile, "data_filter", None)
    if callable(data_filter):
        return data_filter(tarinfo, path)
    return tarinfo


class ZipCompressionStrategy(CompressionStrategy):
    """ZIP 格式处理器"""

    @property
    def supported_extensions(self) -> List[str]:
        return [".zip", ".ZIP"]

    async def extract(self, file_path: str, extract_to: str) -> List[str]:
        """解压 ZIP 文件"""
        extracted_files = []
        try:
            with zipfile.ZipFile(file_path, "r") as zip_ref:
                # 验证 ZIP 文件
                bad_files = zip_ref.testzip()
                if bad_files:
                    raise ValueError(f"ZIP 文件损坏: {bad_files}")

                for member in zip_ref.namelist():
                    # 跳过目录
                    if not member.endswith("/"):
                        zip_ref.extract(member, extract_to)
                        extracted_files.append(member)

            return extracted_files
        except zipfile.BadZipFile as e:
            raise ValueError(f"无效的 ZIP 文件: {str(e)}")

    def validate(self, file_path: str) -> bool:
        """验证 ZIP 文件"""
        try:
            with zipfile.ZipFile(file_path, "r") as zip_ref:
                return zip_ref.testzip() is None
        except Exception:
            return False

    def get_file_list(self, file_path: str) -> List[Dict[str, Any]]:
        """获取 ZIP 内文件列表"""
        files = []
        try:
            with zipfile.ZipFile(file_path, "r") as zip_ref:
                for info in zip_ref.infolist():
                    if not info.is_dir():
                        files.append(
                            {
                                "path": info.filename,
                                "size": info.file_size,
                                "compressed_size": info.compress_size,
                            }
                        )
        except Exception as e:
            raise ValueError(f"读取 ZIP 文件失败: {str(e)}")
        return files


class TarCompressionStrategy(CompressionStrategy):
    """TAR 格式处理器"""

    @property
    def supported_extensions(self) -> List[str]:
        return [".tar"]

    async def extract(self, file_path: str, extract_to: str) -> List[str]:
        """解压 TAR 文件"""
        extracted_files = []
        try:
            with tarfile.open(file_path, "r") as tar_ref:
                for member in tar_ref.getmembers():
                    if not member.isdir():
                        tar_ref.extract(member, extract_to, filter=_preserve_tarinfo)
                        extracted_files.append(member.name)
            return extracted_files
        except tarfile.ReadError as e:
            raise ValueError(f"无效的 TAR 文件: {str(e)}")

    def validate(self, file_path: str) -> bool:
        """验证 TAR 文件"""
        try:
            with tarfile.open(file_path, "r") as tar_ref:
                return tar_ref.getmembers() is not None
        except Exception:
            return False

    def get_file_list(self, file_path: str) -> List[Dict[str, Any]]:
        """获取 TAR 内文件列表"""
        files = []
        try:
            with tarfile.open(file_path, "r") as tar_ref:
                for member in tar_ref.getmembers():
                    if not member.isdir():
                        files.append({"path": member.name, "size": member.size})
        except Exception as e:
            raise ValueError(f"读取 TAR 文件失败: {str(e)}")
        return files


class TarGzCompressionStrategy(CompressionStrategy):
    """TAR.GZ 格式处理器"""

    @property
    def supported_extensions(self) -> List[str]:
        return [".tar.gz", ".tgz", ".tar.gzip"]

    async def extract(self, file_path: str, extract_to: str) -> List[str]:
        """解压 TAR.GZ 文件"""
        extracted_files = []
        try:
            with tarfile.open(file_path, "r:gz") as tar_ref:
                for member in tar_ref.getmembers():
                    if not member.isdir():
                        tar_ref.extract(member, extract_to, filter=_preserve_tarinfo)
                        extracted_files.append(member.name)
            return extracted_files
        except (tarfile.ReadError, EOFError) as e:
            raise ValueError(f"无效的 TAR.GZ 文件: {str(e)}")

    def validate(self, file_path: str) -> bool:
        """验证 TAR.GZ 文件"""
        try:
            with tarfile.open(file_path, "r:gz") as tar_ref:
                return tar_ref.getmembers() is not None
        except Exception:
            return False

    def get_file_list(self, file_path: str) -> List[Dict[str, Any]]:
        """获取 TAR.GZ 内文件列表"""
        files = []
        try:
            with tarfile.open(file_path, "r:gz") as tar_ref:
                for member in tar_ref.getmembers():
                    if not member.isdir():
                        files.append({"path": member.name, "size": member.size})
        except Exception as e:
            raise ValueError(f"读取 TAR.GZ 文件失败: {str(e)}")
        return files


class TarBz2CompressionStrategy(CompressionStrategy):
    """TAR.BZ2 格式处理器"""

    @property
    def supported_extensions(self) -> List[str]:
        return [".tar.bz2", ".tbz", ".tbz2"]

    async def extract(self, file_path: str, extract_to: str) -> List[str]:
        """解压 TAR.BZ2 文件"""
        extracted_files = []
        try:
            with tarfile.open(file_path, "r:bz2") as tar_ref:
                for member in tar_ref.getmembers():
                    if not member.isdir():
                        tar_ref.extract(member, extract_to, filter=_preserve_tarinfo)
                        extracted_files.append(member.name)
            return extracted_files
        except (tarfile.ReadError, EOFError) as e:
            raise ValueError(f"无效的 TAR.BZ2 文件: {str(e)}")

    def validate(self, file_path: str) -> bool:
        """验证 TAR.BZ2 文件"""
        try:
            with tarfile.open(file_path, "r:bz2") as tar_ref:
                return tar_ref.getmembers() is not None
        except Exception:
            return False

    def get_file_list(self, file_path: str) -> List[Dict[str, Any]]:
        """获取 TAR.BZ2 内文件列表"""
        files = []
        try:
            with tarfile.open(file_path, "r:bz2") as tar_ref:
                for member in tar_ref.getmembers():
                    if not member.isdir():
                        files.append({"path": member.name, "size": member.size})
        except Exception as e:
            raise ValueError(f"读取 TAR.BZ2 文件失败: {str(e)}")
        return files


class SevenZCompressionStrategy(CompressionStrategy):
    """7Z 格式处理器"""

    @property
    def supported_extensions(self) -> List[str]:
        return [".7z"]

    async def extract(self, file_path: str, extract_to: str) -> List[str]:
        """解压 7Z 文件"""
        # 需要安装 py7zr 包: pip install py7zr
        try:
            import py7zr
        except ImportError:
            raise ImportError("需要安装 py7zr 包来支持 7Z 格式")

        extracted_files = []
        try:
            with py7zr.SevenZipFile(file_path, "r") as archive:
                archive.extractall(path=extract_to)
                # 获取文件列表
                for name, info in archive.list():
                    if not info.is_directory:
                        extracted_files.append(name)
        except Exception as e:
            raise ValueError(f"无效的 7Z 文件: {str(e)}")

        return extracted_files

    def validate(self, file_path: str) -> bool:
        """验证 7Z 文件"""
        try:
            import py7zr

            with py7zr.SevenZipFile(file_path, "r") as archive:
                archive.list()
            return True
        except Exception:
            return False

    def get_file_list(self, file_path: str) -> List[Dict[str, Any]]:
        """获取 7Z 内文件列表"""
        try:
            import py7zr
        except ImportError:
            raise ImportError("需要安装 py7zr 包来支持 7Z 格式")

        files = []
        try:
            with py7zr.SevenZipFile(file_path, "r") as archive:
                for name, info in archive.list():
                    if not info.is_directory:
                        files.append({"path": name, "size": info.uncompressed})
        except Exception as e:
            raise ValueError(f"读取 7Z 文件失败: {str(e)}")
        return files


class RarCompressionStrategy(CompressionStrategy):
    """RAR 格式处理器"""

    @property
    def supported_extensions(self) -> List[str]:
        return [".rar"]

    async def extract(self, file_path: str, extract_to: str) -> List[str]:
        """解压 RAR 文件"""
        # 需要安装 rarfile 包: pip install rarfile
        try:
            import rarfile
        except ImportError:
            raise ImportError("需要安装 rarfile 包来支持 RAR 格式")

        extracted_files = []
        try:
            with rarfile.RarFile(file_path, "r") as rar_ref:
                for member in rar_ref.infolist():
                    if not member.is_dir():
                        rar_ref.extract(member, extract_to)
                        extracted_files.append(member.filename)
        except Exception as e:
            raise ValueError(f"无效的 RAR 文件: {str(e)}")

        return extracted_files

    def validate(self, file_path: str) -> bool:
        """验证 RAR 文件"""
        try:
            import rarfile

            with rarfile.RarFile(file_path, "r") as rar_ref:
                return rar_ref.testrar() is None
        except Exception:
            return False

    def get_file_list(self, file_path: str) -> List[Dict[str, Any]]:
        """获取 RAR 内文件列表"""
        try:
            import rarfile
        except ImportError:
            raise ImportError("需要安装 rarfile 包来支持 RAR 格式")

        files = []
        try:
            with rarfile.RarFile(file_path, "r") as rar_ref:
                for info in rar_ref.infolist():
                    if not info.is_dir():
                        files.append({"path": info.filename, "size": info.file_size})
        except Exception as e:
            raise ValueError(f"读取 RAR 文件失败: {str(e)}")
        return files
