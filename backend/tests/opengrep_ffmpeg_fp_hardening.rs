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
fn ffmpeg_style_safe_c_idioms_are_not_reported_by_hardened_rules() {
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
#include <stdio.h>
#include <string.h>

#define POSTFIX_PATTERN "segment-%d"

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
        2,
        "expected only the unsafe scan and variable format samples, got {matched_lines:#?}"
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
            .all(|line| !line.contains("PRId64")
                && !line.contains("POSTFIX_PATTERN")
                && !line.contains("sizeof(src)")
                && !line.contains("\"%d\"")
                && !line.contains("\"%63")),
        "safe FFmpeg-style idioms should not be reported: {matched_lines:#?}"
    );
}
