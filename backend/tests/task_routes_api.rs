use axum::{
    body::{to_bytes, Body},
    http::{Method, Request, StatusCode},
};
use backend_rust::{
    app::build_router, config::AppConfig, db::task_state, runtime::shutdown::ShutdownGate,
    state::AppState,
};
use serde_json::{json, Value};
use std::{env, fs, io::Write, os::unix::fs::PermissionsExt, path::PathBuf, sync::LazyLock};
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
            "c" => {
                writer.start_file("src/bplist.c", options).unwrap();
                writer
                    .write_all(
                        b"void parse_string_node(char *dst, const char *src) { while (*src) { *dst++ = *src++; } }\n",
                    )
                    .unwrap();
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
  info)
    printf 'Virtualization: available\n'
    ;;
  image-inspect)
    exit 0
    ;;
  run)
    if [ "${FAKE_A3S_BOX_EXEC_RUN:-0}" = "1" ]; then
      while [ "$#" -gt 0 ] && [ "$1" != "--" ]; do
        shift
      done
      [ "$#" -gt 0 ] || exit 69
      shift
      exec "$@"
    fi
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

fn fake_podman_script(temp_dir: &tempfile::TempDir) -> PathBuf {
    let script_path = temp_dir.path().join("fake-podman.sh");
    let script = r#"#!/bin/sh
set -eu
log_file="${FAKE_PODMAN_LOG:?}"
cmd="${1:-}"
shift || true
printf '%s|%s\n' "$cmd" "$*" >> "$log_file"
case "$cmd" in
  info)
    printf 'true\n'
    ;;
  create)
    printf 'fake-container\n'
    ;;
  start)
    if [ "${1:-}" = "-a" ]; then
      shift || true
    fi
    output="${FAKE_PODMAN_OUTPUT_PATH:-}"
    summary="${FAKE_PODMAN_SUMMARY_PATH:-}"
    scan_log="${FAKE_PODMAN_SCAN_LOG_PATH:-}"
    if [ -z "$summary" ] && [ -n "${FAKE_PODMAN_LOG:-}" ]; then
      create_args="$(grep '^create|' "$log_file" | tail -n 1 | cut -d'|' -f2-)"
      while [ $# -gt 0 ]; do shift || true; done
      set -- $create_args
      output_host_root=""
      while [ "$#" -gt 0 ]; do
        case "$1" in
          -v)
            shift
            volume="${1:-}"
            host_root="${volume%%:*}"
            rest="${volume#*:}"
            container_root="${rest%%:*}"
            if [ "$container_root" = "/scan/output" ]; then
              output_host_root="$host_root"
            fi
            ;;
          --summary)
            shift
            summary="${1:-}"
            ;;
          --output)
            shift
            output="${1:-}"
            ;;
          --log)
            shift
            scan_log="${1:-}"
            ;;
        esac
        shift || true
      done
      if [ -n "$output_host_root" ]; then
        case "$output" in
          /scan/output/*) output="$output_host_root/${output#/scan/output/}" ;;
        esac
        case "$summary" in
          /scan/output/*) summary="$output_host_root/${summary#/scan/output/}" ;;
        esac
        case "$scan_log" in
          /scan/output/*) scan_log="$output_host_root/${scan_log#/scan/output/}" ;;
        esac
      fi
    fi
    if [ -n "$output" ]; then
      mkdir -p "$(dirname "$output")"
      printf '{"results":[]}\n' > "$output"
    fi
    if [ -n "$summary" ]; then
      mkdir -p "$(dirname "$summary")"
      printf '{"status":"scan_completed"}\n' > "$summary"
    fi
    if [ -n "$scan_log" ]; then
      mkdir -p "$(dirname "$scan_log")"
      printf 'fake podman fallback opengrep scan\n' > "$scan_log"
    fi
    printf 'fake podman fallback stdout\n'
    ;;
  wait)
    printf '0\n'
    ;;
  logs)
    if [ "${1:-}" = "--stdout" ]; then
      printf 'fake podman fallback stdout\n'
      exit 0
    fi
    if [ "${1:-}" = "--stderr" ]; then
      printf 'fake podman fallback stderr\n'
      exit 0
    fi
    ;;
  rm)
    printf 'removed\n'
    ;;
esac
"#;
    fs::write(&script_path, script).expect("write fake podman script");
    let mut permissions = fs::metadata(&script_path).unwrap().permissions();
    permissions.set_mode(0o755);
    fs::set_permissions(&script_path, permissions).unwrap();
    script_path
}

fn fake_joern_podman_script(temp_dir: &tempfile::TempDir) -> PathBuf {
    let script_path = temp_dir.path().join("fake-joern-podman.sh");
    let script = r#"#!/bin/sh
set -eu
log_file="${FAKE_PODMAN_LOG:?}"
cmd="${1:-}"
shift || true
printf '%s|%s\n' "$cmd" "$*" >> "$log_file"
case "$cmd" in
  info)
    printf 'true\n'
    ;;
  create)
    printf 'fake-joern-container\n'
    ;;
  start)
    create_args="$(grep '^create|' "$log_file" | tail -n 1 | cut -d'|' -f2-)"
    set -- $create_args
    output_host_root=""
    while [ "$#" -gt 0 ]; do
      case "$1" in
        -v)
          shift
          volume="${1:-}"
          host_root="${volume%%:*}"
          rest="${volume#*:}"
          container_root="${rest%%:*}"
          if [ "$container_root" = "/scan/output" ]; then
            output_host_root="$host_root"
          fi
          ;;
      esac
      shift || true
    done
    if [ -z "$output_host_root" ]; then
      printf 'missing /scan/output mount\n' >&2
      exit 71
    fi
    mkdir -p "$output_host_root"
    printf '{"status":"scan_completed","scanner":"joern","schema_version":"argus.joern.v1"}\n' > "$output_host_root/summary.json"
    printf '{"schema_version":"argus.joern.graph-proof.v1","files":["src/bplist.c"],"functions":["parse_string_node"]}\n' > "$output_host_root/graph-proof.json"
    printf '{"schema_version":"argus.joern.findings.v1","engine":"joern","findings":[]}\n' > "$output_host_root/findings.json"
    printf 'fake joern stdout\n'
    ;;
  inspect)
    printf 'false\n'
    ;;
  wait)
    printf '0\n'
    ;;
  logs)
    if [ "${1:-}" = "--stdout" ]; then
      printf 'fake joern stdout\n'
      exit 0
    fi
    if [ "${1:-}" = "--stderr" ]; then
      printf 'fake joern stderr\n'
      exit 0
    fi
    ;;
  rm)
    printf 'removed\n'
    ;;
esac
"#;
    fs::write(&script_path, script).expect("write fake joern podman script");
    let mut permissions = fs::metadata(&script_path).unwrap().permissions();
    permissions.set_mode(0o755);
    fs::set_permissions(&script_path, permissions).unwrap();
    script_path
}

fn fake_opengrep_scan_script(temp_dir: &tempfile::TempDir) -> PathBuf {
    let script_path = temp_dir.path().join("opengrep-scan");
    let script = r#"#!/bin/sh
set -eu
output=""
summary=""
scan_log=""
while [ "$#" -gt 0 ]; do
  case "$1" in
    --output) shift; output="${1:-}" ;;
    --summary) shift; summary="${1:-}" ;;
    --log) shift; scan_log="${1:-}" ;;
  esac
  shift || true
done
[ -n "$output" ] || exit 64
[ -n "$summary" ] || exit 65
[ -n "$scan_log" ] || exit 66
mkdir -p "$(dirname "$output")" "$(dirname "$summary")" "$(dirname "$scan_log")"
printf '{"results":[]}\n' > "$output"
printf '{"status":"scan_completed","files_scanned":1}\n' > "$summary"
printf 'fake opengrep scan\n' > "$scan_log"
printf 'fake opengrep stdout\n'
"#;
    fs::write(&script_path, script).expect("write fake opengrep-scan script");
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
async fn static_task_api_rejects_unknown_engine_without_opengrep_fallback() {
    let config = isolated_test_config("static-unknown-engine-rejected");
    let state = AppState::from_config(config)
        .await
        .expect("state should build");
    let app = build_router(state.clone(), ShutdownGate::default());
    let project_id = create_project_with_name(&app, "unknown engine project").await;

    let response = app
        .clone()
        .oneshot(
            Request::builder()
                .method(Method::POST)
                .uri("/api/v1/static-tasks/tasks")
                .header("content-type", "application/json")
                .body(Body::from(
                    json!({
                        "engine": "semgrep",
                        "project_id": project_id,
                        "target_path": "."
                    })
                    .to_string(),
                ))
                .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(response.status(), StatusCode::BAD_REQUEST);
    let payload: Value =
        serde_json::from_slice(&to_bytes(response.into_body(), usize::MAX).await.unwrap()).unwrap();
    assert!(payload["error"]
        .as_str()
        .unwrap_or_default()
        .contains("supported engines: opengrep, codeql, joern"));

    let snapshot = task_state::load_snapshot(&state)
        .await
        .expect("snapshot should load");
    assert!(
        snapshot.static_tasks.is_empty(),
        "unknown engines must not create an OpenGrep task"
    );
}

#[tokio::test]
async fn joern_static_task_routes_are_engine_scoped_and_do_not_fall_through_to_opengrep() {
    let _env_lock = ENV_LOCK.lock().await;
    let temp_dir = tempfile::tempdir().expect("temp dir");
    let fake_podman = fake_joern_podman_script(&temp_dir);
    let fake_podman_log = temp_dir.path().join("fake-joern-podman.log");
    let scan_root = temp_dir.path().join("scan-root");
    fs::create_dir_all(&scan_root).expect("mkdir scan root");

    let _podman_bin = EnvVarGuard::set("Argus_PODMAN_BIN", fake_podman.to_str().unwrap());
    let _podman_log = EnvVarGuard::set("FAKE_PODMAN_LOG", fake_podman_log.to_str().unwrap());
    let _workspace_root = EnvVarGuard::set("SCAN_WORKSPACE_ROOT", scan_root.to_str().unwrap());
    let _workspace_volume = EnvVarGuard::set("SCAN_WORKSPACE_VOLUME", scan_root.to_str().unwrap());

    let mut config = isolated_test_config("joern-route-skeleton");
    config.scanner_joern_image = "ghcr.nju.edu.cn/joernio/joern:test".to_string();
    let state = AppState::from_config(config)
        .await
        .expect("state should build");
    let app = build_router(state.clone(), ShutdownGate::default());
    let project_id = create_project_with_name(&app, "joern route skeleton project").await;

    fs::create_dir_all(&*state.config.zip_storage_path).expect("mkdir zip root");
    fs::write(
        state
            .config
            .zip_storage_path
            .join(format!("{project_id}.zip")),
        language_test_zip_bytes("c"),
    )
    .expect("write c project zip");

    let response = app
        .clone()
        .oneshot(
            Request::builder()
                .method(Method::POST)
                .uri("/api/v1/static-tasks/joern/tasks")
                .header("content-type", "application/json")
                .body(Body::from(
                    json!({
                        "project_id": project_id,
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
    assert_eq!(payload["engine"].as_str(), Some("joern"));
    let task_id = payload["id"].as_str().expect("task id").to_string();

    let record = wait_static_task(&state, &task_id).await;
    assert_eq!(record.engine, "joern");
    assert_eq!(record.status, "completed", "{:?}", record.error_message);
    assert_eq!(record.extra["engine"], "joern");
    assert_eq!(record.extra["executor"], "runner_spec_podman");
    assert_eq!(record.total_findings, 0);
    assert!(record.files_scanned >= 1);

    let joern_get = app
        .clone()
        .oneshot(
            Request::builder()
                .method(Method::GET)
                .uri(format!("/api/v1/static-tasks/joern/tasks/{task_id}"))
                .body(Body::empty())
                .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(joern_get.status(), StatusCode::OK);
    let joern_payload: Value =
        serde_json::from_slice(&to_bytes(joern_get.into_body(), usize::MAX).await.unwrap())
            .unwrap();
    assert_eq!(joern_payload["id"].as_str(), Some(task_id.as_str()));
    assert_eq!(joern_payload["engine"].as_str(), Some("joern"));

    let opengrep_get = app
        .clone()
        .oneshot(
            Request::builder()
                .method(Method::GET)
                .uri(format!("/api/v1/static-tasks/tasks/{task_id}"))
                .body(Body::empty())
                .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(opengrep_get.status(), StatusCode::NOT_FOUND);

    let joern_list = app
        .clone()
        .oneshot(
            Request::builder()
                .method(Method::GET)
                .uri("/api/v1/static-tasks/joern/tasks?limit=10")
                .body(Body::empty())
                .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(joern_list.status(), StatusCode::OK);
    let joern_list_payload: Value =
        serde_json::from_slice(&to_bytes(joern_list.into_body(), usize::MAX).await.unwrap())
            .unwrap();
    assert_eq!(joern_list_payload.as_array().unwrap().len(), 1);
    assert_eq!(joern_list_payload[0]["engine"].as_str(), Some("joern"));

    let opengrep_list = app
        .oneshot(
            Request::builder()
                .method(Method::GET)
                .uri("/api/v1/static-tasks/tasks?limit=10")
                .body(Body::empty())
                .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(opengrep_list.status(), StatusCode::OK);
    let opengrep_list_payload: Value = serde_json::from_slice(
        &to_bytes(opengrep_list.into_body(), usize::MAX)
            .await
            .unwrap(),
    )
    .unwrap();
    assert!(
        opengrep_list_payload.as_array().unwrap().is_empty(),
        "Joern route must not create or list OpenGrep tasks"
    );

    let podman_logged = fs::read_to_string(fake_podman_log).expect("fake podman log");
    assert!(podman_logged.contains("info|--format {{.Host.Security.Rootless}}"));
    assert!(podman_logged.contains("create|"));
    assert!(podman_logged.contains("--network none"));
    assert!(podman_logged.contains(":/scan/source:ro"));
    assert!(podman_logged.contains(":/scan/joern-queries:ro"));
    assert!(podman_logged.contains(":/scan/output:rw"));
    assert!(podman_logged.contains("ghcr.nju.edu.cn/joernio/joern:test /bin/sh"));
    assert!(podman_logged.contains("/scan/workspace/argus-joern-wrapper.sh"));
}

#[tokio::test]
async fn opengrep_a3s_box_task_runs_through_static_task_api_with_fake_cli() {
    let _env_lock = ENV_LOCK.lock().await;
    let temp_dir = tempfile::tempdir().expect("temp dir");
    let fake_a3s_box = fake_a3s_box_opengrep_script(&temp_dir);
    let _fake_opengrep_scan = fake_opengrep_scan_script(&temp_dir);
    let fake_log = temp_dir.path().join("fake-a3s-box.log");
    let scan_root = temp_dir.path().join("scan-root");
    fs::create_dir_all(&scan_root).expect("mkdir scan root");

    let _bin = EnvVarGuard::set("A3S_BOX_BIN", fake_a3s_box.to_str().unwrap());
    let _log = EnvVarGuard::set("FAKE_A3S_BOX_LOG", fake_log.to_str().unwrap());
    let _exec = EnvVarGuard::set("FAKE_A3S_BOX_EXEC_RUN", "1");
    let _workspace_root = EnvVarGuard::set("SCAN_WORKSPACE_ROOT", scan_root.to_str().unwrap());
    let original_path = env::var("PATH").unwrap_or_default();
    let _path = EnvVarGuard::set(
        "PATH",
        &format!("{}:{original_path}", temp_dir.path().display()),
    );

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
    assert!(logged.contains("-v "));
    assert!(
        logged.contains("--network none"),
        "A3S OpenGrep scans should run offline: {logged}"
    );
    assert!(logged.contains("argus/opengrep-runner:test -- bash -lc"));
    assert!(logged.contains("opengrep-scan"));
}

#[tokio::test]
async fn opengrep_a3s_box_task_falls_back_to_fake_podman_without_network() {
    let _env_lock = ENV_LOCK.lock().await;
    let temp_dir = tempfile::tempdir().expect("temp dir");
    let fake_a3s_box = fake_a3s_box_opengrep_script(&temp_dir);
    let fake_podman = fake_podman_script(&temp_dir);
    let fake_a3s_log = temp_dir.path().join("fake-a3s-box.log");
    let fake_podman_log = temp_dir.path().join("fake-podman.log");
    let scan_root = temp_dir.path().join("scan-root");
    fs::create_dir_all(&scan_root).expect("mkdir scan root");

    let _bin = EnvVarGuard::set("A3S_BOX_BIN", fake_a3s_box.to_str().unwrap());
    let _podman_bin = EnvVarGuard::set("Argus_PODMAN_BIN", fake_podman.to_str().unwrap());
    let _a3s_log = EnvVarGuard::set("FAKE_A3S_BOX_LOG", fake_a3s_log.to_str().unwrap());
    let _podman_log = EnvVarGuard::set("FAKE_PODMAN_LOG", fake_podman_log.to_str().unwrap());
    let _workspace_root = EnvVarGuard::set("SCAN_WORKSPACE_ROOT", scan_root.to_str().unwrap());
    let _workspace_volume = EnvVarGuard::set("SCAN_WORKSPACE_VOLUME", scan_root.to_str().unwrap());

    let mut config = isolated_test_config("opengrep-a3s-box-fake-podman-fallback");
    config.scanner_opengrep_a3s_box_image = "argus/opengrep-runner:test".to_string();
    config.scanner_opengrep_image = "argus/opengrep-runner:test".to_string();
    config.opengrep_runner_runtime = "podman".to_string();
    let state = AppState::from_config(config)
        .await
        .expect("state should build");
    let app = build_router(state.clone(), ShutdownGate::default());
    let project_id = create_project_with_name(&app, "opengrep fallback fake project").await;

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
    assert_eq!(record.extra["executor"], "a3s_box_fallback_podman");
    assert_eq!(record.total_findings, 0);
    assert!(record.files_scanned >= 1);

    let a3s_logged = fs::read_to_string(fake_a3s_log).expect("fake a3s log");
    assert!(a3s_logged.contains("run|"));
    let podman_logged = fs::read_to_string(fake_podman_log).expect("fake podman log");
    assert!(podman_logged.contains("info|--format {{.Host.Security.Rootless}}"));
    assert!(podman_logged.contains("create|"));
    assert!(podman_logged.contains("--network none"));
    assert!(podman_logged.contains(":/scan/source:ro"));
    assert!(podman_logged.contains(":/scan/opengrep-rules:ro"));
    assert!(podman_logged.contains(":/scan/output:rw"));
    assert!(podman_logged.contains("argus/opengrep-runner:test opengrep-scan"));
    assert!(podman_logged.contains(scan_root.to_str().unwrap()));
}
