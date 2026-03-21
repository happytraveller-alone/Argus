from app.services import scanner as scanner_module


def test_scanner_module_no_longer_exports_legacy_runtime_scan_entrypoint():
    assert hasattr(scanner_module, "scan_repo_task") is False
