#!/usr/bin/env python3

from __future__ import annotations

import argparse
import posixpath
import re
import sys
import time
from html import unescape
from pathlib import Path
from typing import Iterable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from xml.etree import ElementTree


DEFAULT_PMD_VERSION = "7.22.0"
DEFAULT_DOCS_BASE_URL = f"https://docs.pmd-code.org/pmd-doc-{DEFAULT_PMD_VERSION}/"
DEFAULT_INDEX_PAGE = "pmd_rules_apex.html"
DEFAULT_OUTPUT_DIR = Path(__file__).resolve().parents[1] / "app" / "db" / "rules_pmd"
USER_AGENT = "AuditTool PMD rules sync/1.0"
RULESET_PAGE_PATTERN = re.compile(
    r'href="(pmd_rules_[a-z]+_(?:errorprone|security)\.html)"',
)
SOURCE_XML_PATH_PATTERN = re.compile(
    r'href="https://github\.com/pmd/pmd/blob/main/([^"#?]+/(?:errorprone|security)\.xml)"',
)
PMD_NS = "http://pmd.sourceforge.net/ruleset/2.0.0"
XSI_NS = "http://www.w3.org/2001/XMLSchema-instance"
ElementTree.register_namespace("", PMD_NS)
ElementTree.register_namespace("xsi", XSI_NS)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fetch PMD docs pages and generate one builtin XML ruleset per Error Prone / Security rule.",
    )
    parser.add_argument(
        "--pmd-version",
        default=DEFAULT_PMD_VERSION,
        help="PMD version to sync from.",
    )
    parser.add_argument(
        "--docs-base-url",
        default=DEFAULT_DOCS_BASE_URL,
        help="Base PMD docs URL ending with '/'.",
    )
    parser.add_argument(
        "--index-page",
        default=DEFAULT_INDEX_PAGE,
        help="Rule index page used to discover language/category pages.",
    )
    parser.add_argument(
        "--output-dir",
        default=str(DEFAULT_OUTPUT_DIR),
        help="Directory to write per-rule builtin XML rulesets into.",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=30.0,
        help="Per-request timeout in seconds.",
    )
    parser.add_argument(
        "--retries",
        type=int,
        default=3,
        help="Number of request retries for transient failures.",
    )
    parser.add_argument(
        "--github-proxy-base",
        default="",
        help="Optional GitHub proxy base, e.g. https://v6.gh-proxy.org",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print progress while fetching and generating rulesets.",
    )
    return parser.parse_args()


def fetch_text(url: str, *, timeout: float, retries: int) -> str:
    last_error: Exception | None = None
    request = Request(url, headers={"User-Agent": USER_AGENT})

    for attempt in range(1, retries + 1):
        try:
            with urlopen(request, timeout=timeout) as response:
                charset = response.headers.get_content_charset() or "utf-8"
                return response.read().decode(charset, "ignore")
        except (HTTPError, URLError, TimeoutError) as exc:
            last_error = exc
            if attempt == retries:
                break
            time.sleep(0.5 * attempt)

    raise RuntimeError(f"failed to fetch {url}: {last_error}") from last_error


def discover_ruleset_pages(index_html: str) -> list[str]:
    pages: list[str] = []
    seen: set[str] = set()
    for page in RULESET_PAGE_PATTERN.findall(index_html):
        if page in seen:
            continue
        seen.add(page)
        pages.append(page)
    return pages


def normalize_source_xml_path(page_html: str) -> str:
    matches = SOURCE_XML_PATH_PATTERN.findall(page_html)
    if not matches:
        raise ValueError("could not find category XML source path in docs page")
    return posixpath.normpath(unescape(matches[-1]))


def page_language_and_category(page_name: str) -> tuple[str, str]:
    match = re.fullmatch(r"pmd_rules_([a-z]+)_(errorprone|security)\.html", page_name)
    if match is None:
        raise ValueError(f"unsupported ruleset page name: {page_name}")
    return match.group(1), match.group(2)


def build_raw_source_url(source_path: str, pmd_version: str) -> str:
    return (
        "https://raw.githubusercontent.com/pmd/pmd/"
        f"pmd_releases/{pmd_version}/{source_path}"
    )


def apply_github_proxy(url: str, github_proxy_base: str) -> str:
    normalized_proxy = github_proxy_base.strip().rstrip("/")
    if not normalized_proxy:
        return url
    return f"{normalized_proxy}/{url}"


def iter_rule_blocks(category_xml: str) -> Iterable[tuple[str, str]]:
    root = ElementTree.fromstring(category_xml)
    rule_nodes = root.findall("./{*}rule")
    if not rule_nodes:
        raise ValueError("category XML does not contain any <rule> nodes")

    for rule_node in rule_nodes:
        rule_name = rule_node.get("name")
        if not rule_name:
            raise ValueError("encountered rule without name attribute")
        rule_block = ElementTree.tostring(rule_node, encoding="unicode")
        yield rule_name, rule_block


def render_ruleset(rule_name: str, rule_block: str) -> str:
    indented_rule_block = "\n".join(
        f"    {line}" if line else ""
        for line in rule_block.strip("\n").splitlines()
    )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<ruleset name="{rule_name} Ruleset"\n'
        '    xmlns="http://pmd.sourceforge.net/ruleset/2.0.0"\n'
        '    xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"\n'
        '    xsi:schemaLocation="http://pmd.sourceforge.net/ruleset/2.0.0 '
        'https://pmd.sourceforge.io/ruleset_2_0_0.xsd">\n'
        "\n"
        f"    <description>Independent ruleset for {rule_name}</description>\n"
        "\n"
        f"{indented_rule_block}\n"
        "\n"
        "</ruleset>\n"
    )


def language_prefix(language: str) -> str:
    return language[:1].upper() + language[1:]


def category_prefix(category: str) -> str:
    return "ErrorProne" if category == "errorprone" else "Security"


def target_filename(
    *,
    rule_name: str,
    language: str,
    category: str,
    preserved_base_names: set[str],
) -> str:
    legacy_filename = f"{rule_name}.xml"
    if rule_name in preserved_base_names:
        return legacy_filename
    return f"{language_prefix(language)}{category_prefix(category)}{rule_name}.xml"


def validate_ruleset_xml(raw_xml: str, expected_rule_name: str) -> None:
    root = ElementTree.fromstring(raw_xml)
    rule_nodes = root.findall("./{*}rule")
    if len(rule_nodes) != 1:
        raise ValueError(f"{expected_rule_name}: generated XML does not contain exactly one rule")
    if rule_nodes[0].get("name") != expected_rule_name:
        raise ValueError(f"{expected_rule_name}: generated XML rule name mismatch")


def write_rulesets(
    *,
    docs_base_url: str,
    index_page: str,
    output_dir: Path,
    pmd_version: str,
    github_proxy_base: str,
    timeout: float,
    retries: int,
    verbose: bool,
) -> tuple[int, list[str]]:
    output_dir.mkdir(parents=True, exist_ok=True)
    preserved_base_names = {path.stem for path in output_dir.glob("*.xml")}

    index_html = fetch_text(f"{docs_base_url}{index_page}", timeout=timeout, retries=retries)
    ruleset_pages = discover_ruleset_pages(index_html)
    if verbose:
        print(f"discovered {len(ruleset_pages)} docs pages from {docs_base_url}{index_page}", flush=True)

    generated_files: dict[str, str] = {}

    for page_name in ruleset_pages:
        language, category = page_language_and_category(page_name)
        if verbose:
            print(f"syncing {page_name} ({language}/{category})", flush=True)
        page_html = fetch_text(f"{docs_base_url}{page_name}", timeout=timeout, retries=retries)
        source_path = normalize_source_xml_path(page_html)
        source_url = apply_github_proxy(
            build_raw_source_url(source_path, pmd_version),
            github_proxy_base,
        )
        if verbose:
            print(f"  source: {source_path}", flush=True)
        category_xml = fetch_text(
            source_url,
            timeout=timeout,
            retries=retries,
        )

        for rule_name, rule_block in iter_rule_blocks(category_xml):
            filename = target_filename(
                rule_name=rule_name,
                language=language,
                category=category,
                preserved_base_names=preserved_base_names,
            )
            if filename in generated_files:
                raise ValueError(f"filename collision for {filename}")
            rendered = render_ruleset(rule_name, rule_block)
            validate_ruleset_xml(rendered, rule_name)
            generated_files[filename] = rendered

    if len(generated_files) != 143:
        raise ValueError(f"expected 143 generated rulesets, got {len(generated_files)}")

    existing_paths = {path.name: path for path in output_dir.glob("*.xml")}
    for stale_name, stale_path in existing_paths.items():
        if stale_name not in generated_files:
            stale_path.unlink()

    for filename, raw_xml in sorted(generated_files.items()):
        (output_dir / filename).write_text(raw_xml, encoding="utf-8")

    return len(generated_files), sorted(generated_files)


def main() -> None:
    args = parse_args()
    docs_base_url = args.docs_base_url
    if not docs_base_url.endswith("/"):
        docs_base_url = f"{docs_base_url}/"

    generated_count, filenames = write_rulesets(
        docs_base_url=docs_base_url,
        index_page=args.index_page,
        output_dir=Path(args.output_dir),
        pmd_version=args.pmd_version,
        github_proxy_base=args.github_proxy_base,
        timeout=args.timeout,
        retries=args.retries,
        verbose=args.verbose,
    )
    print(
        f"generated {generated_count} PMD builtin rulesets into {args.output_dir} "
        f"(first={filenames[0]}, last={filenames[-1]})"
    )


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # pragma: no cover - script entrypoint
        print(f"error: {exc}", file=sys.stderr)
        raise
