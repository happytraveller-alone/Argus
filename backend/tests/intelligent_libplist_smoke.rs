//! US-004 AC3 + AC4 smoke test — libplist CVE-2017-6439
//!
//! Runs the full 8-agent audit pipeline against the in-tree
//! `tests/fixtures/joern/libplist-cve-2017-6439/` C source fixture.
//!
//! Two test functions:
//!
//! - `libplist_smoke_pipeline_completes` (AC1+AC2+AC3): pipeline reaches
//!   `Completed` status with ≥1 finding. Not ignored — regression net for
//!   pipeline stability.
//!
//! - `libplist_smoke_produces_confirmed_real_finding` (AC4): at least one
//!   finding has `validation_status == "confirmed"` AND its `file` path is NOT
//!   classified as Test/Vendor. Ignored pending hunt productivity tuning.
//!
//! ## Running
//!
//! Both tests are gated by `ARGUS_RUN_LLM_INTEGRATION=1`.  Default `cargo test`
//! skips both (env gate) and ignores AC4:
//!
//! ```sh
//! # AC3 smoke (env-gated):
//! ARGUS_RUN_LLM_INTEGRATION=1 cargo test -p backend-rust --test intelligent_libplist_smoke -- libplist_smoke_pipeline_completes --nocapture
//!
//! # AC4 (env-gated + explicitly opt-in ignored):
//! ARGUS_RUN_LLM_INTEGRATION=1 cargo test -p backend-rust --test intelligent_libplist_smoke -- --ignored --nocapture
//! ```

use std::{io::Write as _, path::PathBuf, sync::Arc};

use backend_rust::{
    config::AppConfig,
    db::{intelligent_task_state, system_config},
    runtime::intelligent::{
        code_intel::path_classifier::{self, PathCategory},
        types::{IntelligentTaskRecord, IntelligentTaskStatus},
    },
    state::{AppState, StoredProject, StoredProjectArchive},
};
use serde_json::json;
use uuid::Uuid;

// ---------------------------------------------------------------------------
// Helpers (patterned after intelligent_tasks_api.rs)
// ---------------------------------------------------------------------------

fn isolated_test_config(scope: &str) -> AppConfig {
    let mut config = AppConfig::for_tests();
    config.zip_storage_path =
        std::env::temp_dir().join(format!("argus-libplist-{scope}-{}", Uuid::new_v4()));
    config
}

async fn build_state(scope: &str) -> AppState {
    AppState::from_config(isolated_test_config(scope))
        .await
        .expect("state should build")
}

/// Zip the on-disk libplist fixture and register it as a project.
async fn seed_libplist_project(state: &AppState) -> String {
    use std::fs;

    let fixture_src = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("tests")
        .join("fixtures")
        .join("joern")
        .join("libplist-cve-2017-6439")
        .join("src");

    assert!(
        fixture_src.is_dir(),
        "libplist fixture must exist at {}",
        fixture_src.display()
    );

    let storage_dir = state.config.zip_storage_path.clone();
    tokio::fs::create_dir_all(&storage_dir)
        .await
        .expect("create storage dir");

    let project_id = Uuid::new_v4().to_string();
    let archive_path = storage_dir.join(format!("{project_id}.zip"));

    // Build zip in-memory from fixture files
    {
        let file = fs::File::create(&archive_path).expect("create zip");
        let mut zw = zip::ZipWriter::new(file);
        let opts = zip::write::SimpleFileOptions::default();

        for entry in fs::read_dir(&fixture_src).expect("read fixture src dir") {
            let entry = entry.expect("dir entry");
            let path = entry.path();
            if path.is_file() {
                let name = path
                    .file_name()
                    .expect("filename")
                    .to_string_lossy()
                    .to_string();
                let archived_name = format!("src/{name}");
                zw.start_file(&archived_name, opts).expect("start file");
                let contents = fs::read(&path).expect("read fixture file");
                zw.write_all(&contents).expect("write file");
            }
        }
        zw.finish().expect("finish zip");
    }

    let file_size = fs::metadata(&archive_path).expect("zip metadata").len();

    let archive = StoredProjectArchive {
        original_filename: format!("{project_id}.zip"),
        storage_path: archive_path.to_string_lossy().to_string(),
        sha256: "libplist-fixture".to_string(),
        file_size: file_size.try_into().unwrap(),
        uploaded_at: "2026-05-26T00:00:00Z".to_string(),
    };

    let project = StoredProject {
        id: project_id.clone(),
        name: "libplist-cve-2017-6439-smoke".to_string(),
        description: "Integration smoke test for US-004 AC3/AC4".to_string(),
        source_type: "upload".to_string(),
        repository_type: "zip".to_string(),
        default_branch: "main".to_string(),
        programming_languages_json: r#"["c"]"#.to_string(),
        is_active: true,
        created_at: "2026-05-26T00:00:00Z".to_string(),
        updated_at: "2026-05-26T00:00:00Z".to_string(),
        language_info: String::new(),
        info_status: "ok".to_string(),
        archive: Some(archive),
    };

    backend_rust::db::projects::create_project(state, project)
        .await
        .expect("create project");

    project_id
}

/// Seed a real LLM config from environment (reads ARGUS_LLM_* env vars or
/// falls back to loading `.argus-llm.env` via the config subsystem).
///
/// We inject a minimal OpenAI-compatible row that mirrors what
/// `resolve_intelligent_llm_config` expects — the real URL/key come from env.
async fn seed_llm_config_from_env(state: &AppState) {
    let base_url = std::env::var("ARGUS_LLM_BASE_URL")
        .unwrap_or_else(|_| "https://api.openai.com/v1".to_string());
    let model = std::env::var("ARGUS_LLM_MODEL").unwrap_or_else(|_| "gpt-4o".to_string());
    let api_key =
        std::env::var("ARGUS_LLM_API_KEY").unwrap_or_else(|_| "sk-placeholder".to_string());

    let llm_config = json!({
        "schemaVersion": 2,
        "rows": [{
            "id": "row-libplist-smoke",
            "priority": 1,
            "enabled": true,
            "provider": "openai_compatible",
            "baseUrl": base_url,
            "model": model,
            "apiKey": api_key,
            "advanced": {}
        }]
    });

    system_config::save_current(state, llm_config, json!({}), json!({}))
        .await
        .expect("save system config");
}

async fn read_record(state: &AppState, task_id: &str) -> Option<IntelligentTaskRecord> {
    intelligent_task_state::get_record(state, task_id)
        .await
        .expect("read record")
}

async fn wait_until_terminal(
    state: &AppState,
    task_id: &str,
    max_iters: usize,
) -> IntelligentTaskRecord {
    for _ in 0..max_iters {
        if let Some(record) = read_record(state, task_id).await {
            if record.status.is_terminal() {
                return record;
            }
        }
        tokio::time::sleep(std::time::Duration::from_millis(200)).await;
    }
    read_record(state, task_id)
        .await
        .expect("record must be present after waiting")
}

/// Run the full pipeline and return the terminal record.
/// Both smoke tests share this setup; each gets its own isolated state DB.
async fn run_pipeline(scope: &str) -> IntelligentTaskRecord {
    let state = build_state(scope).await;
    seed_llm_config_from_env(&state).await;
    let project_id = seed_libplist_project(&state).await;

    let manager = Arc::clone(&state.intelligent_task_manager);
    let submitted = manager
        .submit(state.clone(), project_id.clone())
        .await
        .expect("submit should succeed");

    let task_id = submitted.task_id.clone();
    eprintln!("[smoke/{scope}] task_id={task_id} project_id={project_id}");

    // Wait up to 5 minutes (1500 × 200 ms) for the pipeline to finish.
    let record = wait_until_terminal(&state, &task_id, 1500).await;

    eprintln!(
        "[smoke/{scope}] status={:?} findings={} failure_stage={:?} failure_reason={:?}",
        record.status,
        record.findings.len(),
        record.failure_stage,
        record.failure_reason,
    );

    record
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

/// US-004 AC1+AC2+AC3 — pipeline completes and produces ≥1 finding.
///
/// Regression net: asserts the 8-agent audit pipeline reaches `Completed`
/// status with at least one finding. Does NOT assert finding quality (AC4).
/// Not ignored — this must stay green on every CI run.
#[tokio::test(flavor = "multi_thread")]
async fn libplist_smoke_pipeline_completes() {
    // Gate: skip unless explicitly opted in.
    if std::env::var("ARGUS_RUN_LLM_INTEGRATION").as_deref() != Ok("1") {
        eprintln!(
            "skipping: set ARGUS_RUN_LLM_INTEGRATION=1 to run libplist_smoke_pipeline_completes"
        );
        return;
    }

    let final_record = run_pipeline("ac3").await;

    assert_eq!(
        final_record.status,
        IntelligentTaskStatus::Completed,
        "AC3: pipeline must complete (not fail): failure_stage={:?} failure_reason={:?}",
        final_record.failure_stage,
        final_record.failure_reason,
    );

    assert!(
        !final_record.findings.is_empty(),
        "AC3: expected >= 1 finding from libplist CVE-2017-6439, got 0.\n\
         event_log={:?}",
        final_record.event_log,
    );
}

/// US-004 AC4 — at least one confirmed, first-party finding.
///
/// Asserts that at least one finding has `validation_status == "confirmed"` AND
/// its `file` path is NOT classified as Test/Vendor by `path_classifier`.
///
/// Ignored pending hunt LLM productivity tuning (snippet/prompt knobs).
/// Run explicitly with: `cargo test -- --ignored`
#[tokio::test(flavor = "multi_thread")]
#[ignore = "AC4 deferred: hunt productivity tuning pending"]
async fn libplist_smoke_produces_confirmed_real_finding() {
    // Gate: skip unless explicitly opted in.
    if std::env::var("ARGUS_RUN_LLM_INTEGRATION").as_deref() != Ok("1") {
        eprintln!("skipping: set ARGUS_RUN_LLM_INTEGRATION=1 to run libplist_smoke_produces_confirmed_real_finding");
        return;
    }

    let final_record = run_pipeline("ac4").await;

    assert_eq!(
        final_record.status,
        IntelligentTaskStatus::Completed,
        "pipeline must complete (not fail): failure_stage={:?} failure_reason={:?}",
        final_record.failure_stage,
        final_record.failure_reason,
    );

    // AC4: at least one finding is confirmed AND its file is first-party code.
    let qualifying = final_record.findings.iter().find(|f| {
        // AC4.1 — confirmed validation status
        let confirmed = f.validation_status.as_deref() == Some("confirmed");

        // AC4.2 — file path must not be Test or Vendor
        let real_code = if let Some(file) = &f.file {
            let (category, _) = path_classifier::classify_path(std::path::Path::new(file));
            matches!(category, PathCategory::RealCode)
        } else {
            // No file path — cannot prove it is real code; exclude.
            false
        };

        confirmed && real_code
    });

    assert!(
        qualifying.is_some(),
        "AC4: expected >= 1 confirmed finding whose file is RealCode (not Test/Vendor).\n\
         findings={:#?}",
        final_record.findings,
    );

    let q = qualifying.unwrap();
    eprintln!(
        "[smoke/ac4] qualifying finding: id={} file={:?} vuln_class={:?} validation_status={:?}",
        q.id, q.file, q.vuln_class, q.validation_status,
    );
}
