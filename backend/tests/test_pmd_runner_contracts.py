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


def _assert_backend_depends_on_has_no_pmd_runner(compose_text: str, next_service: str) -> None:
    backend_block = compose_text.split("\n  backend:\n", 1)[1].split(f"\n  {next_service}:\n", 1)[0]
    if "\n    depends_on:\n" not in backend_block:
        return
    depends_on_block = backend_block.split("\n    depends_on:\n", 1)[1]
    if "\n    networks:\n" in depends_on_block:
        depends_on_block = depends_on_block.split("\n    networks:\n", 1)[0]
    assert "\n      pmd-runner:\n" not in depends_on_block


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


def test_compose_exposes_scanner_pmd_image_without_pmd_runner_service() -> None:
    compose_path = _repo_root() / "docker-compose.yml"
    compose_text = compose_path.read_text(encoding="utf-8")

    assert "SCANNER_PMD_IMAGE: ${SCANNER_PMD_IMAGE:-vulhunter/pmd-runner-local:latest}" in compose_text
    assert "\n  pmd-runner:\n" not in compose_text

    _assert_backend_depends_on_has_no_pmd_runner(compose_text, "yasa-runner")


def test_full_overlay_exposes_scanner_pmd_image_without_pmd_runner_service() -> None:
    compose_path = _repo_root() / "docker-compose.full.yml"
    compose_text = compose_path.read_text(encoding="utf-8")

    assert "SCANNER_PMD_IMAGE: ${SCANNER_PMD_IMAGE:-vulhunter/pmd-runner-local:latest}" in compose_text
    assert "\n  pmd-runner:\n" not in compose_text

    _assert_backend_depends_on_has_no_pmd_runner(compose_text, "yasa-runner")
