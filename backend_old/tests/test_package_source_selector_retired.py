from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RETIRED_SELECTOR_PATH = PROJECT_ROOT / "scripts/package_source_selector.py"
SELECTOR_REFERENCE_TARGETS = (
    PROJECT_ROOT / "scripts/dev-entrypoint.sh",
    PROJECT_ROOT.parent / "docker/backend_old.Dockerfile",
    PROJECT_ROOT.parent / "docker/flow-parser-runner.Dockerfile",
)


def test_package_source_selector_script_stays_deleted():
    assert not RETIRED_SELECTOR_PATH.exists(), (
        "package source selector should be rust-owned and the legacy python script must stay deleted"
    )


def test_package_source_selector_has_no_live_shell_or_docker_references():
    offenders: list[str] = []
    for path in SELECTOR_REFERENCE_TARGETS:
        text = path.read_text(encoding="utf-8")
        if "package_source_selector.py" in text:
            offenders.append(str(path))

    assert not offenders, (
        "legacy package_source_selector.py references should stay removed:\n"
        + "\n".join(offenders)
    )
