use axum::{
    body::{to_bytes, Body},
    http::{Method, Request, Response, StatusCode},
};
use backend_rust::{
    app::build_router,
    bootstrap,
    config::AppConfig,
    db::{cubesandbox_task_state, system_config},
    runtime::cubesandbox::{
        client::{CubeSandboxClient, CubeSandboxClientConfig},
        config::CubeSandboxConfig,
        helper::{build_helper_invocation, CubeSandboxHelperCommand},
        types::CubeSandboxTaskStatus,
    },
    state::AppState,
};
use serde_json::{json, Value};
use std::{
    fs,
    io::{Read, Write},
    net::{SocketAddr, TcpListener},
    sync::{Arc, Mutex},
    thread,
};
use tower::util::ServiceExt;
use uuid::Uuid;

fn isolated_test_config(scope: &str) -> AppConfig {
    let mut config = AppConfig::for_tests();
    config.zip_storage_path =
        std::env::temp_dir().join(format!("argus-rust-{scope}-{}", Uuid::new_v4()));
    config
}

#[tokio::test]
async fn cubesandbox_defaults_are_exposed_in_system_config() {
    let state = AppState::from_config(isolated_test_config("cubesandbox-defaults"))
        .await
        .expect("state should build");
    let app = build_router(state);

    let response = app
        .oneshot(
            Request::get("/api/v1/system-config/defaults")
                .body(Body::empty())
                .unwrap(),
        )
        .await
        .expect("defaults request should succeed");

    assert_eq!(response.status(), StatusCode::OK);
    let payload: Value =
        serde_json::from_slice(&to_bytes(response.into_body(), usize::MAX).await.unwrap()).unwrap();
    assert_eq!(payload["otherConfig"]["cubeSandbox"]["enabled"], false);
    assert_eq!(
        payload["otherConfig"]["cubeSandbox"]["apiBaseUrl"],
        "http://127.0.0.1:23000"
    );
    assert_eq!(
        payload["otherConfig"]["cubeSandbox"]["dataPlaneBaseUrl"],
        "https://127.0.0.1:21443"
    );
    assert_eq!(
        payload["otherConfig"]["cubeSandbox"]["helperPath"],
        "scripts/cubesandbox-quickstart.sh"
    );
}

#[tokio::test]
async fn cubesandbox_config_preserves_unknown_other_config_keys() {
    let state = AppState::from_config(isolated_test_config("cubesandbox-other-config"))
        .await
        .expect("state should build");
    let app = build_router(state);
    let save_payload = json!({
        "llmConfig": {
            "llmProvider": "openai_compatible",
            "llmApiKey": "sk-test",
            "llmModel": "gpt-5",
            "llmBaseUrl": "https://api.openai.com/v1"
        },
        "otherConfig": {
            "someFutureKey": {"kept": true},
            "cubeSandbox": {
                "enabled": true,
                "apiBaseUrl": "http://127.0.0.1:23000",
                "dataPlaneBaseUrl": "https://127.0.0.1:21443",
                "templateId": "tpl-test"
            }
        }
    });

    let response = app
        .oneshot(
            Request::builder()
                .method(Method::PUT)
                .uri("/api/v1/system-config")
                .header("content-type", "application/json")
                .body(Body::from(save_payload.to_string()))
                .unwrap(),
        )
        .await
        .expect("save should complete");
    assert_eq!(response.status(), StatusCode::OK);
    let payload: Value =
        serde_json::from_slice(&to_bytes(response.into_body(), usize::MAX).await.unwrap()).unwrap();
    assert_eq!(payload["otherConfig"]["someFutureKey"]["kept"], true);
    assert_eq!(
        payload["otherConfig"]["cubeSandbox"]["templateId"],
        "tpl-test"
    );
}

#[test]
fn cubesandbox_helper_allowlist_and_env_mapping_are_bounded() {
    let config = CubeSandboxConfig {
        enabled: true,
        api_base_url: "http://127.0.0.1:23000".to_string(),
        data_plane_base_url: "https://127.0.0.1:21443".to_string(),
        template_id: "tpl-test".to_string(),
        helper_path: "scripts/cubesandbox-quickstart.sh".to_string(),
        work_dir: ".cubesandbox-test".to_string(),
        auto_start: true,
        auto_install: false,
        helper_timeout_seconds: 600,
        execution_timeout_seconds: 120,
        sandbox_cleanup_timeout_seconds: 30,
        stdout_limit_bytes: 65_536,
        stderr_limit_bytes: 65_536,
    };

    let invocation =
        build_helper_invocation(&config, CubeSandboxHelperCommand::Status).expect("valid helper");
    assert_eq!(invocation.command, "scripts/cubesandbox-quickstart.sh");
    assert_eq!(invocation.args, vec!["status"]);
    assert_eq!(
        invocation.env.get("CUBE_WORK_DIR").map(String::as_str),
        Some(".cubesandbox-test")
    );
    assert_eq!(
        invocation.env.get("CUBE_TEMPLATE_ID").map(String::as_str),
        Some("tpl-test")
    );
    assert_eq!(
        invocation.env.get("CUBE_API_PORT").map(String::as_str),
        Some("23000")
    );
    assert_eq!(
        invocation
            .env
            .get("CUBE_PROXY_HTTPS_PORT")
            .map(String::as_str),
        Some("21443")
    );

    assert!(CubeSandboxHelperCommand::try_from("python-smoke").is_err());
    let remote_config = CubeSandboxConfig {
        api_base_url: "http://example.com:23000".to_string(),
        ..config
    };
    let error = build_helper_invocation(&remote_config, CubeSandboxHelperCommand::Status)
        .expect_err("remote lifecycle must be rejected");
    assert!(error.to_string().contains("remote_lifecycle_not_supported"));
}

#[tokio::test]
async fn cubesandbox_runtime_config_rejects_disabled_missing_template_and_invalid_urls() {
    let state = AppState::from_config(isolated_test_config("cubesandbox-config-failures"))
        .await
        .expect("state should build");
    let app = build_router(state);

    let disabled = submit_cubesandbox_task(
        &app,
        json!({
            "enabled": false,
            "apiBaseUrl": "http://127.0.0.1:23000",
            "dataPlaneBaseUrl": "https://127.0.0.1:21443",
            "templateId": "tpl-test"
        }),
    )
    .await;
    assert_eq!(disabled["status"], "failed");
    assert_eq!(disabled["errorCategory"], "internal");
    assert!(disabled["errorMessage"]
        .as_str()
        .unwrap_or_default()
        .contains("disabled"));

    let missing_template = submit_cubesandbox_task(
        &app,
        json!({
            "enabled": true,
            "apiBaseUrl": "http://127.0.0.1:23000",
            "dataPlaneBaseUrl": "https://127.0.0.1:21443",
            "templateId": ""
        }),
    )
    .await;
    assert_eq!(missing_template["status"], "failed");
    assert!(missing_template["errorMessage"]
        .as_str()
        .unwrap_or_default()
        .contains("templateId"));

    let invalid_url = submit_cubesandbox_task(
        &app,
        json!({
            "enabled": true,
            "apiBaseUrl": "not-a-url",
            "dataPlaneBaseUrl": "https://127.0.0.1:21443",
            "templateId": "tpl-test"
        }),
    )
    .await;
    assert_eq!(invalid_url["status"], "failed");
    assert!(invalid_url["errorMessage"]
        .as_str()
        .unwrap_or_default()
        .contains("apiBaseUrl"));
}

#[tokio::test]
async fn cubesandbox_client_separates_control_plane_from_data_plane() {
    let control_seen = RecordedRequests::default();
    let data_seen = RecordedRequests::default();
    let control_addr = spawn_json_server(
        control_seen.clone(),
        vec![
            (StatusCode::OK, r#"{"status":"ok"}"#.to_string()),
            (
                StatusCode::CREATED,
                r#"{"sandboxID":"sbx-1","templateID":"tpl-test","clientID":"client-1","envdVersion":"0.1","domain":"cube.app"}"#.to_string(),
            ),
            (StatusCode::OK, r#"{"connected":true}"#.to_string()),
            (
                StatusCode::OK,
                r#"{"sandboxID":"sbx-1","templateID":"tpl-test","clientID":"client-1","envdVersion":"0.1","domain":"cube.app"}"#.to_string(),
            ),
            (StatusCode::NO_CONTENT, String::new()),
        ],
    );
    let data_addr = spawn_json_server(
        data_seen.clone(),
        vec![(
            StatusCode::OK,
            r#"{"stdout":"45\n","stderr":"","exitCode":0}"#.to_string(),
        )],
    );
    let client = CubeSandboxClient::new(CubeSandboxClientConfig {
        api_base_url: format!("http://{control_addr}"),
        data_plane_base_url: format!("http://{data_addr}"),
        template_id: "tpl-test".to_string(),
        execution_timeout_seconds: 120,
        cleanup_timeout_seconds: 30,
        stdout_limit_bytes: 65_536,
        stderr_limit_bytes: 65_536,
    })
    .expect("client config should parse");

    client.health().await.expect("health should pass");
    let sandbox = client
        .create_sandbox()
        .await
        .expect("sandbox should create");
    let output = client
        .run_python(&sandbox, "print(sum(range(10)))")
        .await
        .expect("python should run");
    client
        .connect_sandbox(&sandbox.sandbox_id)
        .await
        .expect("connect should pass");
    let diagnostics = client
        .get_sandbox(&sandbox.sandbox_id)
        .await
        .expect("diagnostics should load");
    client
        .delete_sandbox(&sandbox.sandbox_id)
        .await
        .expect("cleanup should pass");

    assert_eq!(output.stdout, "45\n");
    assert_eq!(output.exit_code, Some(0));
    assert_eq!(diagnostics.sandbox_id, "sbx-1");
    assert!(control_seen.paths().iter().any(|path| path == "/sandboxes"));
    assert!(control_seen
        .paths()
        .iter()
        .any(|path| path == "/sandboxes/sbx-1"));
    assert_eq!(data_seen.paths(), vec!["/process"]);
    assert_eq!(
        data_seen.host_headers(),
        vec![format!("49983-sbx-1.cube.app")]
    );
}

#[tokio::test]
async fn cubesandbox_client_truncates_output_and_exposes_non_zero_exit() {
    let data_seen = RecordedRequests::default();
    let data_addr = spawn_json_server(
        data_seen,
        vec![(
            StatusCode::OK,
            r#"{"stdout":"abcdef","stderr":"uvwxyz","exitCode":2}"#.to_string(),
        )],
    );
    let client = CubeSandboxClient::new(CubeSandboxClientConfig {
        api_base_url: "http://127.0.0.1:1".to_string(),
        data_plane_base_url: format!("http://{data_addr}"),
        template_id: "tpl-test".to_string(),
        execution_timeout_seconds: 120,
        cleanup_timeout_seconds: 30,
        stdout_limit_bytes: 3,
        stderr_limit_bytes: 4,
    })
    .expect("client config should parse");
    let output = client
        .run_python(
            &backend_rust::runtime::cubesandbox::client::CubeSandboxSandbox {
                sandbox_id: "sbx-truncate".to_string(),
                template_id: "tpl-test".to_string(),
                client_id: "client-1".to_string(),
                envd_version: "0.1".to_string(),
                domain: Some("cube.app".to_string()),
            },
            "print('x')",
        )
        .await
        .expect("envd output should normalize");

    assert_eq!(output.stdout, "abc");
    assert_eq!(output.stderr, "uvwx");
    assert!(output.stdout_truncated);
    assert!(output.stderr_truncated);
    assert_eq!(output.exit_code, Some(2));
}

#[tokio::test]
async fn cubesandbox_task_route_smoke_returns_45() {
    let mut config = isolated_test_config("cubesandbox-route-smoke");
    let helper_dir = tempfile::tempdir().expect("helper tempdir");
    let helper_path = helper_dir.path().join("cubesandbox-helper.sh");
    fs::write(&helper_path, "#!/bin/sh\nprintf 'status ok\\n'\nexit 0\n")
        .expect("helper script should write");
    let mut permissions = fs::metadata(&helper_path)
        .expect("helper metadata")
        .permissions();
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        permissions.set_mode(0o755);
        fs::set_permissions(&helper_path, permissions).expect("helper chmod");
    }
    let control_seen = RecordedRequests::default();
    let data_seen = RecordedRequests::default();
    let control_addr = spawn_json_server(
        control_seen.clone(),
        vec![
            (StatusCode::OK, r#"{"status":"ok"}"#.to_string()),
            (
                StatusCode::CREATED,
                r#"{"sandboxID":"sbx-task","templateID":"tpl-test","clientID":"client-1","envdVersion":"0.1","domain":"cube.app"}"#.to_string(),
            ),
            (StatusCode::OK, r#"{"connected":true}"#.to_string()),
            (StatusCode::NO_CONTENT, String::new()),
        ],
    );
    let data_addr = spawn_json_server(
        data_seen,
        vec![(
            StatusCode::OK,
            r#"{"stdout":"45\n","stderr":"","exitCode":0}"#.to_string(),
        )],
    );
    config.cubesandbox_api_base_url = format!("http://{control_addr}");
    config.cubesandbox_data_plane_base_url = format!("http://{data_addr}");
    config.cubesandbox_template_id = "tpl-test".to_string();
    config.cubesandbox_helper_path = helper_path.to_string_lossy().to_string();
    let state = AppState::from_config(config)
        .await
        .expect("state should build");
    system_config::save_current(
        &state,
        json!({}),
        json!({
            "cubeSandbox": {
                "enabled": true,
                "apiBaseUrl": format!("http://{control_addr}"),
                "dataPlaneBaseUrl": format!("http://{data_addr}"),
                "templateId": "tpl-test",
                "helperPath": helper_path.to_string_lossy(),
                "autoStart": false
            }
        }),
        json!({}),
    )
    .await
    .expect("config should save");
    let app = build_router(state.clone());

    let submit_response = app
        .clone()
        .oneshot(
            Request::builder()
                .method(Method::POST)
                .uri("/api/v1/cubesandbox-tasks")
                .header("content-type", "application/json")
                .body(Body::from(
                    json!({"code":"print(sum(range(10)))"}).to_string(),
                ))
                .unwrap(),
        )
        .await
        .expect("submit should complete");
    assert_eq!(submit_response.status(), StatusCode::OK);
    let submitted: Value = serde_json::from_slice(
        &to_bytes(submit_response.into_body(), usize::MAX)
            .await
            .unwrap(),
    )
    .unwrap();
    let task_id = submitted["taskId"].as_str().expect("task id");

    let mut record = None;
    let mut last_payload = None;
    for _ in 0..50 {
        let response = app
            .clone()
            .oneshot(
                Request::get(format!("/api/v1/cubesandbox-tasks/{task_id}"))
                    .body(Body::empty())
                    .unwrap(),
            )
            .await
            .expect("get should complete");
        assert_eq!(response.status(), StatusCode::OK);
        let payload: Value =
            serde_json::from_slice(&to_bytes(response.into_body(), usize::MAX).await.unwrap())
                .unwrap();
        if payload["status"] == "completed" {
            record = Some(payload);
            break;
        }
        last_payload = Some(payload);
        tokio::time::sleep(std::time::Duration::from_millis(20)).await;
    }

    let record = record.unwrap_or_else(|| panic!("task should complete, last={last_payload:?}"));
    assert_eq!(record["stdout"], "45\n");
    assert_eq!(record["stdoutTruncated"], false);
    assert_eq!(record["stderrTruncated"], false);
    assert_eq!(record["cleanupStatus"], "completed");
    assert_eq!(
        control_seen.paths().last().map(String::as_str),
        Some("/sandboxes/sbx-task")
    );
}

#[tokio::test]
async fn cubesandbox_delete_rejects_non_terminal_and_deletes_terminal() {
    let state = AppState::from_config(isolated_test_config("cubesandbox-delete"))
        .await
        .expect("state should build");
    let app = build_router(state.clone());
    let running_id = "task-running";
    let mut running = backend_rust::runtime::cubesandbox::types::CubeSandboxTaskRecord::new_queued(
        running_id.to_string(),
        "print(1)".to_string(),
        None,
        None,
    );
    running.status = CubeSandboxTaskStatus::Running;
    cubesandbox_task_state::save_record(&state, running)
        .await
        .expect("running record should save");
    let conflict = app
        .clone()
        .oneshot(
            Request::delete(format!("/api/v1/cubesandbox-tasks/{running_id}"))
                .body(Body::empty())
                .unwrap(),
        )
        .await
        .expect("delete should complete");
    assert_eq!(conflict.status(), StatusCode::CONFLICT);

    let completed_id = "task-completed";
    let mut completed =
        backend_rust::runtime::cubesandbox::types::CubeSandboxTaskRecord::new_queued(
            completed_id.to_string(),
            "print(1)".to_string(),
            None,
            None,
        );
    completed.mark_terminal(CubeSandboxTaskStatus::Completed);
    cubesandbox_task_state::save_record(&state, completed)
        .await
        .expect("completed record should save");
    let deleted = app
        .oneshot(
            Request::delete(format!("/api/v1/cubesandbox-tasks/{completed_id}"))
                .body(Body::empty())
                .unwrap(),
        )
        .await
        .expect("delete should complete");
    assert_eq!(deleted.status(), StatusCode::OK);
    assert!(cubesandbox_task_state::get_record(&state, completed_id)
        .await
        .expect("record lookup should complete")
        .is_none());
}

#[tokio::test]
async fn cubesandbox_orphan_reconciliation_marks_non_terminal_interrupted() {
    let state = AppState::from_config(isolated_test_config("cubesandbox-orphan"))
        .await
        .expect("state should build");
    let mut record = backend_rust::runtime::cubesandbox::types::CubeSandboxTaskRecord::new_queued(
        "task-orphan".to_string(),
        "print(1)".to_string(),
        None,
        None,
    );
    record.status = CubeSandboxTaskStatus::Running;
    cubesandbox_task_state::save_record(&state, record)
        .await
        .expect("record should save");

    let reloaded = AppState::from_config((*state.config).clone())
        .await
        .expect("reloaded state should build");
    bootstrap::run(&reloaded)
        .await
        .expect("bootstrap should reconcile orphans");

    let saved = cubesandbox_task_state::get_record(&reloaded, "task-orphan")
        .await
        .expect("record should load")
        .expect("record should exist");
    assert_eq!(saved.status, CubeSandboxTaskStatus::Interrupted);
    assert_eq!(saved.error_message.as_deref(), Some("backend_restarted"));
}

async fn submit_cubesandbox_task(app: &RouterForTest, cube_sandbox: Value) -> Value {
    let state = AppState::from_config(isolated_test_config("cubesandbox-submit-helper"))
        .await
        .expect("state should build");
    drop(state);
    let response = app
        .clone()
        .oneshot(
            Request::builder()
                .method(Method::PUT)
                .uri("/api/v1/system-config")
                .header("content-type", "application/json")
                .body(Body::from(
                    json!({
                        "llmConfig": {},
                        "otherConfig": { "cubeSandbox": cube_sandbox }
                    })
                    .to_string(),
                ))
                .unwrap(),
        )
        .await
        .expect("save config should complete");
    assert_eq!(response.status(), StatusCode::OK);

    let submit_response = app
        .clone()
        .oneshot(
            Request::builder()
                .method(Method::POST)
                .uri("/api/v1/cubesandbox-tasks")
                .header("content-type", "application/json")
                .body(Body::from(json!({"code":"print(1)"}).to_string()))
                .unwrap(),
        )
        .await
        .expect("submit should complete");
    assert_eq!(submit_response.status(), StatusCode::OK);
    let submitted = response_json(submit_response).await;
    let task_id = submitted["taskId"].as_str().expect("task id");
    poll_task(app, task_id).await
}

type RouterForTest = axum::Router;

async fn poll_task(app: &RouterForTest, task_id: &str) -> Value {
    let mut last_payload = None;
    for _ in 0..50 {
        let response = app
            .clone()
            .oneshot(
                Request::get(format!("/api/v1/cubesandbox-tasks/{task_id}"))
                    .body(Body::empty())
                    .unwrap(),
            )
            .await
            .expect("get task should complete");
        assert_eq!(response.status(), StatusCode::OK);
        let payload = response_json(response).await;
        if payload["status"].as_str().is_some_and(|status| {
            matches!(
                status,
                "completed" | "failed" | "interrupted" | "cleanup_failed"
            )
        }) {
            return payload;
        }
        last_payload = Some(payload);
        tokio::time::sleep(std::time::Duration::from_millis(20)).await;
    }
    panic!("task should reach terminal state, last={last_payload:?}");
}

async fn response_json(response: Response<Body>) -> Value {
    serde_json::from_slice(&to_bytes(response.into_body(), usize::MAX).await.unwrap()).unwrap()
}

#[derive(Clone, Default)]
struct RecordedRequests(Arc<Mutex<Vec<RecordedRequest>>>);

#[derive(Clone, Debug)]
struct RecordedRequest {
    path: String,
    host: Option<String>,
}

impl RecordedRequests {
    fn push(&self, request: RecordedRequest) {
        self.0.lock().unwrap().push(request);
    }

    fn paths(&self) -> Vec<String> {
        self.0
            .lock()
            .unwrap()
            .iter()
            .map(|request| request.path.clone())
            .collect()
    }

    fn host_headers(&self) -> Vec<String> {
        self.0
            .lock()
            .unwrap()
            .iter()
            .filter_map(|request| request.host.clone())
            .collect()
    }
}

fn spawn_json_server(seen: RecordedRequests, responses: Vec<(StatusCode, String)>) -> SocketAddr {
    let listener = TcpListener::bind("127.0.0.1:0").expect("bind test server");
    let address = listener.local_addr().expect("test server address");
    let responses = Arc::new(Mutex::new(responses.into_iter()));
    thread::spawn(move || {
        for stream in listener.incoming() {
            let Ok(mut stream) = stream else {
                break;
            };
            let mut buffer = [0_u8; 8192];
            let read = stream.read(&mut buffer).unwrap_or(0);
            let raw = String::from_utf8_lossy(&buffer[..read]);
            let first = raw.lines().next().unwrap_or_default();
            let path = first.split_whitespace().nth(1).unwrap_or("/").to_string();
            let host = raw.lines().find_map(|line| {
                line.strip_prefix("Host:")
                    .or_else(|| line.strip_prefix("host:"))
                    .map(|value| value.trim().to_string())
            });
            seen.push(RecordedRequest { path, host });
            let (status, body) = responses
                .lock()
                .unwrap()
                .next()
                .unwrap_or((StatusCode::OK, "{}".to_string()));
            let response = if status == StatusCode::NO_CONTENT {
                format!(
                    "HTTP/1.1 {} {}\r\ncontent-length: 0\r\nconnection: close\r\n\r\n",
                    status.as_u16(),
                    status.canonical_reason().unwrap_or("")
                )
            } else {
                format!(
                    "HTTP/1.1 {} {}\r\ncontent-type: application/json\r\ncontent-length: {}\r\nconnection: close\r\n\r\n{}",
                    status.as_u16(),
                    status.canonical_reason().unwrap_or(""),
                    body.len(),
                    body
                )
            };
            let _ = stream.write_all(response.as_bytes());
        }
    });
    address
}
