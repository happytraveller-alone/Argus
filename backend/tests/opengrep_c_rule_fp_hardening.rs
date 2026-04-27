use std::{collections::HashMap, fs, path::Path, process::Command};

use serde_json::Value;
use tempfile::TempDir;

fn opengrep_available() -> bool {
    Command::new("opengrep")
        .arg("--version")
        .output()
        .is_ok_and(|output| output.status.success())
}

fn run_opengrep(configs: &[&str], fixture_path: &Path) -> Vec<(String, String)> {
    let manifest_dir = env!("CARGO_MANIFEST_DIR");
    let mut command = Command::new("opengrep");
    command.arg("--json").arg("--quiet");
    for config in configs {
        command.arg("--config").arg(format!(
            "{manifest_dir}/assets/scan_rule_assets/rules_opengrep/{config}"
        ));
    }
    command.arg(fixture_path);

    let output = command.output().expect("run opengrep");
    assert!(
        output.status.success(),
        "opengrep failed\nstdout:\n{}\nstderr:\n{}",
        String::from_utf8_lossy(&output.stdout),
        String::from_utf8_lossy(&output.stderr)
    );

    let payload: Value = serde_json::from_slice(&output.stdout).expect("opengrep json");
    payload["results"]
        .as_array()
        .expect("results should be an array")
        .iter()
        .map(|result| {
            let rule = result["check_id"].as_str().unwrap_or_default().to_string();
            let line = result["extra"]["lines"]
                .as_str()
                .unwrap_or_default()
                .trim()
                .to_string();
            (rule, line)
        })
        .collect()
}

fn line_counts(results: &[(String, String)]) -> HashMap<String, usize> {
    let mut counts = HashMap::new();
    for (_, line) in results {
        *counts.entry(line.clone()).or_insert(0) += 1;
    }
    counts
}

fn assert_line_count(results: &[(String, String)], expected_line: &str, expected_count: usize) {
    let counts = line_counts(results);
    assert_eq!(
        counts.get(expected_line).copied().unwrap_or_default(),
        expected_count,
        "unexpected count for {expected_line:?}; results: {results:#?}"
    );
}

fn assert_string_rule_expectations(results: &[(String, String)]) {
    assert_line_count(results, r#"sprintf(dst, "%s", src);"#, 1);
    assert_line_count(results, "vsprintf(dst, fmt, args);", 1);
    assert_line_count(
        results,
        "swprintf(dst, dst_len, L\"%ls%lld\", L\"id-\", value);",
        0,
    );
    assert_line_count(results, "wcscat(path, suffix);", 0);
    assert_line_count(results, "wcscat(dst, suffix);", 1);
    assert_line_count(results, "strcat(dst, src);", 1);
    assert_line_count(results, "StrCatA(dst, src);", 1);
}

#[test]
fn c_string_rules_keep_unbounded_risks_without_reporting_sized_or_duplicate_cases() {
    if !opengrep_available() {
        eprintln!("skipping: opengrep CLI is not available");
        return;
    }

    let temp_dir = TempDir::new().expect("temp dir");
    let fixture_path = temp_dir.path().join("c_rule_fp_samples.c");
    fs::write(
        &fixture_path,
        r#"
#include <stdarg.h>
#include <stdio.h>
#include <string.h>
#include <wchar.h>

wchar_t *av_realloc_array(wchar_t *ptr, size_t count, size_t size);
char *StrCatA(char *dst, const char *src);

void unsafe_sprintf(char *dst, const char *src) {
    sprintf(dst, "%s", src);
}

void unsafe_vsprintf(char *dst, const char *fmt, va_list args) {
    vsprintf(dst, fmt, args);
}

void safe_sized_swprintf(wchar_t *dst, size_t dst_len, long long value) {
    swprintf(dst, dst_len, L"%ls%lld", L"id-", value);
}

void safe_wide_append_after_sized_realloc(wchar_t *path, const wchar_t *suffix) {
    size_t pathlen = wcslen(path);
    size_t suffix_len = wcslen(suffix);
    size_t pathsize = pathlen + suffix_len + 2;
    wchar_t *new_path = av_realloc_array(path, pathsize, sizeof *path);
    if (!new_path)
        return;
    path = new_path;
    wcscat(path, suffix);
}

void unsafe_wide_append(wchar_t *dst, const wchar_t *suffix) {
    wcscat(dst, suffix);
}

void unsafe_strcat(char *dst, const char *src) {
    strcat(dst, src);
}

void unsafe_windows_strcat(char *dst, const char *src) {
    StrCatA(dst, src);
}
"#,
    )
    .expect("write fixture");

    let results = run_opengrep(
        &[
            "c/c_buffer_rule-sprintf-vsprintf.yaml",
            "c/c_buffer_rule-lstrcat-wcscat.yaml",
            "c/c_buffer_rule-strcat.yaml",
            "c/c_buffer_rule-StrCat-StrCatA.yaml",
        ],
        &fixture_path,
    );

    assert_string_rule_expectations(&results);
}

#[test]
fn cpp_mirror_string_rules_match_c_rule_intent() {
    if !opengrep_available() {
        eprintln!("skipping: opengrep CLI is not available");
        return;
    }

    let temp_dir = TempDir::new().expect("temp dir");
    let fixture_path = temp_dir.path().join("cpp_rule_fp_samples.cc");
    fs::write(
        &fixture_path,
        r#"
#include <cstdarg>
#include <cstdio>
#include <cstring>
#include <cwchar>

wchar_t *av_realloc_array(wchar_t *ptr, size_t count, size_t size);
char *StrCatA(char *dst, const char *src);

void unsafe_sprintf(char *dst, const char *src) {
    sprintf(dst, "%s", src);
}

void unsafe_vsprintf(char *dst, const char *fmt, va_list args) {
    vsprintf(dst, fmt, args);
}

void safe_sized_swprintf(wchar_t *dst, size_t dst_len, long long value) {
    swprintf(dst, dst_len, L"%ls%lld", L"id-", value);
}

void safe_wide_append_after_sized_realloc(wchar_t *path, const wchar_t *suffix) {
    size_t pathlen = wcslen(path);
    size_t suffix_len = wcslen(suffix);
    size_t pathsize = pathlen + suffix_len + 2;
    wchar_t *new_path = av_realloc_array(path, pathsize, sizeof *path);
    if (!new_path)
        return;
    path = new_path;
    wcscat(path, suffix);
}

void unsafe_wide_append(wchar_t *dst, const wchar_t *suffix) {
    wcscat(dst, suffix);
}

void unsafe_strcat(char *dst, const char *src) {
    strcat(dst, src);
}

void unsafe_windows_strcat(char *dst, const char *src) {
    StrCatA(dst, src);
}
"#,
    )
    .expect("write fixture");

    let results = run_opengrep(
        &[
            "cpp/c_buffer_rule-sprintf-vsprintf.yaml",
            "cpp/c_buffer_rule-lstrcat-wcscat.yaml",
            "cpp/c_buffer_rule-strcat.yaml",
            "cpp/c_buffer_rule-StrCat-StrCatA.yaml",
        ],
        &fixture_path,
    );

    assert_string_rule_expectations(&results);
}
