from __future__ import annotations

import os
from typing import Any, List
from urllib.parse import urlparse

HTTPS_ONLY_REPOSITORY_ERROR = "仅支持 HTTPS 仓库地址，不再支持 SSH 地址"


def _as_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return bool(default)
    text = str(value).strip().lower()
    if not text:
        return bool(default)
    return text in {"1", "true", "yes", "on"}


def _split_csv(raw_values: Any) -> List[str]:
    values = [str(item).strip() for item in str(raw_values or "").split(",")]
    return [item for item in values if item]


def _split_hosts(raw_hosts: Any) -> List[str]:
    return [item.lower() for item in _split_csv(raw_hosts)]


def _split_prefixes(raw_prefixes: Any) -> List[str]:
    return _split_csv(raw_prefixes)


def _unique_keep_order(values: List[str]) -> List[str]:
    deduped: List[str] = []
    seen = set()
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        deduped.append(value)
    return deduped


def is_ssh_git_url(url: str) -> bool:
    text = str(url or "").strip()
    if not text:
        return False
    return text.startswith("git@") or text.startswith("ssh://")


def ensure_supported_repository_url(
    url: str,
    exc_type: type[Exception] = ValueError,
) -> None:
    if is_ssh_git_url(url):
        raise exc_type(HTTPS_ONLY_REPOSITORY_ERROR)


def has_url_auth(url: str) -> bool:
    parsed = urlparse(str(url or "").strip())
    return bool(parsed.username or parsed.password)


def _host_in_allow_list(host: str, allow_hosts: List[str]) -> bool:
    host_lower = str(host or "").strip().lower()
    if not host_lower or not allow_hosts:
        return False
    for allow_host in allow_hosts:
        candidate = str(allow_host or "").strip().lower()
        if not candidate:
            continue
        if host_lower == candidate or host_lower.endswith(f".{candidate}"):
            return True
    return False


def should_use_mirror(
    url: str,
    *,
    enabled: bool,
    allow_auth_url: bool,
    allow_hosts: List[str],
) -> bool:
    text = str(url or "").strip()
    if not text or not enabled:
        return False
    if is_ssh_git_url(text):
        return False

    parsed = urlparse(text)
    if parsed.scheme.lower() not in {"http", "https"}:
        return False
    if not _host_in_allow_list(parsed.netloc.split("@")[-1].split(":")[0], allow_hosts):
        return False
    if (not allow_auth_url) and has_url_auth(text):
        return False
    return True


def build_mirror_url(original_url: str, mirror_prefix: str) -> str:
    raw_url = str(original_url or "").strip()
    raw_prefix = str(mirror_prefix or "").strip()
    if not raw_url or not raw_prefix:
        return raw_url
    if "{url}" in raw_prefix:
        return raw_prefix.replace("{url}", raw_url)
    return f"{raw_prefix.rstrip('/')}/{raw_url}"


def get_mirror_candidates(
    original_url: str,
    *,
    enabled: Any = None,
    mirror_prefix: Any = None,
    mirror_prefixes: Any = None,
    allow_hosts: Any = None,
    allow_auth_url: Any = None,
    fallback_to_origin: Any = None,
) -> List[str]:
    raw_url = str(original_url or "").strip()
    if not raw_url:
        return []

    enabled_value = _as_bool(
        enabled if enabled is not None else os.getenv("GIT_MIRROR_ENABLED", "true"),
        default=True,
    )
    fallback_to_origin_value = _as_bool(
        fallback_to_origin
        if fallback_to_origin is not None
        else os.getenv("GIT_MIRROR_FALLBACK_TO_ORIGIN", "false"),
        default=False,
    )
    hosts_value = _split_hosts(
        allow_hosts if allow_hosts is not None else os.getenv("GIT_MIRROR_HOSTS", "github.com")
    )
    allow_auth_value = _as_bool(
        allow_auth_url
        if allow_auth_url is not None
        else os.getenv("GIT_MIRROR_ALLOW_AUTH_URL", "false")
    )

    if not should_use_mirror(
        raw_url,
        enabled=enabled_value,
        allow_auth_url=allow_auth_value,
        allow_hosts=hosts_value,
    ):
        return [raw_url]

    prefixes_value = _split_prefixes(
        mirror_prefixes
        if mirror_prefixes is not None
        else os.getenv("GIT_MIRROR_PREFIXES", "")
    )
    if not prefixes_value:
        prefix_value = str(
            mirror_prefix
            if mirror_prefix is not None
            else os.getenv("GIT_MIRROR_PREFIX", "https://gh-proxy.org")
        ).strip()
        if prefix_value:
            prefixes_value = [prefix_value]

    candidates: List[str] = []
    for prefix in prefixes_value:
        mirror_url = build_mirror_url(raw_url, prefix)
        if mirror_url:
            candidates.append(mirror_url)

    candidates = _unique_keep_order(candidates)
    if fallback_to_origin_value:
        candidates = _unique_keep_order(candidates + [raw_url])

    if not candidates:
        return [raw_url]
    return candidates
