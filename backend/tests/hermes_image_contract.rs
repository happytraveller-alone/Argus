const HERMES_DOCKERFILE: &str = include_str!("../../docker/hermes-agent-base.Dockerfile");
const ROOT_COMPOSE: &str = include_str!("../../docker-compose.yml");
const STANDALONE_COMPOSE: &str = include_str!("../../docker/docker-compose.hermes-agents.yml");

#[test]
fn hermes_worker_image_excludes_playwright_and_web_build_surfaces() {
    for forbidden in [
        "PLAYWRIGHT_BROWSERS_PATH",
        "npx playwright",
        "web/package.json",
        "web/package-lock.json",
        "npm install",
        "npm run build",
        "nodejs",
        "ffmpeg",
        "HERMES_WEB_DIST",
        ".[all]",
    ] {
        assert!(
            !HERMES_DOCKERFILE.contains(forbidden),
            "Hermes worker Dockerfile must not contain {forbidden:?}"
        );
    }

    assert!(
        HERMES_DOCKERFILE.contains(r#"uv pip install --no-cache-dir -e ".""#),
        "Hermes worker image should install only the base runtime package"
    );
}

#[test]
fn hermes_worker_image_uses_configurable_pull_sources() {
    for required in [
        "ARG DOCKERHUB_LIBRARY_MIRROR=",
        "ARG HERMES_UV_IMAGE=",
        "ARG HERMES_GOSU_IMAGE=",
        "FROM ${HERMES_UV_IMAGE} AS uv_source",
        "FROM ${HERMES_GOSU_IMAGE} AS gosu_source",
        "FROM ${DOCKERHUB_LIBRARY_MIRROR}/debian:13.4",
        "ARG HERMES_APT_MIRROR_PRIMARY",
        "ARG HERMES_APT_MIRROR_FALLBACK",
        r#"ENV PATH="/opt/hermes/.venv/bin:/opt/data/.local/bin:${PATH}""#,
    ] {
        assert!(
            HERMES_DOCKERFILE.contains(required),
            "Hermes worker Dockerfile missing pull/mirror contract {required:?}"
        );
    }

    assert!(
        HERMES_DOCKERFILE.contains("rm -rf web package.json package-lock.json"),
        "Hermes worker image should delete upstream Node/web assets after copying the submodule"
    );
}

#[test]
fn hermes_compose_files_pass_image_pull_optimization_args() {
    for compose in [ROOT_COMPOSE, STANDALONE_COMPOSE] {
        for required in [
            "DOCKERHUB_LIBRARY_MIRROR:",
            "HERMES_UV_IMAGE:",
            "HERMES_GOSU_IMAGE:",
            "HERMES_APT_MIRROR_PRIMARY:",
            "HERMES_APT_SECURITY_PRIMARY:",
            "HERMES_APT_MIRROR_FALLBACK:",
            "HERMES_APT_SECURITY_FALLBACK:",
        ] {
            assert!(
                compose.contains(required),
                "Hermes compose build args missing {required:?}"
            );
        }
    }
}
