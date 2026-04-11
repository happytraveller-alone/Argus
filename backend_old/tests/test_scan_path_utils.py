import app.services.scan_path_utils as scan_path_utils

from app.services.scan_path_utils import (
    build_legacy_scan_path_candidates,
    normalize_scan_file_path,
    resolve_legacy_scan_path,
)


def test_normalize_scan_file_path_converts_absolute_path_under_project_root():
    assert (
        normalize_scan_file_path(
            "/tmp/project-root/src/main.py",
            "/tmp/project-root",
        )
        == "src/main.py"
    )


def test_normalize_scan_file_path_cleans_relative_path():
    assert (
        normalize_scan_file_path(
            "./src//pkg/../main.py",
            "/tmp/project-root",
        )
        == "src/main.py"
    )


def test_build_legacy_scan_path_candidates_strips_temp_prefix_and_archive_root():
    candidates = build_legacy_scan_path_candidates(
        "/tmp/VulHunter_proj_123/archive-root/./src/app/main.py",
    )

    assert candidates[:3] == [
        "tmp/VulHunter_proj_123/archive-root/src/app/main.py",
        "archive-root/src/app/main.py",
        "src/app/main.py",
    ]


def test_resolve_legacy_scan_path_uses_first_known_zip_match():
    resolved = resolve_legacy_scan_path(
        "/tmp/VulHunter_proj_123/archive-root/./src/app/main.py",
        {
            "archive-root/src/app/main.py",
            "src/app/main.py",
        },
    )

    assert resolved == "archive-root/src/app/main.py"


def test_resolve_legacy_scan_path_returns_none_when_zip_has_no_match():
    assert (
        resolve_legacy_scan_path(
            "/tmp/VulHunter_proj_123/archive-root/./src/app/missing.py",
            {"src/app/main.py"},
        )
        is None
    )


def test_build_scan_zip_member_path_candidates_supports_archive_root_prefix():
    assert hasattr(scan_path_utils, "build_scan_zip_member_path_candidates")

    candidates = scan_path_utils.build_scan_zip_member_path_candidates(
        "openclaw-2026.3.7/src/discord/voice-message.ts",
    )

    assert candidates[:2] == [
        "openclaw-2026.3.7/src/discord/voice-message.ts",
        "src/discord/voice-message.ts",
    ]


def test_resolve_scan_zip_member_path_prefers_exact_match_before_archive_root_fallback():
    assert hasattr(scan_path_utils, "resolve_scan_zip_member_path")

    resolved = scan_path_utils.resolve_scan_zip_member_path(
        "openclaw-2026.3.7/src/discord/voice-message.ts",
        {
            "openclaw-2026.3.7/src/discord/voice-message.ts",
            "src/discord/voice-message.ts",
        },
    )

    assert resolved == "openclaw-2026.3.7/src/discord/voice-message.ts"


def test_resolve_scan_zip_member_path_falls_back_to_archive_stripped_relative_path():
    assert hasattr(scan_path_utils, "resolve_scan_zip_member_path")

    resolved = scan_path_utils.resolve_scan_zip_member_path(
        "openclaw-2026.3.7/src/discord/voice-message.ts",
        {"src/discord/voice-message.ts"},
    )

    assert resolved == "src/discord/voice-message.ts"
