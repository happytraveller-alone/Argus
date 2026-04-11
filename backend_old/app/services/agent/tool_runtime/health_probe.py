from __future__ import annotations

import ipaddress
import socket
from typing import Dict, List, Optional, Tuple
from urllib.parse import urlparse, urlunparse

import httpx


_HTTP_HEALTH_STATUS_FALLBACK = {404, 405, 501}


def _default_port(parsed) -> int:
    if parsed.port:
        return int(parsed.port)
    if str(parsed.scheme or "").lower() == "https":
        return 443
    return 80


def _is_loopback_host(host: str) -> bool:
    value = str(host or "").strip().lower()
    if not value:
        return False
    if value == "localhost":
        return True
    try:
        return bool(ipaddress.ip_address(value).is_loopback)
    except ValueError:
        return False


def _candidate_probe_urls(endpoint: str) -> List[str]:
    parsed = urlparse(endpoint)
    candidates = [
        urlunparse(parsed._replace(path="/health", params="", query="", fragment="")),
        urlunparse(parsed._replace(path="/healthz", params="", query="", fragment="")),
        endpoint,
    ]
    seen = set()
    ordered: List[str] = []
    for item in candidates:
        key = str(item or "").strip()
        if not key or key in seen:
            continue
        seen.add(key)
        ordered.append(key)
    return ordered


def _tcp_reachable(endpoint: str, *, timeout: float) -> Tuple[bool, Optional[str]]:
    parsed = urlparse(endpoint)
    host = str(parsed.hostname or "").strip()
    if not host:
        return False, "missing_host"
    port = _default_port(parsed)
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True, None
    except Exception as exc:
        return False, exc.__class__.__name__


def probe_endpoint_readiness(
    endpoint: Optional[str],
    *,
    timeout: float = 1.5,
    headers: Optional[Dict[str, str]] = None,
) -> Tuple[bool, Optional[str]]:
    url = str(endpoint or "").strip()
    if not url:
        return False, "missing_endpoint"
    if not url.startswith(("http://", "https://")):
        return False, "invalid_endpoint"

    parsed = urlparse(url)
    timeout_sec = max(0.5, float(timeout))
    candidate_urls = _candidate_probe_urls(url)
    primary_health_url = candidate_urls[0] if candidate_urls else url

    if _is_loopback_host(str(parsed.hostname or "")):
        tcp_ok, _tcp_reason = _tcp_reachable(url, timeout=timeout_sec)
        if tcp_ok:
            return True, None

    first_hard_failure: Optional[str] = None
    first_exception: Optional[Tuple[str, BaseException]] = None

    try:
        with httpx.Client(timeout=timeout_sec, follow_redirects=True) as client:
            for probe_url in candidate_urls:
                try:
                    response = client.get(probe_url, headers=headers)
                except Exception as exc:
                    if first_exception is None:
                        first_exception = (probe_url, exc)
                    continue

                status_code = int(response.status_code)
                if status_code == 200:
                    return True, None
                if status_code in _HTTP_HEALTH_STATUS_FALLBACK:
                    continue
                if first_hard_failure is None:
                    first_hard_failure = (
                        f"healthcheck_failed:status_{status_code}@{probe_url}"
                    )
    except Exception:
        pass

    tcp_ok, tcp_reason = _tcp_reachable(url, timeout=timeout_sec)
    if tcp_ok:
        return True, None

    if first_hard_failure:
        return False, first_hard_failure
    if first_exception:
        probe_url, exc = first_exception
        return False, f"healthcheck_failed:{exc.__class__.__name__}@{probe_url}"
    return (
        False,
        f"healthcheck_failed:tcp_unreachable:{tcp_reason or 'unknown'}@{primary_health_url}",
    )
