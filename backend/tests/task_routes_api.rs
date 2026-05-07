use axum::{
    body::{to_bytes, Body},
    http::{Method, Request, StatusCode},
};
use backend_rust::{
    app::build_router,
    config::AppConfig,
    db::task_state,
    runtime::shutdown::ShutdownGate,
    state::AppState,
};
use serde_json::{json, Value};
use std::{
    env, fs, io::Write, os::unix::fs::PermissionsExt, path::PathBuf,
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

async fn spawn_openai_mock_server() -> String {
    spawn_openai_mock_server_with_content(|_| "ok".to_string()).await
}

async fn spawn_openai_mock_server_with_content(
    content_for_request: impl Fn(&str) -> String + Send + Sync + 'static,
) -> String {
    let listener = TcpListener::bind("127.0.0.1:0")
        .await
        .expect("bind mock llm server");
    let address = listener.local_addr().expect("mock llm address");
    let content_for_request = std::sync::Arc::new(content_for_request);
    tokio::spawn(async move {
        loop {
            let Ok((mut stream, _)) = listener.accept().await else {
                break;
            };
            let content_for_request = content_for_request.clone();
            tokio::spawn(async move {
                let mut buffer = [0_u8; 4096];
                let read_len = stream.read(&mut buffer).await.unwrap_or(0);
                let request = String::from_utf8_lossy(&buffer[..read_len]);
                let content = content_for_request(&request);
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

fn fake_a3s_box_opengrep_script(temp_dir: &tempfile::TempDir) -> PathBuf {
    let script_path = temp_dir.path().join("fake-a3s-box-opengrep.sh");
    let script = r#"#!/bin/sh
set -eu
log_file="${FAKE_A3S_BOX_LOG:?}"
cmd="${1:-}"
shift || true
printf '%s|%s\n' "$cmd" "$*" >> "$log_file"
case "$cmd" in
  run)
    output=""
    summary=""
    scan_log=""
    seen_sep=0
    while [ "$#" -gt 0 ]; do
      if [ "$1" = "--" ]; then
        seen_sep=1
        shift
        continue
      fi
      if [ "$seen_sep" -eq 1 ]; then
        case "$1" in
          --output) shift; output="${1:-}" ;;
          --summary) shift; summary="${1:-}" ;;
          --log) shift; scan_log="${1:-}" ;;
        esac
      fi
      shift || true
    done
    [ -n "$output" ] || exit 64
    [ -n "$summary" ] || exit 65
    [ -n "$scan_log" ] || exit 66
    mkdir -p "$(dirname "$output")" "$(dirname "$summary")" "$(dirname "$scan_log")"
    printf '{"results":[]}\n' > "$output"
    printf '{"status":"ok","files_scanned":1}\n' > "$summary"
    printf 'fake a3s opengrep scan\n' > "$scan_log"
    printf 'fake a3s stdout\n'
    ;;
  rm)
    printf 'removed\n'
    ;;
  *)
    exit 67
    ;;
esac
"#;
    fs::write(&script_path, script).expect("write fake a3s-box script");
    let mut permissions = fs::metadata(&script_path).unwrap().permissions();
    permissions.set_mode(0o755);
    fs::set_permissions(&script_path, permissions).unwrap();
    script_path
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

#[tokio::test]
async fn static_task_api_binds_project_name_from_backend_project_record() {
    let config = isolated_test_config("static-project-name-binding");
    let state = AppState::from_config(config)
        .await
        .expect("state should build");
    let app = build_router(state.clone(), ShutdownGate::default());
    let project_id = create_project_with_name(&app, "Backend Static Project").await;

    let mut snapshot = task_state::load_snapshot(&state)
        .await
        .expect("snapshot should load");
    snapshot.static_tasks.insert(
        "static-project-name-binding".to_string(),
        task_state::StaticTaskRecord {
            id: "static-project-name-binding".to_string(),
            engine: "opengrep".to_string(),
            project_id: project_id.clone(),
            project_name: None,
            name: "static project name binding".to_string(),
            status: "completed".to_string(),
            target_path: ".".to_string(),
            created_at: "2026-05-03T00:00:00Z".to_string(),
            extra: json!({}),
            ..Default::default()
        },
    );
    task_state::save_snapshot(&state, &snapshot)
        .await
        .expect("snapshot should save");

    let response = app
        .clone()
        .oneshot(
            Request::builder()
                .method(Method::GET)
                .uri("/api/v1/static-tasks/tasks/static-project-name-binding")
                .body(Body::empty())
                .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(response.status(), StatusCode::OK);
    let payload: Value =
        serde_json::from_slice(&to_bytes(response.into_body(), usize::MAX).await.unwrap()).unwrap();
    assert_eq!(payload["project_id"].as_str(), Some(project_id.as_str()));
    assert_eq!(
        payload["project_name"].as_str(),
        Some("Backend Static Project")
    );

    let list_response = app
        .oneshot(
            Request::builder()
                .method(Method::GET)
                .uri("/api/v1/static-tasks/tasks?limit=10")
                .body(Body::empty())
                .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(list_response.status(), StatusCode::OK);
    let list_payload: Value = serde_json::from_slice(
        &to_bytes(list_response.into_body(), usize::MAX)
            .await
            .unwrap(),
    )
    .unwrap();
    assert_eq!(
        list_payload
            .as_array()
            .unwrap()
            .first()
            .and_then(|item| item["project_name"].as_str()),
        Some("Backend Static Project")
    );
}

#[tokio::test]
async fn opengrep_a3s_box_task_runs_through_static_task_api_with_fake_cli() {
    let _env_lock = ENV_LOCK.lock().await;
    let temp_dir = tempfile::tempdir().expect("temp dir");
    let fake_a3s_box = fake_a3s_box_opengrep_script(&temp_dir);
    let fake_log = temp_dir.path().join("fake-a3s-box.log");
    let scan_root = temp_dir.path().join("scan-root");
    fs::create_dir_all(&scan_root).expect("mkdir scan root");

    let _bin = EnvVarGuard::set("A3S_BOX_BIN", fake_a3s_box.to_str().unwrap());
    let _log = EnvVarGuard::set("FAKE_A3S_BOX_LOG", fake_log.to_str().unwrap());
    let _workspace_root = EnvVarGuard::set("SCAN_WORKSPACE_ROOT", scan_root.to_str().unwrap());

    let mut config = isolated_test_config("opengrep-a3s-box-fake-cli");
    config.scanner_opengrep_a3s_box_image = "argus/opengrep-runner:test".to_string();
    let state = AppState::from_config(config)
        .await
        .expect("state should build");
    let app = build_router(state.clone(), ShutdownGate::default());
    let project_id = create_project_with_name(&app, "opengrep a3s fake project").await;

    fs::create_dir_all(&*state.config.zip_storage_path).expect("mkdir zip root");
    fs::write(
        state
            .config
            .zip_storage_path
            .join(format!("{project_id}.zip")),
        language_test_zip_bytes("python"),
    )
    .expect("write python project zip");

    let response = app
        .clone()
        .oneshot(
            Request::builder()
                .method(Method::POST)
                .uri("/api/v1/static-tasks/tasks")
                .header("content-type", "application/json")
                .body(Body::from(
                    json!({
                        "engine": "opengrep",
                        "project_id": project_id,
                        "target_path": ".",
                        "opengrep_sandbox": "a3s_box"
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

    let record = wait_static_task(&state, &task_id).await;
    assert_eq!(record.status, "completed", "{:?}", record.error_message);
    assert_eq!(record.extra["opengrep_sandbox"], "a3s_box");
    assert_eq!(record.extra["executor"], "a3s_box");
    assert_eq!(record.total_findings, 0);
    assert!(record.files_scanned >= 1);

    let logged = fs::read_to_string(fake_log).expect("fake a3s log");
    assert!(logged.contains("run|"));
    assert!(logged.contains("--rm"));
    assert!(logged.contains("--name argus-opengrep-"));
    assert!(logged.contains("--volume "));
    assert!(logged.contains("argus/opengrep-runner:test -- opengrep-scan"));
    assert!(logged.contains("--target "));
    assert!(logged.contains("--output "));
}
