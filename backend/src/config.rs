use std::{env, net::SocketAddr, path::PathBuf, str::FromStr};

use anyhow::{Context, Result};

#[derive(Clone, Debug)]
pub struct AppConfig {
    pub bind_addr: SocketAddr,
    pub database_url: Option<String>,
    pub rust_database_url: Option<String>,
    pub python_database_url: Option<String>,
    pub zip_storage_path: PathBuf,
    pub startup_init_enabled: bool,
    pub startup_recovery_enabled: bool,
    pub runner_preflight_enabled: bool,
    pub runner_preflight_strict: bool,
    pub runner_preflight_timeout_seconds: u64,
    pub runner_preflight_max_concurrency: usize,
    pub secret_key: String,
    pub algorithm: String,
    pub access_token_expire_minutes: i64,
    pub llm_provider: String,
    pub llm_api_key: String,
    pub llm_model: String,
    pub llm_base_url: String,
    pub llm_timeout_seconds: i64,
    pub llm_temperature: f64,
    pub llm_max_tokens: i64,
    pub llm_first_token_timeout_seconds: i64,
    pub llm_stream_timeout_seconds: i64,
    pub agent_timeout_seconds: i64,
    pub sub_agent_timeout_seconds: i64,
    pub tool_timeout_seconds: i64,
    pub openai_api_key: String,
    pub gemini_api_key: String,
    pub claude_api_key: String,
    pub qwen_api_key: String,
    pub deepseek_api_key: String,
    pub zhipu_api_key: String,
    pub moonshot_api_key: String,
    pub baidu_api_key: String,
    pub minimax_api_key: String,
    pub doubao_api_key: String,
    pub ollama_base_url: String,
    pub max_analyze_files: i64,
    pub llm_concurrency: i64,
    pub llm_gap_ms: i64,
    pub scanner_opengrep_image: String,
    pub scanner_opengrep_a3s_box_image: String,
    pub scanner_codeql_image: String,
    pub codeql_threads: usize,
    pub codeql_ram_mb: u64,
    pub codeql_max_build_inference_rounds: u64,
    pub codeql_allow_network_during_build: bool,
    pub codeql_llm_allow_source_snippets: bool,
    pub opengrep_scan_timeout_seconds: u64,
    pub opengrep_scan_jobs: usize,
    pub opengrep_scan_jobs_explicit: bool,
    pub opengrep_scan_max_memory_mb: u64,
    pub opengrep_runner_memory_limit_mb: u64,
    pub opengrep_runner_cpu_limit: f64,
    pub opengrep_runner_cpu_limit_explicit: bool,
    pub opengrep_runner_pids_limit: u64,
    pub opengrep_runner_runtime: String,
    pub opengrep_runner_rootless_socket_required: bool,
    /// Source-directory size limit (MiB) above which the a3s-box opengrep
    /// runner skips localization (the copy of workspace source into the
    /// box-local tmpfs `/tmp/argus-a3s-opengrep-{box_name}`) and runs
    /// opengrep directly against the virtiofs-mounted host workspace.
    ///
    /// Without this gate, FFMPEG-scale projects (~86 MiB source) hit OOM in
    /// the 2 GiB box because the tmpfs copy contests with opengrep's
    /// `--max-memory 2048`. Set to `0` to fully disable localization.
    /// Env: `ARGUS_A3S_LOCALIZE_LIMIT_MB`, default 50 MiB.
    pub argus_a3s_localize_limit_mb: u64,

    // ── Standby pool config (Phase A.3) ──────────────────────────────────────
    /// Target standby count for OpengrepDedicated pool slots.
    /// Env: OPENGREP_STANDBY_POOL_SIZE, default 2.
    pub opengrep_standby_pool_size: usize,
    /// Kill switch: when true, OpengrepDedicated pool is fully bypassed.
    /// Env: OPENGREP_STANDBY_POOL_DISABLED, default false.
    pub opengrep_standby_pool_disabled: bool,
    /// Target standby count for CodeqlCpp pool slots.
    /// Env: CODEQL_STANDBY_POOL_SIZE, default 2.
    /// Read now; used in Phase B.
    pub codeql_standby_pool_size: usize,
    /// Kill switch for CodeqlCpp pool.
    /// Env: CODEQL_STANDBY_POOL_DISABLED, default false.
    /// Read now; used in Phase B.
    pub codeql_standby_pool_disabled: bool,
    /// Hard global cap on total standby sandboxes across all kinds.
    /// Env: ARGUS_MAX_TOTAL_STANDBY, default 8.
    /// TODO(A.3): derive default from host RAM via sysinfo (backend/src/config.rs).
    pub max_total_standby: usize,

    // ── a3s-box standby pool config (Phase C.3) ───────────────────────────────
    /// Target standby count for a3s-box OpengrepDedicated pool slots.
    /// Env: A3S_BOX_STANDBY_POOL_SIZE, default 2.
    /// Each slot is an image-cache warmup entry (Option C.β — no running VM).
    pub a3s_box_standby_pool_size: usize,
    /// Kill switch: when true, a3s-box standby pool is fully bypassed.
    /// Env: A3S_BOX_STANDBY_POOL_DISABLED, default false.
    pub a3s_box_standby_pool_disabled: bool,
    /// Maximum bytes captured from a3s-box subprocess stdout before truncation.
    /// Env: A3S_BOX_STDOUT_LIMIT_BYTES, default 1 MiB.
    ///
    /// Increase if you observe `[a3s-box output truncated]` warnings in logs
    /// and need full output for debugging.
    pub a3s_box_stdout_limit_bytes: usize,
    /// Maximum bytes captured from a3s-box subprocess stderr before truncation.
    /// Env: A3S_BOX_STDERR_LIMIT_BYTES, default 1 MiB.
    ///
    /// Increase if you observe `[a3s-box output truncated]` warnings in logs
    /// and need full output for debugging.
    pub a3s_box_stderr_limit_bytes: usize,
    /// Hard cap on the host-side read of the per-task `results.json` produced by opengrep.
    /// results.json can be large for projects with many findings; default 256 MiB is generous
    /// but bounded. Increase if you observe `[results.json exceeded limit]` errors and need
    /// full output.
    /// Env: OPENGREP_RESULTS_JSON_LIMIT_BYTES, default 256 MiB.
    pub opengrep_results_json_limit_bytes: usize,
}

impl AppConfig {
    pub fn from_env() -> Result<Self> {
        let bind_addr = env::var("BIND_ADDR").unwrap_or_else(|_| "0.0.0.0:8000".to_string());
        let bind_addr = SocketAddr::from_str(&bind_addr)
            .with_context(|| format!("invalid BIND_ADDR: {bind_addr}"))?;

        let database_env = optional_env("DATABASE_URL");
        let rust_database_url = optional_env("RUST_DATABASE_URL").or_else(|| database_env.clone());
        let python_database_url =
            optional_env("PYTHON_DATABASE_URL").or_else(|| database_env.clone());

        let opengrep_scan_jobs_env = optional_env("OPENGREP_SCAN_JOBS");
        let opengrep_runner_cpu_limit_env = optional_env("OPENGREP_RUNNER_CPU_LIMIT");

        Ok(Self {
            bind_addr,
            database_url: database_env.clone(),
            rust_database_url: rust_database_url.clone(),
            python_database_url,
            zip_storage_path: env_path("ZIP_STORAGE_PATH", "./uploads/zip_files"),
            startup_init_enabled: parse_bool_env("STARTUP_INIT_ENABLED", true),
            startup_recovery_enabled: parse_bool_env("STARTUP_RECOVERY_ENABLED", true),
            runner_preflight_enabled: parse_bool_env("RUNNER_PREFLIGHT_ENABLED", true),
            runner_preflight_strict: parse_bool_env("RUNNER_PREFLIGHT_STRICT", false),
            runner_preflight_timeout_seconds: parse_u64_env("RUNNER_PREFLIGHT_TIMEOUT_SECONDS", 30),
            runner_preflight_max_concurrency: parse_usize_env(
                "RUNNER_PREFLIGHT_MAX_CONCURRENCY",
                2,
            ),
            secret_key: env::var("SECRET_KEY")
                .unwrap_or_else(|_| "changethis_in_production_to_a_long_random_string".to_string()),
            algorithm: env::var("ALGORITHM").unwrap_or_else(|_| "HS256".to_string()),
            access_token_expire_minutes: parse_i64_env("ACCESS_TOKEN_EXPIRE_MINUTES", 60 * 24 * 8),
            llm_provider: env::var("LLM_PROVIDER")
                .unwrap_or_else(|_| "openai_compatible".to_string()),
            llm_api_key: env::var("LLM_API_KEY").unwrap_or_default(),
            llm_model: env::var("LLM_MODEL").unwrap_or_else(|_| "gpt-5".to_string()),
            llm_base_url: env::var("LLM_BASE_URL")
                .unwrap_or_else(|_| "https://api.openai.com/v1".to_string()),
            llm_timeout_seconds: parse_i64_env("LLM_TIMEOUT", 300),
            llm_temperature: parse_f64_env("LLM_TEMPERATURE", 0.05),
            llm_max_tokens: parse_i64_env("LLM_MAX_TOKENS", 16_384),
            llm_first_token_timeout_seconds: parse_i64_env("LLM_FIRST_TOKEN_TIMEOUT", 180),
            llm_stream_timeout_seconds: parse_i64_env("LLM_STREAM_TIMEOUT", 180),
            agent_timeout_seconds: parse_i64_env("AGENT_TIMEOUT_SECONDS", 3_600),
            sub_agent_timeout_seconds: parse_i64_env("SUB_AGENT_TIMEOUT_SECONDS", 1_200),
            tool_timeout_seconds: parse_i64_env("TOOL_TIMEOUT_SECONDS", 120),
            openai_api_key: env::var("OPENAI_API_KEY").unwrap_or_default(),
            gemini_api_key: env::var("GEMINI_API_KEY").unwrap_or_default(),
            claude_api_key: env::var("CLAUDE_API_KEY").unwrap_or_default(),
            qwen_api_key: env::var("QWEN_API_KEY").unwrap_or_default(),
            deepseek_api_key: env::var("DEEPSEEK_API_KEY").unwrap_or_default(),
            zhipu_api_key: env::var("ZHIPU_API_KEY").unwrap_or_default(),
            moonshot_api_key: env::var("MOONSHOT_API_KEY").unwrap_or_default(),
            baidu_api_key: env::var("BAIDU_API_KEY").unwrap_or_default(),
            minimax_api_key: env::var("MINIMAX_API_KEY").unwrap_or_default(),
            doubao_api_key: env::var("DOUBAO_API_KEY").unwrap_or_default(),
            ollama_base_url: env::var("OLLAMA_BASE_URL")
                .unwrap_or_else(|_| "http://localhost:11434/v1".to_string()),
            max_analyze_files: parse_i64_env("MAX_ANALYZE_FILES", 0),
            llm_concurrency: parse_i64_env("LLM_CONCURRENCY", 1),
            llm_gap_ms: parse_i64_env("LLM_GAP_MS", 3_000),
            scanner_opengrep_image: normalize_legacy_opengrep_runner_image(
                env::var("SCANNER_OPENGREP_IMAGE")
                    .unwrap_or_else(|_| "argus/opengrep-runner:latest".to_string()),
            ),
            scanner_opengrep_a3s_box_image: env::var("SCANNER_OPENGREP_A3S_BOX_IMAGE")
                .ok()
                .filter(|value| !value.trim().is_empty())
                .or_else(|| env::var("SCANNER_OPENGREP_IMAGE").ok())
                .map(normalize_legacy_opengrep_runner_image)
                .unwrap_or_else(|| "argus/opengrep-runner:latest".to_string()),
            scanner_codeql_image: env::var("SCANNER_CODEQL_IMAGE")
                .unwrap_or_else(|_| "argus/codeql-runner:latest".to_string()),
            codeql_threads: parse_usize_env("CODEQL_THREADS", 0),
            codeql_ram_mb: parse_u64_env("CODEQL_RAM_MB", 6144),
            codeql_max_build_inference_rounds: parse_u64_env(
                "CODEQL_MAX_BUILD_INFERENCE_ROUNDS",
                3,
            ),
            codeql_allow_network_during_build: parse_bool_env(
                "CODEQL_ALLOW_NETWORK_DURING_BUILD",
                true,
            ),
            codeql_llm_allow_source_snippets: parse_bool_env(
                "CODEQL_LLM_ALLOW_SOURCE_SNIPPETS",
                true,
            ),
            opengrep_scan_timeout_seconds: parse_u64_env("OPENGREP_SCAN_TIMEOUT_SECONDS", 0),
            opengrep_scan_jobs: opengrep_scan_jobs_env
                .as_deref()
                .and_then(|value| value.parse().ok())
                .unwrap_or(0),
            opengrep_scan_jobs_explicit: opengrep_scan_jobs_env.is_some(),
            opengrep_scan_max_memory_mb: parse_u64_env("OPENGREP_SCAN_MAX_MEMORY_MB", 2048),
            opengrep_runner_memory_limit_mb: parse_u64_env("OPENGREP_RUNNER_MEMORY_LIMIT_MB", 2048),
            opengrep_runner_cpu_limit: opengrep_runner_cpu_limit_env
                .as_deref()
                .and_then(|value| value.parse().ok())
                .unwrap_or(0.0),
            opengrep_runner_cpu_limit_explicit: opengrep_runner_cpu_limit_env.is_some(),
            opengrep_runner_pids_limit: parse_u64_env("OPENGREP_RUNNER_PIDS_LIMIT", 512),
            opengrep_runner_runtime: normalize_opengrep_runner_runtime(
                optional_env("OPENGREP_RUNNER_RUNTIME").as_deref(),
            ),
            opengrep_runner_rootless_socket_required: parse_bool_env(
                "OPENGREP_RUNNER_ROOTLESS_SOCKET_REQUIRED",
                false,
            ),
            argus_a3s_localize_limit_mb: parse_u64_env("ARGUS_A3S_LOCALIZE_LIMIT_MB", 50),
            opengrep_standby_pool_size: parse_usize_env("OPENGREP_STANDBY_POOL_SIZE", 2),
            opengrep_standby_pool_disabled: parse_bool_env("OPENGREP_STANDBY_POOL_DISABLED", false),
            codeql_standby_pool_size: parse_usize_env("CODEQL_STANDBY_POOL_SIZE", 2),
            codeql_standby_pool_disabled: parse_bool_env("CODEQL_STANDBY_POOL_DISABLED", false),
            max_total_standby: parse_usize_env("ARGUS_MAX_TOTAL_STANDBY", 8),
            a3s_box_standby_pool_size: parse_usize_env("A3S_BOX_STANDBY_POOL_SIZE", 2),
            a3s_box_standby_pool_disabled: parse_bool_env("A3S_BOX_STANDBY_POOL_DISABLED", false),
            a3s_box_stdout_limit_bytes: parse_usize_env("A3S_BOX_STDOUT_LIMIT_BYTES", 1_048_576),
            a3s_box_stderr_limit_bytes: parse_usize_env("A3S_BOX_STDERR_LIMIT_BYTES", 1_048_576),
            opengrep_results_json_limit_bytes: parse_usize_env(
                "OPENGREP_RESULTS_JSON_LIMIT_BYTES",
                268_435_456,
            ),
        })
    }

    pub fn resolved_rust_database_url(&self) -> Option<String> {
        self.rust_database_url
            .clone()
            .or_else(|| self.database_url.clone())
    }

    pub fn for_tests() -> Self {
        Self {
            bind_addr: SocketAddr::from(([127, 0, 0, 1], 0)),
            database_url: None,
            rust_database_url: None,
            python_database_url: None,
            zip_storage_path: PathBuf::from("./tmp/test-zips"),
            startup_init_enabled: true,
            startup_recovery_enabled: true,
            runner_preflight_enabled: false,
            runner_preflight_strict: false,
            runner_preflight_timeout_seconds: 1,
            runner_preflight_max_concurrency: 1,
            secret_key: "changethis_in_production_to_a_long_random_string".to_string(),
            algorithm: "HS256".to_string(),
            access_token_expire_minutes: 60 * 24 * 8,
            llm_provider: "openai_compatible".to_string(),
            llm_api_key: String::new(),
            llm_model: "gpt-5".to_string(),
            llm_base_url: "https://api.openai.com/v1".to_string(),
            llm_timeout_seconds: 300,
            llm_temperature: 0.05,
            llm_max_tokens: 16_384,
            llm_first_token_timeout_seconds: 180,
            llm_stream_timeout_seconds: 180,
            agent_timeout_seconds: 3_600,
            sub_agent_timeout_seconds: 1_200,
            tool_timeout_seconds: 120,
            openai_api_key: String::new(),
            gemini_api_key: String::new(),
            claude_api_key: String::new(),
            qwen_api_key: String::new(),
            deepseek_api_key: String::new(),
            zhipu_api_key: String::new(),
            moonshot_api_key: String::new(),
            baidu_api_key: String::new(),
            minimax_api_key: String::new(),
            doubao_api_key: String::new(),
            ollama_base_url: "http://localhost:11434/v1".to_string(),
            max_analyze_files: 0,
            llm_concurrency: 1,
            llm_gap_ms: 3_000,
            scanner_opengrep_image: "argus/opengrep-runner:test".to_string(),
            scanner_opengrep_a3s_box_image: "argus/opengrep-runner:test".to_string(),
            scanner_codeql_image: "argus/codeql-runner:test".to_string(),
            codeql_threads: 0,
            codeql_ram_mb: 6144,
            codeql_max_build_inference_rounds: 3,
            codeql_allow_network_during_build: true,
            codeql_llm_allow_source_snippets: true,
            opengrep_scan_timeout_seconds: 0,
            opengrep_scan_jobs: 8,
            opengrep_scan_jobs_explicit: true,
            opengrep_scan_max_memory_mb: 2048,
            opengrep_runner_memory_limit_mb: 2048,
            opengrep_runner_cpu_limit: 8.0,
            opengrep_runner_cpu_limit_explicit: true,
            opengrep_runner_pids_limit: 512,
            opengrep_runner_runtime: "docker".to_string(),
            opengrep_runner_rootless_socket_required: false,
            argus_a3s_localize_limit_mb: 50,
            opengrep_standby_pool_size: 0,
            opengrep_standby_pool_disabled: true,
            codeql_standby_pool_size: 0,
            codeql_standby_pool_disabled: true,
            max_total_standby: 8,
            a3s_box_standby_pool_size: 0,
            a3s_box_standby_pool_disabled: true,
            a3s_box_stdout_limit_bytes: 1_048_576,
            a3s_box_stderr_limit_bytes: 1_048_576,
            opengrep_results_json_limit_bytes: 268_435_456,
        }
    }
}

fn optional_env(key: &str) -> Option<String> {
    env::var(key).ok().and_then(|value| {
        let trimmed = value.trim();
        if trimmed.is_empty() {
            None
        } else {
            Some(trimmed.to_string())
        }
    })
}

fn env_path(key: &str, default: &str) -> PathBuf {
    env::var(key)
        .map(PathBuf::from)
        .unwrap_or_else(|_| PathBuf::from(default))
}

fn normalize_opengrep_runner_runtime(value: Option<&str>) -> String {
    match value
        .map(|value| value.trim().to_ascii_lowercase())
        .as_deref()
    {
        None | Some("") => "podman".to_string(),
        Some("podman") => "podman".to_string(),
        _ => "docker".to_string(),
    }
}

fn normalize_legacy_opengrep_runner_image(value: String) -> String {
    match value.trim() {
        "Argus/opengrep-runner-local:latest" => "argus/opengrep-runner-local:latest".to_string(),
        "Argus/opengrep-runner:latest" => "argus/opengrep-runner:latest".to_string(),
        _ => value,
    }
}

fn parse_bool_env(key: &str, default: bool) -> bool {
    env::var(key)
        .ok()
        .map(|value| {
            matches!(
                value.trim().to_ascii_lowercase().as_str(),
                "1" | "true" | "yes" | "on"
            )
        })
        .unwrap_or(default)
}

fn parse_u64_env(key: &str, default: u64) -> u64 {
    env::var(key)
        .ok()
        .and_then(|value| value.trim().parse().ok())
        .unwrap_or(default)
}

fn parse_usize_env(key: &str, default: usize) -> usize {
    env::var(key)
        .ok()
        .and_then(|value| value.trim().parse().ok())
        .unwrap_or(default)
}

fn parse_i64_env(key: &str, default: i64) -> i64 {
    env::var(key)
        .ok()
        .and_then(|value| value.trim().parse().ok())
        .unwrap_or(default)
}

fn parse_f64_env(key: &str, default: f64) -> f64 {
    env::var(key)
        .ok()
        .and_then(|value| value.trim().parse().ok())
        .unwrap_or(default)
}

#[cfg(test)]
mod tests {
    use super::normalize_opengrep_runner_runtime;

    #[test]
    fn opengrep_runner_runtime_accepts_only_podman_override() {
        assert_eq!(normalize_opengrep_runner_runtime(Some("podman")), "podman");
        assert_eq!(normalize_opengrep_runner_runtime(Some("PODMAN")), "podman");
        assert_eq!(normalize_opengrep_runner_runtime(Some("docker")), "docker");
        assert_eq!(
            normalize_opengrep_runner_runtime(Some("surprise")),
            "docker"
        );
        assert_eq!(normalize_opengrep_runner_runtime(None), "podman");
    }
}
