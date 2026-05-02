use std::{
    collections::{BTreeSet, HashMap, HashSet},
    io::Write,
    path::Path,
    sync::{LazyLock, Mutex},
};

use anyhow::{bail, Context, Result};
use base64::{engine::general_purpose::STANDARD, Engine as _};
use flate2::{write::GzEncoder, Compression};
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use sha2::{Digest, Sha256};
use tar::Builder;

use crate::{
    runtime::cubesandbox::{
        client::{
            CubeSandboxClient, CubeSandboxClientConfig, CubeSandboxSandbox, EnvdProcessOutput,
        },
        config::CubeSandboxConfig,
        helper::{run_helper_command, should_run_local_lifecycle, CubeSandboxHelperCommand},
    },
    scan::codeql,
    state::AppState,
};

#[derive(Clone, Debug)]
pub struct CubeSandboxCodeqlInput<'a> {
    pub task_id: &'a str,
    pub workspace_dir: &'a Path,
    pub source_dir: &'a Path,
    pub query_dir: &'a Path,
    pub language: &'a str,
    pub build_mode: Option<&'a str>,
    pub build_plan: Option<Value>,
    pub exploration_rounds: Vec<Value>,
    pub threads: usize,
    pub ram_mb: u64,
    pub allow_network: bool,
}

#[derive(Clone)]
struct ActiveCodeqlSandbox {
    client: CubeSandboxClient,
    sandbox_id: String,
}

static ACTIVE_CODEQL_SANDBOXES: LazyLock<Mutex<HashMap<String, ActiveCodeqlSandbox>>> =
    LazyLock::new(|| Mutex::new(HashMap::new()));
static CANCELLED_CODEQL_TASKS: LazyLock<Mutex<HashSet<String>>> =
    LazyLock::new(|| Mutex::new(HashSet::new()));

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct CubeSandboxCodeqlOutput {
    pub sarif_text: String,
    pub events_text: String,
    pub summary_json: Value,
    pub build_plan_json: Option<Value>,
    pub sandbox_id: String,
    pub cleanup_completed: bool,
}

#[derive(Serialize)]
struct CubeSandboxCodeqlRequest {
    archive_b64: String,
    language: String,
    build_mode: Option<String>,
    build_plan: Option<Value>,
    exploration_rounds: Vec<Value>,
    threads: usize,
    ram_mb: u64,
    allow_network: bool,
}

#[derive(Deserialize)]
struct CubeSandboxCodeqlEnvelope {
    sarif_b64: String,
    events_b64: String,
    summary: Value,
    #[serde(default)]
    build_plan: Option<Value>,
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct CodeqlExplorationCommandOutput {
    pub command: String,
    pub stdout: String,
    pub stderr: String,
    pub exit_code: i32,
    pub failure_category: String,
    pub dependency_installation: Value,
}

#[derive(Deserialize)]
struct CodeqlExplorationCommandEnvelope {
    command: String,
    #[serde(default)]
    stdout: String,
    #[serde(default)]
    stderr: String,
    exit_code: i32,
    #[serde(default)]
    failure_category: String,
    #[serde(default)]
    dependency_installation: Value,
}

pub struct CodeqlSandboxSession {
    task_id: String,
    client: CubeSandboxClient,
    sandbox: CubeSandboxSandbox,
}

impl CodeqlSandboxSession {
    pub async fn start(state: &AppState, task_id: &str) -> Result<Self> {
        let config = CubeSandboxConfig::load_runtime(state).await?;
        config.validate_for_execution()?;
        if take_cancel_request(task_id) {
            bail!("CodeQL CubeSandbox scan cancelled before sandbox creation for task {task_id}");
        }
        let client = prepare_client(&config).await?;
        let sandbox = client.create_sandbox().await?;
        register_active_sandbox(
            task_id,
            ActiveCodeqlSandbox {
                client: client.clone(),
                sandbox_id: sandbox.sandbox_id.clone(),
            },
        );
        if take_cancel_request(task_id) {
            let _ = client.delete_sandbox(&sandbox.sandbox_id).await;
            unregister_active_sandbox(task_id, &sandbox.sandbox_id);
            bail!("CodeQL CubeSandbox scan cancelled before sandbox connect for task {task_id}");
        }
        client.connect_sandbox(&sandbox.sandbox_id).await?;
        Ok(Self {
            task_id: task_id.to_string(),
            client,
            sandbox,
        })
    }

    pub fn sandbox_id(&self) -> &str {
        &self.sandbox.sandbox_id
    }

    pub async fn stage_workspace(
        &self,
        workspace_dir: &Path,
        source_dir: &Path,
        query_dir: &Path,
    ) -> Result<()> {
        let archive_b64 = create_workspace_archive_b64(workspace_dir, source_dir, query_dir)?;
        let script = build_workspace_setup_script(&archive_b64)?;
        let output = self.client.run_command(&self.sandbox, &script).await?;
        ensure_successful_process("CubeSandbox CodeQL workspace setup", output)?;
        Ok(())
    }

    pub async fn run_exploration_command(
        &self,
        command: &str,
    ) -> Result<CodeqlExplorationCommandOutput> {
        let script = build_exploration_command_script(command)?;
        let output = self.client.run_command(&self.sandbox, &script).await?;
        if output.exit_code.unwrap_or(0) != 0 {
            bail!(
                "CubeSandbox CodeQL exploration wrapper failed exit={:?} stdout={} stderr={}",
                output.exit_code,
                codeql::redact_sensitive_text(&output.stdout),
                codeql::redact_sensitive_text(&output.stderr)
            );
        }
        parse_exploration_command_output(output)
    }

    pub async fn run_scan(
        &self,
        input: CubeSandboxCodeqlInput<'_>,
    ) -> Result<CubeSandboxCodeqlOutput> {
        if take_cancel_request(input.task_id) {
            bail!(
                "CodeQL CubeSandbox scan cancelled before CodeQL capture for task {}",
                input.task_id
            );
        }
        let payload = CubeSandboxCodeqlRequest {
            archive_b64: create_workspace_archive_b64(
                input.workspace_dir,
                input.source_dir,
                input.query_dir,
            )?,
            language: codeql::normalize_language(input.language),
            build_mode: input.build_mode.map(str::to_string),
            build_plan: input.build_plan,
            exploration_rounds: input.exploration_rounds,
            threads: input.threads,
            ram_mb: input.ram_mb,
            allow_network: input.allow_network,
        };
        let script = build_codeql_runner_script(&payload)?;
        let output = self.client.run_command(&self.sandbox, &script).await?;
        let mut result = parse_codeql_output(output)?;
        result.sandbox_id = self.sandbox.sandbox_id.clone();
        Ok(result)
    }

    pub async fn cleanup(self) -> Result<()> {
        unregister_active_sandbox(&self.task_id, &self.sandbox.sandbox_id);
        self.client.delete_sandbox(&self.sandbox.sandbox_id).await
    }
}

pub async fn run_codeql_scan(
    state: &AppState,
    input: CubeSandboxCodeqlInput<'_>,
) -> Result<CubeSandboxCodeqlOutput> {
    let session = CodeqlSandboxSession::start(state, input.task_id).await?;
    let mut result = session.run_scan(input).await?;
    let sandbox_id = result.sandbox_id.clone();
    if let Err(error) = session.cleanup().await {
        bail!("CubeSandbox cleanup failed after CodeQL scan: {error}");
    }
    result.sandbox_id = sandbox_id;
    result.cleanup_completed = true;
    Ok(result)
}

pub async fn cancel_codeql_scan(task_id: &str) -> Result<bool> {
    CANCELLED_CODEQL_TASKS
        .lock()
        .expect("cancel set lock")
        .insert(task_id.to_string());
    let active = ACTIVE_CODEQL_SANDBOXES
        .lock()
        .expect("active sandbox lock")
        .remove(task_id);
    let Some(active) = active else {
        return Ok(false);
    };
    active.client.delete_sandbox(&active.sandbox_id).await?;
    Ok(true)
}

fn register_active_sandbox(task_id: &str, active: ActiveCodeqlSandbox) {
    ACTIVE_CODEQL_SANDBOXES
        .lock()
        .expect("active sandbox lock")
        .insert(task_id.to_string(), active);
}

fn unregister_active_sandbox(task_id: &str, sandbox_id: &str) {
    let mut active = ACTIVE_CODEQL_SANDBOXES.lock().expect("active sandbox lock");
    if active
        .get(task_id)
        .is_some_and(|current| current.sandbox_id == sandbox_id)
    {
        active.remove(task_id);
    }
}

fn take_cancel_request(task_id: &str) -> bool {
    CANCELLED_CODEQL_TASKS
        .lock()
        .expect("cancel set lock")
        .remove(task_id)
}

async fn prepare_client(config: &CubeSandboxConfig) -> Result<CubeSandboxClient> {
    if should_run_local_lifecycle(config)? && config.auto_install {
        let output = run_helper_command(config, CubeSandboxHelperCommand::Install).await?;
        ensure_helper_success(CubeSandboxHelperCommand::Install, &output)?;
    }
    if should_run_local_lifecycle(config)? {
        let status_output = run_helper_command(config, CubeSandboxHelperCommand::Status).await?;
        if !status_output.success && config.auto_start {
            let start_output =
                run_helper_command(config, CubeSandboxHelperCommand::RunVmBackground).await?;
            ensure_helper_success(CubeSandboxHelperCommand::RunVmBackground, &start_output)?;
        } else {
            ensure_helper_success(CubeSandboxHelperCommand::Status, &status_output)?;
        }
    }
    let client = CubeSandboxClient::new(CubeSandboxClientConfig {
        api_base_url: config.api_base_url.clone(),
        data_plane_base_url: config.data_plane_base_url.clone(),
        template_id: config.template_id.clone(),
        execution_timeout_seconds: config.execution_timeout_seconds,
        cleanup_timeout_seconds: config.sandbox_cleanup_timeout_seconds,
        stdout_limit_bytes: config.stdout_limit_bytes,
        stderr_limit_bytes: config.stderr_limit_bytes,
    })?;
    client.health().await?;
    Ok(client)
}

fn ensure_helper_success(
    command: CubeSandboxHelperCommand,
    output: &crate::runtime::cubesandbox::helper::CubeSandboxHelperOutput,
) -> Result<()> {
    if output.success {
        return Ok(());
    }
    bail!(
        "CubeSandbox helper command failed: {:?} exit={:?}",
        command,
        output.exit_code
    )
}

fn create_workspace_archive_b64(
    workspace_dir: &Path,
    source_dir: &Path,
    query_dir: &Path,
) -> Result<String> {
    let mut archive = Vec::new();
    {
        let encoder = GzEncoder::new(&mut archive, Compression::default());
        let mut builder = Builder::new(encoder);
        append_dir(&mut builder, source_dir, "source")?;
        append_dir(&mut builder, query_dir, "queries")?;
        append_optional_file(
            &mut builder,
            workspace_dir.join("build-plan/build-plan.json"),
            "build-plan/build-plan.json",
        )?;
        builder.finish()?;
        let encoder = builder.into_inner()?;
        encoder.finish()?;
    }
    Ok(STANDARD.encode(archive))
}

fn append_dir<W: Write>(builder: &mut Builder<W>, dir: &Path, archive_prefix: &str) -> Result<()> {
    if !dir.exists() {
        return Ok(());
    }
    let mut files = Vec::new();
    collect_files(dir, &mut files)?;
    files.sort();
    for path in files {
        let relative = path.strip_prefix(dir)?;
        let archive_path = Path::new(archive_prefix).join(relative);
        builder
            .append_path_with_name(&path, &archive_path)
            .with_context(|| format!("failed to stage {}", path.display()))?;
    }
    Ok(())
}

fn append_optional_file<W: Write>(
    builder: &mut Builder<W>,
    path: impl AsRef<Path>,
    archive_path: &str,
) -> Result<()> {
    let path = path.as_ref();
    if !path.exists() {
        return Ok(());
    }
    builder.append_path_with_name(path, archive_path)?;
    Ok(())
}

fn collect_files(dir: &Path, output: &mut Vec<std::path::PathBuf>) -> Result<()> {
    for entry in std::fs::read_dir(dir)? {
        let entry = entry?;
        let path = entry.path();
        let file_type = entry.file_type()?;
        if file_type.is_dir() {
            collect_files(&path, output)?;
        } else if file_type.is_file() {
            output.push(path);
        }
    }
    Ok(())
}

fn build_codeql_runner_script(payload: &CubeSandboxCodeqlRequest) -> Result<String> {
    let payload_b64 = STANDARD.encode(serde_json::to_vec(payload)?);
    Ok(format!(
        "python3 - {payload_b64} <<'PY'\n{CUBESANDBOX_CODEQL_PY}\nPY"
    ))
}

fn build_workspace_setup_script(archive_b64: &str) -> Result<String> {
    let payload_b64 = STANDARD.encode(serde_json::to_vec(&json!({
        "archive_b64": archive_b64,
    }))?);
    Ok(format!(
        "python3 - {payload_b64} <<'PY'\n{CUBESANDBOX_CODEQL_SETUP_PY}\nPY"
    ))
}

fn build_exploration_command_script(command: &str) -> Result<String> {
    let payload_b64 = STANDARD.encode(serde_json::to_vec(&json!({
        "command": command,
    }))?);
    Ok(format!(
        "python3 - {payload_b64} <<'PY'\n{CUBESANDBOX_CODEQL_EXPLORE_PY}\nPY"
    ))
}

fn ensure_successful_process(label: &str, output: EnvdProcessOutput) -> Result<()> {
    if output.exit_code.unwrap_or(0) == 0 {
        return Ok(());
    }
    bail!(
        "{label} failed exit={:?} stdout={} stderr={}",
        output.exit_code,
        codeql::redact_sensitive_text(&output.stdout),
        codeql::redact_sensitive_text(&output.stderr)
    )
}

fn parse_codeql_output(output: EnvdProcessOutput) -> Result<CubeSandboxCodeqlOutput> {
    if output.exit_code.unwrap_or(0) != 0 {
        bail!(
            "CubeSandbox CodeQL process failed exit={:?} stdout={} stderr={}",
            output.exit_code,
            codeql::redact_sensitive_text(&output.stdout),
            codeql::redact_sensitive_text(&output.stderr)
        );
    }
    let envelope = output
        .stdout
        .lines()
        .rev()
        .find_map(|line| line.strip_prefix("ARGUS_CODEQL_RESULT="))
        .ok_or_else(|| anyhow::anyhow!("CubeSandbox CodeQL output missing result envelope"))?;
    let parsed: CubeSandboxCodeqlEnvelope = serde_json::from_str(envelope)?;
    Ok(CubeSandboxCodeqlOutput {
        sarif_text: decode_text(&parsed.sarif_b64, "sarif")?,
        events_text: decode_text(&parsed.events_b64, "events")?,
        summary_json: parsed.summary,
        build_plan_json: parsed.build_plan,
        sandbox_id: String::new(),
        cleanup_completed: false,
    })
}

fn parse_exploration_command_output(
    output: EnvdProcessOutput,
) -> Result<CodeqlExplorationCommandOutput> {
    let envelope = output
        .stdout
        .lines()
        .rev()
        .find_map(|line| line.strip_prefix("ARGUS_CODEQL_EXPLORATION_RESULT="))
        .ok_or_else(|| anyhow::anyhow!("CubeSandbox CodeQL exploration output missing result"))?;
    let parsed: CodeqlExplorationCommandEnvelope = serde_json::from_str(envelope)?;
    Ok(CodeqlExplorationCommandOutput {
        command: parsed.command,
        stdout: codeql::redact_sensitive_text(&parsed.stdout),
        stderr: codeql::redact_sensitive_text(&parsed.stderr),
        exit_code: parsed.exit_code,
        failure_category: if parsed.failure_category.trim().is_empty() {
            if parsed.exit_code == 0 {
                "none".to_string()
            } else {
                "command_failed".to_string()
            }
        } else {
            parsed.failure_category
        },
        dependency_installation: parsed.dependency_installation,
    })
}

fn decode_text(value: &str, label: &str) -> Result<String> {
    let bytes = STANDARD
        .decode(value)
        .with_context(|| format!("invalid {label} base64"))?;
    String::from_utf8(bytes).with_context(|| format!("invalid {label} utf8"))
}

pub fn capture_events_to_jsonl(events: &str) -> String {
    events
        .lines()
        .filter(|line| !line.trim().is_empty())
        .filter_map(|line| serde_json::from_str::<Value>(line).ok())
        .map(|event| serde_json::to_string(&event).unwrap_or_else(|_| "{}".to_string()))
        .collect::<Vec<_>>()
        .join("\n")
}

pub fn summarize_captured_files(events_text: &str, known_paths: &BTreeSet<String>) -> Value {
    let captured = known_paths
        .iter()
        .filter(|path| {
            let lower = path.to_ascii_lowercase();
            lower.ends_with(".c")
                || lower.ends_with(".cc")
                || lower.ends_with(".cpp")
                || lower.ends_with(".cxx")
                || lower.ends_with(".h")
                || lower.ends_with(".hpp")
        })
        .take(50)
        .cloned()
        .collect::<Vec<_>>();
    json!({
        "database_create": "completed",
        "extractor": "cpp",
        "events_jsonl_sha256": sha256_text(events_text),
        "captured_files": captured,
    })
}

fn sha256_text(value: &str) -> String {
    let mut hasher = Sha256::new();
    hasher.update(value.as_bytes());
    format!("sha256:{:x}", hasher.finalize())
}

const CUBESANDBOX_CODEQL_PY: &str = r#"
import base64
import json
import os
import pathlib
import shlex
import subprocess
import sys
import tarfile
import time

payload = json.loads(base64.b64decode(sys.argv[1]).decode("utf-8"))
work = pathlib.Path("/tmp/argus-codeql-work")
if work.exists():
    subprocess.run(["rm", "-rf", str(work)], check=True)
work.mkdir(parents=True)
archive_path = work / "workspace.tar.gz"
archive_path.write_bytes(base64.b64decode(payload["archive_b64"]))
with tarfile.open(archive_path, "r:gz") as bundle:
    root = work.resolve()
    for member in bundle.getmembers():
        target = (work / member.name).resolve()
        if target != root and root not in target.parents:
            raise SystemExit(f"archive member escapes workspace: {member.name}")
    bundle.extractall(work)

source = work / "source"
queries = work / "queries"
database = work / "codeql-db"
sarif = work / "results.sarif"
summary = {"status": "running", "engine": "codeql", "executor": "cubesandbox"}
events = []

def event(stage, name, message, **extra):
    payload = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "engine": "codeql",
        "executor": "cubesandbox",
        "stage": stage,
        "event": name,
        "message": message,
    }
    payload.update(extra)
    events.append(payload)

def run(cmd, cwd=None):
    event("sandbox_command", "started", " ".join(shlex.quote(str(part)) for part in cmd), command=cmd, cwd=str(cwd or work))
    result = subprocess.run(cmd, cwd=cwd, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=900)
    event(
        "sandbox_command",
        "completed" if result.returncode == 0 else "failed",
        "command exited",
        command=cmd,
        exit_code=result.returncode,
        stdout=result.stdout[-8192:],
        stderr=result.stderr[-8192:],
    )
    if result.returncode != 0:
        raise subprocess.CalledProcessError(result.returncode, cmd, result.stdout, result.stderr)
    return result

language = payload.get("language") or "cpp"
build_mode = payload.get("build_mode")
build_plan = payload.get("build_plan")
exploration_rounds = payload.get("exploration_rounds") or []
threads = str(payload.get("threads") or 0)
ram = str(payload.get("ram_mb") or 6144)

if not source.exists() or not queries.exists():
    raise SystemExit("source and queries must be staged before CodeQL scan")
codeql_path = __import__("shutil").which("codeql")
if not codeql_path:
    event("failed", "codeql_unavailable", "CodeQL CLI is not installed in CubeSandbox template")
    raise SystemExit("CodeQL CLI is not installed in CubeSandbox template")

for index, round_payload in enumerate(exploration_rounds, start=1):
    commands = round_payload.get("commands") or []
    reasoning_summary = round_payload.get("reasoning_summary") or "candidate build command selected"
    event("llm_round", "started", reasoning_summary, round=index, reasoning_summary=reasoning_summary, commands=commands)
    for command in commands:
        result = subprocess.run(command, cwd=source, shell=True, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=900)
        lower_output = (result.stdout + "\n" + result.stderr).lower()
        dependency_detected = any(token in lower_output for token in ["not found", "no such file", "missing", "dependency", "package"])
        event(
            "sandbox_command",
            "completed" if result.returncode == 0 else "failed",
            "exploration command exited",
            round=index,
            command=command,
            exit_code=result.returncode,
            stdout=result.stdout[-8192:],
            stderr=result.stderr[-8192:],
            failure_category="none" if result.returncode == 0 else "compile_error",
            dependency_installation={"detected": dependency_detected},
        )
    event("llm_round", "completed", "exploration round completed", round=index)

event("database_create", "started", f"creating CodeQL database in CubeSandbox language={language}")
create_cmd = ["codeql", "database", "create", str(database), f"--language={language}", f"--source-root={source}", "--overwrite"]
if build_plan:
    mode = build_plan.get("build_mode") or "none"
    commands = build_plan.get("commands") or []
    working_directory = build_plan.get("working_directory") or "."
    if mode == "manual":
        if not commands:
            raise SystemExit("manual build plan requires commands")
        if working_directory != ".":
            raise SystemExit("non-root working_directory is not supported in CubeSandbox CodeQL scan")
        if len(commands) == 1:
            create_cmd.extend(["--command", commands[0]])
            run(create_cmd, cwd=source)
        else:
            init_cmd = ["codeql", "database", "init", str(database), f"--language={language}", f"--source-root={source}", "--overwrite"]
            run(init_cmd, cwd=source)
            for index, command in enumerate(commands, start=1):
                event("database_trace_command", "started", f"tracing build step {index}", command=command, step=index)
                run(["codeql", "database", "trace-command", str(database), "--working-dir", str(source), "--command", command], cwd=source)
                event("database_trace_command", "completed", f"traced build step {index}", command=command, step=index)
            run(["codeql", "database", "finalize", str(database)], cwd=source)
    elif mode == "autobuild":
        create_cmd.append("--build-mode=autobuild")
        run(create_cmd, cwd=source)
    else:
        create_cmd.append("--build-mode=none")
        run(create_cmd, cwd=source)
elif build_mode == "autobuild":
    create_cmd.append("--build-mode=autobuild")
    run(create_cmd, cwd=source)
else:
    create_cmd.append("--build-mode=none")
    run(create_cmd, cwd=source)
event("database_create", "completed", "CodeQL database created in CubeSandbox")

event("database_analyze", "started", "running CodeQL database analyze in CubeSandbox")
run(["codeql", "database", "analyze", str(database), str(queries), "--format=sarifv2.1.0", "--output", str(sarif), "--threads", threads, "--ram", ram])
event("database_analyze", "completed", "CodeQL SARIF generated in CubeSandbox")
summary = {"status": "scan_completed", "engine": "codeql", "executor": "cubesandbox"}

events_text = "\n".join(json.dumps(item, separators=(",", ":")) for item in events) + "\n"
result = {
    "sarif_b64": base64.b64encode(sarif.read_bytes()).decode("ascii"),
    "events_b64": base64.b64encode(events_text.encode("utf-8")).decode("ascii"),
    "summary": summary,
    "build_plan": build_plan,
}
print("ARGUS_CODEQL_RESULT=" + json.dumps(result, separators=(",", ":")))
"#;

const CUBESANDBOX_CODEQL_SETUP_PY: &str = r#"
import base64
import json
import pathlib
import subprocess
import sys
import tarfile

payload = json.loads(base64.b64decode(sys.argv[1]).decode("utf-8"))
work = pathlib.Path("/tmp/argus-codeql-work")
if work.exists():
    subprocess.run(["rm", "-rf", str(work)], check=True)
work.mkdir(parents=True)
archive_path = work / "workspace.tar.gz"
archive_path.write_bytes(base64.b64decode(payload["archive_b64"]))
with tarfile.open(archive_path, "r:gz") as bundle:
    root = work.resolve()
    for member in bundle.getmembers():
        target = (work / member.name).resolve()
        if target != root and root not in target.parents:
            raise SystemExit(f"archive member escapes workspace: {member.name}")
    bundle.extractall(work)
print("ARGUS_CODEQL_SETUP_RESULT=" + json.dumps({"status": "ok"}, separators=(",", ":")))
"#;

const CUBESANDBOX_CODEQL_EXPLORE_PY: &str = r#"
import base64
import json
import pathlib
import subprocess
import sys

payload = json.loads(base64.b64decode(sys.argv[1]).decode("utf-8"))
command = payload["command"]
source = pathlib.Path("/tmp/argus-codeql-work/source")
if not source.exists():
    raise SystemExit("CodeQL exploration workspace has not been staged")
try:
    result = subprocess.run(command, cwd=source, shell=True, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=900)
    stdout = result.stdout[-8192:]
    stderr = result.stderr[-8192:]
    exit_code = result.returncode
except subprocess.TimeoutExpired as error:
    stdout = (error.stdout or "")[-8192:] if isinstance(error.stdout, str) else ""
    stderr = (error.stderr or "")[-8192:] if isinstance(error.stderr, str) else "command timed out"
    exit_code = 124
lower_output = (stdout + "\n" + stderr).lower()
dependency_detected = any(token in lower_output for token in ["not found", "no such file", "missing", "dependency", "package"])
payload = {
    "command": command,
    "stdout": stdout,
    "stderr": stderr,
    "exit_code": exit_code,
    "failure_category": "none" if exit_code == 0 else ("timeout" if exit_code == 124 else "compile_error"),
    "dependency_installation": {"detected": dependency_detected},
}
print("ARGUS_CODEQL_EXPLORATION_RESULT=" + json.dumps(payload, separators=(",", ":")))
"#;

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn codeql_runner_script_passes_payload_as_python_argument() {
        let script = build_codeql_runner_script(&CubeSandboxCodeqlRequest {
            archive_b64: "YXJjaGl2ZQ==".to_string(),
            language: "cpp".to_string(),
            build_mode: None,
            build_plan: None,
            exploration_rounds: Vec::new(),
            threads: 0,
            ram_mb: 1024,
            allow_network: false,
        })
        .expect("script should build");

        assert!(script.starts_with("python3 - "));
        assert!(script.contains(" <<'PY'\n"));
        assert!(script.ends_with("\nPY"));
    }

    #[test]
    fn codeql_runner_script_traces_multi_step_manual_plans_and_round_events() {
        let script = build_codeql_runner_script(&CubeSandboxCodeqlRequest {
            archive_b64: "YXJjaGl2ZQ==".to_string(),
            language: "cpp".to_string(),
            build_mode: None,
            build_plan: Some(json!({
                "build_mode": "manual",
                "commands": ["cmake -S . -B build", "cmake --build build"],
                "working_directory": ".",
            })),
            exploration_rounds: vec![json!({
                "reasoning_summary": "first candidate failed and becomes context",
                "commands": ["false"],
            })],
            threads: 0,
            ram_mb: 1024,
            allow_network: false,
        })
        .expect("script should build");

        assert!(script.contains("exploration_rounds"));
        assert!(script.contains("\"llm_round\""));
        assert!(script.contains("database\", \"init\""));
        assert!(script.contains("database\", \"trace-command\""));
        assert!(script.contains("database\", \"finalize\""));
    }

    #[tokio::test]
    async fn cancel_registry_records_pre_sandbox_cancellation() {
        assert!(!cancel_codeql_scan("codeql-cancel-before-sandbox")
            .await
            .expect("cancel request should be recorded"));
        assert!(take_cancel_request("codeql-cancel-before-sandbox"));
        assert!(!take_cancel_request("codeql-cancel-before-sandbox"));
    }
}
