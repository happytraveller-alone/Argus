use std::{collections::BTreeSet, fs, path::Path, process::Command};

use backend_rust::{db::scan_rule_assets, scan::joern};
use serde_json::Value;
use sha2::{Digest, Sha256};
use tempfile::TempDir;

const FIXTURE_ROOT: &str = concat!(
    env!("CARGO_MANIFEST_DIR"),
    "/tests/fixtures/joern/libplist-cve-2017-6439"
);
const MANIFEST_TEXT: &str = include_str!("fixtures/joern/libplist-cve-2017-6439/manifest.json");
const BPLIST_SOURCE: &[u8] = include_bytes!("fixtures/joern/libplist-cve-2017-6439/src/bplist.c");
const QUERY_ASSET: &str =
    include_str!("../assets/scan_rule_assets/rules_joern/c/argus-joern-scan.sc");

const EXPECTED_JOERN_ASSET_PATHS: [&str; 10] = [
    "rules_joern/c/argus-joern-scan.sc",
    "rules_joern/c/lib/common.sc",
    "rules_joern/c/lib/unsafe_gets.sc",
    "rules_joern/c/lib/tainted_strcpy.sc",
    "rules_joern/c/lib/tainted_memcpy.sc",
    "rules_joern/c/lib/tainted_sprintf_buffer.sc",
    "rules_joern/c/lib/strncpy_missing_null_term.sc",
    "rules_joern/c/lib/alloc_mul_tainted.sc",
    "rules_joern/c/lib/strlen_int_truncation.sc",
    "rules_joern/c/lib/signed_left_shift.sc",
];

fn manifest() -> Value {
    serde_json::from_str(MANIFEST_TEXT).expect("manifest JSON")
}

fn sha256_hex(bytes: &[u8]) -> String {
    let mut hasher = Sha256::new();
    hasher.update(bytes);
    let digest = hasher.finalize();
    digest.iter().map(|byte| format!("{byte:02x}")).collect()
}

fn copy_fixture_output(output_dir: &Path) {
    let expected = Path::new(FIXTURE_ROOT).join("expected-output");
    fs::create_dir_all(output_dir).expect("create output dir");
    for name in ["summary.json", "graph-proof.json", "findings.json"] {
        fs::copy(expected.join(name), output_dir.join(name)).expect("copy expected Joern output");
    }
}

#[test]
fn libplist_fixture_manifest_checksum_and_provenance_are_locked() {
    let payload = manifest();
    assert_eq!(payload["schema_version"], "argus.joern.fixture.v1");
    assert_eq!(payload["fixture_id"], "libplist-cve-2017-6439");
    assert_eq!(payload["cve"], "CVE-2017-6439");
    assert_eq!(payload["cwe"], "CWE-120");
    assert_eq!(payload["runtime_network_download"], false);
    assert_eq!(
        payload["vulnerability_reference"]["nvd"],
        "https://nvd.nist.gov/vuln/detail/CVE-2017-6439"
    );
    assert!(payload["vulnerability_reference"]["nvd_summary"]
        .as_str()
        .unwrap()
        .contains("parse_string_node"));
    assert_eq!(
        payload["source"]["upstream_url"],
        "https://raw.githubusercontent.com/libimobiledevice/libplist/1.12/src/bplist.c"
    );
    assert_eq!(payload["source"]["upstream_tag"], "1.12");
    assert_eq!(
        payload["source"]["sha256"].as_str().unwrap(),
        sha256_hex(BPLIST_SOURCE)
    );
    assert_eq!(
        payload["source"]["bytes"].as_u64().unwrap(),
        BPLIST_SOURCE.len() as u64
    );

    let text = std::str::from_utf8(BPLIST_SOURCE).expect("fixture source should be UTF-8 C code");
    assert!(text.contains("static plist_t parse_string_node"));
    assert!(text.contains("memcpy(data->strval, bnode, size);"));
    assert_eq!(payload["expected"]["file"], "src/bplist.c");
    assert_eq!(payload["expected"]["function"], "parse_string_node");
    assert_eq!(payload["expected"]["sink"], "memcpy");
}

#[tokio::test]
async fn libplist_fixture_expected_output_maps_to_cve_static_finding() {
    let payload = manifest();
    let temp = TempDir::new().expect("temp dir");
    copy_fixture_output(temp.path());
    let known_paths = BTreeSet::from(["src/bplist.c".to_string()]);

    let parsed = joern::parse_output_dir(
        temp.path(),
        "joern-fixture-task",
        Some(FIXTURE_ROOT),
        Some(&known_paths),
        1_000_000,
    )
    .await
    .expect("parse expected Joern fixture output");

    assert_eq!(parsed.graph_proof["files"][0], payload["expected"]["file"]);
    assert_eq!(
        parsed.graph_proof["functions"][0],
        payload["expected"]["function"]
    );
    let target = parsed.findings.iter().find(|f| {
        f.payload.get("rule").and_then(|r| r.get("id"))
            .and_then(|v| v.as_str()) == Some("joern-c-tainted-memcpy")
            && f.payload.get("start_line").and_then(|v| v.as_u64()) == Some(288)
    }).expect("expected joern-c-tainted-memcpy finding at line 288");
    let finding_payload = &target.payload;
    assert_eq!(finding_payload["engine"], "joern");
    assert_eq!(
        finding_payload["rule"]["id"],
        payload["expected"]["rule_id"]
    );
    assert_eq!(finding_payload["file_path"], payload["expected"]["file"]);
    assert_eq!(finding_payload["function"], payload["expected"]["function"]);
    assert_eq!(
        finding_payload["start_line"],
        payload["expected"]["finding_line"]
    );
    assert_eq!(finding_payload["severity"], payload["expected"]["severity"]);
    assert_eq!(
        finding_payload["confidence"],
        payload["expected"]["confidence"]
    );
    assert_eq!(finding_payload["cve"][0], "CVE-2017-6439");
    assert_eq!(finding_payload["cwe"][0], "CWE-120");
    assert_eq!(finding_payload["raw_joern"]["evidence"]["call"], "memcpy");
}

#[tokio::test]
async fn joern_rule_asset_is_bundled_and_targets_libplist_cve() {
    let temp = TempDir::new().expect("temp dir");
    let assets = scan_rule_assets::discover_rule_assets().expect("discover assets");
    let joern_assets: Vec<_> = assets
        .into_iter()
        .filter(|asset| asset.engine == "joern")
        .collect();

    // Filter to only .sc assets (UPSTREAM_PIN.toml is not a query asset)
    let scala_assets: Vec<_> = joern_assets
        .iter()
        .filter(|a| a.asset_path.ends_with(".sc"))
        .collect();
    assert_eq!(
        scala_assets.len(),
        EXPECTED_JOERN_ASSET_PATHS.len(),
        "expected {} .sc joern assets (orchestrator + common + 8 modules), found {}",
        EXPECTED_JOERN_ASSET_PATHS.len(),
        scala_assets.len()
    );
    let asset_paths: std::collections::HashSet<&str> =
        scala_assets.iter().map(|a| a.asset_path.as_str()).collect();
    for expected in &EXPECTED_JOERN_ASSET_PATHS {
        assert!(asset_paths.contains(expected), "missing joern asset {}", expected);
    }

    let orchestrator = scala_assets
        .iter()
        .find(|a| a.asset_path == "rules_joern/c/argus-joern-scan.sc")
        .expect("orchestrator asset missing");
    assert!(
        orchestrator.content.contains("//> using file lib/tainted_memcpy.sc")
            && orchestrator.content.contains("tainted_memcpy.run"),
        "orchestrator missing replpp include directive or run() reference for tainted_memcpy module"
    );
    assert!(
        orchestrator.content.contains("common.tagCves"),
        "orchestrator missing CVE post-filter application"
    );
    let common_sc = scala_assets
        .iter()
        .find(|a| a.asset_path == "rules_joern/c/lib/common.sc")
        .expect("common.sc asset missing");
    assert!(
        common_sc.content.contains("CVE-2017-6439"),
        "common.sc knownCves map missing libplist CVE entry"
    );

    // graph-proof emission moved to common.sc::writeProof in the v2 refactor;
    // the orchestrator now calls common.writeProof rather than emitting inline.
    assert!(
        common_sc.content.contains("graph-proof"),
        "common.sc missing graph-proof schema literal"
    );
    let materialized = joern::materialize_rule_assets(temp.path(), joern_assets)
        .await
        .expect("materialize Joern query assets")
        .expect("non-empty query dir");
    let materialized_query = materialized.join(joern::QUERY_SCRIPT_REL_PATH);
    let query = fs::read_to_string(&materialized_query).expect("materialized Joern query");
    assert_eq!(query, QUERY_ASSET);

    let wrapper = joern::build_wrapper_script(&joern::JoernOutputPaths::default());
    assert!(
        wrapper.contains(&format!(
            "joern --script \"$QUERY_DIR/{}\"",
            joern::QUERY_SCRIPT_REL_PATH
        )),
        "wrapper must execute the same relative query path materialized from bundled assets"
    );
}

#[test]
fn joern_fixture_packaging_has_no_runtime_download_path() {
    let fixture_root = Path::new(FIXTURE_ROOT);
    for relative in [
        "README.md",
        "manifest.json",
        "expected-output/summary.json",
        "expected-output/graph-proof.json",
        "expected-output/findings.json",
    ] {
        let text = fs::read_to_string(fixture_root.join(relative)).expect("read fixture text");
        let lower = text.to_ascii_lowercase();
        assert!(
            !lower.contains("curl ")
                && !lower.contains("wget ")
                && !lower.contains("download at runtime"),
            "fixture metadata must not define a runtime downloader: {relative}"
        );
    }
}

#[ignore = "requires local Podman/Docker-compatible runtime and the configured Joern image"]
#[test]
fn live_joern_container_builds_graph_and_reports_libplist_cve_fixture() {
    let root = Path::new(env!("CARGO_MANIFEST_DIR")).parent().unwrap();
    let script = root.join("scripts/rebuild-joern-runner-verify.sh");
    let output = TempDir::new().expect("output dir");
    let status = Command::new("bash")
        .arg(script)
        .arg("--fixture")
        .arg(FIXTURE_ROOT)
        .arg("--output-dir")
        .arg(output.path())
        .arg("--no-pull")
        .status()
        .expect("run Joern verification script");
    assert!(
        status.success(),
        "live Joern verification script failed: {status}"
    );
}
