const HERMES_DOCKERFILE: &str = include_str!("../../docker/hermes-agent-base.Dockerfile");
const ROOT_COMPOSE: &str = include_str!("../../docker-compose.yml");
const STANDALONE_COMPOSE: &str = include_str!("../../docker/docker-compose.hermes-agents.yml");
const HERMES_WORKER_IMAGE: &str = "Argus/hermes-agent:latest";
const HERMES_WORKER_DOCKERFILE: &str = "docker/hermes-agent-base.Dockerfile";
const HERMES_WORKER_CONTRACT_LABEL: &str = r#"org.Argus.hermes.contract="worker-text-only""#;
const UPSTREAM_HERMES_DOCKERFILE: &str = "third_party/hermes-agent/Dockerfile";
const HERMES_WORKER_SERVICES: [&str; 4] = [
    "hermes-report",
    "hermes-analysis",
    "hermes-recon",
    "hermes-verification",
];

fn compose_service_block(compose: &str, service: &str) -> String {
    let marker = format!("  {service}:");
    let mut block = String::new();
    let mut in_service = false;

    for line in compose.lines() {
        if line == marker {
            in_service = true;
        } else if in_service
            && ((line.starts_with("  ") && !line.starts_with("    "))
                || line == "networks:"
                || line == "volumes:")
        {
            break;
        }

        if in_service {
            block.push_str(line);
            block.push('\n');
        }
    }

    assert!(
        !block.is_empty(),
        "Hermes compose file must define service {service:?}"
    );
    block
}

fn hermes_service_names(compose: &str) -> Vec<&str> {
    compose
        .lines()
        .filter_map(|line| line.strip_prefix("  ")?.strip_suffix(':'))
        .filter(|service| service.starts_with("hermes-"))
        .collect()
}

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
fn hermes_worker_image_declares_text_only_contract_label() {
    assert!(
        HERMES_DOCKERFILE.contains(HERMES_WORKER_CONTRACT_LABEL),
        "Hermes worker image must expose an inspectable text-only contract label"
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

#[test]
fn hermes_compose_files_define_all_worker_services_from_base_dockerfile() {
    for (compose_name, compose) in [
        ("root docker-compose.yml", ROOT_COMPOSE),
        (
            "standalone docker/docker-compose.hermes-agents.yml",
            STANDALONE_COMPOSE,
        ),
    ] {
        let mut actual_services = hermes_service_names(compose);
        actual_services.sort_unstable();
        let mut expected_services = HERMES_WORKER_SERVICES.to_vec();
        expected_services.sort_unstable();
        assert_eq!(
            actual_services, expected_services,
            "{compose_name} must expose exactly the Hermes worker service set"
        );

        for service in HERMES_WORKER_SERVICES {
            let service_block = compose_service_block(compose, service);
            assert!(
                service_block.contains(&format!("dockerfile: {HERMES_WORKER_DOCKERFILE}")),
                "{compose_name} service {service:?} must build from {HERMES_WORKER_DOCKERFILE}"
            );
            assert!(
                service_block.contains(&format!("image: {HERMES_WORKER_IMAGE}")),
                "{compose_name} service {service:?} must publish the final worker image tag {HERMES_WORKER_IMAGE}"
            );
            assert!(
                !service_block.contains(UPSTREAM_HERMES_DOCKERFILE)
                    && !service_block.to_lowercase().contains("nousresearch/hermes-agent"),
                "{compose_name} service {service:?} must not bypass the repo-owned worker Dockerfile"
            );
        }
    }
}

#[test]
fn hermes_worker_image_copies_shared_config_helper_only() {
    assert!(
        !HERMES_DOCKERFILE.contains("backend/agents/shared/bin/apply-shared-config.py"),
        "Hermes worker image must not depend on apply-shared-config.py"
    );
    assert!(
        HERMES_DOCKERFILE.contains("/opt/bin/"),
        "Hermes worker image should copy shared helper scripts into /opt/bin/"
    );
    assert!(
        !HERMES_DOCKERFILE.contains("backend/agents/shared/config.json"),
        "Hermes worker image must not bake backend/agents/shared/config.json into the image"
    );
}

#[test]
fn hermes_compose_files_mount_shared_config_json() {
    for compose in [ROOT_COMPOSE, STANDALONE_COMPOSE] {
        assert!(
            compose.contains("backend/agents/shared/config.json:/opt/shared/config.json:ro"),
            "Hermes compose must mount the shared JSON config into /opt/shared/config.json"
        );
        assert!(
            !compose.contains("backend/agents/recon/container.env")
                && !compose.contains("backend/agents/analysis/container.env")
                && !compose.contains("backend/agents/verification/container.env")
                && !compose.contains("backend/agents/report/container.env"),
            "Hermes compose should not depend on per-role container.env file paths"
        );
    }
}
