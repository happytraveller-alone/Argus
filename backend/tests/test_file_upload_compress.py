from app.services.upload.upload_manager import UploadManager
from app.services.upload.compression_factory import CompressionStrategyFactory
import tempfile
from pathlib import Path
import asyncio


async def test_upload_manager():
    tests_dir = Path(__file__).parent
    test_file = tests_dir / "resources" / "fastjson.zip"
    print(f"Testing with file: {test_file}")
    is_valid, error = UploadManager.validate_file(test_file)
    print(f"Validation: {is_valid}, Error: {error}")
    success, files, error = UploadManager.get_file_list_preview(test_file)
    print(f"File list preview success: {success}, Files: {files}, Error: {error}")
    with tempfile.TemporaryDirectory() as tmpdir:
        success, file_list, error = await UploadManager.extract_file(test_file, tmpdir)
        print(f"Extracted files to {tmpdir}: {file_list}")

    # 4. 查询支持的格式
    formats = CompressionStrategyFactory.get_supported_formats()
    print(formats)

asyncio.run(test_upload_manager())
