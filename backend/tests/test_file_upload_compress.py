import zipfile
from pathlib import Path

import pytest

from app.services.upload.compression_factory import CompressionStrategyFactory
from app.services.upload.upload_manager import UploadManager


@pytest.mark.asyncio
async def test_upload_manager_with_generated_zip(tmp_path: Path):
    test_file = tmp_path / "fastjson.zip"
    with zipfile.ZipFile(test_file, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("fastjson/src/main/java/com/example/App.java", "class App {}\n")

    is_valid, error = UploadManager.validate_file(test_file)
    assert is_valid is True
    assert error is None

    success, files, error = UploadManager.get_file_list_preview(test_file)
    assert success is True
    assert error is None
    assert any(item["path"].endswith("App.java") for item in files)

    extract_dir = tmp_path / "extracted"
    success, file_list, error = await UploadManager.extract_file(test_file, str(extract_dir))
    assert success is True
    assert error is None
    assert any(path.endswith("App.java") for path in file_list)
    assert (extract_dir / "fastjson/src/main/java/com/example/App.java").exists()

    formats = CompressionStrategyFactory.get_supported_formats()
    assert ".zip" in formats
