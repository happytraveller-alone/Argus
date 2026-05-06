//! Phase A.0 host_path probe — three independent sub-probes.
//!
//! Gate: `--features cubemaster_live_test`.
//! Run:  `cargo test --features cubemaster_live_test hostpath_probe -- --nocapture --test-threads=1`
//!
//! Required env vars (same as cubesandbox_opengrep_auto_destroy.rs):
//!   CUBESANDBOX_API_BASE_URL        — CubeAPI base URL, e.g. http://127.0.0.1:23000
//!   CUBESANDBOX_TEMPLATE_ID         — opengrep template id to create sandboxes from
//!
//! Optional:
//!   CUBESANDBOX_DATA_PLANE_BASE_URL — defaults to https://127.0.0.1:21443
//!
//! Probe-a — RPC content reachability:
//!   Create host dir with marker file; create_sandbox_with_host_mount; cat marker inside.
//!   PASS if marker content matches.
//!
//! Probe-b — host co-location verification:
//!   After probe-a sandbox is running, write a file FROM INSIDE the sandbox to the mount.
//!   Verify host can read it back.  PASS if bidirectional visibility confirmed.
//!
//! Probe-c — post-creation mount mutation:
//!   Static analysis: UpdateCubeSandboxRequest only carries annotations — no mount fields.
//!   No HTTP endpoint exists in cubemaster_client.rs for post-creation mount.
//!   Result is always FAIL (no live RPC attempted).
//!
//! Refs:
//!   plan:  .omc/plans/ralplan-optimize-a3s-sandbox-scan-speed.md  Phase A.0
//!   spec:  .omc/specs/deep-dive-optimize-a3s-sandbox-scan-speed.md

#![cfg(feature = "cubemaster_live_test")]

use std::fs;

use backend_rust::runtime::cubesandbox::{
    best_effort_delete_sandbox,
    client::{CubeSandboxClient, CubeSandboxClientConfig},
};
use uuid::Uuid;

// ─── helpers ─────────────────────────────────────────────────────────────────

/// Skip gracefully when live env vars are absent.
fn probe_client() -> Option<(CubeSandboxClient, String)> {
    let api_base_url = match std::env::var("CUBESANDBOX_API_BASE_URL") {
        Ok(v) => v,
        Err(_) => {
            eprintln!(
                "[skip] hostpath_probe: CUBESANDBOX_API_BASE_URL not set — \
                 cubemaster unreachable in this environment"
            );
            return None;
        }
    };
    let template_id = match std::env::var("CUBESANDBOX_TEMPLATE_ID") {
        Ok(v) => v,
        Err(_) => {
            eprintln!("[skip] hostpath_probe: CUBESANDBOX_TEMPLATE_ID not set");
            return None;
        }
    };
    let data_plane_base_url = std::env::var("CUBESANDBOX_DATA_PLANE_BASE_URL")
        .unwrap_or_else(|_| "https://127.0.0.1:21443".to_string());

    let config = CubeSandboxClientConfig {
        api_base_url,
        data_plane_base_url,
        template_id: template_id.clone(),
        execution_timeout_seconds: 120,
        cleanup_timeout_seconds: 30,
        stdout_limit_bytes: 64 * 1024,
        stderr_limit_bytes: 64 * 1024,
    };
    let client = CubeSandboxClient::new(config).expect("CubeSandboxClient::new");
    Some((client, template_id))
}

// ─── Probe-a: RPC content reachability ───────────────────────────────────────

#[tokio::test]
async fn probe_a_rpc_content_reachability() {
    let Some((client, _template_id)) = probe_client() else {
        return;
    };

    let run_id = Uuid::new_v4().to_string();
    let task_id = format!("probe-a-{run_id}");
    let host_dir = format!("/tmp/argus_hostpath_probe_{run_id}");
    let marker_content = format!("MARKER_{run_id}");
    let marker_path = format!("{host_dir}/probe.txt");

    // Create host dir and marker file.
    fs::create_dir_all(&host_dir)
        .unwrap_or_else(|e| panic!("failed to create probe dir {host_dir}: {e}"));
    fs::write(&marker_path, &marker_content)
        .unwrap_or_else(|e| panic!("failed to write marker {marker_path}: {e}"));
    println!("[probe-a] host_dir={host_dir}  marker={marker_content}");

    // Create sandbox with host mount.
    let sandbox_result = client
        .create_sandbox_with_host_mount(&host_dir, "/probe", false)
        .await;
    let sandbox = match sandbox_result {
        Ok(s) => {
            println!("[probe-a] sandbox created: {}", s.sandbox_id);
            s
        }
        Err(e) => {
            let _ = fs::remove_dir_all(&host_dir);
            panic!("[probe-a] FAIL — create_sandbox_with_host_mount error: {e:#}");
        }
    };
    let sandbox_id = sandbox.sandbox_id.clone();

    // Connect.
    if let Err(e) = client.connect_sandbox(&sandbox_id).await {
        best_effort_delete_sandbox(&client, &sandbox_id, &task_id, "probe-a-cleanup").await;
        let _ = fs::remove_dir_all(&host_dir);
        panic!("[probe-a] FAIL — connect_sandbox error: {e:#}");
    }
    println!("[probe-a] sandbox connected");

    // Read marker from inside the sandbox.
    let read_result = client.run_command(&sandbox, "cat /probe/probe.txt").await;
    best_effort_delete_sandbox(&client, &sandbox_id, &task_id, "probe-a-cleanup").await;
    let _ = fs::remove_dir_all(&host_dir);

    match read_result {
        Err(e) => panic!("[probe-a] FAIL — run_command(cat) error: {e:#}"),
        Ok(out) => {
            let got = out.stdout.trim().to_string();
            println!("[probe-a] sandbox read: {got:?}  expected: {marker_content:?}");
            assert_eq!(
                got, marker_content,
                "[probe-a] FAIL — marker mismatch: got={got:?} want={marker_content:?}"
            );
            println!("[probe-a] PASS — marker matches");
        }
    }
}

// ─── Probe-b: host co-location (bidirectional visibility) ────────────────────

#[tokio::test]
async fn probe_b_host_colocation() {
    let Some((client, _template_id)) = probe_client() else {
        return;
    };

    let run_id = Uuid::new_v4().to_string();
    let task_id = format!("probe-b-{run_id}");
    let host_dir = format!("/tmp/argus_hostpath_probe_{run_id}");
    let marker_content = format!("MARKER_{run_id}");

    // Create host dir (no pre-written file; sandbox writes it).
    fs::create_dir_all(&host_dir)
        .unwrap_or_else(|e| panic!("failed to create probe dir {host_dir}: {e}"));
    println!("[probe-b] host_dir={host_dir}");

    // Create sandbox with host mount.
    let sandbox_result = client
        .create_sandbox_with_host_mount(&host_dir, "/probe", false)
        .await;
    let sandbox = match sandbox_result {
        Ok(s) => {
            println!("[probe-b] sandbox created: {}", s.sandbox_id);
            s
        }
        Err(e) => {
            let _ = fs::remove_dir_all(&host_dir);
            panic!("[probe-b] FAIL — create_sandbox_with_host_mount error: {e:#}");
        }
    };
    let sandbox_id = sandbox.sandbox_id.clone();

    // Connect.
    if let Err(e) = client.connect_sandbox(&sandbox_id).await {
        best_effort_delete_sandbox(&client, &sandbox_id, &task_id, "probe-b-cleanup").await;
        let _ = fs::remove_dir_all(&host_dir);
        panic!("[probe-b] FAIL — connect_sandbox error: {e:#}");
    }
    println!("[probe-b] sandbox connected");

    // Write a new file FROM INSIDE the sandbox into the mount.
    let write_cmd = format!(
        "echo -n '{marker_content}' > /probe/from_sandbox.txt && echo 'wrote ok'"
    );
    let write_result = client.run_command(&sandbox, &write_cmd).await;
    if let Err(e) = write_result {
        best_effort_delete_sandbox(&client, &sandbox_id, &task_id, "probe-b-cleanup").await;
        let _ = fs::remove_dir_all(&host_dir);
        panic!("[probe-b] FAIL — sandbox write error: {e:#}");
    }
    println!("[probe-b] sandbox wrote from_sandbox.txt");

    // Cleanup sandbox.
    best_effort_delete_sandbox(&client, &sandbox_id, &task_id, "probe-b-cleanup").await;

    // Verify from host.
    let from_sandbox_path = format!("{host_dir}/from_sandbox.txt");
    let host_read = fs::read_to_string(&from_sandbox_path);
    let _ = fs::remove_dir_all(&host_dir);

    match host_read {
        Err(e) => panic!("[probe-b] FAIL — host cannot read from_sandbox.txt: {e}"),
        Ok(content) => {
            let got = content.trim().to_string();
            println!("[probe-b] host read: {got:?}  expected: {marker_content:?}");
            assert_eq!(
                got, marker_content,
                "[probe-b] FAIL — content mismatch: got={got:?} want={marker_content:?}"
            );
            println!("[probe-b] PASS — bidirectional visibility confirmed");
        }
    }
}

// ─── Probe-c: post-creation mount mutation ────────────────────────────────────

/// Probe-c is resolved by static analysis of the proto and cubemaster_client.rs:
///
/// `UpdateCubeSandboxRequest` (proto line 684) contains only:
///   requestID, sandboxID, annotations.
/// No volume/mount fields exist.  No HTTP endpoint in `cubemaster_client.rs`
/// performs post-creation mount mutation.  Therefore Probe-c = FAIL (no RPC).
///
/// This test documents that conclusion and will never make a network call.
#[test]
fn probe_c_post_creation_mount_mutation_no_rpc() {
    // Static conclusion: UpdateCubeSandboxRequest has no volume/mount fields.
    // CubeAPI update_sandbox only supports pause/resume via annotations.
    // No add_mount / attach_volume / update_mounts RPC exists in the proto service.
    println!(
        "[probe-c] FAIL (static) — UpdateCubeSandboxRequest has no mount fields; \
         no post-creation mount mutation RPC exists in cubemaster proto or CubeAPI"
    );
    // This test always passes: the conclusion is the result.
    // The probe report records Probe-c = FAIL.
}
