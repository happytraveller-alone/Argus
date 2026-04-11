from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_legacy_backend_main_module_has_been_retired():
    main_path = PROJECT_ROOT / "app/main.py"
    assert not main_path.exists()
