use axum::{
    body::{to_bytes, Body},
    http::{Method, Request, StatusCode},
};
use backend_rust::{
    app::build_router,
    bootstrap,
    config::AppConfig,
    db::{codeql_build_plans, task_state},
    state::AppState,
};
use base64::{engine::general_purpose::STANDARD, Engine as _};
use serde_json::{json, Value};
use std::{
    env, fs, io::Write, net::SocketAddr, os::unix::fs::PermissionsExt, path::PathBuf,
    sync::LazyLock,
};
use tokio::{
    io::{AsyncReadExt, AsyncWriteExt},
    net::TcpListener,
    sync::Mutex,
    time::{sleep, Duration},
};
use tower::util::ServiceExt;
use uuid::Uuid;

static ENV_LOCK: LazyLock<Mutex<()>> = LazyLock::new(|| Mutex::new(()));

fn isolated_test_config(scope: &str) -> AppConfig {
    let mut config = AppConfig::for_tests();
    config.zip_storage_path =
        std::env::temp_dir().join(format!("argus-rust-{scope}-{}", Uuid::new_v4()));
    config
}

async fn isolated_codeql_cubesandbox_test_config(
    scope: &str,
) -> (AppConfig, CubeSandboxTestHarness) {
    isolated_codeql_cubesandbox_test_config_with_make_failure(scope, false).await
}

async fn isolated_codeql_cubesandbox_test_config_with_make_failure(
    scope: &str,
    fail_make_exploration: bool,
) -> (AppConfig, CubeSandboxTestHarness) {
    let harness = CubeSandboxTestHarness::spawn(fail_make_exploration).await;
    let mut config = isolated_test_config(scope);
    config.cubesandbox_enabled = true;
    config.cubesandbox_template_id = "tpl-codeql-test".to_string();
    config.cubesandbox_api_base_url = harness.control_base_url.clone();
    config.cubesandbox_data_plane_base_url = harness.data_base_url.clone();
    config.cubesandbox_auto_start = false;
    config.cubesandbox_auto_install = false;
    config.cubesandbox_helper_path = harness.helper_path.to_string_lossy().to_string();
    config.cubesandbox_execution_timeout_seconds = 120;
    (config, harness)
}

fn optional_db_test_config(scope: &str) -> Option<AppConfig> {
    let database_url = std::env::var("RUST_DATABASE_URL")
        .or_else(|_| std::env::var("DATABASE_URL"))
        .ok()?;
    let mut config = isolated_test_config(scope);
    config.rust_database_url = Some(database_url);
    Some(config)
}

fn require_db_test_config(scope: &str) -> Option<AppConfig> {
    match optional_db_test_config(scope) {
        Some(config) => Some(config),
        None => {
            eprintln!(
                "skipping DB-backed CodeQL build-plan assertion without RUST_DATABASE_URL/DATABASE_URL"
            );
            None
        }
    }
}

async fn spawn_openai_mock_server() -> String {
    spawn_openai_mock_server_with_retry_feedback(false).await
}

async fn spawn_openai_mock_server_with_retry_feedback(
    retry_after_missing_compiler: bool,
) -> String {
    let listener = TcpListener::bind("127.0.0.1:0")
        .await
        .expect("bind mock llm server");
    let address = listener.local_addr().expect("mock llm address");
    tokio::spawn(async move {
        loop {
            let Ok((mut stream, _)) = listener.accept().await else {
                break;
            };
            tokio::spawn(async move {
                let mut buffer = [0_u8; 4096];
                let read_len = stream.read(&mut buffer).await.unwrap_or(0);
                let request = String::from_utf8_lossy(&buffer[..read_len]);
                let content = if request.contains("selecting a safe C/C++ build plan") {
                    if retry_after_missing_compiler && request.contains("missing compiler") {
                        r#"{"reasoning_summary":"Previous CubeSandbox output reported missing compiler; retry with the portable fallback command.","commands":["cc -c src/main.c"]}"#
                    } else if retry_after_missing_compiler {
                        r#"{"reasoning_summary":"First try make; if CubeSandbox reports a missing compiler the next round will adjust.","commands":["make -B -j2"]}"#
                    } else {
                        r#"{"reasoning_summary":"Makefile is present, so force a clean make build for CodeQL capture.","commands":["make -B -j2"]}"#
                    }
                } else {
                    "ok"
                };
                let body = json!({
                    "choices": [{
                        "message": {
                            "content": content
                        }
                    }]
                })
                .to_string();
                let response = format!(
                    "HTTP/1.1 200 OK\r\ncontent-type: application/json\r\ncontent-length: {}\r\nconnection: close\r\n\r\n{}",
                    body.len(),
                    body
                );
                let _ = stream.write_all(response.as_bytes()).await;
            });
        }
    });
    format!("http://{address}/v1")
}

async fn configure_verified_llm(app: &axum::Router) {
    let base_url = spawn_openai_mock_server().await;
    configure_verified_llm_with_base_url(app, base_url).await;
}

async fn configure_verified_llm_with_base_url(app: &axum::Router, base_url: String) {
    let save_payload = json!({
        "llmConfig": {
            "llmProvider": "openai_compatible",
            "llmApiKey": "sk-task-test",
            "llmModel": "gpt-5",
            "llmBaseUrl": base_url
        },
        "otherConfig": {
            "llmConcurrency": 1,
            "llmGapMs": 0
        }
    });
    let save_response = app
        .clone()
        .oneshot(
            Request::builder()
                .method(Method::PUT)
                .uri("/api/v1/system-config")
                .header("content-type", "application/json")
                .body(Body::from(save_payload.to_string()))
                .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(save_response.status(), StatusCode::OK);
    let test_response = app
        .clone()
        .oneshot(
            Request::builder()
                .method(Method::POST)
                .uri("/api/v1/system-config/test-llm")
                .header("content-type", "application/json")
                .body(Body::from(
                    json!({
                        "provider": "openai_compatible",
                        "apiKey": "sk-task-test",
                        "model": "gpt-5",
                        "baseUrl": save_payload["llmConfig"]["llmBaseUrl"]
                    })
                    .to_string(),
                ))
                .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(test_response.status(), StatusCode::OK);
    let payload: Value = serde_json::from_slice(
        &to_bytes(test_response.into_body(), usize::MAX)
            .await
            .unwrap(),
    )
    .unwrap();
    assert_eq!(payload["success"], true);
    assert!(payload["metadata"]["fingerprint"]
        .as_str()
        .unwrap()
        .starts_with("sha256:"));
}

struct EnvVarGuard {
    key: String,
    original: Option<String>,
}

impl EnvVarGuard {
    fn set(key: &str, value: &str) -> Self {
        let original = env::var(key).ok();
        env::set_var(key, value);
        Self {
            key: key.to_string(),
            original,
        }
    }
}

impl Drop for EnvVarGuard {
    fn drop(&mut self) {
        if let Some(original) = &self.original {
            env::set_var(&self.key, original);
        } else {
            env::remove_var(&self.key);
        }
    }
}

#[derive(Clone)]
struct CubeSandboxTestHarness {
    control_base_url: String,
    data_base_url: String,
    helper_path: PathBuf,
    seen_commands: std::sync::Arc<std::sync::Mutex<Vec<String>>>,
    deleted_sandboxes: std::sync::Arc<std::sync::Mutex<Vec<String>>>,
}

impl CubeSandboxTestHarness {
    async fn spawn(fail_make_exploration: bool) -> Self {
        Self::spawn_with_delay(fail_make_exploration, false).await
    }

    async fn spawn_with_delay(fail_make_exploration: bool, delay_until_delete: bool) -> Self {
        let seen_commands = std::sync::Arc::new(std::sync::Mutex::new(Vec::new()));
        let deleted_sandboxes = std::sync::Arc::new(std::sync::Mutex::new(Vec::new()));
        let temp_dir = tempfile::tempdir().expect("temp helper dir");
        let helper_dir = temp_dir.keep();
        let helper_path = helper_dir.join("cubesandbox-helper.sh");
        fs::write(
            &helper_path,
            "#!/bin/sh\ncase \"$1\" in status) exit 0 ;; *) exit 0 ;; esac\n",
        )
        .expect("write helper");
        let mut permissions = fs::metadata(&helper_path).unwrap().permissions();
        permissions.set_mode(0o755);
        fs::set_permissions(&helper_path, permissions).unwrap();

        let control_addr = spawn_cubesandbox_control_server(deleted_sandboxes.clone()).await;
        let data_addr = spawn_cubesandbox_data_server(
            seen_commands.clone(),
            deleted_sandboxes.clone(),
            fail_make_exploration,
            delay_until_delete,
        )
        .await;
        Self {
            control_base_url: format!("http://{control_addr}"),
            data_base_url: format!("http://{data_addr}"),
            helper_path,
            seen_commands,
            deleted_sandboxes,
        }
    }

    fn commands(&self) -> Vec<String> {
        self.seen_commands.lock().unwrap().clone()
    }

    fn deleted_sandboxes(&self) -> Vec<String> {
        self.deleted_sandboxes.lock().unwrap().clone()
    }
}

async fn spawn_cubesandbox_control_server(
    deleted_sandboxes: std::sync::Arc<std::sync::Mutex<Vec<String>>>,
) -> SocketAddr {
    let listener = TcpListener::bind("127.0.0.1:0")
        .await
        .expect("bind CubeSandbox control server");
    let address = listener.local_addr().expect("control address");
    tokio::spawn(async move {
        loop {
            let Ok((mut stream, _)) = listener.accept().await else {
                break;
            };
            let deleted_sandboxes = deleted_sandboxes.clone();
            tokio::spawn(async move {
                let mut buffer = [0_u8; 8192];
                let read = stream.read(&mut buffer).await.unwrap_or(0);
                let raw = String::from_utf8_lossy(&buffer[..read]);
                let first = raw.lines().next().unwrap_or_default();
                let path = first.split_whitespace().nth(1).unwrap_or("/");
                let (status, body) = if path == "/health" {
                    ("200 OK", r#"{"status":"ok"}"#.to_string())
                } else if path == "/sandboxes" && first.starts_with("POST ") {
                    (
                        "201 Created",
                        r#"{"sandboxID":"sbx-codeql","templateID":"tpl-codeql-test","clientID":"client-test","envdVersion":"0.1","domain":"cube.test"}"#.to_string(),
                    )
                } else if path == "/sandboxes/sbx-codeql/connect" {
                    ("200 OK", r#"{"connected":true}"#.to_string())
                } else if path == "/sandboxes/sbx-codeql" && first.starts_with("DELETE ") {
                    deleted_sandboxes
                        .lock()
                        .unwrap()
                        .push("sbx-codeql".to_string());
                    ("204 No Content", String::new())
                } else {
                    ("200 OK", "{}".to_string())
                };
                let response = if body.is_empty() {
                    format!("HTTP/1.1 {status}\r\ncontent-length: 0\r\nconnection: close\r\n\r\n")
                } else {
                    format!(
                        "HTTP/1.1 {status}\r\ncontent-type: application/json\r\ncontent-length: {}\r\nconnection: close\r\n\r\n{}",
                        body.len(),
                        body
                    )
                };
                let _ = stream.write_all(response.as_bytes()).await;
            });
        }
    });
    address
}

async fn spawn_cubesandbox_data_server(
    seen_commands: std::sync::Arc<std::sync::Mutex<Vec<String>>>,
    deleted_sandboxes: std::sync::Arc<std::sync::Mutex<Vec<String>>>,
    fail_make_exploration: bool,
    delay_until_delete: bool,
) -> SocketAddr {
    let listener = TcpListener::bind("127.0.0.1:0")
        .await
        .expect("bind CubeSandbox data server");
    let address = listener.local_addr().expect("data address");
    tokio::spawn(async move {
        loop {
            let Ok((mut stream, _)) = listener.accept().await else {
                break;
            };
            let seen_commands = seen_commands.clone();
            let deleted_sandboxes = deleted_sandboxes.clone();
            tokio::spawn(async move {
                let raw = read_http_request(&mut stream).await;
                let body = raw.split("\r\n\r\n").nth(1).unwrap_or("{}");
                let cmd = serde_json::from_str::<Value>(body)
                    .ok()
                    .and_then(|value| value.get("cmd").and_then(Value::as_str).map(str::to_string))
                    .unwrap_or_default();
                seen_commands.lock().unwrap().push(cmd.clone());
                if delay_until_delete {
                    for _ in 0..100 {
                        if deleted_sandboxes
                            .lock()
                            .unwrap()
                            .iter()
                            .any(|id| id == "sbx-codeql")
                        {
                            break;
                        }
                        sleep(Duration::from_millis(20)).await;
                    }
                }
                let output = if cmd.contains("CUBESANDBOX_CODEQL_EXPLORE_PY")
                    || cmd.contains("ARGUS_CODEQL_EXPLORATION_RESULT")
                {
                    let exploration_command =
                        decode_cubesandbox_exploration_command(&cmd).unwrap_or_default();
                    fake_cubesandbox_exploration_output_for_command(
                        &exploration_command,
                        fail_make_exploration,
                    )
                } else if cmd.contains("CUBESANDBOX_CODEQL_SETUP_PY")
                    || cmd.contains("ARGUS_CODEQL_SETUP_RESULT")
                {
                    "ARGUS_CODEQL_SETUP_RESULT={\"status\":\"ok\"}\n".to_string()
                } else {
                    fake_cubesandbox_process_output()
                };
                let response_body = json!({
                    "stdout": output,
                    "stderr": "",
                    "exitCode": 0,
                })
                .to_string();
                let response = format!(
                    "HTTP/1.1 200 OK\r\ncontent-type: application/json\r\ncontent-length: {}\r\nconnection: close\r\n\r\n{}",
                    response_body.len(),
                    response_body
                );
                let _ = stream.write_all(response.as_bytes()).await;
            });
        }
    });
    address
}

async fn read_http_request(stream: &mut tokio::net::TcpStream) -> String {
    let mut buffer = Vec::new();
    let mut chunk = [0_u8; 8192];
    loop {
        let read = stream.read(&mut chunk).await.unwrap_or(0);
        if read == 0 {
            break;
        }
        buffer.extend_from_slice(&chunk[..read]);
        if let Some(header_end) = find_header_end(&buffer) {
            let headers = String::from_utf8_lossy(&buffer[..header_end]);
            let content_length = headers
                .lines()
                .find_map(|line| {
                    let (name, value) = line.split_once(':')?;
                    name.eq_ignore_ascii_case("content-length")
                        .then(|| value.trim().parse::<usize>().ok())
                        .flatten()
                })
                .unwrap_or(0);
            if buffer.len() >= header_end + 4 + content_length {
                break;
            }
        }
    }
    String::from_utf8_lossy(&buffer).into_owned()
}

fn find_header_end(buffer: &[u8]) -> Option<usize> {
    buffer.windows(4).position(|window| window == b"\r\n\r\n")
}

fn fake_cubesandbox_process_output() -> String {
    let events = r#"{"stage":"llm_round","event":"started","round":1,"message":"probe failed and becomes retry context","reasoning_summary":"probe the C/C++ build environment","commands":["command -v make"]}
{"stage":"sandbox_command","event":"failed","round":1,"message":"exploration command exited","command":"command -v make","stdout":"","stderr":"make: not found sk-test-secret","exit_code":127,"failure_category":"compile_error","dependency_installation":{"detected":true}}
{"stage":"llm_round","event":"started","round":2,"message":"selected accepted build path","reasoning_summary":"run selected C/C++ build command","commands":["make -B -j2"]}
{"stage":"sandbox_command","event":"completed","round":2,"message":"exploration command exited","command":"make -B -j2","stdout":"ok","stderr":"","exit_code":0,"failure_category":"none","dependency_installation":{"detected":false}}
{"stage":"database_create","event":"completed","message":"CodeQL database created in CubeSandbox"}
{"stage":"database_analyze","event":"completed","message":"CodeQL SARIF generated in CubeSandbox"}
"#;
    let sarif = r#"{"version":"2.1.0","runs":[{"tool":{"driver":{"name":"CodeQL","rules":[]}},"results":[]}]}"#;
    let build_plan = json!({
        "language": "cpp",
        "target_path": ".",
        "build_mode": "manual",
        "commands": ["make -B -j2"],
        "working_directory": ".",
        "allow_network": false,
        "source_fingerprint": "sha256:source",
        "dependency_fingerprint": "sha256:deps",
        "status": "accepted",
        "evidence_json": {
            "artifacts_role": "evidence_only",
            "capture_validation": {
                "database_create": "completed",
                "extractor": "cpp"
            }
        }
    });
    let envelope = json!({
        "sarif_b64": STANDARD.encode(sarif),
        "events_b64": STANDARD.encode(events),
        "summary": {
            "status": "scan_completed",
            "engine": "codeql",
            "executor": "cubesandbox"
        },
        "build_plan": build_plan,
    });
    format!("ARGUS_CODEQL_RESULT={envelope}\n")
}

fn decode_cubesandbox_exploration_command(script: &str) -> Option<String> {
    let payload_b64 = script
        .strip_prefix("python3 - ")?
        .split_whitespace()
        .next()?;
    let payload = STANDARD.decode(payload_b64).ok()?;
    let parsed: Value = serde_json::from_slice(&payload).ok()?;
    parsed
        .get("command")
        .and_then(Value::as_str)
        .map(str::to_string)
}

fn fake_cubesandbox_exploration_output_for_command(
    command: &str,
    fail_make_exploration: bool,
) -> String {
    let (stdout, stderr, exit_code, failure_category, dependency_detected) =
        if command.contains("cc -c src/main.c") {
            ("compiled", "", 0, "none", false)
        } else if !fail_make_exploration && command.contains("make -B -j2") {
            ("ok", "", 0, "none", false)
        } else {
            ("", "missing compiler for make", 127, "compile_error", true)
        };
    let envelope = json!({
        "command": if command.contains("cc -c src/main.c") {
            "cc -c src/main.c"
        } else {
            "make -B -j2"
        },
        "stdout": stdout,
        "stderr": stderr,
        "exit_code": exit_code,
        "failure_category": failure_category,
        "dependency_installation": {"detected": dependency_detected},
    });
    format!("ARGUS_CODEQL_EXPLORATION_RESULT={envelope}\n")
}

fn cpp_test_zip_bytes() -> Vec<u8> {
    let mut bytes = Vec::new();
    {
        let cursor = std::io::Cursor::new(&mut bytes);
        let mut writer = zip::ZipWriter::new(cursor);
        let options = zip::write::SimpleFileOptions::default();
        writer.start_file("Makefile", options).unwrap();
        writer.write_all(b"all:\n\tcc src/main.c -o app\n").unwrap();
        writer.start_file("src/main.c", options).unwrap();
        writer.write_all(b"int main(void) { return 0; }\n").unwrap();
        writer.finish().unwrap();
    }
    bytes
}

fn language_test_zip_bytes(language: &str) -> Vec<u8> {
    let mut bytes = Vec::new();
    {
        let cursor = std::io::Cursor::new(&mut bytes);
        let mut writer = zip::ZipWriter::new(cursor);
        let options = zip::write::SimpleFileOptions::default();
        match language {
            "javascript-typescript" => {
                writer.start_file("package.json", options).unwrap();
                writer
                    .write_all(br#"{"scripts":{"build":"tsc --noEmit"},"devDependencies":{"typescript":"latest"}}"#)
                    .unwrap();
                writer.start_file("src/index.ts", options).unwrap();
                writer
                    .write_all(b"export const value: string = 'ok';\n")
                    .unwrap();
            }
            "python" => {
                writer.start_file("app.py", options).unwrap();
                writer.write_all(b"print('ok')\n").unwrap();
            }
            "java" => {
                writer.start_file("pom.xml", options).unwrap();
                writer.write_all(br#"<project><modelVersion>4.0.0</modelVersion><groupId>test</groupId><artifactId>sample</artifactId><version>1.0.0</version></project>"#).unwrap();
                writer
                    .start_file("src/main/java/App.java", options)
                    .unwrap();
                writer
                    .write_all(b"public class App { public static void main(String[] args) {} }\n")
                    .unwrap();
            }
            "go" => {
                writer.start_file("go.mod", options).unwrap();
                writer
                    .write_all(b"module example.com/sample\n\ngo 1.22\n")
                    .unwrap();
                writer.start_file("main.go", options).unwrap();
                writer.write_all(b"package main\nfunc main() {}\n").unwrap();
            }
            other => panic!("unsupported language fixture: {other}"),
        }
        writer.finish().unwrap();
    }
    bytes
}

async fn create_project_with_name(app: &axum::Router, name: &str) -> String {
    configure_verified_llm(app).await;
    let create_payload = json!({
        "name": name,
        "source_type": "zip",
        "default_branch": "main",
        "programming_languages": ["python", "typescript"]
    });

    let response = app
        .clone()
        .oneshot(
            Request::builder()
                .method(Method::POST)
                .uri("/api/v1/projects")
                .header("content-type", "application/json")
                .body(Body::from(create_payload.to_string()))
                .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(response.status(), StatusCode::OK);
    let payload: Value =
        serde_json::from_slice(&to_bytes(response.into_body(), usize::MAX).await.unwrap()).unwrap();
    payload["id"].as_str().unwrap().to_string()
}

async fn wait_static_task(state: &AppState, task_id: &str) -> task_state::StaticTaskRecord {
    loop {
        let snapshot = task_state::load_snapshot(state).await.expect("snapshot");
        let record = snapshot
            .static_tasks
            .get(task_id)
            .expect("static task record should exist");
        if record.status == "completed" || record.status == "failed" {
            return record.clone();
        }
        sleep(Duration::from_millis(50)).await;
    }
}

async fn wait_until<F>(label: &str, mut condition: F)
where
    F: FnMut() -> bool,
{
    for _ in 0..100 {
        if condition() {
            return;
        }
        sleep(Duration::from_millis(20)).await;
    }
    panic!("timed out waiting for {label}");
}

#[tokio::test]
async fn codeql_compile_sandbox_persists_plan_to_postgres_when_configured() {
    let Some(mut config) = require_db_test_config("codeql-cpp-compile-sandbox-db") else {
        return;
    };
    let _env_lock = ENV_LOCK.lock().await;
    let temp_dir = tempfile::tempdir().expect("temp dir");
    let cubesandbox = CubeSandboxTestHarness::spawn(false).await;
    config.cubesandbox_enabled = true;
    config.cubesandbox_template_id = "tpl-codeql-test".to_string();
    config.cubesandbox_api_base_url = cubesandbox.control_base_url.clone();
    config.cubesandbox_data_plane_base_url = cubesandbox.data_base_url.clone();
    config.cubesandbox_auto_start = false;
    config.cubesandbox_auto_install = false;
    config.cubesandbox_helper_path = cubesandbox.helper_path.to_string_lossy().to_string();
    let scan_root = temp_dir.path().join("scan-root");
    fs::create_dir_all(&scan_root).expect("mkdir scan root");

    let _workspace_root = EnvVarGuard::set("SCAN_WORKSPACE_ROOT", scan_root.to_str().unwrap());
    let _workspace_volume = EnvVarGuard::set("SCAN_WORKSPACE_VOLUME", "Argus_scan_workspace");

    let state = AppState::from_config(config)
        .await
        .expect("state should build");
    bootstrap::run(&state)
        .await
        .expect("startup bootstrap should create CodeQL build plan schema");
    assert!(state.db_pool.is_some(), "test requires DB-backed state");
    let app = build_router(state.clone());
    let project_id = create_project_with_name(&app, "codeql cpp db truth project").await;
    fs::create_dir_all(&*state.config.zip_storage_path).expect("mkdir zip root");
    fs::write(
        state
            .config
            .zip_storage_path
            .join(format!("{project_id}.zip")),
        cpp_test_zip_bytes(),
    )
    .expect("write cpp project zip");

    let response = app
        .clone()
        .oneshot(
            Request::builder()
                .method(Method::POST)
                .uri("/api/v1/static-tasks/codeql/tasks")
                .header("content-type", "application/json")
                .body(Body::from(
                    json!({
                        "project_id": project_id,
                        "name": "codeql cpp db truth task",
                        "target_path": "."
                    })
                    .to_string(),
                ))
                .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(response.status(), StatusCode::OK);
    let payload: Value =
        serde_json::from_slice(&to_bytes(response.into_body(), usize::MAX).await.unwrap()).unwrap();
    let task_id = payload["id"].as_str().expect("task id").to_string();

    let final_status = loop {
        let snapshot = task_state::load_snapshot(&state).await.expect("snapshot");
        let record = snapshot
            .static_tasks
            .get(&task_id)
            .expect("static task record should exist");
        if record.status == "completed" || record.status == "failed" {
            break record.clone();
        }
        sleep(Duration::from_millis(50)).await;
    };

    assert_eq!(final_status.status, "completed", "{final_status:?}");
    let plan_id = final_status.extra["build_plan_record_id"]
        .as_str()
        .expect("build plan id");
    let db_record = codeql_build_plans::load_build_plan_by_id(&state, plan_id)
        .await
        .expect("DB-backed CodeQL build plan lookup should succeed")
        .expect("compile sandbox plan persisted in rust_codeql_build_plans");
    assert_eq!(db_record.project_id, project_id);
    assert_eq!(db_record.language, "cpp");
    assert_eq!(db_record.status, "accepted");
    assert_eq!(db_record.commands, vec!["make -B -j2"]);
    assert_eq!(db_record.evidence_json["role"], "evidence_only");

    assert_eq!(cubesandbox.commands().len(), 1);
}

#[tokio::test]
async fn codeql_task_runs_cpp_compile_sandbox_before_replay_and_persists_db_truth() {
    let _env_lock = ENV_LOCK.lock().await;
    let temp_dir = tempfile::tempdir().expect("temp dir");
    let (config, cubesandbox) =
        isolated_codeql_cubesandbox_test_config("codeql-cpp-cubesandbox").await;
    let scan_root = temp_dir.path().join("scan-root");
    fs::create_dir_all(&scan_root).expect("mkdir scan root");

    let _workspace_root = EnvVarGuard::set("SCAN_WORKSPACE_ROOT", scan_root.to_str().unwrap());
    let _workspace_volume = EnvVarGuard::set("SCAN_WORKSPACE_VOLUME", "Argus_scan_workspace");

    let state = AppState::from_config(config)
        .await
        .expect("state should build");
    if state.db_pool.is_some() {
        bootstrap::run(&state)
            .await
            .expect("startup bootstrap should create CodeQL build plan schema");
    }
    let app = build_router(state.clone());
    let project_id = create_project_with_name(&app, "codeql cpp project").await;
    fs::create_dir_all(&*state.config.zip_storage_path).expect("mkdir zip root");
    fs::write(
        state
            .config
            .zip_storage_path
            .join(format!("{project_id}.zip")),
        cpp_test_zip_bytes(),
    )
    .expect("write cpp project zip");

    let response = app
        .clone()
        .oneshot(
            Request::builder()
                .method(Method::POST)
                .uri("/api/v1/static-tasks/codeql/tasks")
                .header("content-type", "application/json")
                .body(Body::from(
                    json!({
                        "project_id": project_id,
                        "name": "codeql cpp compile sandbox task",
                        "target_path": "."
                    })
                    .to_string(),
                ))
                .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(response.status(), StatusCode::OK);
    let payload: Value =
        serde_json::from_slice(&to_bytes(response.into_body(), usize::MAX).await.unwrap()).unwrap();
    let task_id = payload["id"].as_str().expect("task id").to_string();

    let final_status = loop {
        let snapshot = task_state::load_snapshot(&state).await.expect("snapshot");
        let record = snapshot
            .static_tasks
            .get(&task_id)
            .expect("static task record should exist");
        if record.status == "completed" || record.status == "failed" {
            break record.clone();
        }
        sleep(Duration::from_millis(50)).await;
    };

    assert_eq!(final_status.status, "completed", "{final_status:?}");
    assert_eq!(final_status.engine, "codeql");
    assert_eq!(final_status.extra["language"], "cpp");
    assert_eq!(
        final_status.extra["build_plan_source"],
        "compile_sandbox_db_truth"
    );
    assert_eq!(
        final_status.extra["compile_sandbox"]["evidence_role"],
        "evidence_only"
    );
    assert_eq!(
        final_status.extra["compile_sandbox"]["executor"],
        "cubesandbox"
    );

    let snapshot = task_state::load_snapshot(&state).await.expect("snapshot");
    let plan_id = final_status.extra["build_plan_record_id"]
        .as_str()
        .expect("build plan id");
    let persisted = if state.db_pool.is_some() {
        let db_record = codeql_build_plans::load_build_plan_by_id(&state, plan_id)
            .await
            .expect("DB-backed CodeQL build plan lookup should succeed")
            .expect("compile sandbox plan persisted in rust_codeql_build_plans");
        let snapshot_record = snapshot
            .codeql_build_plans
            .get(plan_id)
            .expect("compile sandbox plan projected into task-state status cache");
        assert_eq!(snapshot_record.evidence_json, db_record.evidence_json);
        db_record
    } else {
        snapshot
            .codeql_build_plans
            .get(plan_id)
            .expect("compile sandbox plan persisted in task-state fallback truth")
            .clone()
    };
    assert_eq!(persisted.language, "cpp");
    assert_eq!(persisted.status, "accepted");
    assert_eq!(persisted.commands, vec!["make -B -j2"]);
    assert_eq!(persisted.evidence_json["role"], "evidence_only");
    assert_eq!(
        persisted.evidence_json["capture_validation"]["extractor"],
        "cpp"
    );
    assert!(snapshot
        .static_tasks
        .get(&task_id)
        .expect("final task in snapshot")
        .progress
        .events
        .iter()
        .any(|event| event.stage == "codeql_capture_validation"));
    let progress_response = app
        .clone()
        .oneshot(
            Request::builder()
                .method(Method::GET)
                .uri(format!(
                    "/api/v1/static-tasks/codeql/tasks/{task_id}/progress?include_logs=true"
                ))
                .body(Body::empty())
                .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(progress_response.status(), StatusCode::OK);
    let progress_payload: Value = serde_json::from_slice(
        &to_bytes(progress_response.into_body(), usize::MAX)
            .await
            .unwrap(),
    )
    .unwrap();
    let events = progress_payload["events"]
        .as_array()
        .expect("progress events should be returned");
    assert!(
        events
            .iter()
            .any(|event| event["stage"] == "llm_round" && event["round"] == 1),
        "{events:?}"
    );
    assert!(
        events.iter().any(|event| {
            event["stage"] == "llm_round_completed"
                && event["payload"]["llm_mode"] == "saved_system_config"
                && event["payload"]["commands"]
                    .as_array()
                    .is_some_and(|commands| commands.iter().any(|command| command == "make -B -j2"))
        }),
        "{events:?}"
    );
    assert!(
        events.iter().any(|event| {
            event["stage"] == "sandbox_command"
                && event["payload"]["exit_code"] == 127
                && event["payload"]["dependency_installation"]["detected"] == true
        }),
        "{events:?}"
    );
    assert!(
        events
            .iter()
            .all(|event| !event.to_string().contains("sk-test-secret")),
        "{events:?}"
    );
    assert!(
        events
            .iter()
            .any(|event| event.to_string().contains("[REDACTED]")),
        "{events:?}"
    );

    let commands = cubesandbox.commands();
    assert_eq!(commands.len(), 3, "{commands:?}");
    assert!(commands[0].starts_with("python3 - "), "{commands:?}");
    assert!(commands[0].contains(" <<'PY'"), "{commands:?}");
    assert!(
        commands
            .iter()
            .any(|command| command.contains("ARGUS_CODEQL_SETUP_RESULT")),
        "{commands:?}"
    );
    assert!(
        commands
            .iter()
            .any(|command| command.contains("ARGUS_CODEQL_EXPLORATION_RESULT")),
        "{commands:?}"
    );
    assert!(
        commands
            .iter()
            .all(|command| !command.contains("docker") && !command.contains("codeql-scan")),
        "{commands:?}"
    );
}

#[tokio::test]
async fn codeql_cpp_exploration_feeds_failed_command_into_next_llm_round() {
    let _env_lock = ENV_LOCK.lock().await;
    let temp_dir = tempfile::tempdir().expect("temp dir");
    let (config, cubesandbox) = isolated_codeql_cubesandbox_test_config_with_make_failure(
        "codeql-cpp-retry-feedback",
        true,
    )
    .await;
    let scan_root = temp_dir.path().join("scan-root");
    fs::create_dir_all(&scan_root).expect("mkdir scan root");

    let _workspace_root = EnvVarGuard::set("SCAN_WORKSPACE_ROOT", scan_root.to_str().unwrap());
    let _workspace_volume = EnvVarGuard::set("SCAN_WORKSPACE_VOLUME", "Argus_scan_workspace");

    let state = AppState::from_config(config)
        .await
        .expect("state should build");
    if state.db_pool.is_some() {
        bootstrap::run(&state)
            .await
            .expect("startup bootstrap should create CodeQL build plan schema");
    }
    let app = build_router(state.clone());
    let project_id = create_project_with_name(&app, "codeql cpp retry feedback project").await;
    let retry_base_url = spawn_openai_mock_server_with_retry_feedback(true).await;
    configure_verified_llm_with_base_url(&app, retry_base_url).await;
    fs::create_dir_all(&*state.config.zip_storage_path).expect("mkdir zip root");
    fs::write(
        state
            .config
            .zip_storage_path
            .join(format!("{project_id}.zip")),
        cpp_test_zip_bytes(),
    )
    .expect("write cpp project zip");

    let response = app
        .clone()
        .oneshot(
            Request::builder()
                .method(Method::POST)
                .uri("/api/v1/static-tasks/codeql/tasks")
                .header("content-type", "application/json")
                .body(Body::from(
                    json!({
                        "project_id": project_id,
                        "name": "codeql cpp retry feedback task",
                        "target_path": "."
                    })
                    .to_string(),
                ))
                .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(response.status(), StatusCode::OK);
    let payload: Value =
        serde_json::from_slice(&to_bytes(response.into_body(), usize::MAX).await.unwrap()).unwrap();
    let task_id = payload["id"].as_str().expect("task id").to_string();

    let final_status = wait_static_task(&state, &task_id).await;
    assert_eq!(final_status.status, "completed", "{final_status:?}");
    let final_snapshot = task_state::load_snapshot(&state).await.expect("snapshot");
    let build_plan_record_id = final_status.extra["build_plan_record_id"]
        .as_str()
        .expect("build plan record id");
    let accepted_plan = final_snapshot
        .codeql_build_plans
        .get(build_plan_record_id)
        .expect("accepted build plan persisted");
    assert_eq!(accepted_plan.commands, vec!["cc -c src/main.c".to_string()]);

    let progress_response = app
        .clone()
        .oneshot(
            Request::builder()
                .method(Method::GET)
                .uri(format!(
                    "/api/v1/static-tasks/codeql/tasks/{task_id}/progress?include_logs=true"
                ))
                .body(Body::empty())
                .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(progress_response.status(), StatusCode::OK);
    let progress_payload: Value = serde_json::from_slice(
        &to_bytes(progress_response.into_body(), usize::MAX)
            .await
            .unwrap(),
    )
    .unwrap();
    let events = progress_payload["events"]
        .as_array()
        .expect("progress events should be returned");
    assert!(
        events.iter().any(|event| {
            event["stage"] == "sandbox_command_completed"
                && event["round"] == 1
                && event["payload"]["command"] == "make -B -j2"
                && event["payload"]["exit_code"] == 127
                && event["payload"]["stderr"]
                    .as_str()
                    .is_some_and(|stderr| stderr.contains("missing compiler"))
        }),
        "{events:?}"
    );
    assert!(
        events.iter().any(|event| {
            event["stage"] == "llm_round_started"
                && event["round"] == 2
                && event["payload"]["previous_failures"]
                    .as_array()
                    .is_some_and(|failures| {
                        failures.iter().any(|failure| {
                            failure["stderr"]
                                .as_str()
                                .is_some_and(|stderr| stderr.contains("missing compiler"))
                        })
                    })
        }),
        "{events:?}"
    );
    assert!(
        events.iter().any(|event| {
            event["stage"] == "sandbox_command_completed"
                && event["round"] == 2
                && event["payload"]["command"] == "cc -c src/main.c"
                && event["payload"]["exit_code"] == 0
        }),
        "{events:?}"
    );

    let commands = cubesandbox.commands();
    assert_eq!(commands.len(), 4, "{commands:?}");
    assert!(
        commands
            .iter()
            .all(|command| !command.contains("docker") && !command.contains("codeql-scan")),
        "{commands:?}"
    );
}

#[tokio::test]
async fn codeql_interrupt_deletes_active_cubesandbox_and_preserves_cancelled_status() {
    let _env_lock = ENV_LOCK.lock().await;
    let temp_dir = tempfile::tempdir().expect("temp dir");
    let harness = CubeSandboxTestHarness::spawn_with_delay(false, true).await;
    let mut config = isolated_test_config("codeql-active-cubesandbox-cancel");
    config.cubesandbox_enabled = true;
    config.cubesandbox_template_id = "tpl-codeql-test".to_string();
    config.cubesandbox_api_base_url = harness.control_base_url.clone();
    config.cubesandbox_data_plane_base_url = harness.data_base_url.clone();
    config.cubesandbox_auto_start = false;
    config.cubesandbox_auto_install = false;
    config.cubesandbox_helper_path = harness.helper_path.to_string_lossy().to_string();
    config.cubesandbox_execution_timeout_seconds = 120;
    let scan_root = temp_dir.path().join("scan-root");
    fs::create_dir_all(&scan_root).expect("mkdir scan root");

    let _workspace_root = EnvVarGuard::set("SCAN_WORKSPACE_ROOT", scan_root.to_str().unwrap());
    let _workspace_volume = EnvVarGuard::set("SCAN_WORKSPACE_VOLUME", "Argus_scan_workspace");

    let state = AppState::from_config(config)
        .await
        .expect("state should build");
    let app = build_router(state.clone());
    let project_id =
        create_project_with_name(&app, "codeql active cubesandbox cancel project").await;
    fs::create_dir_all(&*state.config.zip_storage_path).expect("mkdir zip root");
    fs::write(
        state
            .config
            .zip_storage_path
            .join(format!("{project_id}.zip")),
        cpp_test_zip_bytes(),
    )
    .expect("write cpp project zip");

    let response = app
        .clone()
        .oneshot(
            Request::builder()
                .method(Method::POST)
                .uri("/api/v1/static-tasks/codeql/tasks")
                .header("content-type", "application/json")
                .body(Body::from(
                    json!({
                        "project_id": project_id,
                        "name": "codeql active cubesandbox cancel task",
                        "target_path": "."
                    })
                    .to_string(),
                ))
                .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(response.status(), StatusCode::OK);
    let payload: Value =
        serde_json::from_slice(&to_bytes(response.into_body(), usize::MAX).await.unwrap()).unwrap();
    let task_id = payload["id"].as_str().expect("task id").to_string();

    wait_until("active CubeSandbox data-plane command", || {
        !harness.commands().is_empty()
    })
    .await;

    let interrupt_response = app
        .clone()
        .oneshot(
            Request::builder()
                .method(Method::POST)
                .uri(format!(
                    "/api/v1/static-tasks/codeql/tasks/{task_id}/interrupt"
                ))
                .body(Body::empty())
                .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(interrupt_response.status(), StatusCode::OK);

    wait_until("CubeSandbox DELETE request", || {
        harness
            .deleted_sandboxes()
            .iter()
            .any(|id| id == "sbx-codeql")
    })
    .await;
    sleep(Duration::from_millis(250)).await;

    let snapshot = task_state::load_snapshot(&state).await.expect("snapshot");
    let record = snapshot
        .static_tasks
        .get(&task_id)
        .expect("static task record should exist");
    assert_eq!(record.status, "interrupted", "{record:?}");
    assert_eq!(
        record.progress.current_stage.as_deref(),
        Some("interrupted"),
        "{record:?}"
    );
    assert!(
        record.progress.events.iter().any(|event| {
            event.stage == "cancelled_cleanup_completed"
                && event.payload["cubesandbox_cleanup"] == "deleted_active_sandbox"
        }),
        "{:?}",
        record.progress.events
    );
}

#[tokio::test]
async fn codeql_cpp_task_reuses_and_resets_project_sticky_build_plan() {
    let _env_lock = ENV_LOCK.lock().await;
    let temp_dir = tempfile::tempdir().expect("temp dir");
    let (config, cubesandbox) =
        isolated_codeql_cubesandbox_test_config("codeql-cpp-sticky-plan").await;
    let scan_root = temp_dir.path().join("scan-root");
    fs::create_dir_all(&scan_root).expect("mkdir scan root");

    let _workspace_root = EnvVarGuard::set("SCAN_WORKSPACE_ROOT", scan_root.to_str().unwrap());
    let _workspace_volume = EnvVarGuard::set("SCAN_WORKSPACE_VOLUME", "Argus_scan_workspace");

    let state = AppState::from_config(config)
        .await
        .expect("state should build");
    if state.db_pool.is_some() {
        bootstrap::run(&state)
            .await
            .expect("startup bootstrap should create CodeQL build plan schema");
    }
    let app = build_router(state.clone());
    let project_id = create_project_with_name(&app, "codeql cpp sticky project").await;
    fs::create_dir_all(&*state.config.zip_storage_path).expect("mkdir zip root");
    fs::write(
        state
            .config
            .zip_storage_path
            .join(format!("{project_id}.zip")),
        cpp_test_zip_bytes(),
    )
    .expect("write cpp project zip");

    async fn create_codeql_task(app: &axum::Router, project_id: &str, reset: bool) -> String {
        let response = app
            .clone()
            .oneshot(
                Request::builder()
                    .method(Method::POST)
                    .uri("/api/v1/static-tasks/codeql/tasks")
                    .header("content-type", "application/json")
                    .body(Body::from(
                        json!({
                            "project_id": project_id,
                            "name": "codeql cpp sticky task",
                            "target_path": ".",
                            "reset_build_plan": reset
                        })
                        .to_string(),
                    ))
                    .unwrap(),
            )
            .await
            .unwrap();
        assert_eq!(response.status(), StatusCode::OK);
        let payload: Value =
            serde_json::from_slice(&to_bytes(response.into_body(), usize::MAX).await.unwrap())
                .unwrap();
        payload["id"].as_str().expect("task id").to_string()
    }

    async fn wait_task(state: &AppState, task_id: &str) -> task_state::StaticTaskRecord {
        loop {
            let snapshot = task_state::load_snapshot(state).await.expect("snapshot");
            let record = snapshot
                .static_tasks
                .get(task_id)
                .expect("static task record should exist");
            if record.status == "completed" || record.status == "failed" {
                return record.clone();
            }
            sleep(Duration::from_millis(50)).await;
        }
    }

    let first_task = create_codeql_task(&app, &project_id, false).await;
    let first = wait_task(&state, &first_task).await;
    assert_eq!(first.status, "completed", "{first:?}");
    assert_eq!(first.extra["build_plan_source"], "compile_sandbox_db_truth");

    let second_task = create_codeql_task(&app, &project_id, false).await;
    let second = wait_task(&state, &second_task).await;
    assert_eq!(second.status, "completed", "{second:?}");
    assert_eq!(second.extra["build_plan_source"], "project_sticky_reuse");
    assert_eq!(
        second.extra["build_plan_record_id"],
        first.extra["build_plan_record_id"]
    );

    let reset_response = app
        .clone()
        .oneshot(
            Request::builder()
                .method(Method::POST)
                .uri(format!(
                    "/api/v1/static-tasks/codeql/projects/{project_id}/build-plan/reset"
                ))
                .body(Body::empty())
                .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(reset_response.status(), StatusCode::OK);

    let third_task = create_codeql_task(&app, &project_id, false).await;
    let third = wait_task(&state, &third_task).await;
    assert_eq!(third.status, "completed", "{third:?}");
    assert_eq!(third.extra["build_plan_source"], "compile_sandbox_db_truth");
    assert_ne!(
        third.extra["build_plan_record_id"],
        first.extra["build_plan_record_id"]
    );

    assert_eq!(
        cubesandbox.commands().len(),
        7,
        "first and third exploration tasks should setup/explore/scan; sticky reuse should scan only"
    );
}

#[tokio::test]
async fn codeql_task_honors_non_cpp_language_payloads_without_compile_sandbox() {
    let cases = [
        ("python", "none"),
        ("javascript-typescript", "none"),
        ("java", "none"),
        ("go", "autobuild"),
    ];

    for (language, expected_build_mode) in cases {
        let _env_lock = ENV_LOCK.lock().await;
        let temp_dir = tempfile::tempdir().expect("temp dir");
        let (config, cubesandbox) =
            isolated_codeql_cubesandbox_test_config(&format!("codeql-language-{language}")).await;
        let scan_root = temp_dir.path().join("scan-root");
        fs::create_dir_all(&scan_root).expect("mkdir scan root");

        let _workspace_root = EnvVarGuard::set("SCAN_WORKSPACE_ROOT", scan_root.to_str().unwrap());
        let _workspace_volume = EnvVarGuard::set("SCAN_WORKSPACE_VOLUME", "Argus_scan_workspace");

        let state = AppState::from_config(config)
            .await
            .expect("state should build");
        let app = build_router(state.clone());
        let project_id =
            create_project_with_name(&app, &format!("codeql {language} project")).await;
        fs::create_dir_all(&*state.config.zip_storage_path).expect("mkdir zip root");
        fs::write(
            state
                .config
                .zip_storage_path
                .join(format!("{project_id}.zip")),
            language_test_zip_bytes(language),
        )
        .expect("write language project zip");

        let response = app
            .clone()
            .oneshot(
                Request::builder()
                    .method(Method::POST)
                    .uri("/api/v1/static-tasks/codeql/tasks")
                    .header("content-type", "application/json")
                    .body(Body::from(
                        json!({
                            "project_id": project_id,
                            "name": format!("codeql {language} task"),
                            "target_path": ".",
                            "languages": [language]
                        })
                        .to_string(),
                    ))
                    .unwrap(),
            )
            .await
            .unwrap();
        assert_eq!(response.status(), StatusCode::OK, "{language}");
        let payload: Value =
            serde_json::from_slice(&to_bytes(response.into_body(), usize::MAX).await.unwrap())
                .unwrap();
        let task_id = payload["id"].as_str().expect("task id").to_string();

        let final_status = loop {
            let snapshot = task_state::load_snapshot(&state).await.expect("snapshot");
            let record = snapshot
                .static_tasks
                .get(&task_id)
                .expect("static task record should exist");
            if record.status == "completed" || record.status == "failed" {
                break record.clone();
            }
            sleep(Duration::from_millis(50)).await;
        };

        assert_eq!(
            final_status.status, "completed",
            "{language}: {final_status:?}"
        );
        assert_eq!(final_status.extra["language"], language);
        assert_eq!(final_status.extra["build_mode"], expected_build_mode);
        assert_eq!(
            final_status.extra["build_plan_source"],
            "direct_codeql_build_mode"
        );
        assert_eq!(final_status.extra["first_version_complete"], false);
        let commands = cubesandbox.commands();
        assert_eq!(commands.len(), 1, "{language}: {commands:?}");
        assert!(
            commands[0].starts_with("python3 - "),
            "{language}: {commands:?}"
        );
        assert!(commands[0].contains(" <<'PY'"), "{language}: {commands:?}");
        assert!(
            !commands[0].contains("codeql-compile-sandbox") && !commands[0].contains("docker"),
            "{language}: {commands:?}"
        );
    }
}
