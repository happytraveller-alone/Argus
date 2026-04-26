use std::path::Path;

const ROOT_COMPOSE: &str = include_str!("../../docker-compose.yml");
const GITMODULES: &str = include_str!("../../.gitmodules");
const RELEASE_WORKFLOW: &str = include_str!("../../.github/workflows/release.yml");
const DOCKER_PUBLISH_WORKFLOW: &str = include_str!("../../.github/workflows/docker-publish.yml");
const BACKEND_MIGRATION_SMOKE_WORKFLOW: &str =
    include_str!("../../.github/workflows/backend-migration-smoke.yml");

const HERMES_WORKER_SERVICES: [&str; 4] = [
    "hermes-recon",
    "hermes-analysis",
    "hermes-verification",
    "hermes-report",
];

fn repo_root() -> &'static Path {
    Path::new(env!("CARGO_MANIFEST_DIR"))
        .parent()
        .expect("backend crate must live below the repository root")
}

fn root_compose_service_names() -> Vec<&'static str> {
    ROOT_COMPOSE
        .lines()
        .filter_map(|line| line.strip_prefix("  ")?.strip_suffix(':'))
        .collect()
}

fn retired_build_file_path() -> String {
    ["docker/hermes-agent-", "base.Dockerfile"].concat()
}

fn retired_standalone_compose_path() -> String {
    ["docker/docker-compose.hermes-", "agents.yml"].concat()
}

fn retired_build_tokens() -> Vec<String> {
    vec![
        ["x-hermes-", "build-args"].concat(),
        ["dockerfile: ", &retired_build_file_path()].concat(),
        ["HERMES_", "UV_IMAGE"].concat(),
        ["HERMES_", "GOSU_IMAGE"].concat(),
        ["HERMES_", "APT_"].concat(),
        ["HERMES_", "SOURCE_DIGEST"].concat(),
        ["HERMES_", "SUBMODULE_STATUS"].concat(),
    ]
}

#[test]
fn repo_owned_hermes_container_build_files_are_absent() {
    let root = repo_root();

    for retired_path in [retired_build_file_path(), retired_standalone_compose_path()] {
        assert!(
            !root.join(&retired_path).exists(),
            "retired Hermes build surface must stay absent: {retired_path}"
        );
    }
}

#[test]
fn root_compose_no_longer_defines_hermes_build_surface() {
    for forbidden in retired_build_tokens() {
        assert!(
            !ROOT_COMPOSE.contains(&forbidden),
            "root docker-compose.yml must not contain retired Hermes build token {forbidden:?}"
        );
    }

    let services = root_compose_service_names();
    for service in HERMES_WORKER_SERVICES {
        assert!(
            !services.contains(&service),
            "root docker-compose.yml must not define repo-managed Hermes worker service {service:?}"
        );
    }
}

#[test]
fn hermes_upstream_source_submodule_contract_is_preserved() {
    assert!(
        GITMODULES.contains(r#"[submodule "third_party/hermes-agent"]"#),
        ".gitmodules must keep the Hermes upstream source submodule entry"
    );
    assert!(
        GITMODULES.contains("path = third_party/hermes-agent"),
        ".gitmodules must keep the Hermes submodule path"
    );
    assert!(
        GITMODULES.contains("url = https://github.com/NousResearch/hermes-agent.git"),
        ".gitmodules must keep the Hermes upstream source URL"
    );
    assert!(
        repo_root().join("third_party/hermes-agent").is_dir(),
        "Hermes upstream source submodule directory must remain present"
    );
}

#[test]
fn key_workflows_still_checkout_recursive_submodules() {
    for (workflow_name, workflow) in [
        (".github/workflows/release.yml", RELEASE_WORKFLOW),
        (
            ".github/workflows/docker-publish.yml",
            DOCKER_PUBLISH_WORKFLOW,
        ),
        (
            ".github/workflows/backend-migration-smoke.yml",
            BACKEND_MIGRATION_SMOKE_WORKFLOW,
        ),
    ] {
        assert!(
            workflow.contains("submodules: recursive"),
            "{workflow_name} must preserve recursive submodule checkout"
        );
    }
}
