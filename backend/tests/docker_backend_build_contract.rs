const ROOT_COMPOSE: &str = include_str!("../../docker-compose.yml");
const BACKEND_DOCKERFILE: &str = include_str!("../../docker/backend.Dockerfile");
const OPENGREP_RUNNER_DOCKERFILE: &str = include_str!("../../docker/opengrep-runner.Dockerfile");
const OPENGREP_REBUILD_VERIFY_SCRIPT: &str =
    include_str!("../../scripts/rebuild-opengrep-runner-verify.sh");
const RELEASE_BACKEND_DOCKERFILE: &str =
    include_str!("../../scripts/release-templates/backend.Dockerfile");

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
