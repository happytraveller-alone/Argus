use axum::{
    body::{to_bytes, Body},
    http::{Method, Request, StatusCode},
};
use backend_rust::{app::build_router, config::AppConfig, db::task_state, state::AppState};
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
    create_project_with_name(app, "task-api-project").await
}

async fn create_project_with_name(app: &axum::Router, name: &str) -> String {
    let create_payload = json!({
        "name": name,
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

async fn seed_agent_report_findings(
    state: &AppState,
    task_id: &str,
) -> (String, String) {
    let mut snapshot = task_state::load_snapshot(state).await.unwrap();
    let record = snapshot.agent_tasks.get_mut(task_id).unwrap();
    record.findings.clear();
    let first_id = Uuid::new_v4().to_string();
    let second_id = Uuid::new_v4().to_string();
    record.findings.push(task_state::AgentFindingRecord {
        id: first_id.clone(),
        task_id: task_id.to_string(),
        vulnerability_type: "sql_injection".to_string(),
        severity: "high".to_string(),
        title: "SQL injection in login".to_string(),
        display_title: Some("登录 SQL 注入".to_string()),
        description: Some("raw SQL string interpolation".to_string()),
        description_markdown: Some("登录查询拼接了用户输入。".to_string()),
        file_path: Some("src/auth/login.ts".to_string()),
        line_start: Some(42),
        line_end: Some(48),
        resolved_file_path: Some("src/auth/login.ts".to_string()),
        resolved_line_start: Some(42),
        code_snippet: Some("SELECT * FROM users WHERE email = '${email}'".to_string()),
        status: "verified".to_string(),
        is_verified: true,
        verdict: Some("confirmed".to_string()),
        authenticity: Some("confirmed".to_string()),
        suggestion: Some("use parameterized query".to_string()),
        fix_code: Some("SELECT * FROM users WHERE email = ?".to_string()),
        report: Some("first finding report".to_string()),
        confidence: Some(0.95),
        created_at: "2026-04-12T10:00:00Z".to_string(),
        ..Default::default()
    });
    record.findings.push(task_state::AgentFindingRecord {
        id: second_id.clone(),
        task_id: task_id.to_string(),
        vulnerability_type: "xss".to_string(),
        severity: "medium".to_string(),
        title: "Reflected XSS in search".to_string(),
        display_title: Some("搜索页反射型 XSS".to_string()),
        description: Some("unsafe HTML render".to_string()),
        description_markdown: Some("搜索词进入了危险 HTML 渲染链路。".to_string()),
        file_path: Some("src/web/search.tsx".to_string()),
        line_start: Some(77),
        line_end: Some(82),
        resolved_file_path: Some("src/web/search.tsx".to_string()),
        resolved_line_start: Some(77),
        code_snippet: Some("<div dangerouslySetInnerHTML={...} />".to_string()),
        status: "pending".to_string(),
        is_verified: false,
        verdict: Some("likely".to_string()),
        authenticity: Some("likely".to_string()),
        suggestion: Some("escape output".to_string()),
        confidence: Some(0.71),
        created_at: "2026-04-12T10:05:00Z".to_string(),
        ..Default::default()
    });
    record.findings_count = 2;
    record.verified_count = 1;
    record.false_positive_count = 0;
    record.critical_count = 0;
    record.high_count = 1;
    record.medium_count = 1;
    record.low_count = 0;
    record.verified_high_count = 1;
    record.verified_medium_count = 0;
    record.report = Some("## 项目风险结论\n\n存在高危注入风险，建议优先修复。".to_string());
    task_state::save_snapshot(state, &snapshot).await.unwrap();
    (first_id, second_id)
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
async fn agent_task_report_exports_cover_task_and_finding_downloads() {
    let state = AppState::from_config(isolated_test_config("agent-task-report-exports"))
        .await
        .expect("state should build");
    let app = build_router(state.clone());
    let project_id = create_project_with_name(&app, "审计项目 Demo").await;

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
                        "name": "report-export-task",
                        "description": "report export contract test",
                        "max_iterations": 2
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

    let (first_finding_id, second_finding_id) = seed_agent_report_findings(&state, &task_id).await;

    let markdown_response = app
        .clone()
        .oneshot(
            Request::get(format!(
                "/api/v1/agent-tasks/{task_id}/report?format=markdown&include_code_snippets=false&include_remediation=false&include_metadata=true&compact_mode=true"
            ))
            .body(Body::empty())
            .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(markdown_response.status(), StatusCode::OK);
    assert_eq!(
        markdown_response.headers()["content-type"],
        "text/markdown; charset=utf-8"
    );
    let markdown_disposition = markdown_response
        .headers()
        .get("content-disposition")
        .unwrap()
        .to_str()
        .unwrap();
    assert!(markdown_disposition.contains("attachment; filename=\""));
    assert!(markdown_disposition.contains("filename*=UTF-8''"));
    assert!(markdown_disposition.contains(".md"));
    let markdown_body =
        String::from_utf8(to_bytes(markdown_response.into_body(), usize::MAX).await.unwrap().to_vec())
            .unwrap();
    assert!(markdown_body.contains("# 漏洞报告：审计项目 Demo"));
    assert!(markdown_body.contains("登录 SQL 注入"));
    assert!(!markdown_body.contains("SELECT * FROM users WHERE email = '${email}'"));
    assert!(!markdown_body.contains("use parameterized query"));

    let json_response = app
        .clone()
        .oneshot(
            Request::get(format!(
                "/api/v1/agent-tasks/{task_id}/report?format=json&include_code_snippets=true&include_remediation=true&include_metadata=true&compact_mode=false"
            ))
            .body(Body::empty())
            .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(json_response.status(), StatusCode::OK);
    assert_eq!(json_response.headers()["content-type"], "application/json");
    let json_payload: Value =
        serde_json::from_slice(&to_bytes(json_response.into_body(), usize::MAX).await.unwrap())
            .unwrap();
    assert_eq!(json_payload["summary"]["total_findings"], 2);
    assert_eq!(json_payload["summary"]["verified_findings"], 1);
    assert_eq!(
        json_payload["report_metadata"]["project_name"],
        "审计项目 Demo"
    );
    assert_eq!(json_payload["findings"][0]["id"], first_finding_id);
    assert_eq!(
        json_payload["findings"][0]["code_snippet"],
        "SELECT * FROM users WHERE email = '${email}'"
    );
    assert_eq!(json_payload["findings"][1]["id"], second_finding_id);

    let pdf_response = app
        .clone()
        .oneshot(
            Request::get(format!("/api/v1/agent-tasks/{task_id}/report?format=pdf"))
                .body(Body::empty())
                .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(pdf_response.status(), StatusCode::OK);
    assert_eq!(pdf_response.headers()["content-type"], "application/pdf");
    let pdf_disposition = pdf_response
        .headers()
        .get("content-disposition")
        .unwrap()
        .to_str()
        .unwrap();
    assert!(pdf_disposition.contains("filename*=UTF-8''"));
    assert!(pdf_disposition.contains(".pdf"));
    let pdf_body = to_bytes(pdf_response.into_body(), usize::MAX).await.unwrap();
    assert!(pdf_body.starts_with(b"%PDF-1.4"));

    let finding_markdown_response = app
        .clone()
        .oneshot(
            Request::get(format!(
                "/api/v1/agent-tasks/{task_id}/findings/{first_finding_id}/report?format=markdown&include_code_snippets=true&include_remediation=true&include_metadata=true"
            ))
            .body(Body::empty())
            .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(finding_markdown_response.status(), StatusCode::OK);
    assert_eq!(
        finding_markdown_response.headers()["content-type"],
        "text/markdown; charset=utf-8"
    );
    let finding_md = String::from_utf8(
        to_bytes(finding_markdown_response.into_body(), usize::MAX)
            .await
            .unwrap()
            .to_vec(),
    )
    .unwrap();
    assert!(finding_md.contains("漏洞详情报告：登录 SQL 注入"));
    assert!(finding_md.contains("SELECT * FROM users WHERE email = '${email}'"));
    assert!(finding_md.contains("use parameterized query"));

    let finding_json_response = app
        .clone()
        .oneshot(
            Request::get(format!(
                "/api/v1/agent-tasks/{task_id}/findings/{first_finding_id}/report?format=json&include_code_snippets=false&include_remediation=false&include_metadata=false"
            ))
            .body(Body::empty())
            .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(finding_json_response.status(), StatusCode::OK);
    assert_eq!(finding_json_response.headers()["content-type"], "application/json");
    let finding_json: Value = serde_json::from_slice(
        &to_bytes(finding_json_response.into_body(), usize::MAX)
            .await
            .unwrap(),
    )
    .unwrap();
    assert_eq!(finding_json["report_metadata"]["finding_id"], first_finding_id);
    assert!(finding_json["finding"].get("code_snippet").is_none());
    assert!(finding_json["finding"].get("suggestion").is_none());

    let finding_pdf_response = app
        .oneshot(
            Request::get(format!(
                "/api/v1/agent-tasks/{task_id}/findings/{first_finding_id}/report?format=pdf"
            ))
            .body(Body::empty())
            .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(finding_pdf_response.status(), StatusCode::OK);
    assert_eq!(
        finding_pdf_response.headers()["content-type"],
        "application/pdf"
    );
    let finding_pdf_disposition = finding_pdf_response
        .headers()
        .get("content-disposition")
        .unwrap()
        .to_str()
        .unwrap();
    assert!(finding_pdf_disposition.contains("filename*=UTF-8''"));
    assert!(finding_pdf_disposition.contains(".pdf"));
    let finding_pdf_body = to_bytes(finding_pdf_response.into_body(), usize::MAX)
        .await
        .unwrap();
    assert!(finding_pdf_body.starts_with(b"%PDF-1.4"));
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
    let opengrep_progress_json: Value = serde_json::from_slice(
        &to_bytes(opengrep_progress.into_body(), usize::MAX)
            .await
            .unwrap(),
    )
    .unwrap();
    assert_eq!(opengrep_progress_json["status"], "completed");
    assert_eq!(opengrep_progress_json["progress"], 100.0);
    assert_eq!(opengrep_progress_json["current_stage"], "completed");
    assert!(
        opengrep_progress_json["logs"]
            .as_array()
            .is_some_and(|logs| !logs.is_empty())
    );

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

    let opengrep_finding_detail = app
        .clone()
        .oneshot(
            Request::get(format!(
                "/api/v1/static-tasks/tasks/{}/findings?limit=20",
                created_task_ids[0]
            ))
            .body(Body::empty())
            .unwrap(),
        )
        .await
        .unwrap();
    let opengrep_finding_detail_json: Value = serde_json::from_slice(
        &to_bytes(opengrep_finding_detail.into_body(), usize::MAX)
            .await
            .unwrap(),
    )
    .unwrap();
    let opengrep_finding_id = opengrep_finding_detail_json[0]["id"]
        .as_str()
        .unwrap()
        .to_string();

    let opengrep_finding_response = app
        .clone()
        .oneshot(
            Request::get(format!(
                "/api/v1/static-tasks/tasks/{}/findings/{}",
                created_task_ids[0], opengrep_finding_id
            ))
            .body(Body::empty())
            .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(opengrep_finding_response.status(), StatusCode::OK);
    let opengrep_finding_json: Value = serde_json::from_slice(
        &to_bytes(opengrep_finding_response.into_body(), usize::MAX)
            .await
            .unwrap(),
    )
    .unwrap();
    assert_eq!(opengrep_finding_json["status"], "open");
    assert_eq!(opengrep_finding_json["rule_name"], "rust-placeholder-opengrep-rule");
    assert_eq!(opengrep_finding_json["resolved_file_path"], ".");
    assert_eq!(opengrep_finding_json["resolved_line_start"], 1);

    let opengrep_context_response = app
        .clone()
        .oneshot(
            Request::get(format!(
                "/api/v1/static-tasks/tasks/{}/findings/{}/context?before=1&after=1",
                created_task_ids[0], opengrep_finding_id
            ))
            .body(Body::empty())
            .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(opengrep_context_response.status(), StatusCode::OK);
    let opengrep_context_json: Value = serde_json::from_slice(
        &to_bytes(opengrep_context_response.into_body(), usize::MAX)
            .await
            .unwrap(),
    )
    .unwrap();
    assert_eq!(opengrep_context_json["file_path"], ".");
    assert_eq!(opengrep_context_json["start_line"], 1);
    assert_eq!(opengrep_context_json["end_line"], 1);
    assert!(
        opengrep_context_json["lines"]
            .as_array()
            .is_some_and(|lines| !lines.is_empty())
    );

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
async fn opengrep_rule_batch_select_supports_rule_ids_keyword_and_current_state_filters() {
    let state = AppState::from_config(isolated_test_config("opengrep-rule-select"))
        .await
        .expect("state should build");
    let app = build_router(state);

    let create_rule = |name: &str, is_active: bool, source: &str, language: &str, severity: &str, confidence: &str| {
        json!({
            "name": name,
            "pattern_yaml": format!("rules:\\n  - id: {}\\n    languages: [python]\\n    severity: WARNING\\n    message: demo\\n    pattern: dangerous_call", name.replace(' ', "-")),
            "language": language,
            "severity": severity,
            "source": source,
            "confidence": confidence,
            "correct": true,
            "is_active": is_active
        })
    };

    let alpha_response = app
        .clone()
        .oneshot(
            Request::builder()
                .method(Method::POST)
                .uri("/api/v1/static-tasks/rules/upload/json")
                .header("content-type", "application/json")
                .body(Body::from(create_rule("auth-alpha", false, "json", "python", "WARNING", "MEDIUM").to_string()))
                .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(alpha_response.status(), StatusCode::OK);
    let alpha_json: Value =
        serde_json::from_slice(&to_bytes(alpha_response.into_body(), usize::MAX).await.unwrap())
            .unwrap();
    let alpha_rule_id = alpha_json["id"].as_str().unwrap().to_string();

    let beta_response = app
        .clone()
        .oneshot(
            Request::builder()
                .method(Method::POST)
                .uri("/api/v1/static-tasks/rules/upload/json")
                .header("content-type", "application/json")
                .body(Body::from(create_rule("auth-beta", true, "upload", "javascript", "ERROR", "HIGH").to_string()))
                .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(beta_response.status(), StatusCode::OK);
    let beta_json: Value =
        serde_json::from_slice(&to_bytes(beta_response.into_body(), usize::MAX).await.unwrap())
            .unwrap();
    let beta_rule_id = beta_json["id"].as_str().unwrap().to_string();

    let select_by_keyword = app
        .clone()
        .oneshot(
            Request::builder()
                .method(Method::POST)
                .uri("/api/v1/static-tasks/rules/select")
                .header("content-type", "application/json")
                .body(Body::from(
                    json!({
                        "keyword": "auth-",
                        "current_is_active": false,
                        "is_active": true
                    })
                    .to_string(),
                ))
                .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(select_by_keyword.status(), StatusCode::OK);
    let select_by_keyword_json: Value = serde_json::from_slice(
        &to_bytes(select_by_keyword.into_body(), usize::MAX)
            .await
            .unwrap(),
    )
    .unwrap();
    assert_eq!(select_by_keyword_json["updated_count"], 1);
    assert_eq!(select_by_keyword_json["is_active"], true);

    let alpha_detail = app
        .clone()
        .oneshot(
            Request::get(format!("/api/v1/static-tasks/rules/{alpha_rule_id}"))
                .body(Body::empty())
                .unwrap(),
        )
        .await
        .unwrap();
    let alpha_detail_json: Value =
        serde_json::from_slice(&to_bytes(alpha_detail.into_body(), usize::MAX).await.unwrap())
            .unwrap();
    assert_eq!(alpha_detail_json["is_active"], true);

    let beta_detail = app
        .clone()
        .oneshot(
            Request::get(format!("/api/v1/static-tasks/rules/{beta_rule_id}"))
                .body(Body::empty())
                .unwrap(),
        )
        .await
        .unwrap();
    let beta_detail_json: Value =
        serde_json::from_slice(&to_bytes(beta_detail.into_body(), usize::MAX).await.unwrap())
            .unwrap();
    assert_eq!(beta_detail_json["is_active"], true);

    let select_by_rule_ids = app
        .clone()
        .oneshot(
            Request::builder()
                .method(Method::POST)
                .uri("/api/v1/static-tasks/rules/select")
                .header("content-type", "application/json")
                .body(Body::from(
                    json!({
                        "rule_ids": [alpha_rule_id],
                        "is_active": false
                    })
                    .to_string(),
                ))
                .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(select_by_rule_ids.status(), StatusCode::OK);
    let select_by_rule_ids_json: Value = serde_json::from_slice(
        &to_bytes(select_by_rule_ids.into_body(), usize::MAX)
            .await
            .unwrap(),
    )
    .unwrap();
    assert_eq!(select_by_rule_ids_json["updated_count"], 1);
    assert_eq!(select_by_rule_ids_json["is_active"], false);

    let alpha_after_rule_ids = app
        .clone()
        .oneshot(
            Request::get(format!("/api/v1/static-tasks/rules/{alpha_rule_id}"))
                .body(Body::empty())
                .unwrap(),
        )
        .await
        .unwrap();
    let alpha_after_rule_ids_json: Value = serde_json::from_slice(
        &to_bytes(alpha_after_rule_ids.into_body(), usize::MAX)
            .await
            .unwrap(),
    )
    .unwrap();
    assert_eq!(alpha_after_rule_ids_json["is_active"], false);

    let beta_after_rule_ids = app
        .clone()
        .oneshot(
            Request::get(format!("/api/v1/static-tasks/rules/{beta_rule_id}"))
                .body(Body::empty())
                .unwrap(),
        )
        .await
        .unwrap();
    let beta_after_rule_ids_json: Value = serde_json::from_slice(
        &to_bytes(beta_after_rule_ids.into_body(), usize::MAX)
            .await
            .unwrap(),
    )
    .unwrap();
    assert_eq!(beta_after_rule_ids_json["is_active"], true);

    let invalid_rule_ids = app
        .clone()
        .oneshot(
            Request::builder()
                .method(Method::POST)
                .uri("/api/v1/static-tasks/rules/select")
                .header("content-type", "application/json")
                .body(Body::from(
                    json!({
                        "rule_ids": "not-an-array",
                        "is_active": true
                    })
                    .to_string(),
                ))
                .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(invalid_rule_ids.status(), StatusCode::BAD_REQUEST);

    let invalid_rule_ids_item = app
        .clone()
        .oneshot(
            Request::builder()
                .method(Method::POST)
                .uri("/api/v1/static-tasks/rules/select")
                .header("content-type", "application/json")
                .body(Body::from(
                    json!({
                        "rule_ids": [123],
                        "is_active": true
                    })
                    .to_string(),
                ))
                .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(invalid_rule_ids_item.status(), StatusCode::BAD_REQUEST);

    let invalid_current_is_active = app
        .clone()
        .oneshot(
            Request::builder()
                .method(Method::POST)
                .uri("/api/v1/static-tasks/rules/select")
                .header("content-type", "application/json")
                .body(Body::from(
                    json!({
                        "keyword": "auth-",
                        "current_is_active": "false",
                        "is_active": true
                    })
                    .to_string(),
                ))
                .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(invalid_current_is_active.status(), StatusCode::BAD_REQUEST);

    let select_by_dimensions = app
        .clone()
        .oneshot(
            Request::builder()
                .method(Method::POST)
                .uri("/api/v1/static-tasks/rules/select")
                .header("content-type", "application/json")
                .body(Body::from(
                    json!({
                        "source": "upload",
                        "language": "javascript",
                        "severity": "ERROR",
                        "confidence": "HIGH",
                        "current_is_active": true,
                        "is_active": false
                    })
                    .to_string(),
                ))
                .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(select_by_dimensions.status(), StatusCode::OK);
    let select_by_dimensions_json: Value = serde_json::from_slice(
        &to_bytes(select_by_dimensions.into_body(), usize::MAX)
            .await
            .unwrap(),
    )
    .unwrap();
    assert_eq!(select_by_dimensions_json["updated_count"], 1);

    let alpha_after = app
        .clone()
        .oneshot(
            Request::get(format!("/api/v1/static-tasks/rules/{alpha_rule_id}"))
                .body(Body::empty())
                .unwrap(),
        )
        .await
        .unwrap();
    let alpha_after_json: Value =
        serde_json::from_slice(&to_bytes(alpha_after.into_body(), usize::MAX).await.unwrap())
            .unwrap();
    assert_eq!(alpha_after_json["is_active"], false);

    let beta_after = app
        .clone()
        .oneshot(
            Request::get(format!("/api/v1/static-tasks/rules/{beta_rule_id}"))
                .body(Body::empty())
                .unwrap(),
        )
        .await
        .unwrap();
    let beta_after_json: Value =
        serde_json::from_slice(&to_bytes(beta_after.into_body(), usize::MAX).await.unwrap())
            .unwrap();
    assert_eq!(beta_after_json["is_active"], false);
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

#[tokio::test]
async fn agent_test_streams_emit_structured_tool_and_result_events() {
    let state = AppState::from_config(isolated_test_config("agent-test-events"))
        .await
        .expect("state should build");
    let app = build_router(state);

    let response = app
        .oneshot(
            Request::builder()
                .method(Method::POST)
                .uri("/api/v1/agent-test/recon/run")
                .header("content-type", "application/json")
                .body(Body::from(
                    json!({
                        "project_path": "/tmp/demo-project",
                        "project_name": "demo-project",
                        "framework_hint": "fastapi",
                        "max_iterations": 3
                    })
                    .to_string(),
                ))
                .unwrap(),
        )
        .await
        .unwrap();

    assert_eq!(response.status(), StatusCode::OK);
    assert_eq!(response.headers()["content-type"], "text/event-stream");
    let body = String::from_utf8(
        to_bytes(response.into_body(), usize::MAX)
            .await
            .unwrap()
            .to_vec(),
    )
    .unwrap();
    let mut events = Vec::new();
    for chunk in body.split("\n\n") {
        if let Some(line) = chunk.lines().find(|line| line.starts_with("data: ")) {
            let payload = serde_json::from_str::<Value>(&line[6..]).unwrap();
            events.push(payload);
        }
    }

    let event_types = events
        .iter()
        .filter_map(|event| event.get("type").and_then(Value::as_str))
        .collect::<Vec<_>>();
    assert!(event_types.contains(&"phase_start"));
    assert!(event_types.contains(&"tool_call"));
    assert!(event_types.contains(&"tool_result"));
    assert!(event_types.contains(&"queue_snapshot"));
    assert!(event_types.contains(&"result"));
    assert!(event_types.contains(&"done"));

    let tool_call = events
        .iter()
        .find(|event| event["type"] == "tool_call")
        .expect("tool_call event missing");
    assert_eq!(tool_call["tool_name"], "prepare_project");
    assert_eq!(tool_call["tool_input"]["project_name"], "demo-project");

    let tool_result = events
        .iter()
        .find(|event| event["type"] == "tool_result")
        .expect("tool_result event missing");
    assert_eq!(tool_result["tool_name"], "prepare_project");
    assert!(tool_result["tool_output"]
        .as_str()
        .is_some_and(|value| value.contains("prepared")));

    let queue_snapshot = events
        .iter()
        .find(|event| event["type"] == "queue_snapshot")
        .expect("queue_snapshot event missing");
    assert_eq!(queue_snapshot["data"]["recon"]["label"], "风险点队列");

    let result = events
        .iter()
        .find(|event| event["type"] == "result")
        .expect("result event missing");
    assert_eq!(result["data"]["project_name"], "demo-project");
    assert_eq!(result["data"]["test_mode"], "recon");
}
