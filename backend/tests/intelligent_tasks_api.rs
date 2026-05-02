use std::sync::Arc;

use axum::{
    body::{to_bytes, Body},
    http::{Method, Request, StatusCode},
};
use backend_rust::{
    app::build_router,
    config::AppConfig,
    db::intelligent_task_state,
    runtime::intelligent::{
        config::IntelligentLlmConfig,
        llm::{IntelligentLlmInvocation, IntelligentLlmInvocationError, IntelligentLlmInvoker},
        task::IntelligentTaskManager,
        types::{IntelligentTaskEvent, IntelligentTaskRecord, IntelligentTaskStatus},
    },
    state::{AppState, StoredProject, StoredProjectArchive},
};
use serde_json::{json, Value};
use tokio::sync::Mutex;
use tower::util::ServiceExt;
use uuid::Uuid;

fn isolated_test_config(scope: &str) -> AppConfig {
    let mut config = AppConfig::for_tests();
    config.zip_storage_path =
        std::env::temp_dir().join(format!("argus-intelligent-api-{scope}-{}", Uuid::new_v4()));
    config
}

#[derive(Clone)]
struct ScriptedInvoker {
    state: Arc<Mutex<ScriptedState>>,
}

struct ScriptedState {
    /// Number of times invoke() has been called.
    pub attempts: usize,
    /// Optional pre-invocation delay in milliseconds.
    pub delay_ms: u64,
    /// Behavior: Ok(content) or Err(redacted_message).
    pub result: Result<String, String>,
}

impl ScriptedInvoker {
    fn ok(content: &str, delay_ms: u64) -> Self {
        Self {
            state: Arc::new(Mutex::new(ScriptedState {
                attempts: 0,
                delay_ms,
                result: Ok(content.to_string()),
            })),
        }
    }

    fn fail(redacted: &str) -> Self {
        Self {
            state: Arc::new(Mutex::new(ScriptedState {
                attempts: 0,
                delay_ms: 0,
                result: Err(redacted.to_string()),
            })),
        }
    }

    async fn attempts(&self) -> usize {
        self.state.lock().await.attempts
    }
}

#[async_trait::async_trait]
impl IntelligentLlmInvoker for ScriptedInvoker {
    async fn invoke(
        &self,
        _prompt: &str,
        _config: &IntelligentLlmConfig,
    ) -> Result<IntelligentLlmInvocation, IntelligentLlmInvocationError> {
        let (delay, result) = {
            let mut guard = self.state.lock().await;
            guard.attempts += 1;
            (guard.delay_ms, guard.result.clone())
        };
        if delay > 0 {
            tokio::time::sleep(std::time::Duration::from_millis(delay)).await;
        }
        match result {
            Ok(content) => Ok(IntelligentLlmInvocation {
                content,
                finished_at: "2026-05-02T00:00:00Z".to_string(),
                attempt_event: IntelligentTaskEvent::new("llm_attempt"),
            }),
            Err(redacted) => Err(IntelligentLlmInvocationError {
                stage: "llm_request",
                redacted_message: redacted,
            }),
        }
    }
}

async fn build_state_with_invoker(
    scope: &str,
    invoker: Arc<dyn IntelligentLlmInvoker + Send + Sync>,
) -> AppState {
    let mut state = AppState::from_config(isolated_test_config(scope))
        .await
        .expect("state should build");
    state.intelligent_task_manager = Arc::new(IntelligentTaskManager::with_invoker(invoker));
    state
}

async fn build_state_default(scope: &str) -> AppState {
    AppState::from_config(isolated_test_config(scope))
        .await
        .expect("state should build")
}

/// Create a fixture project (file-store mode) with an archive that lists at least one file.
async fn seed_project_with_archive(state: &AppState, project_id: &str) {
    use std::io::Write;

    // Create a tiny zip archive on disk so list_archive_files_from_path can iterate it.
    let storage_dir = state.config.zip_storage_path.clone();
    tokio::fs::create_dir_all(&storage_dir)
        .await
        .expect("create storage dir");
    let archive_path = storage_dir.join(format!("{project_id}.zip"));
    let file = std::fs::File::create(&archive_path).expect("create zip");
    let mut zw = zip::ZipWriter::new(file);
    let opts: zip::write::SimpleFileOptions = zip::write::SimpleFileOptions::default();
    zw.start_file("README.md", opts).expect("start file");
    zw.write_all(b"hello world").expect("write file");
    zw.finish().expect("finish zip");

    let archive = StoredProjectArchive {
        original_filename: format!("{project_id}.zip"),
        storage_path: archive_path.to_string_lossy().to_string(),
        sha256: "deadbeef".to_string(),
        file_size: 100,
        uploaded_at: "2026-05-02T00:00:00Z".to_string(),
    };
    let project = StoredProject {
        id: project_id.to_string(),
        name: format!("test-{project_id}"),
        description: String::new(),
        source_type: "upload".to_string(),
        repository_type: "zip".to_string(),
        default_branch: "main".to_string(),
        programming_languages_json: "[]".to_string(),
        is_active: true,
        created_at: "2026-05-02T00:00:00Z".to_string(),
        updated_at: "2026-05-02T00:00:00Z".to_string(),
        language_info: String::new(),
        info_status: "ok".to_string(),
        archive: Some(archive),
    };
    backend_rust::db::projects::create_project(state, project)
        .await
        .expect("create project should succeed");
}

/// Save an enabled OpenAI-compatible LLM row into system_config so resolve_intelligent_llm_config succeeds.
async fn seed_enabled_llm_config(state: &AppState) {
    let llm_config = json!({
        "schemaVersion": 2,
        "rows": [{
            "id": "row-test",
            "priority": 1,
            "enabled": true,
            "provider": "openai_compatible",
            "baseUrl": "https://api.openai.test/v1",
            "model": "gpt-test",
            "apiKey": "sk-test",
            "advanced": {}
        }]
    });
    backend_rust::db::system_config::save_current(state, llm_config, json!({}), json!({}))
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
        tokio::time::sleep(std::time::Duration::from_millis(50)).await;
    }
    read_record(state, task_id)
        .await
        .expect("record should still exist")
}

#[tokio::test]
async fn create_returns_pending_or_running_then_completes_zero_findings() {
    // Use a small delay so the first list/get observation can see pending/running.
    let invoker = Arc::new(ScriptedInvoker::ok(
        "no security concerns detected; project file inventory looks routine.",
        80,
    ));
    let state = build_state_with_invoker("create-success", invoker.clone()).await;
    seed_enabled_llm_config(&state).await;
    let project_id = Uuid::new_v4().to_string();
    seed_project_with_archive(&state, &project_id).await;

    let app = build_router(state.clone());
    let response = app
        .oneshot(
            Request::builder()
                .method(Method::POST)
                .uri("/api/v1/intelligent-tasks")
                .header("content-type", "application/json")
                .body(Body::from(json!({"projectId": project_id}).to_string()))
                .unwrap(),
        )
        .await
        .expect("create should respond");
    assert_eq!(response.status(), StatusCode::OK);
    let payload: Value =
        serde_json::from_slice(&to_bytes(response.into_body(), usize::MAX).await.unwrap()).unwrap();
    assert!(payload["taskId"].is_string());
    assert_eq!(payload["projectId"].as_str().unwrap(), project_id);

    // Returns pending immediately
    let initial_status = payload["status"].as_str().unwrap();
    assert!(
        matches!(initial_status, "pending" | "running" | "completed"),
        "unexpected initial status: {initial_status}"
    );

    let task_id = payload["taskId"].as_str().unwrap().to_string();
    let final_record = wait_until_terminal(&state, &task_id, 200).await;
    assert_eq!(final_record.status, IntelligentTaskStatus::Completed);
    assert!(final_record.duration_ms.is_some());
    assert!(!final_record.input_summary.is_empty());
    assert!(!final_record.report_summary.is_empty());
    assert!(final_record.findings.is_empty());
    assert!(final_record
        .event_log
        .iter()
        .any(|event| event.kind == "run_started"));
    assert!(final_record
        .event_log
        .iter()
        .any(|event| event.kind == "llm_attempt"));
    assert_eq!(invoker.attempts().await, 1, "no retry expected");
}

#[tokio::test]
async fn create_with_no_llm_config_records_failed_llm_config_stage() {
    let invoker = Arc::new(ScriptedInvoker::ok("unused", 0));
    let state = build_state_with_invoker("no-llm-config", invoker).await;
    let project_id = Uuid::new_v4().to_string();
    seed_project_with_archive(&state, &project_id).await;

    let app = build_router(state.clone());
    let response = app
        .oneshot(
            Request::builder()
                .method(Method::POST)
                .uri("/api/v1/intelligent-tasks")
                .header("content-type", "application/json")
                .body(Body::from(json!({"projectId": project_id}).to_string()))
                .unwrap(),
        )
        .await
        .expect("create should respond");
    assert_eq!(response.status(), StatusCode::OK);
    let payload: Value =
        serde_json::from_slice(&to_bytes(response.into_body(), usize::MAX).await.unwrap()).unwrap();
    let task_id = payload["taskId"].as_str().unwrap().to_string();

    let final_record = wait_until_terminal(&state, &task_id, 100).await;
    assert_eq!(final_record.status, IntelligentTaskStatus::Failed);
    assert_eq!(
        final_record.failure_stage.as_deref(),
        Some("llm_config"),
        "expected llm_config stage, got: {:?}",
        final_record.failure_stage
    );
}

#[tokio::test]
async fn create_with_llm_request_failure_records_failed_llm_request_stage_no_retry() {
    let invoker = Arc::new(ScriptedInvoker::fail("network error masked"));
    let state = build_state_with_invoker("llm-request-fail", invoker.clone()).await;
    seed_enabled_llm_config(&state).await;
    let project_id = Uuid::new_v4().to_string();
    seed_project_with_archive(&state, &project_id).await;

    let app = build_router(state.clone());
    let response = app
        .oneshot(
            Request::builder()
                .method(Method::POST)
                .uri("/api/v1/intelligent-tasks")
                .header("content-type", "application/json")
                .body(Body::from(json!({"projectId": project_id}).to_string()))
                .unwrap(),
        )
        .await
        .expect("create should respond");
    assert_eq!(response.status(), StatusCode::OK);
    let payload: Value =
        serde_json::from_slice(&to_bytes(response.into_body(), usize::MAX).await.unwrap()).unwrap();
    let task_id = payload["taskId"].as_str().unwrap().to_string();

    let final_record = wait_until_terminal(&state, &task_id, 100).await;
    assert_eq!(final_record.status, IntelligentTaskStatus::Failed);
    assert_eq!(final_record.failure_stage.as_deref(), Some("llm_request"));
    assert_eq!(invoker.attempts().await, 1, "no retry on llm_request fail");
}

#[tokio::test]
async fn create_with_missing_archive_records_failed_input_read_stage() {
    let invoker = Arc::new(ScriptedInvoker::ok("unused", 0));
    let state = build_state_with_invoker("input-read-fail", invoker).await;
    seed_enabled_llm_config(&state).await;
    // Seed a project WITHOUT an archive
    let project_id = Uuid::new_v4().to_string();
    let project = StoredProject {
        id: project_id.clone(),
        name: "no-archive".to_string(),
        description: String::new(),
        source_type: "upload".to_string(),
        repository_type: "zip".to_string(),
        default_branch: "main".to_string(),
        programming_languages_json: "[]".to_string(),
        is_active: true,
        created_at: "2026-05-02T00:00:00Z".to_string(),
        updated_at: "2026-05-02T00:00:00Z".to_string(),
        language_info: String::new(),
        info_status: "ok".to_string(),
        archive: None,
    };
    backend_rust::db::projects::create_project(&state, project)
        .await
        .expect("create project");

    let app = build_router(state.clone());
    let response = app
        .oneshot(
            Request::builder()
                .method(Method::POST)
                .uri("/api/v1/intelligent-tasks")
                .header("content-type", "application/json")
                .body(Body::from(json!({"projectId": project_id}).to_string()))
                .unwrap(),
        )
        .await
        .expect("create should respond");
    assert_eq!(response.status(), StatusCode::OK);
    let payload: Value =
        serde_json::from_slice(&to_bytes(response.into_body(), usize::MAX).await.unwrap()).unwrap();
    let task_id = payload["taskId"].as_str().unwrap().to_string();

    let final_record = wait_until_terminal(&state, &task_id, 100).await;
    assert_eq!(final_record.status, IntelligentTaskStatus::Failed);
    assert_eq!(final_record.failure_stage.as_deref(), Some("input_read"));
}

#[tokio::test]
async fn list_returns_records_sorted_with_limit() {
    let invoker = Arc::new(ScriptedInvoker::ok("ok", 0));
    let state = build_state_with_invoker("list-limit", invoker).await;
    seed_enabled_llm_config(&state).await;
    let project_id = Uuid::new_v4().to_string();
    seed_project_with_archive(&state, &project_id).await;

    let app = build_router(state.clone());
    for _ in 0..3 {
        let _ = app
            .clone()
            .oneshot(
                Request::builder()
                    .method(Method::POST)
                    .uri("/api/v1/intelligent-tasks")
                    .header("content-type", "application/json")
                    .body(Body::from(json!({"projectId": project_id}).to_string()))
                    .unwrap(),
            )
            .await;
    }

    let response = app
        .oneshot(
            Request::get("/api/v1/intelligent-tasks?limit=10")
                .body(Body::empty())
                .unwrap(),
        )
        .await
        .expect("list should respond");
    assert_eq!(response.status(), StatusCode::OK);
    let payload: Value =
        serde_json::from_slice(&to_bytes(response.into_body(), usize::MAX).await.unwrap()).unwrap();
    assert!(payload.is_array(), "list should be an array");
    let items = payload.as_array().unwrap();
    assert!(!items.is_empty());
    assert!(items.len() <= 10);
}

#[tokio::test]
async fn get_unknown_task_returns_not_found() {
    let state = build_state_default("get-unknown").await;
    let app = build_router(state);
    let response = app
        .oneshot(
            Request::get("/api/v1/intelligent-tasks/missing-task-id")
                .body(Body::empty())
                .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(response.status(), StatusCode::NOT_FOUND);
}

#[tokio::test]
async fn cancel_pending_task_persists_cancelled_status() {
    // Long delay so the task remains running while we cancel.
    let invoker = Arc::new(ScriptedInvoker::ok("late content", 5_000));
    let state = build_state_with_invoker("cancel-pending", invoker).await;
    seed_enabled_llm_config(&state).await;
    let project_id = Uuid::new_v4().to_string();
    seed_project_with_archive(&state, &project_id).await;

    let app = build_router(state.clone());
    let create_response = app
        .clone()
        .oneshot(
            Request::builder()
                .method(Method::POST)
                .uri("/api/v1/intelligent-tasks")
                .header("content-type", "application/json")
                .body(Body::from(json!({"projectId": project_id}).to_string()))
                .unwrap(),
        )
        .await
        .unwrap();
    let payload: Value = serde_json::from_slice(
        &to_bytes(create_response.into_body(), usize::MAX)
            .await
            .unwrap(),
    )
    .unwrap();
    let task_id = payload["taskId"].as_str().unwrap().to_string();

    let cancel_response = app
        .oneshot(
            Request::builder()
                .method(Method::POST)
                .uri(format!("/api/v1/intelligent-tasks/{task_id}/cancel"))
                .body(Body::empty())
                .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(cancel_response.status(), StatusCode::OK);
    let cancelled: Value = serde_json::from_slice(
        &to_bytes(cancel_response.into_body(), usize::MAX)
            .await
            .unwrap(),
    )
    .unwrap();
    assert_eq!(cancelled["status"].as_str().unwrap(), "cancelled");
    assert!(cancelled["eventLog"]
        .as_array()
        .unwrap()
        .iter()
        .any(|event| event["kind"].as_str() == Some("cancelled")));
}

#[tokio::test]
async fn delete_completed_task_removes_record() {
    let state = build_state_default("delete-completed").await;
    let mut record = IntelligentTaskRecord::new_pending(
        "task-delete".to_string(),
        "proj-delete".to_string(),
        "model".to_string(),
        "fp".to_string(),
    );
    record.status = IntelligentTaskStatus::Completed;
    intelligent_task_state::save_record(&state, record)
        .await
        .expect("save completed task");

    let app = build_router(state.clone());
    let response = app
        .oneshot(
            Request::builder()
                .method(Method::DELETE)
                .uri("/api/v1/intelligent-tasks/task-delete")
                .body(Body::empty())
                .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(response.status(), StatusCode::OK);
    let payload: Value =
        serde_json::from_slice(&to_bytes(response.into_body(), usize::MAX).await.unwrap()).unwrap();
    assert_eq!(payload["deleted"].as_bool(), Some(true));
    assert_eq!(payload["taskId"].as_str(), Some("task-delete"));
    assert!(read_record(&state, "task-delete").await.is_none());
}

#[tokio::test]
async fn delete_running_task_returns_conflict() {
    let state = build_state_default("delete-running").await;
    let mut record = IntelligentTaskRecord::new_pending(
        "task-running".to_string(),
        "proj-running".to_string(),
        "model".to_string(),
        "fp".to_string(),
    );
    record.status = IntelligentTaskStatus::Running;
    intelligent_task_state::save_record(&state, record)
        .await
        .expect("save running task");

    let app = build_router(state.clone());
    let response = app
        .oneshot(
            Request::builder()
                .method(Method::DELETE)
                .uri("/api/v1/intelligent-tasks/task-running")
                .body(Body::empty())
                .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(response.status(), StatusCode::CONFLICT);
    assert!(read_record(&state, "task-running").await.is_some());
}

#[tokio::test]
async fn missing_project_id_field_returns_bad_request() {
    let state = build_state_default("missing-project-id").await;
    let app = build_router(state);
    let response = app
        .oneshot(
            Request::builder()
                .method(Method::POST)
                .uri("/api/v1/intelligent-tasks")
                .header("content-type", "application/json")
                .body(Body::from(json!({"projectId": ""}).to_string()))
                .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(response.status(), StatusCode::BAD_REQUEST);
}

#[tokio::test]
async fn legacy_agent_tasks_route_is_absent() {
    let state = build_state_default("legacy-absent").await;
    let app = build_router(state);
    for path in [
        "/api/v1/agent-tasks",
        "/api/v1/agent-tasks/",
        "/api/v1/agent-tasks/some-id",
    ] {
        let response = app
            .clone()
            .oneshot(Request::get(path).body(Body::empty()).unwrap())
            .await
            .unwrap();
        assert_eq!(
            response.status(),
            StatusCode::NOT_FOUND,
            "{path} must return 404"
        );
    }
}

#[tokio::test]
async fn project_deletion_removes_related_intelligent_tasks() {
    let invoker = Arc::new(ScriptedInvoker::ok("ok", 0));
    let state = build_state_with_invoker("project-delete", invoker).await;
    seed_enabled_llm_config(&state).await;
    let project_id = Uuid::new_v4().to_string();
    seed_project_with_archive(&state, &project_id).await;

    let app = build_router(state.clone());
    let create_response = app
        .clone()
        .oneshot(
            Request::builder()
                .method(Method::POST)
                .uri("/api/v1/intelligent-tasks")
                .header("content-type", "application/json")
                .body(Body::from(json!({"projectId": project_id}).to_string()))
                .unwrap(),
        )
        .await
        .unwrap();
    let payload: Value = serde_json::from_slice(
        &to_bytes(create_response.into_body(), usize::MAX)
            .await
            .unwrap(),
    )
    .unwrap();
    let task_id = payload["taskId"].as_str().unwrap().to_string();

    let _ = wait_until_terminal(&state, &task_id, 100).await;
    assert!(read_record(&state, &task_id).await.is_some());

    backend_rust::db::projects::delete_project_with_related_tasks(&state, &project_id)
        .await
        .expect("project deletion should succeed");

    assert!(
        read_record(&state, &task_id).await.is_none(),
        "intelligent task record should be removed after project deletion"
    );
}
