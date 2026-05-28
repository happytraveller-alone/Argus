#!/usr/bin/env python3
"""Validate the curated CWE catalog seed without third-party dependencies."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

EXPECTED_COUNT = 969
EXPECTED_VERSION = "4.20"
EXPECTED_DATE = "2026-04-30"
COMMON_LABELS = {
    "CWE-89": "SQL注入",
    "CWE-79": "跨站脚本",
    "CWE-22": "路径遍历",
}

TECH_TOKEN_ALLOWLIST = {
    "AI", "ML", "LLM", "DS_Store", "System.exit", "super.finalize", "super.clone", "equals", "hashCode", "finally", "Secure", "I", "O", "METHOD_NEITHER", "McCabe", "Chicken", "Junction", "dirname", "include", "require", "Unicode", "Web", "Java", "Shatter", "Alist", "window.opener", "final", "SQL", "NoSQL", "XML", "XSS", "CSRF", "SSRF", "LDAP", "XPath", "XQuery", "HTTP", "HTTPS", "URI", "URL", "API", "J2EE", "EJB", "ASP", "NET", "PHP", "SSI", "CRLF", "JNI", "JTAG", "UNIX", "Windows", "UNC", "HFS", "LNK", "DATA", "WebSocket", "WebSockets", "Servlet", "Struts", "Bean", "Action", "ActionForm", "validate", "Eval", "OS", "HTML", "IMG", "Cookie", "HttpOnly", "SameSite", "JWT", "OAuth", "JSON", "CSV", "DNS", "FTP", "SSL", "OpenSSL", "RSA", "OAEP", "CBC", "IV", "PRNG", "TRNG", "CAPTCHA", "GUI", "UI", "CPU", "DMA", "IOCTL", "ROM", "SOC", "SoC", "NoC", "Jail", "chroot", "chmod", "umask", "NUL", "NULL", "NullPointerException", "clone", "finalize", "sizeof", "getlogin", "Referer", "opener", "WSDL", "ActiveX", "AWT", "Swing", "Hibernate", "Android", "Apple", "Session", "ID", "CVE", "CWE", "C", "Cplusplus", "Cxx", "Cookie", "Shell", "Nonce", "Halstead", "Servlet", "OAuth",
}

# English fragments that are almost always failed machine translation rather
# than accepted technical tokens.
SUSPICIOUS_WORDS = {
    "Improper", "Incorrect", "Missing", "Insufficient", "Improperly", "Failure", "Neutralization", "Sanitization", "Sanitize", "Handling", "Control", "Validation", "Exposure", "Reliance", "Excessive", "Insecure", "Weak", "Unsafe", "Uncontrolled", "Unexpected", "External", "Internal", "Special", "Elements", "Element", "Data", "Information", "Resource", "Resources", "Buffer", "Pointer", "Memory", "Access", "Permissions", "Permission", "Authentication", "Authorization", "Credentials", "Password", "Configuration", "Misconfiguration", "Transmission", "Encryption", "Custom", "Error", "Page", "Method", "Methods", "Class", "File", "Path", "Traversal", "Equivalence", "Directory", "Filename", "Name", "Names", "Object", "Function", "Code", "Command", "Argument", "Injection", "Expression", "Generation", "Use", "Using", "Used", "Before", "After", "During", "Within", "Without", "With", "From", "Into", "Between", "Through", "By", "For", "And", "Or", "Of", "The", "A", "An",
}


def load_payload(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def english_tokens(value: str) -> list[str]:
    return re.findall(r"[A-Za-z][A-Za-z0-9.+_-]*", value or "")


def is_literal_context(name_zh: str, token: str) -> bool:
    # Keep path/code fragments such as filedir, filename, dirname, absolute/pathname.
    if token.lower() in {"filedir", "filename", "dirname", "pathname", "absolute", "here", "dir", "fakedir", "realdir", "share", "name"}:
        return any(ch in name_zh for ch in "/\\:.*")
    return False


def find_suspicious_entries(payload: dict) -> list[dict]:
    suspicious = []
    for entry in payload.get("entries") or []:
        name = str(entry.get("nameZh") or "")
        bad = []
        for token in english_tokens(name):
            if token in TECH_TOKEN_ALLOWLIST:
                continue
            if re.fullmatch(r"[A-Z0-9.#+_-]{2,}", token):
                continue
            if is_literal_context(name, token):
                continue
            if token in SUSPICIOUS_WORDS or token[:1].isupper() or token.islower():
                bad.append(token)
        if bad:
            suspicious.append({"id": entry.get("id"), "tokens": sorted(set(bad)), "nameZh": name})
    return suspicious


def validate(
    path: Path,
    review_path: Path | None = None,
    match_seed_path: Path | None = None,
) -> tuple[list[str], str]:
    payload = load_payload(path)
    errors: list[str] = []
    if payload.get("contentVersion") != EXPECTED_VERSION:
        errors.append(f"contentVersion must be {EXPECTED_VERSION}")
    if payload.get("contentDate") != EXPECTED_DATE:
        errors.append(f"contentDate must be {EXPECTED_DATE}")
    entries = payload.get("entries")
    if not isinstance(entries, list):
        errors.append("entries must be a list")
        entries = []
    if payload.get("entryCount") != EXPECTED_COUNT:
        errors.append(f"entryCount must be {EXPECTED_COUNT}")
    if len(entries) != EXPECTED_COUNT:
        errors.append(f"entries length must be {EXPECTED_COUNT}, got {len(entries)}")

    seen_ids = set()
    seen_nums = set()
    for idx, entry in enumerate(entries):
        cwe_id = str(entry.get("id") or "")
        match = re.fullmatch(r"CWE-([1-9][0-9]*)", cwe_id)
        if not match:
            errors.append(f"entry {idx} malformed id: {cwe_id}")
            continue
        numeric = int(match.group(1))
        if entry.get("numericId") != numeric:
            errors.append(f"{cwe_id} numericId mismatch: {entry.get('numericId')}")
        if cwe_id in seen_ids:
            errors.append(f"duplicate id: {cwe_id}")
        seen_ids.add(cwe_id)
        if numeric in seen_nums:
            errors.append(f"duplicate numericId: {numeric}")
        seen_nums.add(numeric)
        if not str(entry.get("nameEnOfficial") or "").strip():
            errors.append(f"{cwe_id} blank nameEnOfficial")
        if not str(entry.get("nameEnShort") or "").strip():
            errors.append(f"{cwe_id} blank nameEnShort")
        zh = str(entry.get("nameZh") or "").strip()
        if not zh:
            errors.append(f"{cwe_id} blank nameZh")
        if not re.search(r"[\u4e00-\u9fff]", zh):
            errors.append(f"{cwe_id} nameZh lacks Chinese characters: {zh}")

    by_id = {entry.get("id"): entry for entry in entries if isinstance(entry, dict)}
    for cwe_id, expected in COMMON_LABELS.items():
        actual = by_id.get(cwe_id, {}).get("nameZh")
        if actual != expected:
            errors.append(f"{cwe_id} nameZh must be {expected}, got {actual}")

    suspicious = find_suspicious_entries(payload)
    for item in suspicious[:100]:
        errors.append(f"{item['id']} suspicious untranslated tokens {item['tokens']} in {item['nameZh']}")
    if len(suspicious) > 100:
        errors.append(f"... plus {len(suspicious)-100} more suspicious entries")

    seed_bytes = path.read_bytes()
    seed_hash = hashlib.sha256(seed_bytes).hexdigest()
    if match_seed_path:
        if not match_seed_path.exists():
            errors.append(f"match seed missing: {match_seed_path}")
        else:
            match_bytes = match_seed_path.read_bytes()
            match_hash = hashlib.sha256(match_bytes).hexdigest()
            if match_hash != seed_hash:
                errors.append(
                    f"seed mismatch: {path} sha256={seed_hash} != {match_seed_path} sha256={match_hash}"
                )
            else:
                try:
                    match_payload = json.loads(match_bytes)
                    if match_payload.get("contentVersion") != payload.get("contentVersion"):
                        errors.append("matched seed contentVersion differs")
                    if match_payload.get("contentDate") != payload.get("contentDate"):
                        errors.append("matched seed contentDate differs")
                    if len(match_payload.get("entries") or []) != len(entries):
                        errors.append("matched seed entry count differs")
                except Exception as exc:  # pragma: no cover - defensive CLI diagnostics
                    errors.append(f"failed to parse matched seed: {exc}")
    if review_path:
        if not review_path.exists():
            errors.append(f"review artifact missing: {review_path}")
        else:
            review_text = review_path.read_text(encoding="utf-8")
            if seed_hash not in review_text:
                errors.append("review artifact does not contain current seed SHA-256")
            if "Reviewed at:" not in review_text:
                errors.append("review artifact missing Reviewed at")
            if "Retained English-token allowlist" not in review_text:
                errors.append("review artifact missing allowlist section")
    return errors, seed_hash


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("path", nargs="?", default="backend/assets/cwe_catalog/cwe_catalog_v4_20_zh.json")
    ap.add_argument("--review", default="backend/assets/cwe_catalog/cwe_catalog_v4_20_zh.review.md")
    ap.add_argument("--matches-seed", default=None, help="Optional second seed JSON that must match byte-for-byte/checksum.")
    args = ap.parse_args()
    errors, seed_hash = validate(
        Path(args.path),
        Path(args.review) if args.review else None,
        Path(args.matches_seed) if args.matches_seed else None,
    )
    if errors:
        print("CWE catalog validation failed:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1
    print(f"CWE catalog validation passed: {EXPECTED_COUNT} entries, sha256={seed_hash}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
