use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use std::fs;
use std::path::Path;

const CORE_AUDIT_EXCLUDE_PATTERNS: &[&str] = &[
    "test/**",
    "tests/**",
    "**/test/**",
    "**/tests/**",
    ".*/**",
    "**/.*/**",
    "*config*.*",
    "**/*config*.*",
    "*settings*.*",
    "**/*settings*.*",
    ".env*",
    "**/.env*",
    "*.yml",
    "**/*.yml",
    "*.yaml",
    "**/*.yaml",
    "*.json",
    "**/*.json",
    "*.ini",
    "**/*.ini",
    "*.conf",
    "**/*.conf",
    "*.toml",
    "**/*.toml",
    "*.properties",
    "**/*.properties",
    "*.plist",
    "**/*.plist",
    "*.xml",
    "**/*.xml",
];

const STATIC_SCAN_TEST_FUZZ_DIRS: &[&str] = &[
    "test",
    "tests",
    "__tests__",
    "testdata",
    "test_data",
    "testing",
    "fuzz",
    "fuzzing",
    "fuzzer",
    "fuzzers",
    "fuzz_tests",
    "fuzz_corpus",
];

const STATIC_SCAN_TEST_FUZZ_FILE_PATTERNS: &[&str] = &[
    "test_*",
    "tests_*",
    "*_test",
    "*_tests",
    "*_test.*",
    "*_tests.*",
    "*-test",
    "*-tests",
    "*-test.*",
    "*-tests.*",
    "*.test.*",
    "*.tests.*",
    "fuzz_*",
    "fuzzer_*",
    "*_fuzz",
    "*_fuzzer",
    "*_fuzzing",
    "*_fuzz.*",
    "*_fuzzer.*",
    "*_fuzzing.*",
    "*-fuzz",
    "*-fuzzer",
    "*-fuzzing",
    "*-fuzz.*",
    "*-fuzzer.*",
    "*-fuzzing.*",
    "*.fuzz.*",
    "*.fuzzer.*",
    "*.fuzzing.*",
];

#[derive(Debug, Clone, Deserialize, PartialEq)]
#[serde(rename_all = "kebab-case")]
pub enum ScopeFilterOperation {
    BuildPatterns,
    IsIgnored,
    FilterBootstrapFindings,
}

impl ScopeFilterOperation {
    pub fn from_cli(raw: &str) -> Result<Self, String> {
        match raw.trim() {
            "build-patterns" => Ok(Self::BuildPatterns),
            "is-ignored" => Ok(Self::IsIgnored),
            "filter-bootstrap-findings" => Ok(Self::FilterBootstrapFindings),
            other => Err(format!("unsupported_scope_filter_operation:{other}")),
        }
    }
}

#[derive(Debug, Clone, Deserialize)]
pub struct ScopeFilterRequest {
    #[serde(default)]
    pub path: Option<String>,
    #[serde(default)]
    pub exclude_patterns: Option<Vec<String>>,
    #[serde(default)]
    pub findings: Option<Vec<Value>>,
}

#[derive(Debug, Clone, Serialize, PartialEq)]
pub struct ScopeFilterResponse {
    pub ok: bool,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub patterns: Option<Vec<String>>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub ignored: Option<bool>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub items: Option<Vec<Value>>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub error: Option<String>,
}

pub fn execute_from_request_path(operation: ScopeFilterOperation, request_path: &Path) -> Value {
    let payload = match fs::read_to_string(request_path) {
        Ok(raw) => match serde_json::from_str::<ScopeFilterRequest>(&raw) {
            Ok(value) => value,
            Err(error) => {
                return json!({
                    "ok": false,
                    "error": format!("invalid_scope_filter_request:{error}"),
                });
            }
        },
        Err(error) => {
            return json!({
                "ok": false,
                "error": format!("read_scope_filter_request_failed:{error}"),
            });
        }
    };

    serde_json::to_value(execute(operation, payload)).unwrap_or_else(
        |error| json!({"ok": false, "error": format!("scope_filter_response_failed:{error}")}),
    )
}

pub fn execute(
    operation: ScopeFilterOperation,
    request: ScopeFilterRequest,
) -> ScopeFilterResponse {
    match operation {
        ScopeFilterOperation::BuildPatterns => ScopeFilterResponse {
            ok: true,
            patterns: Some(build_core_audit_exclude_patterns(
                request.exclude_patterns.as_deref(),
            )),
            ignored: None,
            items: None,
            error: None,
        },
        ScopeFilterOperation::IsIgnored => {
            let path = request.path.unwrap_or_default();
            ScopeFilterResponse {
                ok: true,
                patterns: None,
                ignored: Some(is_core_ignored_path(
                    &path,
                    request.exclude_patterns.as_deref(),
                )),
                items: None,
                error: None,
            }
        }
        ScopeFilterOperation::FilterBootstrapFindings => ScopeFilterResponse {
            ok: true,
            patterns: None,
            ignored: None,
            items: Some(filter_bootstrap_findings(
                request.findings.as_deref().unwrap_or(&[]),
                request.exclude_patterns.as_deref(),
            )),
            error: None,
        },
    }
}

pub fn build_core_audit_exclude_patterns(user_patterns: Option<&[String]>) -> Vec<String> {
    let mut merged = Vec::new();
    let mut seen = std::collections::HashSet::new();

    for raw in user_patterns
        .unwrap_or(&[])
        .iter()
        .map(String::as_str)
        .chain(CORE_AUDIT_EXCLUDE_PATTERNS.iter().copied())
    {
        let normalized = raw.trim().replace('\\', "/");
        if normalized.is_empty() {
            continue;
        }
        let lowered = normalized.to_ascii_lowercase();
        if !seen.insert(lowered) {
            continue;
        }
        merged.push(normalized);
    }

    merged
}

pub fn is_core_ignored_path(path: &str, exclude_patterns: Option<&[String]>) -> bool {
    let normalized = normalize_scan_path(path);
    if normalized.is_empty() {
        return false;
    }

    let parts = path_components(&normalized);
    for part in parts.iter().take(parts.len().saturating_sub(1)) {
        let lowered = part.to_ascii_lowercase();
        if lowered == "test" || lowered == "tests" || part.starts_with('.') {
            return true;
        }
    }

    if let Some(last) = parts.last() {
        let lowered = last.to_ascii_lowercase();
        if lowered == "test" || lowered == "tests" || last.starts_with('.') {
            return true;
        }
    }

    let effective_patterns = build_core_audit_exclude_patterns(exclude_patterns);
    matches_exclude_patterns(&normalized, &effective_patterns)
}

pub fn is_static_scan_test_or_fuzz_path(path: &str) -> bool {
    let normalized = normalize_scan_path(path);
    if normalized.is_empty() {
        return false;
    }

    let parts = path_components(&normalized);
    if parts.is_empty() {
        return false;
    }

    for part in parts.iter().take(parts.len().saturating_sub(1)) {
        if is_static_scan_test_or_fuzz_dir(part) {
            return true;
        }
    }

    parts
        .last()
        .is_some_and(|basename| is_static_scan_test_or_fuzz_file(basename))
}

pub fn filter_bootstrap_findings(
    normalized_findings: &[Value],
    exclude_patterns: Option<&[String]>,
) -> Vec<Value> {
    let mut filtered = Vec::new();

    for item in normalized_findings {
        let Some(object) = item.as_object() else {
            continue;
        };

        let file_path = object
            .get("file_path")
            .and_then(Value::as_str)
            .map(str::trim)
            .unwrap_or_default();
        if !file_path.is_empty() && is_core_ignored_path(file_path, exclude_patterns) {
            continue;
        }

        let severity_value = object
            .get("severity")
            .and_then(Value::as_str)
            .map(str::trim)
            .unwrap_or_default()
            .to_ascii_uppercase();
        if severity_value != "ERROR" {
            continue;
        }

        let Some(confidence_value) = normalize_bootstrap_confidence(object.get("confidence"))
        else {
            continue;
        };
        if confidence_value != "HIGH" && confidence_value != "MEDIUM" {
            continue;
        }

        let mut copied = object.clone();
        copied.insert("confidence".to_string(), Value::String(confidence_value));
        filtered.push(Value::Object(copied));
    }

    filtered
}

fn is_static_scan_test_or_fuzz_dir(name: &str) -> bool {
    let lowered = name.trim().to_ascii_lowercase();
    STATIC_SCAN_TEST_FUZZ_DIRS
        .iter()
        .any(|candidate| lowered == *candidate)
}

fn is_static_scan_test_or_fuzz_file(name: &str) -> bool {
    let lowered = name.trim().to_ascii_lowercase();
    if lowered.is_empty() {
        return false;
    }
    if STATIC_SCAN_TEST_FUZZ_DIRS
        .iter()
        .any(|candidate| lowered == *candidate)
    {
        return true;
    }
    STATIC_SCAN_TEST_FUZZ_FILE_PATTERNS
        .iter()
        .any(|pattern| wildcard_matches(&lowered, pattern))
}

fn normalize_bootstrap_confidence(value: Option<&Value>) -> Option<String> {
    let normalized = match value {
        Some(Value::String(text)) => text.trim().to_ascii_uppercase(),
        Some(Value::Number(number)) => number.to_string().trim().to_ascii_uppercase(),
        Some(Value::Bool(flag)) => flag.to_string().trim().to_ascii_uppercase(),
        _ => String::new(),
    };

    match normalized.as_str() {
        "HIGH" | "MEDIUM" | "LOW" => Some(normalized),
        _ => None,
    }
}

fn normalize_scan_path(path: &str) -> String {
    let mut normalized = path.trim().replace('\\', "/");
    while normalized.starts_with("./") {
        normalized = normalized[2..].to_string();
    }
    while normalized.starts_with('/') {
        normalized = normalized[1..].to_string();
    }
    while normalized.contains("//") {
        normalized = normalized.replace("//", "/");
    }
    normalized
}

fn path_components(path: &str) -> Vec<String> {
    let normalized = normalize_scan_path(path);
    if normalized.is_empty() {
        return Vec::new();
    }

    normalized
        .split('/')
        .filter(|part| !part.is_empty() && *part != "." && *part != "..")
        .map(str::to_string)
        .collect()
}

fn matches_exclude_patterns(path: &str, patterns: &[String]) -> bool {
    let basename = path.rsplit('/').next().unwrap_or(path);
    patterns.iter().any(|pattern| {
        let candidate = pattern.trim().replace('\\', "/");
        !candidate.is_empty()
            && (wildcard_matches(path, &candidate) || wildcard_matches(basename, &candidate))
    })
}

fn wildcard_matches(input: &str, pattern: &str) -> bool {
    let input_chars = input.chars().collect::<Vec<_>>();
    let pattern_chars = pattern.chars().collect::<Vec<_>>();
    let mut memo = std::collections::HashMap::new();
    wildcard_matches_chars(&input_chars, &pattern_chars, 0, 0, &mut memo)
}

fn wildcard_matches_chars(
    input: &[char],
    pattern: &[char],
    input_index: usize,
    pattern_index: usize,
    memo: &mut std::collections::HashMap<(usize, usize), bool>,
) -> bool {
    if let Some(cached) = memo.get(&(input_index, pattern_index)) {
        return *cached;
    }

    let matched = if pattern_index == pattern.len() {
        input_index == input.len()
    } else {
        match pattern[pattern_index] {
            '*' => (input_index..=input.len())
                .any(|next| wildcard_matches_chars(input, pattern, next, pattern_index + 1, memo)),
            '?' => {
                input_index < input.len()
                    && wildcard_matches_chars(
                        input,
                        pattern,
                        input_index + 1,
                        pattern_index + 1,
                        memo,
                    )
            }
            '[' => {
                if let Some((matches_class, next_pattern_index)) =
                    match_character_class(input, pattern, input_index, pattern_index)
                {
                    matches_class
                        && wildcard_matches_chars(
                            input,
                            pattern,
                            input_index + 1,
                            next_pattern_index,
                            memo,
                        )
                } else {
                    input.get(input_index) == Some(&'[')
                        && wildcard_matches_chars(
                            input,
                            pattern,
                            input_index + 1,
                            pattern_index + 1,
                            memo,
                        )
                }
            }
            current => {
                input.get(input_index) == Some(&current)
                    && wildcard_matches_chars(
                        input,
                        pattern,
                        input_index + 1,
                        pattern_index + 1,
                        memo,
                    )
            }
        }
    };

    memo.insert((input_index, pattern_index), matched);
    matched
}

fn match_character_class(
    input: &[char],
    pattern: &[char],
    input_index: usize,
    pattern_index: usize,
) -> Option<(bool, usize)> {
    let candidate = *input.get(input_index)?;
    let mut index = pattern_index + 1;
    if index >= pattern.len() {
        return None;
    }

    let mut negated = false;
    if matches!(pattern[index], '!' | '^') {
        negated = true;
        index += 1;
    }
    if index >= pattern.len() {
        return None;
    }

    let mut matched = false;
    let mut saw_token = false;
    let mut previous: Option<char> = None;

    while index < pattern.len() {
        let current = pattern[index];
        if current == ']' && saw_token {
            return Some((((matched && !negated) || (!matched && negated)), index + 1));
        }

        saw_token = true;
        if current == '-' {
            if let (Some(start), Some(&end)) = (previous, pattern.get(index + 1)) {
                if end != ']' {
                    if start <= candidate && candidate <= end {
                        matched = true;
                    }
                    previous = Some(end);
                    index += 2;
                    continue;
                }
            }
        }

        if current == candidate {
            matched = true;
        }
        previous = Some(current);
        index += 1;
    }

    None
}

#[cfg(test)]
mod tests {
    use super::{
        build_core_audit_exclude_patterns, execute, execute_from_request_path,
        filter_bootstrap_findings, is_core_ignored_path, is_static_scan_test_or_fuzz_path,
        ScopeFilterOperation, ScopeFilterRequest,
    };
    use serde_json::json;
    use std::fs;
    use tempfile::TempDir;

    #[test]
    fn builds_patterns_with_user_entries_first_and_deduped() {
        let patterns = build_core_audit_exclude_patterns(Some(&[
            " custom/*.py ".to_string(),
            "custom/*.py".to_string(),
            "TESTS/**".to_string(),
        ]));

        assert_eq!(patterns[0], "custom/*.py");
        assert!(patterns
            .iter()
            .any(|item| item.eq_ignore_ascii_case("tests/**")));
        assert_eq!(
            patterns
                .iter()
                .filter(|item| *item == "custom/*.py")
                .count(),
            1
        );
        assert_eq!(
            patterns
                .iter()
                .filter(|item| item.eq_ignore_ascii_case("tests/**"))
                .count(),
            1
        );
    }

    #[test]
    fn detects_hidden_test_and_config_paths() {
        let custom = vec!["custom/*.py".to_string()];
        assert!(is_core_ignored_path("tests/test_api.py", None));
        assert!(is_core_ignored_path(".github/workflows/pipeline.py", None));
        assert!(is_core_ignored_path("app/settings.py", None));
        assert!(is_core_ignored_path("custom/demo.py", Some(&custom)));
        assert!(!is_core_ignored_path("src/service.py", None));
    }

    #[test]
    fn detects_static_scan_test_and_fuzz_paths() {
        for path in [
            "tests/test_api.py",
            "src/test/login_test.go",
            "src/__tests__/widget.ts",
            "src/testdata/fixture.json",
            "src/service_test.py",
            "src/service.tests.ts",
            "src/foo.test.ts",
            "src/fuzz/fuzz_target.c",
            "src/fuzzers/parser.cc",
            "src/fuzz_corpus/input.bin",
            "src/fuzz_parser.c",
            "src/parser_fuzz.cc",
            "src/parser.fuzz.cpp",
        ] {
            assert!(
                is_static_scan_test_or_fuzz_path(path),
                "expected {path} to be excluded from static scans"
            );
        }

        for path in [
            "src/service.py",
            "src/contest/ranking.py",
            "src/profuzzer_client.c",
            "src/fuzzy_matcher.rs",
        ] {
            assert!(
                !is_static_scan_test_or_fuzz_path(path),
                "expected {path} to remain in static scans"
            );
        }
    }

    #[test]
    fn filters_bootstrap_findings_by_path_severity_and_confidence() {
        let findings = vec![
            json!({"id": "keep", "severity": "ERROR", "confidence": "HIGH", "file_path": "src/api.py"}),
            json!({"id": "drop-tests", "severity": "ERROR", "confidence": "HIGH", "file_path": "tests/test_api.py"}),
            json!({"id": "drop-severity", "severity": "WARN", "confidence": "HIGH", "file_path": "src/api.py"}),
            json!({"id": "drop-confidence", "severity": "ERROR", "confidence": "LOW", "file_path": "src/api.py"}),
        ];

        let filtered =
            filter_bootstrap_findings(&findings, Some(&build_core_audit_exclude_patterns(None)));
        assert_eq!(
            filtered,
            vec![
                json!({"id": "keep", "severity": "ERROR", "confidence": "HIGH", "file_path": "src/api.py"})
            ]
        );
    }

    #[test]
    fn supports_fnmatch_question_mark_and_character_classes() {
        let question = vec!["src/file?.py".to_string()];
        let char_class = vec!["src/file[12].py".to_string()];
        let negated = vec!["src/file[!3].py".to_string()];

        assert!(is_core_ignored_path("src/file1.py", Some(&question)));
        assert!(is_core_ignored_path("src/file2.py", Some(&char_class)));
        assert!(!is_core_ignored_path("src/file3.py", Some(&char_class)));
        assert!(is_core_ignored_path("src/file1.py", Some(&negated)));
        assert!(!is_core_ignored_path("src/file3.py", Some(&negated)));
    }

    #[test]
    fn matches_basename_patterns_with_fnmatch_parity() {
        let basename_question = vec!["file?.py".to_string()];
        let basename_class = vec!["file[ab].py".to_string()];

        assert!(is_core_ignored_path(
            "nested/file1.py",
            Some(&basename_question)
        ));
        assert!(is_core_ignored_path(
            "nested/filea.py",
            Some(&basename_class)
        ));
        assert!(!is_core_ignored_path(
            "nested/filez.py",
            Some(&basename_class)
        ));
    }

    #[test]
    fn execute_from_request_path_handles_is_ignored_and_filter_operations() {
        let temp_dir = TempDir::new().expect("tempdir should build");

        let ignored_request = temp_dir.path().join("ignored.json");
        fs::write(
            &ignored_request,
            json!({"path": "tests/test_api.py"}).to_string(),
        )
        .expect("request should write");
        let ignored = execute_from_request_path(ScopeFilterOperation::IsIgnored, &ignored_request);
        assert_eq!(ignored, json!({"ok": true, "ignored": true}));

        let filter_request = temp_dir.path().join("filter.json");
        fs::write(
            &filter_request,
            json!({
                "findings": [
                    {"id": "keep", "severity": "ERROR", "confidence": "HIGH", "file_path": "src/api.py"},
                    {"id": "drop", "severity": "ERROR", "confidence": "HIGH", "file_path": ".github/workflows/pipeline.py"}
                ]
            })
            .to_string(),
        )
        .expect("request should write");
        let filtered = execute_from_request_path(
            ScopeFilterOperation::FilterBootstrapFindings,
            &filter_request,
        );
        assert_eq!(
            filtered,
            json!({
                "ok": true,
                "items": [{"id": "keep", "severity": "ERROR", "confidence": "HIGH", "file_path": "src/api.py"}]
            })
        );
    }

    #[test]
    fn execute_returns_patterns_for_build_request() {
        let response = execute(
            ScopeFilterOperation::BuildPatterns,
            ScopeFilterRequest {
                path: None,
                exclude_patterns: Some(vec!["custom/*.py".to_string()]),
                findings: None,
            },
        );

        assert!(response.ok);
        assert!(response
            .patterns
            .unwrap_or_default()
            .iter()
            .any(|item| item == "custom/*.py"));
    }
}
