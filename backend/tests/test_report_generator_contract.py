from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]


def test_report_generator_no_longer_looks_for_removed_backend_static_logo_tree() -> None:
    source_text = (REPO_ROOT / "backend" / "app" / "services" / "report_generator.py").read_text(
        encoding="utf-8"
    )

    assert "../../static/images/logo_nobg.png" not in source_text
    assert "../../../frontend/public/images/logo_nobg.png" in source_text
