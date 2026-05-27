//! Per-rule corpus integration test for Joern C/C++ vulnerability rules.
//!
//! Combined-CPG strategy: copies all 16 fixture sources (8 positive + 8 negative)
//! into one workspace, builds ONE CPG via joern-parse, then runs the orchestrator
//! ONCE and asserts per-rule expected hits. Gated by `#[ignore]` because it
//! requires the live Joern container; mirrors `joern_fixture_acceptance::
//! live_joern_container_builds_graph_and_reports_libplist_cve_fixture`.
//!
//! Wall-clock budget: configurable via `JOERN_CORPUS_TIMEOUT_SECS` (default 600s).

use std::collections::HashSet;
use std::path::{Path, PathBuf};
use std::time::Duration;

use serde_json::Value;
use tempfile::TempDir;
use tokio::fs;
use tokio::process::Command;

const FIXTURE_ROOT: &str = concat!(env!("CARGO_MANIFEST_DIR"), "/tests/fixtures/joern/rules");
const QUERY_ASSETS_ROOT: &str = concat!(
    env!("CARGO_MANIFEST_DIR"),
    "/assets/scan_rule_assets/rules_joern"
);
const JOERN_IMAGE: &str = "ghcr.nju.edu.cn/joernio/joern:nightly";

const RULES: [&str; 8] = [
    "joern-c-unsafe-gets",
    "joern-c-tainted-strcpy",
    "joern-c-tainted-memcpy",
    "joern-c-tainted-sprintf-buffer",
    "joern-c-strncpy-missing-null-term",
    "joern-c-alloc-mul-tainted",
    "joern-c-strlen-int-truncation",
    "joern-c-signed-left-shift",
];

const TAINT_RULES: [&str; 4] = [
    "joern-c-tainted-strcpy",
    "joern-c-tainted-memcpy",
    "joern-c-tainted-sprintf-buffer",
    "joern-c-alloc-mul-tainted",
];

fn corpus_timeout() -> Duration {
    let secs = std::env::var("JOERN_CORPUS_TIMEOUT_SECS")
        .ok()
        .and_then(|v| v.parse::<u64>().ok())
        .unwrap_or(600);
    Duration::from_secs(secs)
}

async fn copy_recursive(src: &Path, dst: &Path) {
    let mut stack = vec![(src.to_path_buf(), dst.to_path_buf())];
    while let Some((s, d)) = stack.pop() {
        fs::create_dir_all(&d).await.expect("mkdir");
        let mut entries = fs::read_dir(&s).await.expect("read_dir");
        while let Some(entry) = entries.next_entry().await.expect("next_entry") {
            let path = entry.path();
            let name = entry.file_name();
            let target = d.join(&name);
            let meta = entry.metadata().await.expect("meta");
            if meta.is_dir() {
                stack.push((path, target));
            } else {
                fs::copy(&path, &target).await.expect("copy");
            }
        }
    }
}

#[ignore = "requires local Podman/Docker-compatible runtime and the configured Joern image"]
#[tokio::test]
async fn joern_rule_corpus_combined_run() {
    let work = TempDir::new().expect("temp dir");
    let work_path = work.path();

    // 1. Lay out a combined source tree: copy each <rule_id>/{positive,negative}.c
    //    as <rule_id>__{positive,negative}.c into a single src directory.
    let src_dir = work_path.join("src");
    fs::create_dir_all(&src_dir).await.expect("create src dir");
    for rule in &RULES {
        for kind in &["positive", "negative"] {
            let src = PathBuf::from(FIXTURE_ROOT)
                .join(rule)
                .join(format!("{}.c", kind));
            let dst = src_dir.join(format!("{}__{}.c", rule, kind));
            fs::copy(&src, &dst)
                .await
                .unwrap_or_else(|e| panic!("copy {} -> {}: {}", src.display(), dst.display(), e));
        }
    }

    // 2. Copy rules_joern queries into the workspace under q/
    let q_dir = work_path.join("q");
    copy_recursive(Path::new(QUERY_ASSETS_ROOT), &q_dir).await;

    // 3. podman run joern-parse → cpg.bin
    let work_mount = format!("{}:/work", work_path.display());
    let parse_status = Command::new("podman")
        .args([
            "run",
            "--rm",
            "-v",
            &work_mount,
            JOERN_IMAGE,
            "joern-parse",
            "/work/src",
            "--output",
            "/work/cpg.bin",
        ])
        .status()
        .await
        .expect("spawn podman joern-parse");
    assert!(parse_status.success(), "joern-parse failed: {parse_status}");

    // 4. podman run joern --script orchestrator → findings.json (with timeout)
    let script_fut = Command::new("podman")
        .args([
            "run",
            "--rm",
            "-v",
            &work_mount,
            JOERN_IMAGE,
            "joern",
            "--script",
            "/work/q/c/argus-joern-scan.sc",
            "--param",
            "cpgFile=/work/cpg.bin",
            "--param",
            "sourceDir=/work/src",
            "--param",
            "graphProofOut=/work/proof.json",
            "--param",
            "findingsOut=/work/findings.json",
        ])
        .status();
    let script_status = tokio::time::timeout(corpus_timeout(), script_fut)
        .await
        .expect("orchestrator exceeded JOERN_CORPUS_TIMEOUT_SECS")
        .expect("spawn podman joern --script");
    assert!(
        script_status.success(),
        "orchestrator script failed: {script_status}"
    );

    // 5. Parse findings.json
    let findings_path = work_path.join("findings.json");
    let raw = fs::read_to_string(&findings_path)
        .await
        .expect("read findings.json");
    let doc: Value = serde_json::from_str(&raw).expect("parse findings.json");
    assert_eq!(
        doc["schema_version"], "argus.joern.findings.v1",
        "schema_version mismatch"
    );
    let findings = doc["findings"]
        .as_array()
        .expect("findings.json: findings must be array");

    // 6. Per-rule positive/negative assertions.
    //    Joern's c2cpg may report file_path either as basename or as a path inside
    //    the source root; tolerate both by substring-matching the synthesized name.
    for rule in &RULES {
        let positive_marker = format!("{}__positive.c", rule);
        let negative_marker = format!("{}__negative.c", rule);
        let positive_hits: Vec<&Value> = findings
            .iter()
            .filter(|f| {
                f["rule_id"].as_str() == Some(*rule)
                    && f["file_path"]
                        .as_str()
                        .map(|p| p.contains(&positive_marker))
                        .unwrap_or(false)
            })
            .collect();
        assert!(
            !positive_hits.is_empty(),
            "rule {} did not fire on positive fixture (marker {})",
            rule,
            positive_marker
        );
        let negative_hits: Vec<&Value> = findings
            .iter()
            .filter(|f| {
                f["rule_id"].as_str() == Some(*rule)
                    && f["file_path"]
                        .as_str()
                        .map(|p| p.contains(&negative_marker))
                        .unwrap_or(false)
            })
            .collect();
        assert!(
            negative_hits.is_empty(),
            "rule {} FIRED on negative fixture (FP): {:?}",
            rule,
            negative_hits
        );
    }

    // 7. All finding ids must be distinct (C4 collision check).
    let ids: HashSet<&str> = findings
        .iter()
        .map(|f| f["id"].as_str().unwrap_or(""))
        .collect();
    assert_eq!(
        ids.len(),
        findings.len(),
        "finding id collisions: count={}, distinct={}",
        findings.len(),
        ids.len()
    );

    // 8. For tainted-* rules, evidence.taint_source must be either absent (dataflow
    //    unavailable) or a non-empty string (round-trip integrity, C11).
    for rule in &TAINT_RULES {
        for f in findings
            .iter()
            .filter(|f| f["rule_id"].as_str() == Some(*rule))
        {
            if let Some(ts) = f["evidence"].get("taint_source") {
                if !ts.is_null() {
                    assert!(
                        ts.as_str().map(|s| !s.is_empty()).unwrap_or(false),
                        "taint_source malformed for {}: {:?}",
                        rule,
                        ts
                    );
                }
            }
        }
    }
}
