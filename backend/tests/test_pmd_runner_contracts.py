from pathlib import Path


def _repo_root() -> Path:
    current = Path(__file__).resolve()
    for candidate in current.parents:
        if (candidate / "backend" / "Dockerfile").exists():
            return candidate
    raise AssertionError("failed to locate repository root from test path")


def _stage_block(dockerfile_text: str, stage_header: str) -> str:
    start = dockerfile_text.find(stage_header)
    assert start != -1, f"missing stage header: {stage_header}"
    next_stage = dockerfile_text.find("\nFROM ", start + len(stage_header))
    return dockerfile_text[start:] if next_stage == -1 else dockerfile_text[start:next_stage]


def test_backend_dockerfile_no_longer_installs_local_pmd_runtime() -> None:
    dockerfile_path = _repo_root() / "backend" / "Dockerfile"
    dockerfile_text = dockerfile_path.read_text(encoding="utf-8")

    runtime_base_block = _stage_block(dockerfile_text, "FROM python-base AS runtime-base")
    scanner_tools_base_block = _stage_block(dockerfile_text, "FROM runtime-base AS scanner-tools-base")
    runtime_block = _stage_block(dockerfile_text, "FROM runtime-base AS runtime")

    assert "openjdk-21-jre-headless" not in runtime_base_block
    assert "php-cli" not in runtime_base_block
    assert "unzip" not in runtime_base_block

    assert "apt-get install -y --no-install-recommends unzip" in scanner_tools_base_block

    assert "PMD_CACHE" not in runtime_block
    assert "pmd-dist-7.0.0-bin.zip" not in runtime_block
    assert "/usr/local/bin/pmd" not in runtime_block
