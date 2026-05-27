//! Step 13 — AC1/AC4 integration tests for blacklist + reflection.
//!
//! AC1: blacklisted findings (e.g. `tests/...`) must never reach the final
//! task record. The reflection meta-loop in `run_pipeline_with_config`
//! filters them out via `code_intel::is_blacklisted` and stage-level
//! predicates that mark `BLACKLIST_VIOLATION`.
//!
//! AC4: a caller-supplied `path_blacklist_extra` (via `AuditConfigOverride`)
//! must extend the default blacklist. Findings under `custom_dir/` should
//! be excluded when the override is provided, and present otherwise (since
//! `custom_dir` is NOT in the default `BLACKLIST_DIRS`).
//!
//! The pipeline is driven through `IntelligentTaskManager::with_invoker` and
//! a `MockInvoker` that detects the active stage by sniffing the prompt
//! prefix (`stage_prompt()` in `audit_pipeline/mod.rs` always emits
//! `"You are the {stage} agent ..."`) and returns canned JSON. The full
//! 8-agent pipeline runs without any HTTP traffic.

use std::{
    collections::{HashMap, VecDeque},
    io::Write as _,
    sync::Arc,
};

use backend_rust::{
    config::AppConfig,
    db::{intelligent_task_state, system_config},
    runtime::intelligent::{
        audit_pipeline::types::AuditConfigOverride,
        config::IntelligentLlmConfig,
        llm::{IntelligentLlmInvocation, IntelligentLlmInvocationError, IntelligentLlmInvoker},
        task::IntelligentTaskManager,
        types::{IntelligentTaskEvent, IntelligentTaskRecord, IntelligentTaskStatus},
    },
    state::{AppState, StoredProject, StoredProjectArchive},
};
use serde_json::{json, Value};
use tokio::sync::Mutex;
use uuid::Uuid;

// ---------------------------------------------------------------------------
// MockInvoker — stage-aware canned-response invoker
// ---------------------------------------------------------------------------

/// Detect the active pipeline stage from the prompt.
///
/// `audit_pipeline::stage_prompt()` always renders the prompt with the
/// prefix `"You are the {stage} agent ..."`. Sniffing the first line is
/// enough — we don't need to parse the contract body.
fn stage_from_prompt(prompt: &str) -> &'static str {
    let head = prompt.lines().next().unwrap_or("");
    for stage in [
        "recon", "hunt", "validate", "gapfill", "dedupe", "trace", "feedback", "report",
    ] {
        if head.contains(&format!("the {stage} agent")) {
            return stage;
        }
    }
    "unknown"
}

#[derive(Default)]
struct MockState {
    /// FIFO of canned responses per stage. Empty queue → default response.
    responses: HashMap<String, VecDeque<Value>>,
}

#[derive(Clone)]
struct MockInvoker {
    state: Arc<Mutex<MockState>>,
}

impl MockInvoker {
    fn new() -> Self {
        Self {
            state: Arc::new(Mutex::new(MockState::default())),
        }
    }

    async fn queue(&self, stage: &str, value: Value) {
        let mut guard = self.state.lock().await;
        guard
            .responses
            .entry(stage.to_string())
            .or_default()
            .push_back(value);
    }
}

#[async_trait::async_trait]
impl IntelligentLlmInvoker for MockInvoker {
    async fn invoke(
        &self,
        prompt: &str,
        _config: &IntelligentLlmConfig,
    ) -> Result<IntelligentLlmInvocation, IntelligentLlmInvocationError> {
        let stage = stage_from_prompt(prompt);
        let value = {
            let mut guard = self.state.lock().await;
            guard
                .responses
                .get_mut(stage)
                .and_then(|q| q.pop_front())
                .unwrap_or_else(|| default_response(stage))
        };
        Ok(IntelligentLlmInvocation {
            content: value.to_string(),
            finished_at: "2026-05-27T00:00:00Z".to_string(),
            attempt_event: IntelligentTaskEvent::new("llm_attempt"),
        })
    }
}

/// Safe defaults when the per-stage queue is empty. These mirror the minimal
/// shape each stage's deserializer accepts and pass the default
/// `StageGatesPolicy` predicates wherever possible.
fn default_response(stage: &str) -> Value {
    match stage {
        "recon" => json!({
            "architectureSummary": "default",
            "subsystems": [],
            "initialTasks": [{
                "task_id": "t-default",
                "source": "recon",
                "attack_class": "generic",
                "scope_hint": "default",
                "target_files": ["src/real.py"],
                "rationale": "fallback",
                "priority": 3,
            }],
        }),
        "hunt" => json!({ "findings": [] }),
        "validate" => json!({ "findings": [] }),
        "gapfill" => json!({ "new_tasks": [], "rationale": "no gaps" }),
        "dedupe" => json!({ "groups": [] }),
        "trace" => json!({ "traces": [] }),
        "feedback" => json!({ "new_tasks": [], "patterns": [] }),
        "report" => json!({
            "summary": "Mock audit complete. No issues to report in this sandbox.",
            "findings": [],
            "recommendations": [],
        }),
        _ => json!({}),
    }
}

// ---------------------------------------------------------------------------
// State / project seeding
// ---------------------------------------------------------------------------

fn isolated_test_config(scope: &str) -> AppConfig {
    let mut config = AppConfig::for_tests();
    config.zip_storage_path =
        std::env::temp_dir().join(format!("argus-blacklist-{scope}-{}", Uuid::new_v4()));
    config
}

async fn build_state(
    scope: &str,
    invoker: Arc<dyn IntelligentLlmInvoker + Send + Sync>,
) -> AppState {
    let mut state = AppState::from_config(isolated_test_config(scope))
        .await
        .expect("state should build");
    state.intelligent_task_manager = Arc::new(IntelligentTaskManager::with_invoker(invoker));
    state
}

/// Seed an enabled openai-compatible LLM config so `submit` resolves a config.
async fn seed_llm_config(state: &AppState) {
    let cfg = json!({
        "schemaVersion": 2,
        "rows": [{
            "id": "row-mock",
            "priority": 1,
            "enabled": true,
            "provider": "openai_compatible",
            "baseUrl": "http://mock.invalid/v1",
            "model": "mock-model",
            "apiKey": "sk-mock",
            "advanced": {}
        }]
    });
    system_config::save_current(state, cfg, json!({}), json!({}))
        .await
        .expect("save system config");
}

/// Build a tiny in-memory zip archive with the given relative paths populated
/// with non-empty placeholder source. Register the project so the pipeline
/// can locate it via `state.config.zip_storage_path`.
async fn seed_project_with_files(state: &AppState, paths: &[&str]) -> String {
    let storage_dir = state.config.zip_storage_path.clone();
    tokio::fs::create_dir_all(&storage_dir)
        .await
        .expect("create storage dir");
    let project_id = Uuid::new_v4().to_string();
    let archive_path = storage_dir.join(format!("{project_id}.zip"));

    {
        let file = std::fs::File::create(&archive_path).expect("create zip");
        let mut zw = zip::ZipWriter::new(file);
        let opts = zip::write::SimpleFileOptions::default();
        for path in paths {
            zw.start_file(*path, opts).expect("start file");
            // Non-empty body so list_entries reports size > 0.
            zw.write_all(format!("// {path}\nfn placeholder() {{}}\n").as_bytes())
                .expect("write file");
        }
        zw.finish().expect("finish zip");
    }

    let file_size = std::fs::metadata(&archive_path)
        .expect("zip metadata")
        .len() as i64;
    let archive = StoredProjectArchive {
        original_filename: format!("{project_id}.zip"),
        storage_path: archive_path.to_string_lossy().to_string(),
        sha256: "mock-fixture".to_string(),
        file_size,
        uploaded_at: "2026-05-27T00:00:00Z".to_string(),
    };
    let project = StoredProject {
        id: project_id.clone(),
        name: format!("blacklist-fixture-{project_id}"),
        description: String::new(),
        source_type: "upload".to_string(),
        repository_type: "zip".to_string(),
        default_branch: "main".to_string(),
        programming_languages_json: "[]".to_string(),
        is_active: true,
        created_at: "2026-05-27T00:00:00Z".to_string(),
        updated_at: "2026-05-27T00:00:00Z".to_string(),
        language_info: String::new(),
        info_status: "ok".to_string(),
        archive: Some(archive),
    };
    backend_rust::db::projects::create_project(state, project)
        .await
        .expect("create project");
    project_id
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
        if let Some(rec) = read_record(state, task_id).await {
            if rec.status.is_terminal() {
                return rec;
            }
        }
        tokio::time::sleep(std::time::Duration::from_millis(50)).await;
    }
    read_record(state, task_id)
        .await
        .expect("record present after waiting")
}

// ---------------------------------------------------------------------------
// Canned-response helpers
// ---------------------------------------------------------------------------

/// Recon output that hands hunt two tasks: one targets a blacklisted file,
/// one targets a clean file.
fn recon_two_tasks(real_path: &str, vuln_path: &str) -> Value {
    json!({
        "architectureSummary": "fixture",
        "subsystems": [{
            "name": "core",
            "path": "src/",
            "purpose": "fixture core",
        }],
        "initialTasks": [
            {
                "task_id": "t-real",
                "source": "recon",
                "attack_class": "injection",
                "scope_hint": "scan real code",
                "target_files": [real_path],
                "rationale": "real file scan",
                "priority": 2,
            },
            {
                "task_id": "t-vuln",
                "source": "recon",
                "attack_class": "injection",
                "scope_hint": "scan vuln path",
                "target_files": [vuln_path],
                "rationale": "vuln path scan",
                "priority": 2,
            },
        ],
    })
}

fn hunt_with_findings(real_path: &str, vuln_path: &str) -> Value {
    json!({
        "findings": [
            {
                "findingId": "f-real-1",
                "file": real_path,
                "lineStart": 10,
                "lineEnd": 12,
                "vulnClass": "injection",
                "severity": "high",
                "description": "Mock finding in real code",
                "evidence": "format!(\"{}\", input)",
                "confidence": 0.9,
                "taskId": "t-real",
                "language": "python",
            },
            {
                "findingId": "f-vuln-1",
                "file": vuln_path,
                "lineStart": 5,
                "lineEnd": 6,
                "vulnClass": "injection",
                "severity": "high",
                "description": "Mock finding in non-source path",
                "evidence": "exec(user_input)",
                "confidence": 0.9,
                "taskId": "t-vuln",
                "language": "python",
            },
        ]
    })
}

fn validate_confirm_all(findings: &Value) -> Value {
    let arr = findings["findings"].as_array().cloned().unwrap_or_default();
    let mut validated = Vec::new();
    for f in arr {
        let mut vf = f.clone();
        vf["validationStatus"] = Value::String("confirmed".to_string());
        vf["validationRationale"] = Value::String("Mock confirmed".to_string());
        validated.push(vf);
    }
    json!({ "findings": validated })
}

fn dedupe_groups_for(findings: &Value) -> Value {
    let arr = findings["findings"].as_array().cloned().unwrap_or_default();
    let mut groups = Vec::new();
    for (idx, f) in arr.iter().enumerate() {
        let fid = f["findingId"].as_str().unwrap_or("").to_string();
        groups.push(json!({
            "groupId": format!("g-{idx}"),
            "canonicalFindingId": fid,
            "findingIds": [fid],
            "rootCause": "mock",
        }));
    }
    json!({ "groups": groups })
}

fn trace_for(findings: &Value) -> Value {
    let arr = findings["findings"].as_array().cloned().unwrap_or_default();
    let mut traces = Vec::new();
    for f in arr.iter() {
        let fid = f["findingId"].as_str().unwrap_or("").to_string();
        traces.push(json!({
            "findingId": fid,
            "reachable": true,
            "confidence": 0.9,
            "rationale": "mock trace",
        }));
    }
    json!({ "traces": traces })
}

/// Queue every stage with enough responses to satisfy retry budgets
/// (recon=2, hunt=3, validate=2, dedupe=1, trace=1, report=2 retries) so
/// that a single predicate failure does not exhaust the queue.
async fn queue_full_pipeline(
    mock: &MockInvoker,
    recon: Value,
    hunt: Value,
    validate: Value,
    dedupe: Value,
    trace: Value,
    report: Value,
) {
    // Same canned response works for every attempt within a stage.
    for _ in 0..6 {
        mock.queue("recon", recon.clone()).await;
        mock.queue("hunt", hunt.clone()).await;
        mock.queue("validate", validate.clone()).await;
        mock.queue("dedupe", dedupe.clone()).await;
        mock.queue("trace", trace.clone()).await;
        mock.queue("report", report.clone()).await;
    }
}

// ---------------------------------------------------------------------------
// AC1 — blacklisted findings never reach the final task record
// ---------------------------------------------------------------------------

#[tokio::test(flavor = "multi_thread")]
async fn blacklisted_findings_never_reach_record() {
    let mock = Arc::new(MockInvoker::new());
    let state = build_state("ac1", mock.clone()).await;
    seed_llm_config(&state).await;

    let real_path = "src/real.py";
    // "tests/" is a TEST_DIRS entry → is_blacklisted returns Some("test_dir").
    let vuln_path = "tests/vuln.py";
    let project_id = seed_project_with_files(&state, &[real_path, vuln_path]).await;

    let recon = recon_two_tasks(real_path, vuln_path);
    let hunt = hunt_with_findings(real_path, vuln_path);
    // Hunt predicate fires BLACKLIST_VIOLATION on the vuln finding. Reflection
    // re-runs hunt; we queue a "clean" hunt output without the vuln finding.
    let hunt_clean = json!({
        "findings": [hunt["findings"][0].clone()]
    });
    let validate_clean = validate_confirm_all(&hunt_clean);
    let dedupe = dedupe_groups_for(&hunt_clean);
    let trace = trace_for(&hunt_clean);
    let report = json!({
        "summary": "Mock audit complete. AC1 path-blacklist exclusion verified.",
        "findings": [],
        "recommendations": [],
    });

    // Queue the first hunt response with the blacklisted finding so reflection
    // observes the violation, then ALL subsequent hunt calls return the clean
    // output.
    mock.queue("recon", recon).await;
    mock.queue("hunt", hunt).await; // first attempt — triggers reflection
    for _ in 0..8 {
        mock.queue("hunt", hunt_clean.clone()).await;
    }
    for _ in 0..6 {
        mock.queue("validate", validate_clean.clone()).await;
        mock.queue("dedupe", dedupe.clone()).await;
        mock.queue("trace", trace.clone()).await;
        mock.queue("report", report.clone()).await;
    }

    let manager = Arc::clone(&state.intelligent_task_manager);
    let submitted = manager
        .submit(state.clone(), project_id.clone(), None)
        .await
        .expect("submit succeeds");

    let record = wait_until_terminal(&state, &submitted.task_id, 600).await;

    eprintln!(
        "[ac1] status={:?} findings={} failure={:?}/{:?}",
        record.status,
        record.findings.len(),
        record.failure_stage,
        record.failure_reason,
    );

    // AC1 core assertion: no final finding has a file path under any
    // built-in blacklist (tests/, vendor/, examples/, ...).
    for f in &record.findings {
        if let Some(file) = &f.file {
            let path = std::path::Path::new(file);
            let reason = backend_rust::runtime::intelligent::code_intel::is_blacklisted(path, &[]);
            assert!(
                reason.is_none(),
                "blacklisted path leaked to record: {file} (reason={reason:?})"
            );
        }
    }
}

// ---------------------------------------------------------------------------
// AC4 — per-task override extends the path blacklist
// ---------------------------------------------------------------------------

/// H1: prepare a fresh MockInvoker pre-queued with the SAME canned responses
/// used by both Run A and Run B. The LLM continues to emit the custom_dir
/// finding every round — the ONLY variable between runs is the
/// `AuditConfigOverride.path_blacklist_extra`. This isolates the override as
/// the cause of any observable difference.
async fn prepare_mock_with_blacklisted_finding(real_path: &str, custom_path: &str) -> MockInvoker {
    let mock = MockInvoker::new();
    let recon = recon_two_tasks(real_path, custom_path);
    let hunt = hunt_with_findings(real_path, custom_path);
    let validate = validate_confirm_all(&hunt);
    let dedupe = dedupe_groups_for(&hunt);
    let trace = trace_for(&hunt);
    let report = json!({
        "summary": "Mock audit complete. AC4 identical-mock run.",
        "findings": [],
        "recommendations": [],
    });
    // queue_full_pipeline enqueues the same canned response 6x per stage —
    // ensures both Run A and Run B see identical LLM output every round.
    queue_full_pipeline(&mock, recon, hunt, validate, dedupe, trace, report).await;
    mock
}

#[tokio::test(flavor = "multi_thread")]
async fn per_task_override_extends_blacklist() {
    let real_path = "src/real.py";
    let custom_path = "custom_dir/vuln.py";

    // -------------------------------------------------------------------------
    // Run A: identical mock, NO override. "custom_dir" is NOT in the built-in
    // BLACKLIST_DIRS so the custom_dir finding survives all the way to the
    // final record.
    // -------------------------------------------------------------------------
    let mock_a = Arc::new(prepare_mock_with_blacklisted_finding(real_path, custom_path).await);
    let state_a = build_state("ac4-default", mock_a.clone()).await;
    seed_llm_config(&state_a).await;
    let project_a = seed_project_with_files(&state_a, &[real_path, custom_path]).await;

    let manager_a = Arc::clone(&state_a.intelligent_task_manager);
    let submitted_a = manager_a
        .submit(state_a.clone(), project_a, None)
        .await
        .expect("submit a");
    let record_a = wait_until_terminal(&state_a, &submitted_a.task_id, 600).await;

    eprintln!(
        "[ac4-default] status={:?} findings={} failure={:?}/{:?}",
        record_a.status,
        record_a.findings.len(),
        record_a.failure_stage,
        record_a.failure_reason,
    );

    let custom_count_a = record_a
        .findings
        .iter()
        .filter(|f| {
            f.file
                .as_deref()
                .map(|p| p.starts_with("custom_dir/"))
                .unwrap_or(false)
        })
        .count();
    assert!(
        custom_count_a > 0,
        "AC4 baseline: custom_dir finding must survive without override. record_a.findings={:?}",
        record_a
            .findings
            .iter()
            .map(|f| f.file.clone())
            .collect::<Vec<_>>()
    );

    // -------------------------------------------------------------------------
    // Run B: IDENTICAL mock queue, WITH override.
    // The LLM still emits the custom_dir finding every round; the only
    // difference vs Run A is the per-task `path_blacklist_extra` override.
    // -------------------------------------------------------------------------
    let mock_b = Arc::new(prepare_mock_with_blacklisted_finding(real_path, custom_path).await);
    let state_b = build_state("ac4-override", mock_b.clone()).await;
    seed_llm_config(&state_b).await;
    let project_b = seed_project_with_files(&state_b, &[real_path, custom_path]).await;

    let override_cfg = AuditConfigOverride {
        path_blacklist_extra: Some(vec!["custom_dir".to_string()]),
        reflection_iterations: Some(3),
    };

    let manager_b = Arc::clone(&state_b.intelligent_task_manager);
    let submitted_b = manager_b
        .submit(state_b.clone(), project_b, Some(override_cfg))
        .await
        .expect("submit b");
    let record_b = wait_until_terminal(&state_b, &submitted_b.task_id, 600).await;

    eprintln!(
        "[ac4-override] status={:?} findings={} failure={:?}/{:?}",
        record_b.status,
        record_b.findings.len(),
        record_b.failure_stage,
        record_b.failure_reason,
    );

    // Override must exclude every custom_dir/* finding.
    for f in &record_b.findings {
        if let Some(file) = &f.file {
            assert!(
                !file.starts_with("custom_dir/"),
                "AC4: override must exclude custom_dir/* but found: {file}"
            );
        }
    }

    let custom_count_b = record_b
        .findings
        .iter()
        .filter(|f| {
            f.file
                .as_deref()
                .map(|p| p.starts_with("custom_dir/"))
                .unwrap_or(false)
        })
        .count();
    assert_eq!(
        custom_count_b, 0,
        "AC4: per-task override must drop all custom_dir findings"
    );

    // H1 — attribution assertion: with identical mock queues, the ONLY
    // difference between Run A and Run B is the override. The custom_dir
    // finding count therefore went from > 0 in A to 0 in B *because of* the
    // override.
    assert!(
        custom_count_a > custom_count_b,
        "AC4: override is the sole independent variable across runs A and B \
         (identical MockInvoker), so custom_count must strictly decrease: \
         A={custom_count_a} B={custom_count_b}"
    );

    // Smoke: both runs reached terminal state.
    assert!(
        matches!(
            record_a.status,
            IntelligentTaskStatus::Completed | IntelligentTaskStatus::Failed
        ),
        "record_a must be terminal: {:?}",
        record_a.status
    );
    assert!(
        matches!(
            record_b.status,
            IntelligentTaskStatus::Completed | IntelligentTaskStatus::Failed
        ),
        "record_b must be terminal: {:?}",
        record_b.status
    );
}
