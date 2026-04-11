use axum::{
    body::{to_bytes, Body},
    http::{Method, Request, StatusCode},
};
use backend_rust::{app::build_router, config::AppConfig, state::AppState};
use serde_json::{json, Value};
use tower::util::ServiceExt;
use uuid::Uuid;

fn isolated_test_config(scope: &str) -> AppConfig {
    let mut config = AppConfig::for_tests();
    config.zip_storage_path =
        std::env::temp_dir().join(format!("audittool-rust-{scope}-{}", Uuid::new_v4()));
    config
}

fn encode_path_segment(value: &str) -> String {
    value.replace('%', "%25").replace('/', "%2F")
}

async fn create_project(app: &axum::Router) -> String {
    let create_payload = json!({
        "name": "task-api-project",
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
async fn agent_task_routes_are_rust_owned_without_python_upstream() {
    let state = AppState::from_config(isolated_test_config("agent-task-routes"))
        .await
        .expect("state should build");
    let app = build_router(state);
    let project_id = create_project(&app).await;

    let create_response = app
        .clone()
        .oneshot(
            Request::builder()
                .method(Method::POST)
                .uri("/api/v1/agent-tasks/")
                .header("content-type", "application/json")
                .body(Body::from(
                    json!({
                        "project_id": project_id,
                        "name": "demo-agent-task",
                        "description": "run agent task from rust",
                        "max_iterations": 3
                    })
                    .to_string(),
                ))
                .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(create_response.status(), StatusCode::OK);
    let create_json: Value =
        serde_json::from_slice(&to_bytes(create_response.into_body(), usize::MAX).await.unwrap())
            .unwrap();
    let task_id = create_json["id"].as_str().unwrap().to_string();
    assert_eq!(create_json["project_id"], project_id);

    let list_response = app
        .clone()
        .oneshot(
            Request::get("/api/v1/agent-tasks/?limit=20")
                .body(Body::empty())
                .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(list_response.status(), StatusCode::OK);

    let start_response = app
        .clone()
        .oneshot(
            Request::builder()
                .method(Method::POST)
                .uri(format!("/api/v1/agent-tasks/{task_id}/start"))
                .body(Body::empty())
                .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(start_response.status(), StatusCode::OK);

    let events_response = app
        .clone()
        .oneshot(
            Request::get(format!(
                "/api/v1/agent-tasks/{task_id}/events/list?after_sequence=0&limit=50"
            ))
            .body(Body::empty())
            .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(events_response.status(), StatusCode::OK);
    let events_json: Value =
        serde_json::from_slice(&to_bytes(events_response.into_body(), usize::MAX).await.unwrap())
            .unwrap();
    assert!(events_json.as_array().is_some_and(|items| !items.is_empty()));

    let stream_response = app
        .clone()
        .oneshot(
            Request::get(format!("/api/v1/agent-tasks/{task_id}/events?after_sequence=0"))
                .body(Body::empty())
                .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(stream_response.status(), StatusCode::OK);
    assert_eq!(stream_response.headers()["content-type"], "text/event-stream");

    let findings_response = app
        .clone()
        .oneshot(
            Request::get(format!("/api/v1/agent-tasks/{task_id}/findings?limit=20"))
                .body(Body::empty())
                .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(findings_response.status(), StatusCode::OK);

    let summary_response = app
        .clone()
        .oneshot(
            Request::get(format!("/api/v1/agent-tasks/{task_id}/summary"))
                .body(Body::empty())
                .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(summary_response.status(), StatusCode::OK);

    let agent_tree_response = app
        .clone()
        .oneshot(
            Request::get(format!("/api/v1/agent-tasks/{task_id}/agent-tree"))
                .body(Body::empty())
                .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(agent_tree_response.status(), StatusCode::OK);

    let checkpoints_response = app
        .clone()
        .oneshot(
            Request::get(format!("/api/v1/agent-tasks/{task_id}/checkpoints"))
                .body(Body::empty())
                .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(checkpoints_response.status(), StatusCode::OK);

    let report_response = app
        .clone()
        .oneshot(
            Request::get(format!("/api/v1/agent-tasks/{task_id}/report?format=markdown"))
                .body(Body::empty())
                .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(report_response.status(), StatusCode::OK);

    let cancel_response = app
        .oneshot(
            Request::builder()
                .method(Method::POST)
                .uri(format!("/api/v1/agent-tasks/{task_id}/cancel"))
                .body(Body::empty())
                .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(cancel_response.status(), StatusCode::OK);
}

#[tokio::test]
async fn static_task_routes_and_rule_catalogs_are_rust_owned_without_python_upstream() {
    let state = AppState::from_config(isolated_test_config("static-task-routes"))
        .await
        .expect("state should build");
    let app = build_router(state);
    let project_id = create_project(&app).await;

    let smoke_routes = [
        "/api/v1/static-tasks/rules?limit=5",
        "/api/v1/static-tasks/rules/generating/status",
        "/api/v1/static-tasks/gitleaks/rules?limit=5",
        "/api/v1/static-tasks/bandit/rules?limit=5",
        "/api/v1/static-tasks/phpstan/rules?limit=5",
        "/api/v1/static-tasks/pmd/presets",
        "/api/v1/static-tasks/pmd/builtin-rulesets?limit=5",
        "/api/v1/static-tasks/cache/repo-stats",
    ];

    for route in smoke_routes {
        let response = app
            .clone()
            .oneshot(Request::get(route).body(Body::empty()).unwrap())
            .await
            .unwrap();
        assert_eq!(response.status(), StatusCode::OK, "route should be rust-owned: {route}");
    }

    let create_payloads = [
        (
            "/api/v1/static-tasks/tasks",
            json!({
                "project_id": project_id,
                "name": "opengrep task",
                "rule_ids": [],
                "target_path": "."
            }),
        ),
        (
            "/api/v1/static-tasks/gitleaks/scan",
            json!({
                "project_id": project_id,
                "name": "gitleaks task",
                "target_path": ".",
                "no_git": true
            }),
        ),
        (
            "/api/v1/static-tasks/bandit/scan",
            json!({
                "project_id": project_id,
                "name": "bandit task",
                "target_path": ".",
                "severity_level": "medium",
                "confidence_level": "medium"
            }),
        ),
        (
            "/api/v1/static-tasks/phpstan/scan",
            json!({
                "project_id": project_id,
                "name": "phpstan task",
                "target_path": ".",
                "level": 5
            }),
        ),
        (
            "/api/v1/static-tasks/pmd/scan",
            json!({
                "project_id": project_id,
                "name": "pmd task",
                "target_path": ".",
                "ruleset": "security"
            }),
        ),
    ];

    let mut created_task_ids = Vec::new();
    for (route, payload) in create_payloads {
        let response = app
            .clone()
            .oneshot(
                Request::builder()
                    .method(Method::POST)
                    .uri(route)
                    .header("content-type", "application/json")
                    .body(Body::from(payload.to_string()))
                    .unwrap(),
            )
            .await
            .unwrap();
        assert_eq!(response.status(), StatusCode::OK, "create route should work: {route}");
        let body: Value =
            serde_json::from_slice(&to_bytes(response.into_body(), usize::MAX).await.unwrap())
                .unwrap();
        created_task_ids.push(body["id"].as_str().unwrap().to_string());
    }

    let opengrep_progress = app
        .clone()
        .oneshot(
            Request::get(format!(
                "/api/v1/static-tasks/tasks/{}/progress?include_logs=true",
                created_task_ids[0]
            ))
            .body(Body::empty())
            .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(opengrep_progress.status(), StatusCode::OK);

    let follow_up_routes = [
        format!("/api/v1/static-tasks/tasks/{}", created_task_ids[0]),
        format!("/api/v1/static-tasks/tasks/{}/findings?limit=20", created_task_ids[0]),
        format!("/api/v1/static-tasks/gitleaks/tasks/{}", created_task_ids[1]),
        format!(
            "/api/v1/static-tasks/gitleaks/tasks/{}/findings?limit=20",
            created_task_ids[1]
        ),
        format!("/api/v1/static-tasks/bandit/tasks/{}", created_task_ids[2]),
        format!(
            "/api/v1/static-tasks/bandit/tasks/{}/findings?limit=20",
            created_task_ids[2]
        ),
        format!("/api/v1/static-tasks/phpstan/tasks/{}", created_task_ids[3]),
        format!(
            "/api/v1/static-tasks/phpstan/tasks/{}/findings?limit=20",
            created_task_ids[3]
        ),
        format!("/api/v1/static-tasks/pmd/tasks/{}", created_task_ids[4]),
        format!(
            "/api/v1/static-tasks/pmd/tasks/{}/findings?limit=20",
            created_task_ids[4]
        ),
    ];

    for route in follow_up_routes {
        let response = app
            .clone()
            .oneshot(Request::get(&route).body(Body::empty()).unwrap())
            .await
            .unwrap();
        assert_eq!(response.status(), StatusCode::OK, "follow-up route should work: {route}");
    }

    let gitleaks_rules_response = app
        .clone()
        .oneshot(
            Request::get("/api/v1/static-tasks/gitleaks/rules?limit=5")
                .body(Body::empty())
                .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(gitleaks_rules_response.status(), StatusCode::OK);
    let gitleaks_rules_json: Value = serde_json::from_slice(
        &to_bytes(gitleaks_rules_response.into_body(), usize::MAX)
            .await
            .unwrap(),
    )
    .unwrap();
    let gitleaks_rule_id = gitleaks_rules_json[0]["id"].as_str().unwrap().to_string();

    let gitleaks_rule_detail = app
        .clone()
        .oneshot(
            Request::get(format!("/api/v1/static-tasks/gitleaks/rules/{gitleaks_rule_id}"))
                .body(Body::empty())
                .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(gitleaks_rule_detail.status(), StatusCode::OK);

    let bandit_rules_response = app
        .clone()
        .oneshot(
            Request::get("/api/v1/static-tasks/bandit/rules?limit=5")
                .body(Body::empty())
                .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(bandit_rules_response.status(), StatusCode::OK);
    let bandit_rules_json: Value = serde_json::from_slice(
        &to_bytes(bandit_rules_response.into_body(), usize::MAX)
            .await
            .unwrap(),
    )
    .unwrap();
    let bandit_rule_id = bandit_rules_json[0]["id"].as_str().unwrap().to_string();

    let bandit_toggle_response = app
        .clone()
        .oneshot(
            Request::builder()
                .method(Method::POST)
                .uri(format!("/api/v1/static-tasks/bandit/rules/{bandit_rule_id}/enabled"))
                .header("content-type", "application/json")
                .body(Body::from(json!({ "is_active": false }).to_string()))
                .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(bandit_toggle_response.status(), StatusCode::OK);

    let phpstan_rules_response = app
        .clone()
        .oneshot(
            Request::get("/api/v1/static-tasks/phpstan/rules?limit=5")
                .body(Body::empty())
                .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(phpstan_rules_response.status(), StatusCode::OK);
    let phpstan_rules_json: Value = serde_json::from_slice(
        &to_bytes(phpstan_rules_response.into_body(), usize::MAX)
            .await
            .unwrap(),
    )
    .unwrap();
    let phpstan_rule_id = phpstan_rules_json[0]["id"].as_str().unwrap().to_string();

    let phpstan_rule_update = app
        .clone()
        .oneshot(
            Request::builder()
                .method(Method::PATCH)
                .uri(format!(
                    "/api/v1/static-tasks/phpstan/rules/{}",
                    encode_path_segment(&phpstan_rule_id)
                ))
                .header("content-type", "application/json")
                .body(Body::from(json!({ "name": "patched-rule-name" }).to_string()))
                .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(phpstan_rule_update.status(), StatusCode::OK);

    let pmd_builtin_response = app
        .clone()
        .oneshot(
            Request::get("/api/v1/static-tasks/pmd/builtin-rulesets?limit=5")
                .body(Body::empty())
                .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(pmd_builtin_response.status(), StatusCode::OK);
    let pmd_builtin_json: Value = serde_json::from_slice(
        &to_bytes(pmd_builtin_response.into_body(), usize::MAX)
            .await
            .unwrap(),
    )
    .unwrap();
    let pmd_ruleset_id = pmd_builtin_json[0]["id"].as_str().unwrap().to_string();

    let pmd_builtin_detail = app
        .clone()
        .oneshot(
            Request::get(format!(
                "/api/v1/static-tasks/pmd/builtin-rulesets/{}",
                encode_path_segment(&pmd_ruleset_id)
            ))
            .body(Body::empty())
            .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(pmd_builtin_detail.status(), StatusCode::OK);

    let opengrep_findings_response = app
        .clone()
        .oneshot(
            Request::get(format!("/api/v1/static-tasks/tasks/{}/findings?limit=20", created_task_ids[0]))
                .body(Body::empty())
                .unwrap(),
        )
        .await
        .unwrap();
    let opengrep_findings_json: Value = serde_json::from_slice(
        &to_bytes(opengrep_findings_response.into_body(), usize::MAX)
            .await
            .unwrap(),
    )
    .unwrap();
    let opengrep_finding_id = opengrep_findings_json[0]["id"].as_str().unwrap().to_string();

    let opengrep_finding_status = app
        .clone()
        .oneshot(
            Request::builder()
                .method(Method::POST)
                .uri(format!(
                    "/api/v1/static-tasks/findings/{opengrep_finding_id}/status?status=verified"
                ))
                .body(Body::empty())
                .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(opengrep_finding_status.status(), StatusCode::OK);

    let gitleaks_findings_response = app
        .clone()
        .oneshot(
            Request::get(format!(
                "/api/v1/static-tasks/gitleaks/tasks/{}/findings?limit=20",
                created_task_ids[1]
            ))
            .body(Body::empty())
            .unwrap(),
        )
        .await
        .unwrap();
    let gitleaks_findings_json: Value = serde_json::from_slice(
        &to_bytes(gitleaks_findings_response.into_body(), usize::MAX)
            .await
            .unwrap(),
    )
    .unwrap();
    let gitleaks_finding_id = gitleaks_findings_json[0]["id"].as_str().unwrap().to_string();

    let gitleaks_finding_status = app
        .clone()
        .oneshot(
            Request::builder()
                .method(Method::POST)
                .uri(format!(
                    "/api/v1/static-tasks/gitleaks/findings/{gitleaks_finding_id}/status?status=verified"
                ))
                .body(Body::empty())
                .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(gitleaks_finding_status.status(), StatusCode::OK);

    let bandit_findings_response = app
        .clone()
        .oneshot(
            Request::get(format!(
                "/api/v1/static-tasks/bandit/tasks/{}/findings?limit=20",
                created_task_ids[2]
            ))
            .body(Body::empty())
            .unwrap(),
        )
        .await
        .unwrap();
    let bandit_findings_json: Value = serde_json::from_slice(
        &to_bytes(bandit_findings_response.into_body(), usize::MAX)
            .await
            .unwrap(),
    )
    .unwrap();
    let bandit_finding_id = bandit_findings_json[0]["id"].as_str().unwrap().to_string();

    let bandit_finding_status = app
        .clone()
        .oneshot(
            Request::builder()
                .method(Method::POST)
                .uri(format!(
                    "/api/v1/static-tasks/bandit/findings/{bandit_finding_id}/status?status=verified"
                ))
                .body(Body::empty())
                .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(bandit_finding_status.status(), StatusCode::OK);

    let phpstan_findings_response = app
        .clone()
        .oneshot(
            Request::get(format!(
                "/api/v1/static-tasks/phpstan/tasks/{}/findings?limit=20",
                created_task_ids[3]
            ))
            .body(Body::empty())
            .unwrap(),
        )
        .await
        .unwrap();
    let phpstan_findings_json: Value = serde_json::from_slice(
        &to_bytes(phpstan_findings_response.into_body(), usize::MAX)
            .await
            .unwrap(),
    )
    .unwrap();
    let phpstan_finding_id = phpstan_findings_json[0]["id"].as_str().unwrap().to_string();

    let phpstan_finding_status = app
        .clone()
        .oneshot(
            Request::builder()
                .method(Method::POST)
                .uri(format!(
                    "/api/v1/static-tasks/phpstan/findings/{phpstan_finding_id}/status?status=verified"
                ))
                .body(Body::empty())
                .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(phpstan_finding_status.status(), StatusCode::OK);

    let pmd_findings_response = app
        .clone()
        .oneshot(
            Request::get(format!(
                "/api/v1/static-tasks/pmd/tasks/{}/findings?limit=20",
                created_task_ids[4]
            ))
            .body(Body::empty())
            .unwrap(),
        )
        .await
        .unwrap();
    let pmd_findings_json: Value = serde_json::from_slice(
        &to_bytes(pmd_findings_response.into_body(), usize::MAX)
            .await
            .unwrap(),
    )
    .unwrap();
    let pmd_finding_id = pmd_findings_json[0]["id"].as_str().unwrap().to_string();

    let pmd_finding_status = app
        .oneshot(
            Request::builder()
                .method(Method::POST)
                .uri(format!(
                    "/api/v1/static-tasks/pmd/findings/{pmd_finding_id}/status?status=verified"
                ))
                .body(Body::empty())
                .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(pmd_finding_status.status(), StatusCode::OK);
}

#[tokio::test]
async fn agent_test_routes_are_rust_owned_without_python_upstream() {
    let state = AppState::from_config(isolated_test_config("agent-test-routes"))
        .await
        .expect("state should build");
    let app = build_router(state);

    let routes = [
        (
            "/api/v1/agent-test/recon/run",
            json!({"project_path": "/tmp/demo", "project_name": "demo"}),
        ),
        (
            "/api/v1/agent-test/analysis/run",
            json!({"project_path": "/tmp/demo", "project_name": "demo", "high_risk_areas": [], "entry_points": [], "task_description": ""}),
        ),
        (
            "/api/v1/agent-test/verification/run",
            json!({"project_path": "/tmp/demo", "findings": []}),
        ),
    ];

    for (route, payload) in routes {
        let response = app
            .clone()
            .oneshot(
                Request::builder()
                    .method(Method::POST)
                    .uri(route)
                    .header("content-type", "application/json")
                    .body(Body::from(payload.to_string()))
                    .unwrap(),
            )
            .await
            .unwrap();
        assert_eq!(response.status(), StatusCode::OK, "agent-test route should work: {route}");
        assert_eq!(response.headers()["content-type"], "text/event-stream");
    }
}
