const ROOT_COMPOSE: &str = include_str!("../../docker-compose.yml");
const BACKEND_DOCKERFILE: &str = include_str!("../../docker/backend.Dockerfile");
const OPENGREP_RUNNER_DOCKERFILE: &str = include_str!("../../docker/opengrep-runner.Dockerfile");
const AGENTFLOW_RUNNER_DOCKERFILE: &str = include_str!("../../docker/agentflow-runner.Dockerfile");
const AGENTFLOW_RUNNER_SCRIPT: &str = include_str!("../../docker/agentflow-runner.sh");
const AGENTFLOW_RUNNER_ADAPTER: &str = include_str!("../../docker/agentflow-runner-adapter.py");
const AGENTFLOW_RUNNER_OUTPUT_SCHEMA: &str =
    include_str!("../agentflow/schemas/runner_output.schema.json");
const OPENGREP_REBUILD_VERIFY_SCRIPT: &str =
    include_str!("../../scripts/rebuild-opengrep-runner-verify.sh");
const RELEASE_BACKEND_DOCKERFILE: &str =
    include_str!("../../scripts/release-templates/backend.Dockerfile");
const AGENT_TASKS_ROUTE: &str = include_str!("../src/routes/agent_tasks.rs");
const SYSTEM_CONFIG_ROUTE: &str = include_str!("../src/routes/system_config.rs");

#[test]
fn compose_passes_backend_cargo_network_build_args() {
    assert!(
        ROOT_COMPOSE.contains(
            "BACKEND_CARGO_REGISTRY: ${BACKEND_CARGO_REGISTRY:-sparse+https://rsproxy.cn/index/}"
        ),
        "root compose must pass the configurable Cargo sparse mirror into the backend build"
    );
    assert!(
        ROOT_COMPOSE.contains(
            "BACKEND_CARGO_HTTP_TIMEOUT_SECONDS: ${BACKEND_CARGO_HTTP_TIMEOUT_SECONDS:-30}"
        ),
        "root compose must bound Cargo HTTP waits during backend builds"
    );
    assert!(
        ROOT_COMPOSE.contains("BACKEND_CARGO_NET_RETRY: ${BACKEND_CARGO_NET_RETRY:-10}"),
        "root compose must pass a bounded Cargo retry count into the backend build"
    );
}

#[test]
fn backend_dockerfiles_configure_cargo_mirror_before_building() {
    for (name, dockerfile) in [
        ("docker/backend.Dockerfile", BACKEND_DOCKERFILE),
        (
            "scripts/release-templates/backend.Dockerfile",
            RELEASE_BACKEND_DOCKERFILE,
        ),
    ] {
        assert!(
            dockerfile.contains("ARG BACKEND_CARGO_REGISTRY=sparse+https://rsproxy.cn/index/"),
            "{name} must default to a Cargo sparse mirror for weak crates.io connectivity"
        );
        assert!(
            dockerfile.contains("replace-with = \"argus-cargo-mirror\""),
            "{name} must replace the default crates.io source before cargo build"
        );
        assert!(
            dockerfile.contains("printf 'registry = \"%s\"\\n' \"${BACKEND_CARGO_REGISTRY}\""),
            "{name} must keep the Cargo mirror configurable by build arg"
        );
        assert!(
            dockerfile.contains("CARGO_HTTP_TIMEOUT=\"${BACKEND_CARGO_HTTP_TIMEOUT_SECONDS}\""),
            "{name} must bound Cargo HTTP waits"
        );
        assert!(
            dockerfile.contains("CARGO_NET_RETRY=\"${BACKEND_CARGO_NET_RETRY}\""),
            "{name} must bound Cargo retry attempts"
        );
        assert!(
            dockerfile.contains("cargo build --locked --release --bin backend-rust"),
            "{name} must build from the committed lockfile"
        );
    }
}

#[test]
fn backend_dockerfile_locks_cargo_cache_mounts_for_multi_platform_builds() {
    for mount in [
        "id=argus-backend-cargo-registry,target=/usr/local/cargo/registry,sharing=locked",
        "id=argus-backend-cargo-git,target=/usr/local/cargo/git,sharing=locked",
        "id=argus-backend-cargo-target,target=/app/target,sharing=locked",
    ] {
        assert!(
            BACKEND_DOCKERFILE.contains(mount),
            "docker/backend.Dockerfile must lock Cargo cache mount {mount} so concurrent buildx platforms cannot corrupt shared cache state"
        );
    }
}

#[test]
fn backend_runtime_images_package_agentflow_pipeline_assets() {
    for (name, dockerfile) in [
        ("docker/backend.Dockerfile", BACKEND_DOCKERFILE),
        (
            "scripts/release-templates/backend.Dockerfile",
            RELEASE_BACKEND_DOCKERFILE,
        ),
    ] {
        assert!(
            dockerfile.contains("COPY backend/agentflow /app/backend/agentflow"),
            "{name} must package backend/agentflow so backend preflight can see /app/backend/agentflow/pipelines/intelligent_audit.py"
        );
    }
    assert!(
        AGENTFLOW_RUNNER_DOCKERFILE.contains("COPY backend/agentflow /app/backend/agentflow"),
        "agentflow runner image must preserve the same packaged pipeline path"
    );
    assert!(
        AGENTFLOW_RUNNER_ADAPTER.contains(
            "DEFAULT_PIPELINE = \"/app/backend/agentflow/pipelines/intelligent_audit.py\""
        ),
        "agentflow runner adapter must keep the packaged pipeline default"
    );
}

#[test]
fn backend_agentflow_preflight_routes_share_pipeline_resolver() {
    for (name, source) in [
        ("backend/src/routes/agent_tasks.rs", AGENT_TASKS_ROUTE),
        ("backend/src/routes/system_config.rs", SYSTEM_CONFIG_ROUTE),
    ] {
        assert!(
            source.contains("resolve_agentflow_pipeline_path"),
            "{name} must use the shared AgentFlow pipeline resolver"
        );
        assert!(
            !source.contains("Path::new(\"backend/agentflow/pipelines/intelligent_audit.py\")"),
            "{name} must not reintroduce duplicated source-path fallback logic"
        );
        assert!(
            !source.contains("PathBuf::from(\"agentflow/pipelines/intelligent_audit.py\")"),
            "{name} must not fall back to the known-missing repo-root path"
        );
    }
}

#[test]
fn opengrep_runner_packages_only_unified_rule_root() {
    assert!(
        OPENGREP_RUNNER_DOCKERFILE.contains("COPY backend/assets/scan_rule_assets/rules_opengrep"),
        "opengrep runner image must package the unified rules_opengrep root"
    );
    assert!(
        OPENGREP_RUNNER_DOCKERFILE.contains("rules.tar.gz rules_opengrep"),
        "opengrep runner image must archive the unified rules_opengrep root"
    );
    assert!(
        !OPENGREP_RUNNER_DOCKERFILE.contains("rules_from_patches"),
        "opengrep runner image must not reference the retired rules_from_patches root"
    );
}

#[test]
fn agentflow_runner_emits_argus_contract_instead_of_native_runrecord() {
    assert!(
        AGENTFLOW_RUNNER_DOCKERFILE
            .contains("ARG AGENTFLOW_COMMIT=1667fa35ed99e3c1583a7d60cac8e3406cafd3ee"),
        "agentflow runner image must pin the reviewed AgentFlow source commit"
    );
    assert!(
        ROOT_COMPOSE.contains(
            "AGENTFLOW_BUILD_CACHE_SCOPE: ${AGENTFLOW_BUILD_CACHE_SCOPE:-argus-agentflow}"
        ),
        "agentflow runner build must expose a cache scope knob for fresh dependency rebuilds"
    );
    assert!(
        AGENTFLOW_RUNNER_DOCKERFILE
            .contains("id=${AGENTFLOW_BUILD_CACHE_SCOPE}-pip,target=/root/.cache/pip"),
        "agentflow runner pip cache mount must be scoped by build arg so a rebuild can avoid stale cache mounts"
    );
    for required in [
        "ARG CODEX_NPM_PACKAGE=\"@openai/codex@latest\"",
        "ARG CODEX_NPM_REGISTRY_PRIMARY=",
        "ARG CODEX_NPM_REGISTRY=",
        "ARG CODEX_NPM_REGISTRY_DEFAULT=https://registry.npmmirror.com",
        "ARG CODEX_NPM_REGISTRY_FALLBACK=https://registry.npmjs.org/",
        "ARG CODEX_NPM_INSTALL_TIMEOUT_SECONDS=120",
        "id=${AGENTFLOW_BUILD_CACHE_SCOPE}-npm,target=/root/.npm",
        "CODEX_NPM_REGISTRY_PRIMARY > CODEX_NPM_REGISTRY > CODEX_NPM_REGISTRY_DEFAULT",
        "codex_npm_primary=\"${CODEX_NPM_REGISTRY_PRIMARY:-}\"",
        "codex_npm_primary=\"${CODEX_NPM_REGISTRY:-}\"",
        "codex_npm_primary=\"${CODEX_NPM_REGISTRY_DEFAULT}\"",
        "Trying fallback Codex npm registry",
        "timeout \"${CODEX_NPM_INSTALL_TIMEOUT_SECONDS}\" npm install --global",
        "--cache /root/.npm",
        "codex --version >/dev/null",
    ] {
        assert!(
            AGENTFLOW_RUNNER_DOCKERFILE.contains(required),
            "agentflow runner Dockerfile must contain npm mirror/fallback contract marker {required:?}"
        );
    }
    for required in [
        "CODEX_NPM_PACKAGE: ${CODEX_NPM_PACKAGE:-@openai/codex@latest}",
        "CODEX_NPM_REGISTRY_PRIMARY: ${CODEX_NPM_REGISTRY_PRIMARY:-}",
        "CODEX_NPM_REGISTRY: ${CODEX_NPM_REGISTRY:-}",
        "CODEX_NPM_REGISTRY_DEFAULT: ${CODEX_NPM_REGISTRY_DEFAULT:-https://registry.npmmirror.com}",
        "CODEX_NPM_REGISTRY_FALLBACK: ${CODEX_NPM_REGISTRY_FALLBACK:-https://registry.npmjs.org/}",
        "CODEX_NPM_INSTALL_TIMEOUT_SECONDS: ${CODEX_NPM_INSTALL_TIMEOUT_SECONDS:-120}",
    ] {
        assert!(
            ROOT_COMPOSE.contains(required),
            "root compose must pass AgentFlow Codex npm build arg {required:?}"
        );
    }
    assert!(
        AGENTFLOW_RUNNER_DOCKERFILE.contains("COPY docker/agentflow-runner-adapter.py"),
        "agentflow runner image must package the Argus output adapter"
    );
    assert!(
        AGENTFLOW_RUNNER_SCRIPT.contains("argus-agentflow-runner-adapter"),
        "agentflow runner entrypoint must delegate to the Argus adapter"
    );
    assert!(
        ROOT_COMPOSE.contains(
            "AGENTFLOW_RUNNER_WORK_VOLUME: ${AGENTFLOW_RUNNER_WORK_VOLUME:-Argus_agentflow_runner_work}"
        ),
        "backend must know the named AgentFlow runner work volume used by docker-runner invocations"
    );
    assert!(
        ROOT_COMPOSE.contains(
            "agentflow_runner_work:\n    name: ${AGENTFLOW_RUNNER_WORK_VOLUME:-Argus_agentflow_runner_work}"
        ),
        "AgentFlow runner work volume must be stable so backend-launched containers can mount it"
    );
    assert!(
        ROOT_COMPOSE
            .contains("agentflow-runner:\n        condition: service_completed_successfully"),
        "backend must wait for the AgentFlow runner image preflight service before serving tasks"
    );
    for required in [
        "CONTRACT_VERSION = \"argus-agentflow-p1/v1\"",
        "TOPOLOGY_VERSION = \"p1-fixed-dag-v1\"",
        "[\"agentflow\", \"validate\", pipeline_path]",
        "[\"agentflow\", \"run\", pipeline_path, \"--runs-dir\", runs_dir, \"--output\", \"json\", *extra_args]",
        "safe_path_segment(task_id)",
        "extract_argus_contract",
        "failure_contract",
        "redact_text",
        "dynamic_experts_enabled",
        "remote_target_enabled",
        "agentflow_serve_enabled",
        "SUPPORTED_CONTRACT_VERSIONS",
        "\"runner_output_invalid\"",
    ] {
        assert!(
            AGENTFLOW_RUNNER_ADAPTER.contains(required),
            "agentflow adapter must contain contract marker {required:?}"
        );
    }
}

#[test]
fn agentflow_runner_output_schema_accepts_p2_p3_observation_fields_without_enabling_them() {
    for required in [
        "argus-agentflow-p2/v1",
        "argus-agentflow-p3/v1",
        "artifact_index",
        "feedback_bundle",
        "risk_lifecycle",
        "discard_reason",
        "statistics",
        "timeline",
        "topology_change",
        "resource_diagnostics",
        "dynamic_expert_diagnostics",
        "dynamic_experts_enabled",
        "remote_target_enabled",
        "agentflow_serve_enabled",
    ] {
        assert!(
            AGENTFLOW_RUNNER_OUTPUT_SCHEMA.contains(required),
            "runner output schema must accept backward-compatible field {required:?}"
        );
    }
}

#[test]
fn opengrep_rebuild_verify_script_rebuilds_image_and_scans_in_container() {
    assert!(
        OPENGREP_REBUILD_VERIFY_SCRIPT
            .contains("SCANNER_OPENGREP_IMAGE:-Argus/opengrep-runner-local:latest"),
        "script must default to the same local opengrep runner image used by compose"
    );
    assert!(
        OPENGREP_REBUILD_VERIFY_SCRIPT
            .contains("docker build -f \"$ROOT_DIR/docker/opengrep-runner.Dockerfile\""),
        "script must rebuild the opengrep runner Dockerfile after rule changes"
    );
    assert!(
        OPENGREP_REBUILD_VERIFY_SCRIPT.contains("opengrep-scan --self-test"),
        "script must run the packaged scanner self-test before scanning a project"
    );
    assert!(
        OPENGREP_REBUILD_VERIFY_SCRIPT.contains("opengrep-scan \\"),
        "script must execute the container scanner entrypoint"
    );
    assert!(
        OPENGREP_REBUILD_VERIFY_SCRIPT.contains("--target /scan/source")
            && OPENGREP_REBUILD_VERIFY_SCRIPT.contains("--output /scan/output/results.json")
            && OPENGREP_REBUILD_VERIFY_SCRIPT.contains("--summary /scan/output/summary.json"),
        "script must write stable scan artifacts from the container"
    );
    assert!(
        OPENGREP_REBUILD_VERIFY_SCRIPT
            .contains("ARGUS_BACKEND_UPLOADS_VOLUME:-argus_backend_uploads"),
        "script must support the compose uploads volume as a default validation source"
    );
    assert!(
        OPENGREP_REBUILD_VERIFY_SCRIPT.contains("-v \"$UPLOADS_VOLUME:/uploads:ro\""),
        "script must read imported archives through Docker volume mounts"
    );
    assert!(
        !OPENGREP_REBUILD_VERIFY_SCRIPT.contains("/var/lib/docker/volumes"),
        "script must not depend on host-specific Docker volume mount paths"
    );
}

#[test]
fn opengrep_rebuild_verify_script_supports_zstd_archives() {
    for suffix in ["*.tar.zst", "*.tar.zstd", "*.tzst", "*.zst", "*.zstd"] {
        assert!(
            OPENGREP_REBUILD_VERIFY_SCRIPT.contains(suffix),
            "script must discover uploaded zstd archive suffix {suffix}"
        );
    }
    assert!(
        OPENGREP_REBUILD_VERIFY_SCRIPT.contains("zstd archive support requires the zstd command"),
        "script must fail clearly when zstd support is unavailable"
    );
    assert!(
        OPENGREP_REBUILD_VERIFY_SCRIPT.contains("original_filename")
            && OPENGREP_REBUILD_VERIFY_SCRIPT.contains(".original-name"),
        "script must recover the backend-uploaded .archive original filename from adjacent metadata"
    );
    assert!(
        OPENGREP_REBUILD_VERIFY_SCRIPT.contains("zstd_magic_seen")
            && OPENGREP_REBUILD_VERIFY_SCRIPT.contains("tar_magic_seen"),
        "script must sniff zstd .archive payloads and decoded tar payloads"
    );
    assert!(
        OPENGREP_REBUILD_VERIFY_SCRIPT.contains("os.replace(decoded_path, target)"),
        "script must keep backend-compatible plain .zst extraction for non-tar payloads"
    );
}
