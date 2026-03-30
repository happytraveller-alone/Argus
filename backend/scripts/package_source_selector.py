from __future__ import annotations

import argparse
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Iterable, Sequence


DEFAULT_NPM_PROBE_PATHS = ["/-/ping", "/"]
DEFAULT_PYPI_PROBE_PATHS = ["/simple/pip/", "/simple/"]


@dataclass(frozen=True)
class ProbeResult:
    url: str
    ok: bool
    latency_ms: float | None
    matched_probe: str | None


def normalize_candidates(raw_candidates: str | Iterable[str]) -> list[str]:
    if isinstance(raw_candidates, str):
        items = raw_candidates.split(",")
    else:
        items = list(raw_candidates)

    normalized: list[str] = []
    seen: set[str] = set()
    for item in items:
        candidate = str(item or "").strip()
        if not candidate or candidate in seen:
            continue
        seen.add(candidate)
        normalized.append(candidate)
    return normalized


def default_probe_paths(kind: str) -> list[str]:
    normalized_kind = str(kind or "").strip().lower()
    if normalized_kind == "pypi":
        return list(DEFAULT_PYPI_PROBE_PATHS)
    return list(DEFAULT_NPM_PROBE_PATHS)


def build_probe_url(candidate: str, probe_path: str) -> str:
    if probe_path.startswith(("http://", "https://")):
        return probe_path
    if not probe_path:
        return candidate.rstrip("/")
    if probe_path.startswith("/"):
        return f"{candidate.rstrip('/')}{probe_path}"
    return f"{candidate.rstrip('/')}/{probe_path}"


def probe_candidate(
    candidate: str,
    probe_paths: Sequence[str],
    timeout_seconds: float = 2.0,
) -> ProbeResult:
    timeout = max(0.2, float(timeout_seconds))
    for probe_path in probe_paths:
        probe_url = build_probe_url(candidate, str(probe_path or ""))
        request = urllib.request.Request(
            probe_url,
            headers={"User-Agent": "AuditTool-package-source-selector/1.0"},
        )
        started_at = time.monotonic()
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                status = getattr(response, "status", 200)
                if 200 <= int(status) < 400:
                    latency_ms = round((time.monotonic() - started_at) * 1000, 3)
                    return ProbeResult(
                        url=candidate,
                        ok=True,
                        latency_ms=latency_ms,
                        matched_probe=str(probe_path or ""),
                    )
        except (urllib.error.URLError, TimeoutError, ValueError):
            continue
    return ProbeResult(url=candidate, ok=False, latency_ms=None, matched_probe=None)


def order_candidates_by_probe(
    raw_candidates: str | Iterable[str],
    *,
    probe_paths: Sequence[str],
    timeout_seconds: float = 2.0,
) -> list[str]:
    candidates = normalize_candidates(raw_candidates)
    if not candidates:
        return []

    # 并行探测所有候选源，总等待时间由最慢的单次探测决定（而非串行累加）
    with ThreadPoolExecutor(max_workers=len(candidates)) as executor:
        futures = {
            executor.submit(
                probe_candidate, candidate, probe_paths=probe_paths, timeout_seconds=timeout_seconds
            ): candidate
            for candidate in candidates
        }
        results = [future.result() for future in as_completed(futures)]

    candidate_index = {candidate: index for index, candidate in enumerate(candidates)}

    successful = sorted(
        (result for result in results if result.ok),
        key=lambda result: (
            float("inf") if result.latency_ms is None else result.latency_ms,
            candidate_index[result.url],
        ),
    )
    failed = [result.url for result in results if not result.ok]
    return [result.url for result in successful] + failed


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Order package sources by probe latency.")
    parser.add_argument("--candidates", required=True, help="Comma-separated candidate base URLs.")
    parser.add_argument("--kind", default="npm", choices=["npm", "pypi"])
    parser.add_argument("--probe-path", action="append", default=[])
    parser.add_argument("--timeout-seconds", type=float, default=2.0)
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    probe_paths = args.probe_path or default_probe_paths(args.kind)
    ordered = order_candidates_by_probe(
        args.candidates,
        probe_paths=probe_paths,
        timeout_seconds=args.timeout_seconds,
    )
    for candidate in ordered:
        print(candidate)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
