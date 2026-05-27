//! Path-based file classification for dismissal evidence.
//!
//! Plan Phase 0 (`.omc/plans/ralplan-codegraph-ac2-ac3-internal-product.md`,
//! AC0.C) — deterministic, audit-grade classification of a file path into one
//! of three buckets:
//!
//! - [`PathCategory::Test`] — unit/integration test code (e.g. `tests/`,
//!   `__tests__/`, `*_test.rs`, `src/test/java/`)
//! - [`PathCategory::Vendor`] — third-party vendored code (e.g. `vendor/`,
//!   `third_party/`, `node_modules/`)
//! - [`PathCategory::Blacklisted`] — non-source directories that should never
//!   appear in audit findings (e.g. `.git`, `docs`, `examples`, `fuzz`)
//! - [`PathCategory::RealCode`] — everything else (presumed first-party source)
//!
//! ## Matching semantics
//!
//! Patterns are matched against **path components**, not arbitrary substrings.
//! E.g. a directory named `tests` matches, but the substring `test` inside the
//! filename `attestation.py` does NOT. Filename-glob patterns (`*_test.*`,
//! `*.test.ts`, etc.) match only against the trailing filename component.
//!
//! This guarantees a finding under `src/attestation.py` is not silently
//! reclassified as test code.

use std::path::{Component, Path};

/// Classification bucket emitted by [`classify_path`].
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum PathCategory {
    /// First-party source code (or anything that did not match a known
    /// test/vendor/blacklist pattern).
    RealCode,
    /// Unit, integration, or specification test code.
    Test,
    /// Third-party vendored dependencies.
    Vendor,
    /// Non-source directories that must never appear in audit findings
    /// (docs, examples, build output, fuzz harnesses, etc.).
    /// The inner `&'static str` names the matched `BLACKLIST_DIRS` entry.
    Blacklisted(&'static str),
}

/// Vendor directory components — matched whole against any path component.
const VENDOR_DIRS: &[&str] = &["vendor", "third_party", "node_modules"];

/// Blacklisted directory components — matched whole against any path component.
/// These directories contain non-source material (docs, build output, fuzz
/// harnesses, examples, etc.) and must never appear in audit findings.
const BLACKLIST_DIRS: &[&str] = &[
    ".git",
    ".github",
    "bench",
    "benchmark",
    "benchmarks",
    "build",
    "demo",
    "demos",
    "dist",
    "doc",
    "docs",
    "example",
    "examples",
    "fuzz",
    "fuzzing",
    "sample",
    "samples",
    "scripts",
    "target",
    "tools",
];

/// Test directory components — matched whole against any path component.
const TEST_DIRS: &[&str] = &["tests", "test", "__tests__", "spec"];

/// Multi-segment test path prefix patterns (matched as adjacent path components).
///
/// Each entry is a slash-joined path fragment whose components must appear in
/// the input as a contiguous adjacent run.
const TEST_PATH_PREFIXES: &[&str] = &["src/test/java"];

/// Filename-glob test patterns. Matched only against the last path component
/// (the file name). `*` is a wildcard standing in for any non-empty span.
const TEST_FILENAME_GLOBS: &[&str] = &["*_test.*", "*.test.ts", "*.test.js", "*_spec.rb"];

/// Classify a file path into one of [`PathCategory::Test`],
/// [`PathCategory::Vendor`], [`PathCategory::Blacklisted`], or
/// [`PathCategory::RealCode`].
///
/// Returns the category plus, when matched, a human-readable glob fragment that
/// identifies WHICH pattern fired — suitable for filling the
/// `dismissal_evidence.path_pattern` field on an `AuditFinding`.
///
/// Matching is precedence-ordered: Vendor > Test > Blacklisted > RealCode.
/// (Vendor first because a `vendor/test/foo.go` path is more honestly
/// "vendored" than "test code".)
#[must_use]
pub fn classify_path(path: &Path) -> (PathCategory, Option<String>) {
    let components: Vec<&str> = path
        .components()
        .filter_map(|c| match c {
            Component::Normal(os) => os.to_str(),
            _ => None,
        })
        .collect();

    // Vendor takes precedence — a path under vendor/ is vendor code even if it
    // also lives under a tests/ subdir.
    for comp in &components {
        if VENDOR_DIRS.contains(comp) {
            return (PathCategory::Vendor, Some(format!("{comp}/")));
        }
    }

    // Multi-segment test prefix (e.g. src/test/java/...).
    for prefix in TEST_PATH_PREFIXES {
        let needle: Vec<&str> = prefix.split('/').collect();
        if components
            .windows(needle.len())
            .any(|w| w == needle.as_slice())
        {
            return (PathCategory::Test, Some(format!("{prefix}/")));
        }
    }

    // Single-component test dir (tests/, __tests__/, spec/, ...).
    for comp in &components {
        if TEST_DIRS.contains(comp) {
            return (PathCategory::Test, Some(format!("{comp}/")));
        }
    }

    // Filename-glob test patterns — last component only.
    if let Some(filename) = components.last() {
        for pattern in TEST_FILENAME_GLOBS {
            if matches_glob(pattern, filename) {
                return (PathCategory::Test, Some((*pattern).to_string()));
            }
        }
    }

    // Blacklisted dirs — non-source material that must never reach findings.
    for comp in &components {
        for &dir in BLACKLIST_DIRS {
            if *comp == dir {
                return (PathCategory::Blacklisted(dir), Some(format!("{dir}/")));
            }
        }
    }

    (PathCategory::RealCode, None)
}

/// Returns the blacklist reason for `path` (considering both built-in patterns
/// and the caller-supplied `extra` component list), or `None` if the path is
/// legitimate first-party source code.
///
/// The returned `&'static str` is one of:
/// - `"vendor_dir"` — matched a `VENDOR_DIRS` entry
/// - `"test_dir"` — matched a `TEST_DIRS` / `TEST_PATH_PREFIXES` entry or a
///   filename-glob test pattern
/// - `"blacklist_dir"` — matched a `BLACKLIST_DIRS` entry
/// - `"path_blacklist_extra"` — matched a caller-supplied `extra` component
///
/// Precedence follows `classify_path`: Vendor > Test > Blacklisted > extra.
pub fn is_blacklisted(path: &Path, extra: &[String]) -> Option<&'static str> {
    match classify_path(path) {
        (PathCategory::Vendor, _) => Some("vendor_dir"),
        (PathCategory::Test, _) => Some("test_dir"),
        (PathCategory::Blacklisted(_), _) => Some("blacklist_dir"),
        (PathCategory::RealCode, _) => {
            // Check caller-supplied extra components.
            let components: Vec<&str> = path
                .components()
                .filter_map(|c| match c {
                    std::path::Component::Normal(os) => os.to_str(),
                    _ => None,
                })
                .collect();
            for comp in &components {
                if extra.iter().any(|e| e == comp) {
                    return Some("path_blacklist_extra");
                }
            }
            None
        }
    }
}

/// Minimal glob matcher: supports `*` as wildcard. The whole pattern must
/// consume the whole input.
fn matches_glob(pattern: &str, input: &str) -> bool {
    glob_recurse(pattern.as_bytes(), input.as_bytes())
}

fn glob_recurse(pattern: &[u8], input: &[u8]) -> bool {
    match (pattern.first(), input.first()) {
        (None, None) => true,
        (None, Some(_)) => false,
        (Some(&b'*'), _) => {
            // Star matches zero-or-more bytes; try every split.
            for split in 0..=input.len() {
                if glob_recurse(&pattern[1..], &input[split..]) {
                    return true;
                }
            }
            false
        }
        (Some(&p), Some(&i)) if p == i => glob_recurse(&pattern[1..], &input[1..]),
        _ => false,
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::path::PathBuf;

    fn classify(s: &str) -> (PathCategory, Option<String>) {
        classify_path(&PathBuf::from(s))
    }

    #[test]
    fn real_code_main() {
        let (cat, pat) = classify("src/main.rs");
        assert_eq!(cat, PathCategory::RealCode);
        assert_eq!(pat, None);
    }

    #[test]
    fn test_dir_top_level() {
        let (cat, pat) = classify("tests/integration.rs");
        assert_eq!(cat, PathCategory::Test);
        assert_eq!(pat.as_deref(), Some("tests/"));
    }

    #[test]
    fn test_dir_java_maven_layout() {
        let (cat, pat) = classify("src/test/java/Foo.java");
        assert_eq!(cat, PathCategory::Test);
        assert_eq!(pat.as_deref(), Some("src/test/java/"));
    }

    #[test]
    fn vendor_dir_go() {
        let (cat, pat) = classify("vendor/lib/foo.go");
        assert_eq!(cat, PathCategory::Vendor);
        assert_eq!(pat.as_deref(), Some("vendor/"));
    }

    #[test]
    fn vendor_dir_node_modules() {
        let (cat, pat) = classify("node_modules/react/index.js");
        assert_eq!(cat, PathCategory::Vendor);
        assert_eq!(pat.as_deref(), Some("node_modules/"));
    }

    /// Boundary: a file whose NAME contains the substring "test" but no path
    /// component IS "test" must remain real code. This guards against the
    /// classic substring-vs-component bug.
    #[test]
    fn substring_test_in_filename_is_not_test() {
        let (cat, pat) = classify("src/attestation.py");
        assert_eq!(cat, PathCategory::RealCode);
        assert_eq!(pat, None);
    }

    #[test]
    fn filename_glob_rust_test() {
        let (cat, pat) = classify("src/foo_test.rs");
        assert_eq!(cat, PathCategory::Test);
        assert_eq!(pat.as_deref(), Some("*_test.*"));
    }

    #[test]
    fn filename_glob_ts_test() {
        let (cat, pat) = classify("src/app.test.ts");
        assert_eq!(cat, PathCategory::Test);
        assert_eq!(pat.as_deref(), Some("*.test.ts"));
    }

    #[test]
    fn vendor_wins_over_test() {
        // vendor/tests/foo.go — vendor takes precedence (R3 audit honesty:
        // vendored test code is still vendored).
        let (cat, pat) = classify("vendor/tests/foo.go");
        assert_eq!(cat, PathCategory::Vendor);
        assert_eq!(pat.as_deref(), Some("vendor/"));
    }

    #[test]
    fn empty_path_is_real_code() {
        let (cat, pat) = classify("");
        assert_eq!(cat, PathCategory::RealCode);
        assert_eq!(pat, None);
    }

    // ── Blacklisted variant tests ──────────────────────────────────────────

    #[test]
    fn classify_path_returns_blacklisted_for_dot_github() {
        let (cat, pat) = classify(".github/workflows/ci.yml");
        assert_eq!(cat, PathCategory::Blacklisted(".github"));
        assert_eq!(pat.as_deref(), Some(".github/"));
    }

    #[test]
    fn classify_path_returns_blacklisted_for_fuzz() {
        let (cat, pat) = classify("fuzz/fuzz_targets/target.rs");
        assert_eq!(cat, PathCategory::Blacklisted("fuzz"));
        assert_eq!(pat.as_deref(), Some("fuzz/"));
    }

    #[test]
    fn classify_path_precedence_vendor_beats_test_beats_blacklist() {
        // vendor/tests/docs/foo.rs — vendor wins (highest precedence)
        let (cat, _) = classify("vendor/tests/docs/foo.rs");
        assert_eq!(cat, PathCategory::Vendor);

        // tests/docs/foo.rs — test wins over blacklist
        let (cat, _) = classify("tests/docs/foo.rs");
        assert_eq!(cat, PathCategory::Test);

        // docs/foo.rs — blacklist fires (no vendor or test component)
        let (cat, _) = classify("docs/foo.rs");
        assert_eq!(cat, PathCategory::Blacklisted("docs"));
    }

    // ── is_blacklisted tests ──────────────────────────────────────────────

    #[test]
    fn is_blacklisted_matches_extra_components() {
        let extra = vec!["internal".to_string(), "generated".to_string()];
        let path = PathBuf::from("src/generated/proto.rs");
        assert_eq!(is_blacklisted(&path, &extra), Some("path_blacklist_extra"));
    }

    #[test]
    fn is_blacklisted_returns_none_for_real_code() {
        let path = PathBuf::from("src/lib.rs");
        assert_eq!(is_blacklisted(&path, &[]), None);
    }

    #[test]
    fn is_blacklisted_filename_globs_still_work() {
        // *_test.rs pattern should still classify as test_dir via is_blacklisted
        let path = PathBuf::from("src/parser_test.rs");
        assert_eq!(is_blacklisted(&path, &[]), Some("test_dir"));
    }
}
