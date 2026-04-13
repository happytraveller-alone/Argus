from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_legacy_backend_main_module_has_been_retired():
    main_path = PROJECT_ROOT / "app/main.py"
    assert not main_path.exists()


def test_legacy_root_main_script_has_been_retired():
    root_main_path = PROJECT_ROOT / "main.py"
    assert not root_main_path.exists()


def test_legacy_root_verify_llm_script_has_been_retired():
    verify_path = PROJECT_ROOT / "verify_llm.py"
    assert not verify_path.exists()


def test_legacy_root_check_docker_direct_script_has_been_retired():
    docker_check_path = PROJECT_ROOT / "check_docker_direct.py"
    assert not docker_check_path.exists()


def test_legacy_root_check_sandbox_script_has_been_retired():
    sandbox_check_path = PROJECT_ROOT / "check_sandbox.py"
    assert not sandbox_check_path.exists()
