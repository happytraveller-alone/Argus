const ROOT_COMPOSE: &str = include_str!("../../docker-compose.yml");
const BACKEND_DOCKERFILE: &str = include_str!("../../docker/backend.Dockerfile");
const RELEASE_BACKEND_DOCKERFILE: &str =
    include_str!("../../scripts/release-templates/backend.Dockerfile");

#[test]
fn compose_passes_backend_cargo_network_build_args() {
    assert!(
        ROOT_COMPOSE
            .contains("BACKEND_CARGO_REGISTRY: ${BACKEND_CARGO_REGISTRY:-sparse+https://rsproxy.cn/index/}"),
        "root compose must pass the configurable Cargo sparse mirror into the backend build"
    );
    assert!(
        ROOT_COMPOSE
            .contains("BACKEND_CARGO_HTTP_TIMEOUT_SECONDS: ${BACKEND_CARGO_HTTP_TIMEOUT_SECONDS:-30}"),
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
