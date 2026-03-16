from __future__ import annotations

import asyncio
import os
import tempfile
import time
from pathlib import Path

import httpx

from app.core.config import settings
from app.services.git_mirror import get_mirror_candidates


class SeedArchiveDownloadError(RuntimeError):
    pass


def _unique_keep_order(values: list[str]) -> list[str]:
    deduped: list[str] = []
    seen: set[str] = set()
    for value in values:
        normalized = str(value or "").strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        deduped.append(normalized)
    return deduped


def build_github_archive_url(*, owner: str, repo: str, ref_type: str, ref: str) -> str:
    normalized_ref_type = str(ref_type or "").strip().lower()
    if normalized_ref_type == "tag":
        return f"https://github.com/{owner}/{repo}/archive/refs/tags/{ref}.zip"
    if normalized_ref_type == "commit":
        return f"https://github.com/{owner}/{repo}/archive/{ref}.zip"
    raise ValueError(f"unsupported seed archive ref_type: {ref_type}")


def build_seed_archive_candidates(canonical_url: str) -> list[str]:
    candidates = get_mirror_candidates(
        canonical_url,
        enabled=getattr(settings, "GIT_MIRROR_ENABLED", True),
        mirror_prefix=getattr(settings, "GIT_MIRROR_PREFIX", "https://gh-proxy.org"),
        mirror_prefixes=getattr(
            settings,
            "GIT_MIRROR_PREFIXES",
            "https://gh-proxy.org,https://v6.gh-proxy.org",
        ),
        allow_hosts=getattr(settings, "GIT_MIRROR_HOSTS", "github.com"),
        allow_auth_url=getattr(settings, "GIT_MIRROR_ALLOW_AUTH_URL", False),
        fallback_to_origin=False,
    )
    return _unique_keep_order([*candidates, canonical_url])


def _build_http_timeout(timeout_seconds: float) -> httpx.Timeout:
    value = max(float(timeout_seconds), 0.1)
    connect_timeout = min(value, 10.0)
    return httpx.Timeout(value, connect=connect_timeout)


async def _measure_seed_archive_first_byte(url: str, timeout_seconds: float) -> float:
    started_at = time.perf_counter()
    async with httpx.AsyncClient(
        follow_redirects=True,
        headers={"User-Agent": "VulHunter seed archive installer"},
        timeout=_build_http_timeout(timeout_seconds),
    ) as client:
        async with client.stream("GET", url) as response:
            response.raise_for_status()
            async for chunk in response.aiter_bytes():
                if chunk:
                    return time.perf_counter() - started_at
            return time.perf_counter() - started_at


async def _probe_seed_archive_candidate(
    url: str,
    attempts: int,
    timeout_seconds: float,
) -> float | None:
    probe_attempts = max(int(attempts), 1)
    samples: list[float] = []

    for _ in range(probe_attempts):
        try:
            samples.append(await _measure_seed_archive_first_byte(url, timeout_seconds))
        except Exception:
            continue

    if not samples:
        return None

    samples.sort()
    middle = len(samples) // 2
    if len(samples) % 2 == 1:
        return samples[middle]
    return (samples[middle - 1] + samples[middle]) / 2


async def rank_seed_archive_candidates(
    candidates: list[str],
    *,
    attempts: int | None = None,
    timeout_seconds: float | None = None,
) -> list[str]:
    deduped_candidates = _unique_keep_order(candidates)
    if not deduped_candidates:
        return []

    resolved_attempts = int(
        attempts if attempts is not None else getattr(settings, "SEED_ARCHIVE_PROBE_ATTEMPTS", 2)
    )
    resolved_timeout = float(
        timeout_seconds
        if timeout_seconds is not None
        else getattr(settings, "SEED_ARCHIVE_PROBE_TIMEOUT_SECONDS", 5)
    )

    probe_results = await asyncio.gather(
        *[
            _probe_seed_archive_candidate(url, resolved_attempts, resolved_timeout)
            for url in deduped_candidates
        ]
    )

    ranked = sorted(
        enumerate(deduped_candidates),
        key=lambda item: (
            probe_results[item[0]] is None,
            float("inf") if probe_results[item[0]] is None else probe_results[item[0]],
            item[0],
        ),
    )
    return [url for _, url in ranked]


async def _download_seed_archive_candidate(
    url: str,
    destination_path: str,
    timeout_seconds: float,
) -> None:
    async with httpx.AsyncClient(
        follow_redirects=True,
        headers={"User-Agent": "VulHunter seed archive installer"},
        timeout=_build_http_timeout(timeout_seconds),
    ) as client:
        async with client.stream("GET", url) as response:
            response.raise_for_status()
            with open(destination_path, "wb") as file_obj:
                async for chunk in response.aiter_bytes():
                    if chunk:
                        file_obj.write(chunk)


async def download_seed_archive(
    *,
    owner: str,
    repo: str,
    ref_type: str,
    ref: str,
    archive_name: str,
    probe_attempts: int | None = None,
    probe_timeout_seconds: float | None = None,
    download_timeout_seconds: float | None = None,
    temp_dir: str | None = None,
) -> str:
    canonical_url = build_github_archive_url(owner=owner, repo=repo, ref_type=ref_type, ref=ref)
    ranked_candidates = await rank_seed_archive_candidates(
        build_seed_archive_candidates(canonical_url),
        attempts=probe_attempts,
        timeout_seconds=probe_timeout_seconds,
    )
    if not ranked_candidates:
        raise SeedArchiveDownloadError(f"no available archive candidates for {owner}/{repo}@{ref}")

    resolved_download_timeout = float(
        download_timeout_seconds
        if download_timeout_seconds is not None
        else getattr(settings, "SEED_ARCHIVE_DOWNLOAD_TIMEOUT_SECONDS", 180)
    )
    prefix = f"seed_archive_{Path(archive_name).stem}_"
    file_descriptor, archive_path = tempfile.mkstemp(
        prefix=prefix,
        suffix=".zip",
        dir=temp_dir,
    )
    os.close(file_descriptor)

    errors: list[str] = []
    for candidate_url in ranked_candidates:
        try:
            if os.path.exists(archive_path):
                os.remove(archive_path)
            await _download_seed_archive_candidate(
                candidate_url,
                archive_path,
                resolved_download_timeout,
            )
            if not os.path.exists(archive_path) or os.path.getsize(archive_path) == 0:
                raise SeedArchiveDownloadError(f"empty archive downloaded from {candidate_url}")
            return archive_path
        except Exception as exc:
            errors.append(f"{candidate_url}: {exc}")
            if os.path.exists(archive_path):
                os.remove(archive_path)

    raise SeedArchiveDownloadError(
        f"failed to download {owner}/{repo}@{ref}: {'; '.join(errors)}"
    )
