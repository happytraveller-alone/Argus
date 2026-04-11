from pathlib import Path

import pytest

from app.services import seed_archive


def test_build_github_archive_url_for_tag():
    assert (
        seed_archive.build_github_archive_url(
            owner="libimobiledevice",
            repo="libplist",
            ref_type="tag",
            ref="2.7.0",
        )
        == "https://github.com/libimobiledevice/libplist/archive/refs/tags/2.7.0.zip"
    )


def test_build_github_archive_url_for_commit():
    assert (
        seed_archive.build_github_archive_url(
            owner="alibaba",
            repo="fastjson",
            ref_type="commit",
            ref="abc123",
        )
        == "https://github.com/alibaba/fastjson/archive/abc123.zip"
    )


def test_build_seed_archive_candidates_appends_origin_and_dedups(monkeypatch):
    canonical_url = "https://github.com/example/repo/archive/refs/tags/v1.0.0.zip"

    monkeypatch.setattr(
        seed_archive,
        "get_mirror_candidates",
        lambda *args, **kwargs: [
            "https://mirror-a.example/https://github.com/example/repo/archive/refs/tags/v1.0.0.zip",
            canonical_url,
            "https://mirror-a.example/https://github.com/example/repo/archive/refs/tags/v1.0.0.zip",
        ],
    )

    assert seed_archive.build_seed_archive_candidates(canonical_url) == [
        "https://mirror-a.example/https://github.com/example/repo/archive/refs/tags/v1.0.0.zip",
        canonical_url,
    ]


@pytest.mark.asyncio
async def test_rank_seed_archive_candidates_orders_by_latency(monkeypatch):
    async def _fake_probe(url: str, attempts: int, timeout_seconds: float):
        latencies = {
            "https://slow.example/archive.zip": 0.9,
            "https://fast.example/archive.zip": 0.1,
            "https://fail.example/archive.zip": None,
        }
        return latencies[url]

    monkeypatch.setattr(seed_archive, "_probe_seed_archive_candidate", _fake_probe)

    ranked = await seed_archive.rank_seed_archive_candidates(
        [
            "https://slow.example/archive.zip",
            "https://fail.example/archive.zip",
            "https://fast.example/archive.zip",
        ],
        attempts=2,
        timeout_seconds=1.0,
    )

    assert ranked == [
        "https://fast.example/archive.zip",
        "https://slow.example/archive.zip",
        "https://fail.example/archive.zip",
    ]


@pytest.mark.asyncio
async def test_download_seed_archive_uses_ranked_candidates(monkeypatch, tmp_path: Path):
    canonical_url = "https://github.com/example/repo/archive/refs/tags/v1.0.0.zip"
    ranked_candidates = [
        "https://mirror-fast.example/archive.zip",
        canonical_url,
    ]
    download_attempts: list[str] = []

    monkeypatch.setattr(seed_archive, "build_seed_archive_candidates", lambda _: ranked_candidates)

    async def _fake_rank(candidates, attempts: int, timeout_seconds: float):
        assert candidates == ranked_candidates
        return candidates

    monkeypatch.setattr(seed_archive, "rank_seed_archive_candidates", _fake_rank)

    async def _fake_download(url: str, destination_path: str, timeout_seconds: float):
        download_attempts.append(url)
        if "mirror-fast" in url:
            Path(destination_path).write_bytes(b"zip-content")
            return
        raise AssertionError("should not fall back after successful mirror download")

    monkeypatch.setattr(seed_archive, "_download_seed_archive_candidate", _fake_download)

    archive_path = await seed_archive.download_seed_archive(
        owner="example",
        repo="repo",
        ref_type="tag",
        ref="v1.0.0",
        archive_name="repo-v1.0.0.zip",
        probe_attempts=2,
        probe_timeout_seconds=1.0,
        download_timeout_seconds=3.0,
        temp_dir=str(tmp_path),
    )

    assert Path(archive_path).exists()
    assert Path(archive_path).read_bytes() == b"zip-content"
    assert download_attempts == ["https://mirror-fast.example/archive.zip"]


@pytest.mark.asyncio
async def test_download_seed_archive_removes_temp_file_after_all_failures(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(
        seed_archive,
        "build_seed_archive_candidates",
        lambda _: ["https://mirror-a.example/archive.zip", "https://github.com/example/repo/archive/main.zip"],
    )
    async def _fake_rank(candidates, attempts: int, timeout_seconds: float):
        return candidates

    monkeypatch.setattr(seed_archive, "rank_seed_archive_candidates", _fake_rank)

    async def _fake_download(url: str, destination_path: str, timeout_seconds: float):
        Path(destination_path).write_bytes(b"partial")
        raise RuntimeError(f"download failed: {url}")

    monkeypatch.setattr(seed_archive, "_download_seed_archive_candidate", _fake_download)

    with pytest.raises(seed_archive.SeedArchiveDownloadError):
        await seed_archive.download_seed_archive(
            owner="example",
            repo="repo",
            ref_type="commit",
            ref="abc123",
            archive_name="repo.zip",
            probe_attempts=2,
            probe_timeout_seconds=1.0,
            download_timeout_seconds=3.0,
            temp_dir=str(tmp_path),
        )

    assert list(tmp_path.iterdir()) == []
