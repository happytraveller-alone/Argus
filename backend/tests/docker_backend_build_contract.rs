const ROOT_COMPOSE: &str = include_str!("../../docker-compose.yml");
const BACKEND_DOCKERFILE: &str = include_str!("../../docker/backend.Dockerfile");
const DOCKER_PUBLISH_WORKFLOW: &str = include_str!("../../.github/workflows/docker-publish.yml");
const OPENGREP_RUNNER_DOCKERFILE: &str = include_str!("../../docker/opengrep-runner.Dockerfile");
const OPENGREP_REBUILD_VERIFY_SCRIPT: &str =
    include_str!("../../scripts/rebuild-opengrep-runner-verify.sh");
const RELEASE_BACKEND_DOCKERFILE: &str =
    include_str!("../../scripts/release-templates/backend.Dockerfile");
const RELEASE_COMPOSE: &str =
    include_str!("../../scripts/release-templates/docker-compose.release-slim.yml");

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
fn compose_exposes_a3s_box_opengrep_image_override() {
    assert!(
        ROOT_COMPOSE.contains(
            "SCANNER_OPENGREP_A3S_BOX_IMAGE: ${SCANNER_OPENGREP_A3S_BOX_IMAGE:-${SCANNER_OPENGREP_IMAGE:-argus/opengrep-runner-local:latest}}"
        ),
        "root compose must let A3S Box OpenGrep scans use a dedicated image while defaulting to the normal runner image"
    );
    assert!(
        RELEASE_COMPOSE.contains("SCANNER_OPENGREP_A3S_BOX_IMAGE: ${SCANNER_OPENGREP_A3S_BOX_IMAGE:-${SCANNER_OPENGREP_IMAGE:-"),
        "release compose must preserve the A3S Box OpenGrep image override"
    );
}

#[test]
fn backend_images_download_a3s_box_v203_binary_package_for_target_arch() {
    for (name, dockerfile) in [
        ("docker/backend.Dockerfile", BACKEND_DOCKERFILE),
        (
            "scripts/release-templates/backend.Dockerfile",
            RELEASE_BACKEND_DOCKERFILE,
        ),
    ] {
        assert!(
            dockerfile.contains("ARG A3S_BOX_VERSION=v2.0.3"),
            "{name} must pin the Box binary package version used for backend images"
        );
        assert!(
            dockerfile.contains("github.com/AI45Lab/Box/releases/download"),
            "{name} must fetch AI45Lab Box release binary packages through the configured mirror prefix"
        );
        assert!(
            dockerfile.contains("amd64) package_arch=\"linux-x86_64\"")
                && dockerfile.contains("arm64) package_arch=\"linux-arm64\""),
            "{name} must choose the x86_64 or arm64 Box binary package from TARGETARCH"
        );
        assert!(
            dockerfile.contains("install -m 0755 /tmp/a3s-box/a3s-box /opt/a3s-box/bin/a3s-box")
                && dockerfile.contains("install -m 0755 /tmp/a3s-box/a3s-box-shim /opt/a3s-box/bin/a3s-box-shim")
                && dockerfile.contains("install -m 0755 /tmp/a3s-box/a3s-box-guest-init /opt/a3s-box/bin/a3s-box-guest-init"),
            "{name} must keep the Box runtime binaries needed by a3s-box run"
        );
        assert!(
            dockerfile.contains("COPY --from=a3s-box-binary-src /opt/a3s-box/bin/ /usr/local/bin/")
                && dockerfile.contains("COPY --from=a3s-box-binary-src /opt/a3s-box/lib/ /usr/local/lib/")
                && dockerfile.contains("ENV LD_LIBRARY_PATH=/usr/local/lib"),
            "{name} must copy only release binaries/libs into runtime and expose libkrun to the loader"
        );
        assert!(
            dockerfile.contains("podman"),
            "{name} must include the Podman CLI so no-socket Podman deployments can run the default Opengrep runner through a rootless Podman API"
        );
        assert!(
            dockerfile.contains("/app/data/runtime/home")
                && dockerfile.contains("ENV HOME=/app/data/runtime/home"),
            "{name} must give appuser a writable HOME for the A3S Box image store"
        );
        assert!(
            dockerfile.contains("rm -rf /tmp/a3s-box /tmp/a3s-box.tar.gz"),
            "{name} must remove the unpacked Box package after extracting runtime artifacts"
        );
    }
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
fn backend_compose_exposes_a3s_microvm_devices() {
    for compose in [ROOT_COMPOSE, RELEASE_COMPOSE] {
        assert!(
            compose.contains("/dev/kvm:/dev/kvm")
                && compose.contains("/dev/vhost-vsock:/dev/vhost-vsock")
                && compose.contains("/dev/net/tun:/dev/net/tun")
                && compose.contains("${ARGUS_KVM_GROUP_ID:-109}"),
            "backend compose service must expose KVM/vsock/tun devices and kvm group access for A3S Box MicroVM scans"
        );
    }
}

#[test]
fn opengrep_runner_publish_uses_oci_image_media_types() {
    assert!(
        DOCKER_PUBLISH_WORKFLOW.contains(
            "\"outputs\": \"type=image,push=true,oci-mediatypes=true\""
        ),
        "opengrep runner publish matrix must export an OCI image container instead of relying on Docker media defaults"
    );
    assert!(
        DOCKER_PUBLISH_WORKFLOW.contains("outputs: ${{ matrix.outputs }}"),
        "docker-publish workflow must pass per-image exporter settings to buildx"
    );
    assert!(
        DOCKER_PUBLISH_WORKFLOW.contains("push: ${{ matrix.outputs == '' }}"),
        "images without explicit exporter settings should keep the normal build-push-action push path"
    );
}

#[test]
fn opengrep_rebuild_verify_script_rebuilds_image_and_scans_in_container() {
    assert!(
        OPENGREP_REBUILD_VERIFY_SCRIPT
            .contains("SCANNER_OPENGREP_IMAGE:-argus/opengrep-runner-local:latest"),
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
