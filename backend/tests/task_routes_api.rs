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
use serde_json::{json, Value};
use std::{env, fs, io::Write, os::unix::fs::PermissionsExt, path::PathBuf, sync::LazyLock};
use tempfile::TempDir;
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
                let _ = stream.read(&mut buffer).await;
                let body = r#"{"choices":[{"message":{"content":"ok"}}]}"#;
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

fn fake_codeql_compile_task_docker(temp_dir: &TempDir) -> PathBuf {
    let script_path = temp_dir.path().join("fake-codeql-compile-task-docker.sh");
    let script = r#"#!/bin/sh
set -eu
log_file="${FAKE_DOCKER_LOG:?}"
state_dir="${FAKE_TASK_DOCKER_STATE_DIR:?}"
cmd="${1:-}"
shift || true
printf '%s|%s
' "$cmd" "$*" >> "$log_file"
case "$cmd" in
  create)
    summary_path=""
    events_path=""
    plan_path=""
    sarif_path=""
    image_seen=""
    prev=""
    for arg in "$@"; do
      case "$prev" in
        summary) summary_path="$arg"; prev="" ;;
        events) events_path="$arg"; prev="" ;;
        plan) plan_path="$arg"; prev="" ;;
        sarif) sarif_path="$arg"; prev="" ;;
        *)
          case "$arg" in
            --summary) prev="summary" ;;
            --events) prev="events" ;;
            --plan|--build-plan) prev="plan" ;;
            --sarif) prev="sarif" ;;
            Argus/codeql-runner:test) image_seen="$arg" ;;
          esac
          ;;
      esac
    done
    count_file="$state_dir/create_count"
    count="$(cat "$count_file" 2>/dev/null || printf '0')"
    count=$((count + 1))
    printf '%s' "$count" > "$count_file"
    if [ "$count" = "1" ]; then
      printf '%s' "$summary_path" > "$state_dir/compile_summary_path"
      printf '%s' "$events_path" > "$state_dir/compile_events_path"
      printf '%s' "$plan_path" > "$state_dir/compile_plan_path"
      printf 'compile-container
'
    else
      printf '%s' "$summary_path" > "$state_dir/codeql_summary_path"
      printf '%s' "$events_path" > "$state_dir/codeql_events_path"
      printf '%s' "$sarif_path" > "$state_dir/sarif_path"
      printf '%s' "$plan_path" > "$state_dir/codeql_build_plan_path"
      printf 'codeql-container
'
    fi
    ;;
  start)
    container_id="${1:-}"
    if [ "$container_id" = "compile-container" ]; then
      summary_path="$(cat "$state_dir/compile_summary_path")"
      events_path="$(cat "$state_dir/compile_events_path")"
      plan_path="$(cat "$state_dir/compile_plan_path")"
      mkdir -p "$(dirname "$summary_path")" "$(dirname "$events_path")" "$(dirname "$plan_path")"
      printf '%s
' '{"ts":"2026-05-01T00:00:00Z","stage":"compile_sandbox","event":"command_exit","message":"compile command completed","exit_code":0}' > "$events_path"
      printf '%s
' '{"status":"compile_completed","language":"cpp","commands":["make -j2"],"evidence_json":{"artifacts_role":"evidence_only"}}' > "$summary_path"
      printf '%s
' '{"language":"cpp","target_path":".","build_mode":"manual","commands":["make -j2"],"working_directory":".","allow_network":false,"source_fingerprint":"sha256:source","dependency_fingerprint":"sha256:deps","status":"accepted","evidence_json":{"artifacts_role":"evidence_only","stdout_path":"/scan/evidence/stdout.txt"}}' > "$plan_path"
    else
      summary_path="$(cat "$state_dir/codeql_summary_path")"
      events_path="$(cat "$state_dir/codeql_events_path")"
      sarif_path="$(cat "$state_dir/sarif_path")"
      build_plan_path="$(cat "$state_dir/codeql_build_plan_path")"
      mkdir -p "$(dirname "$summary_path")" "$(dirname "$events_path")" "$(dirname "$sarif_path")"
      cp "$build_plan_path" "$state_dir/replayed-build-plan.json"
      printf '%s
' '{"ts":"2026-05-01T00:00:01Z","stage":"database_create","event":"completed","message":"CodeQL database created"}' > "$events_path"
      printf '%s
' '{"version":"2.1.0","runs":[{"tool":{"driver":{"name":"CodeQL","rules":[]}},"results":[]}]}' > "$sarif_path"
      printf '%s
' '{"status":"scan_completed","engine":"codeql"}' > "$summary_path"
    fi
    ;;
  wait)
    printf '0
'
    ;;
  logs)
    if [ "${1:-}" = "--stdout" ]; then
      printf '%s
' "${FAKE_TASK_STDOUT:-codeql fake stdout}"
    else
      printf '%s
' "${FAKE_TASK_STDERR:-codeql fake stderr}"
    fi
    ;;
  rm)
    ;;
  *)
    ;;
esac
"#;
    fs::write(&script_path, script).expect("write fake codeql docker");
    let mut permissions = fs::metadata(&script_path).unwrap().permissions();
    permissions.set_mode(0o755);
    fs::set_permissions(&script_path, permissions).unwrap();
    script_path
}

fn fake_codeql_language_task_docker(temp_dir: &TempDir) -> PathBuf {
    let script_path = temp_dir.path().join("fake-codeql-language-task-docker.sh");
    let script = r#"#!/bin/sh
set -eu
log_file="${FAKE_DOCKER_LOG:?}"
state_dir="${FAKE_TASK_DOCKER_STATE_DIR:?}"
cmd="${1:-}"
shift || true
printf '%s|%s
' "$cmd" "$*" >> "$log_file"
case "$cmd" in
  create)
    summary_path=""
    events_path=""
    sarif_path=""
    image_seen=""
    prev=""
    language=""
    build_plan_seen="false"
    for arg in "$@"; do
      case "$prev" in
        summary) summary_path="$arg"; prev="" ;;
        events) events_path="$arg"; prev="" ;;
        sarif) sarif_path="$arg"; prev="" ;;
        language) language="$arg"; prev="" ;;
        plan) build_plan_seen="true"; prev="" ;;
        *)
          case "$arg" in
            --summary) prev="summary" ;;
            --events) prev="events" ;;
            --sarif) prev="sarif" ;;
            --language) prev="language" ;;
            --build-plan) prev="plan" ;;
            Argus/codeql-runner:test) image_seen="$arg" ;;
          esac
          ;;
      esac
    done
    printf '%s' "$summary_path" > "$state_dir/codeql_summary_path"
    printf '%s' "$events_path" > "$state_dir/codeql_events_path"
    printf '%s' "$sarif_path" > "$state_dir/sarif_path"
    printf '%s' "$language" > "$state_dir/codeql_language"
    printf '%s' "$build_plan_seen" > "$state_dir/build_plan_seen"
    printf 'codeql-container
'
    ;;
  start)
    summary_path="$(cat "$state_dir/codeql_summary_path")"
    events_path="$(cat "$state_dir/codeql_events_path")"
    sarif_path="$(cat "$state_dir/sarif_path")"
    mkdir -p "$(dirname "$summary_path")" "$(dirname "$events_path")" "$(dirname "$sarif_path")"
    printf '%s
' '{"ts":"2026-05-01T00:00:01Z","stage":"database_create","event":"completed","message":"CodeQL database created"}' > "$events_path"
    printf '%s
' '{"version":"2.1.0","runs":[{"tool":{"driver":{"name":"CodeQL","rules":[]}},"results":[]}]}' > "$sarif_path"
    printf '%s
' '{"status":"scan_completed","engine":"codeql"}' > "$summary_path"
    ;;
  wait)
    printf '0
'
    ;;
  logs)
    if [ "${1:-}" = "--stdout" ]; then
      printf '%s
' "${FAKE_TASK_STDOUT:-codeql fake stdout}"
    else
      printf '%s
' "${FAKE_TASK_STDERR:-codeql fake stderr}"
    fi
    ;;
  rm)
    ;;
  *)
    ;;
esac
"#;
    fs::write(&script_path, script).expect("write fake language codeql docker");
    let mut permissions = fs::metadata(&script_path).unwrap().permissions();
    permissions.set_mode(0o755);
    fs::set_permissions(&script_path, permissions).unwrap();
    script_path
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

#[tokio::test]
async fn codeql_compile_sandbox_persists_plan_to_postgres_when_configured() {
    let Some(config) = require_db_test_config("codeql-cpp-compile-sandbox-db") else {
        return;
    };
    let _env_lock = ENV_LOCK.lock().await;
    let temp_dir = tempfile::tempdir().expect("temp dir");
    let fake_log = temp_dir.path().join("docker.log");
    let fake_docker = fake_codeql_compile_task_docker(&temp_dir);
    let fake_state_dir = temp_dir.path().join("docker-state");
    let scan_root = temp_dir.path().join("scan-root");
    fs::create_dir_all(&fake_state_dir).expect("mkdir state dir");
    fs::create_dir_all(&scan_root).expect("mkdir scan root");

    let _docker_bin = EnvVarGuard::set("Argus_DOCKER_BIN", fake_docker.to_str().unwrap());
    let _docker_log = EnvVarGuard::set("FAKE_DOCKER_LOG", fake_log.to_str().unwrap());
    let _docker_state = EnvVarGuard::set(
        "FAKE_TASK_DOCKER_STATE_DIR",
        fake_state_dir.to_str().unwrap(),
    );
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
    assert_eq!(db_record.commands, vec!["make -j2"]);
    assert_eq!(db_record.evidence_json["role"], "evidence_only");

    let replayed = fs::read_to_string(fake_state_dir.join("replayed-build-plan.json"))
        .expect("CodeQL runner should receive DB-backed replay build plan");
    assert!(replayed.contains("make -j2"), "{replayed}");
    assert!(replayed.contains("evidence_only"), "{replayed}");
}

#[tokio::test]
async fn codeql_task_runs_cpp_compile_sandbox_before_replay_and_persists_db_truth() {
    let _env_lock = ENV_LOCK.lock().await;
    let temp_dir = tempfile::tempdir().expect("temp dir");
    let fake_log = temp_dir.path().join("docker.log");
    let fake_docker = fake_codeql_compile_task_docker(&temp_dir);
    let fake_state_dir = temp_dir.path().join("docker-state");
    let scan_root = temp_dir.path().join("scan-root");
    fs::create_dir_all(&fake_state_dir).expect("mkdir state dir");
    fs::create_dir_all(&scan_root).expect("mkdir scan root");

    let _docker_bin = EnvVarGuard::set("Argus_DOCKER_BIN", fake_docker.to_str().unwrap());
    let _docker_log = EnvVarGuard::set("FAKE_DOCKER_LOG", fake_log.to_str().unwrap());
    let _docker_state = EnvVarGuard::set(
        "FAKE_TASK_DOCKER_STATE_DIR",
        fake_state_dir.to_str().unwrap(),
    );
    let _workspace_root = EnvVarGuard::set("SCAN_WORKSPACE_ROOT", scan_root.to_str().unwrap());
    let _workspace_volume = EnvVarGuard::set("SCAN_WORKSPACE_VOLUME", "Argus_scan_workspace");

    let state = AppState::from_config(
        optional_db_test_config("codeql-cpp-compile-sandbox")
            .unwrap_or_else(|| isolated_test_config("codeql-cpp-compile-sandbox")),
    )
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
    assert_eq!(persisted.commands, vec!["make -j2"]);
    assert_eq!(persisted.evidence_json["role"], "evidence_only");

    let replayed = fs::read_to_string(fake_state_dir.join("replayed-build-plan.json"))
        .expect("CodeQL runner should receive replay build plan");
    assert!(replayed.contains("make -j2"), "{replayed}");
    assert!(replayed.contains("evidence_only"), "{replayed}");

    let logged = fs::read_to_string(&fake_log).expect("docker log");
    let create_count = logged
        .lines()
        .filter(|line| line.starts_with("create|"))
        .count();
    assert_eq!(
        create_count, 2,
        "compile sandbox then CodeQL runner expected\n{logged}"
    );
    assert!(logged.contains("codeql-compile-sandbox"), "{logged}");
    assert!(logged.contains("codeql-scan"), "{logged}");
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
        let fake_log = temp_dir.path().join("docker.log");
        let fake_docker = fake_codeql_language_task_docker(&temp_dir);
        let fake_state_dir = temp_dir.path().join("docker-state");
        let scan_root = temp_dir.path().join("scan-root");
        fs::create_dir_all(&fake_state_dir).expect("mkdir state dir");
        fs::create_dir_all(&scan_root).expect("mkdir scan root");

        let _docker_bin = EnvVarGuard::set("Argus_DOCKER_BIN", fake_docker.to_str().unwrap());
        let _docker_log = EnvVarGuard::set("FAKE_DOCKER_LOG", fake_log.to_str().unwrap());
        let _docker_state = EnvVarGuard::set(
            "FAKE_TASK_DOCKER_STATE_DIR",
            fake_state_dir.to_str().unwrap(),
        );
        let _workspace_root = EnvVarGuard::set("SCAN_WORKSPACE_ROOT", scan_root.to_str().unwrap());
        let _workspace_volume = EnvVarGuard::set("SCAN_WORKSPACE_VOLUME", "Argus_scan_workspace");

        let state =
            AppState::from_config(isolated_test_config(&format!("codeql-language-{language}")))
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
        assert_eq!(
            fs::read_to_string(fake_state_dir.join("codeql_language")).unwrap(),
            language
        );
        assert_eq!(
            fs::read_to_string(fake_state_dir.join("build_plan_seen")).unwrap(),
            "false"
        );

        let logged = fs::read_to_string(&fake_log).expect("docker log");
        let create_count = logged
            .lines()
            .filter(|line| line.starts_with("create|"))
            .count();
        assert_eq!(create_count, 1, "{language}: {logged}");
        assert!(logged.contains("codeql-scan"), "{language}: {logged}");
        assert!(
            !logged.contains("codeql-compile-sandbox"),
            "{language}: {logged}"
        );
    }
}
