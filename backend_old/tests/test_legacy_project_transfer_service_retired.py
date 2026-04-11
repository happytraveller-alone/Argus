from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_legacy_project_transfer_service_module_has_been_retired():
    service_path = PROJECT_ROOT / "app/services/project_transfer_service.py"
    assert not service_path.exists()
