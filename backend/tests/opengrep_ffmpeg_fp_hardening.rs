use std::{fs, process::Command};

use serde_json::Value;
use tempfile::TempDir;

fn opengrep_available() -> bool {
    Command::new("opengrep")
        .arg("--version")
        .output()
        .is_ok_and(|output| output.status.success())
}

#[test]
fn opengrep_rule_hardening_reports_unproven_risks_and_suppresses_proven_safe_idioms() {
    if !opengrep_available() {
        eprintln!("skipping: opengrep CLI is not available");
        return;
    }

    let temp_dir = TempDir::new().expect("temp dir");
    let fixture_path = temp_dir.path().join("ffmpeg_fp_samples.c");
    fs::write(
        &fixture_path,
        r#"
#include <inttypes.h>
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <wchar.h>

#define POSTFIX_PATTERN "segment-%d"

wchar_t *av_realloc_array(wchar_t *ptr, size_t count, size_t size);
char *producer(void);
void observer(char **out);
void sink(char *value);

void safe_numeric_scan(const char *buf) {
    int a;
    float f;
    sscanf(buf, "%d", &a);
    sscanf(buf, "%f", &f);
}

void safe_bounded_scan(const char *buf) {
    char target[64];
    double time;
    char command[256];
    char arg[256];
    sscanf(buf, "%63[^ ] %lf %255[^ ] %255[^\n]", target, &time, command, arg);
}

void unsafe_unbounded_scan(const char *buf) {
    char target[64];
    sscanf(buf, "%s", target);
}

void safe_macro_format(char *optval_buf, long long value) {
    snprintf(optval_buf, 64, "%" PRId64, value);
}

void safe_uppercase_macro_format(char *name, size_t name_len, int i) {
    snprintf(name, name_len, POSTFIX_PATTERN, i);
}

void unsafe_variable_format(char *buf, const char *fmt, int value) {
    snprintf(buf, 64, fmt, value);
}

void unsafe_variable_vformat(char *buf, const char *fmt, va_list args) {
    vsnprintf(buf, 64, fmt, args);
}

void literal_status_copy_requires_review(void) {
    char status[32];
    strcpy(status, "unknown");
}

void unsafe_literal_overflow(void) {
    char tiny[4];
    strcpy(tiny, "this literal is too long");
}

void unsafe_external_copy(char *dst, const char *src) {
    strcpy(dst, src);
}

void safe_wide_copy_after_sized_realloc(wchar_t *path, const wchar_t *name_w) {
    size_t pathlen = wcslen(path);
    size_t namelen = wcslen(name_w);
    size_t pathsize = pathlen + namelen + 2;
    wchar_t *new_path = av_realloc_array(path, pathsize, sizeof *path);
    if (!new_path)
        return;
    path = new_path;
    wcscpy(path + pathlen + 1, name_w);
}

void unsafe_wide_copy_after_unrelated_realloc(wchar_t *path, const wchar_t *name_w, size_t cap) {
    size_t pathlen = wcslen(path);
    size_t pathsize = cap + 2;
    wchar_t *new_path = av_realloc_array(path, pathsize, sizeof *path);
    if (!new_path)
        return;
    path = new_path;
    wcscpy(path + pathlen + 1, name_w);
}

void unsafe_wide_copy(wchar_t *dst, const wchar_t *src) {
    wcscpy(dst, src);
}

void wide_literal_copy_requires_review(void) {
    wchar_t label[16];
    wcscpy(label, L"Capture");
}

void unsafe_wide_literal_overflow(void) {
    wchar_t tiny[4];
    wcscpy(tiny, L"this literal is too long");
}

void safe_constant_printf_help(void) {
    printf("tool version %s\n"
           "usage: tool [options]\n",
           "1.0");
}

void unsafe_printf_format(const char *fmt) {
    printf(fmt);
}

void unsafe_vfprintf_format(FILE *file, const char *fmt, va_list args) {
    vfprintf(file, fmt, args);
}

void safe_reassigned_after_free(char *buf) {
    free(buf);
    buf = producer();
    sink(buf);
    free(buf);
}

void unsafe_use_after_free(char *freed) {
    free(freed);
    sink(freed);
}

void unsafe_branch_reassign_after_free(char *maybe, int cond) {
    free(maybe);
    if (cond)
        maybe = producer();
    sink(maybe);
}

void unsafe_observed_after_free(char *observed) {
    free(observed);
    observer(&observed);
    sink(observed);
}

void unsafe_double_free(char *victim) {
    free(victim);
    free(victim);
}

void unsafe_observed_double_free(char *observed) {
    free(observed);
    observer(&observed);
    free(observed);
}

void safe_bulk_copy(void) {
    int src[8];
    int dst[8];
    memcpy(dst, src, sizeof(src));
    memmove(dst + 1, dst, sizeof(dst[0]) * 7);
}
"#,
    )
    .expect("write fixture");

    let manifest_dir = env!("CARGO_MANIFEST_DIR");
    let output = Command::new("opengrep")
        .arg("--json")
        .arg("--quiet")
        .arg("--config")
        .arg(format!(
            "{manifest_dir}/assets/scan_rule_assets/rules_opengrep/c/c_buffer_rule-fscanf-sscanf.yaml"
        ))
        .arg("--config")
        .arg(format!(
            "{manifest_dir}/assets/scan_rule_assets/rules_opengrep/c/c_format_rule-snprintf-vsnprintf.yaml"
        ))
        .arg("--config")
        .arg(format!(
            "{manifest_dir}/assets/scan_rule_assets/rules_opengrep/c/c_format_rule-printf-vprintf.yaml"
        ))
        .arg("--config")
        .arg(format!(
            "{manifest_dir}/assets/scan_rule_assets/rules_opengrep/c/c_format_rule-fprintf-vfprintf.yaml"
        ))
        .arg("--config")
        .arg(format!(
            "{manifest_dir}/assets/scan_rule_assets/rules_opengrep/c/c_buffer_rule-strcpy.yaml"
        ))
        .arg("--config")
        .arg(format!(
            "{manifest_dir}/assets/scan_rule_assets/rules_opengrep/c/c_buffer_rule-lstrcpy-wcscpy.yaml"
        ))
        .arg("--config")
        .arg(format!(
            "{manifest_dir}/assets/scan_rule_assets/rules_opengrep/c/double-free.yaml"
        ))
        .arg("--config")
        .arg(format!(
            "{manifest_dir}/assets/scan_rule_assets/rules_opengrep/c/use-after-free.yaml"
        ))
        .arg("--config")
        .arg(format!(
            "{manifest_dir}/assets/scan_rule_assets/rules_opengrep/c/raptor-incorrect-use-of-strncpy-memcpy-etc.yaml"
        ))
        .arg(&fixture_path)
        .output()
        .expect("run opengrep");
    assert!(
        output.status.success(),
        "opengrep failed\nstdout:\n{}\nstderr:\n{}",
        String::from_utf8_lossy(&output.stdout),
        String::from_utf8_lossy(&output.stderr)
    );

    let payload: Value = serde_json::from_slice(&output.stdout).expect("opengrep json");
    let results = payload["results"]
        .as_array()
        .expect("results should be an array");
    let matched_lines = results
        .iter()
        .map(|result| {
            result["extra"]["lines"]
                .as_str()
                .unwrap_or_default()
                .trim()
                .to_string()
        })
        .collect::<Vec<_>>();

    assert_eq!(
        matched_lines.len(),
        19,
        "expected only unsafe or unproven-risk samples, got {matched_lines:#?}"
    );
    assert!(
        matched_lines
            .iter()
            .any(|line| line == r#"sscanf(buf, "%s", target);"#),
        "unbounded string scan should still be reported: {matched_lines:#?}"
    );
    assert!(
        matched_lines
            .iter()
            .any(|line| line == "snprintf(buf, 64, fmt, value);"),
        "variable snprintf format should still be reported: {matched_lines:#?}"
    );
    assert!(
        matched_lines
            .iter()
            .any(|line| line == "vsnprintf(buf, 64, fmt, args);"),
        "variable vsnprintf format should still be reported: {matched_lines:#?}"
    );
    assert!(
        matched_lines
            .iter()
            .any(|line| line == r#"strcpy(status, "unknown");"#),
        "literal strcpy remains under review without buffer-size proof: {matched_lines:#?}"
    );
    assert!(
        matched_lines
            .iter()
            .any(|line| line == r#"strcpy(tiny, "this literal is too long");"#),
        "unsafe literal strcpy should still be reported: {matched_lines:#?}"
    );
    assert!(
        matched_lines.iter().any(|line| line == "strcpy(dst, src);"),
        "external strcpy should still be reported: {matched_lines:#?}"
    );
    assert!(
        matched_lines
            .iter()
            .any(|line| line == "wcscpy(path + pathlen + 1, name_w);"),
        "unproven wide copy allocation should still be reported: {matched_lines:#?}"
    );
    assert!(
        matched_lines.iter().any(|line| line == "wcscpy(dst, src);"),
        "external wcscpy should still be reported: {matched_lines:#?}"
    );
    assert!(
        matched_lines
            .iter()
            .any(|line| line == r#"wcscpy(label, L"Capture");"#),
        "literal wcscpy remains under review without buffer-size proof: {matched_lines:#?}"
    );
    assert!(
        matched_lines
            .iter()
            .any(|line| line == r#"wcscpy(tiny, L"this literal is too long");"#),
        "unsafe literal wcscpy should still be reported: {matched_lines:#?}"
    );
    assert!(
        matched_lines.iter().any(|line| line == "printf(fmt);"),
        "variable printf format should still be reported: {matched_lines:#?}"
    );
    assert!(
        matched_lines
            .iter()
            .any(|line| line == "vfprintf(file, fmt, args);"),
        "variable vfprintf format should still be reported: {matched_lines:#?}"
    );
    assert!(
        matched_lines.iter().any(|line| line == "sink(freed);"),
        "use-after-free should still be reported: {matched_lines:#?}"
    );
    assert!(
        matched_lines.iter().any(|line| line == "sink(maybe);"),
        "branch-conditional reassignment after free should still be reported: {matched_lines:#?}"
    );
    assert!(
        matched_lines.iter().any(|line| line == "sink(observed);"),
        "observer call after free should not suppress use-after-free: {matched_lines:#?}"
    );
    assert!(
        matched_lines
            .iter()
            .any(|line| line == "observer(&observed);"),
        "observer call after free should remain under review: {matched_lines:#?}"
    );
    assert!(
        matched_lines.iter().any(|line| line == "free(victim);"),
        "double-free should still be reported: {matched_lines:#?}"
    );
    assert!(
        matched_lines.iter().any(|line| line == "free(observed);"),
        "observer call after free should not suppress double-free: {matched_lines:#?}"
    );
    assert!(
        matched_lines.iter().all(|line| !line.contains("PRId64")
            && !line.contains("POSTFIX_PATTERN")
            && !line.contains("sizeof(src)")
            && !line.contains("printf(\"tool version")
            && !line.contains("\"%d\"")
            && !line.contains("\"%63")),
        "safe FFmpeg-style idioms should not be reported: {matched_lines:#?}"
    );
}
