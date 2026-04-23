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

async fn seed_agent_report_findings(state: &AppState, task_id: &str) -> (String, String) {
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

async fn seed_agent_result_state(state: &AppState, task_id: &str) -> (String, String, String) {
    let mut snapshot = task_state::load_snapshot(state).await.unwrap();
    let record = snapshot.agent_tasks.get_mut(task_id).unwrap();
    record.status = "completed".to_string();
    record.current_phase = Some("reporting".to_string());
    record.current_step = Some("agent findings ready".to_string());
    record.progress_percentage = 100.0;
    record.started_at = Some("2026-04-12T10:00:00Z".to_string());
    record.completed_at = Some("2026-04-12T10:30:00Z".to_string());
    record.total_files = 12;
    record.indexed_files = 12;
    record.analyzed_files = 10;
    record.total_chunks = 22;
    record.files_with_findings = 2;
    record.findings.clear();
    record.checkpoints.clear();
    let verified_id = Uuid::new_v4().to_string();
    let pending_id = Uuid::new_v4().to_string();
    let false_positive_id = Uuid::new_v4().to_string();
    record.findings.push(task_state::AgentFindingRecord {
        id: verified_id.clone(),
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
        verification_evidence: Some("verified by rust integration test".to_string()),
        suggestion: Some("use parameterized query".to_string()),
        confidence: Some(0.95),
        created_at: "2026-04-12T10:00:00Z".to_string(),
        ..Default::default()
    });
    record.findings.push(task_state::AgentFindingRecord {
        id: pending_id.clone(),
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
    record.findings.push(task_state::AgentFindingRecord {
        id: false_positive_id.clone(),
        task_id: task_id.to_string(),
        vulnerability_type: "xss".to_string(),
        severity: "low".to_string(),
        title: "Dismissed XSS alert".to_string(),
        display_title: Some("已驳回的 XSS 误报".to_string()),
        description: Some("template escapes output".to_string()),
        description_markdown: Some("模板层已统一编码，这条告警判定为误报。".to_string()),
        file_path: Some("src/web/search.tsx".to_string()),
        line_start: Some(84),
        line_end: Some(84),
        resolved_file_path: Some("src/web/search.tsx".to_string()),
        resolved_line_start: Some(84),
        status: "false_positive".to_string(),
        is_verified: false,
        verdict: Some("false_positive".to_string()),
        authenticity: Some("false_positive".to_string()),
        verification_evidence: Some("renderer already escapes user input".to_string()),
        confidence: Some(0.12),
        created_at: "2026-04-12T10:08:00Z".to_string(),
        ..Default::default()
    });
    record.findings_count = 2;
    record.verified_count = 1;
    record.false_positive_count = 1;
    record.critical_count = 0;
    record.high_count = 1;
    record.medium_count = 1;
    record.low_count = 0;
    record.verified_high_count = 1;
    record.verified_medium_count = 0;
    record.verified_low_count = 0;
    record.security_score = Some(85.0);
    record.quality_score = 92.0;
    record.agent_tree = vec![
        json!({
            "id": format!("root-{task_id}"),
            "agent_id": format!("root-{task_id}"),
            "agent_name": "RustAgentRoot",
            "agent_type": "root",
            "parent_agent_id": Value::Null,
            "depth": 0,
            "task_description": "orchestrate agent audit",
            "status": "completed",
            "result_summary": "aggregated agent results",
            "findings_count": 2,
            "verified_findings_count": 1,
            "iterations": 4,
            "tokens_used": 320,
            "tool_calls": 6,
            "duration_ms": 120000,
            "children": Vec::<Value>::new(),
        }),
        json!({
            "id": format!("analysis-{task_id}"),
            "agent_id": format!("analysis-{task_id}"),
            "agent_name": "RustAnalysisAgent",
            "agent_type": "analysis",
            "parent_agent_id": format!("root-{task_id}"),
            "depth": 1,
            "task_description": "trace suspicious sinks",
            "status": "completed",
            "result_summary": "found 2 candidate issues",
            "findings_count": 2,
            "verified_findings_count": 0,
            "iterations": 3,
            "tokens_used": 180,
            "tool_calls": 4,
            "duration_ms": 80000,
            "children": Vec::<Value>::new(),
        }),
        json!({
            "id": format!("verify-{task_id}"),
            "agent_id": format!("verify-{task_id}"),
            "agent_name": "RustVerificationAgent",
            "agent_type": "verification",
            "parent_agent_id": format!("root-{task_id}"),
            "depth": 1,
            "task_description": "confirm exploitability",
            "status": "completed",
            "result_summary": "verified 1 finding and rejected 1 alert",
            "findings_count": 2,
            "verified_findings_count": 1,
            "iterations": 1,
            "tokens_used": 96,
            "tool_calls": 2,
            "duration_ms": 24000,
            "children": Vec::<Value>::new(),
        }),
    ];
    record.checkpoints.push(task_state::AgentCheckpointRecord {
        id: Uuid::new_v4().to_string(),
        task_id: task_id.to_string(),
        agent_id: format!("root-{task_id}"),
        agent_name: "RustAgentRoot".to_string(),
        agent_type: "root".to_string(),
        parent_agent_id: None,
        iteration: 0,
        status: "created".to_string(),
        total_tokens: 0,
        tool_calls: 0,
        findings_count: 0,
        checkpoint_type: "auto".to_string(),
        checkpoint_name: Some("created".to_string()),
        created_at: Some("2026-04-12T10:00:00Z".to_string()),
        state_data: json!({"phase": "created"}),
        metadata: Some(json!({"source": "seed"})),
    });
    record.checkpoints.push(task_state::AgentCheckpointRecord {
        id: Uuid::new_v4().to_string(),
        task_id: task_id.to_string(),
        agent_id: format!("analysis-{task_id}"),
        agent_name: "RustAnalysisAgent".to_string(),
        agent_type: "analysis".to_string(),
        parent_agent_id: Some(format!("root-{task_id}")),
        iteration: 3,
        status: "completed".to_string(),
        total_tokens: 180,
        tool_calls: 4,
        findings_count: 2,
        checkpoint_type: "auto".to_string(),
        checkpoint_name: Some("analysis-complete".to_string()),
        created_at: Some("2026-04-12T10:20:00Z".to_string()),
        state_data: json!({"phase": "analysis"}),
        metadata: Some(json!({"source": "seed"})),
    });
    record.checkpoints.push(task_state::AgentCheckpointRecord {
        id: Uuid::new_v4().to_string(),
        task_id: task_id.to_string(),
        agent_id: format!("verify-{task_id}"),
        agent_name: "RustVerificationAgent".to_string(),
        agent_type: "verification".to_string(),
        parent_agent_id: Some(format!("root-{task_id}")),
        iteration: 1,
        status: "completed".to_string(),
        total_tokens: 96,
        tool_calls: 2,
        findings_count: 2,
        checkpoint_type: "final".to_string(),
        checkpoint_name: Some("verification-complete".to_string()),
        created_at: Some("2026-04-12T10:29:00Z".to_string()),
        state_data: json!({"phase": "verification"}),
        metadata: Some(json!({"source": "seed"})),
    });
    task_state::save_snapshot(state, &snapshot).await.unwrap();
    (verified_id, pending_id, false_positive_id)
}

async fn seed_agent_lifecycle_state(state: &AppState, task_id: &str) {
    let mut snapshot = task_state::load_snapshot(state).await.unwrap();
    let record = snapshot.agent_tasks.get_mut(task_id).unwrap();
    record.status = "running".to_string();
    record.current_phase = Some("analysis".to_string());
    record.current_step = Some("streaming events".to_string());
    record.progress_percentage = 64.0;
    record.started_at = Some("2026-04-12T11:00:00Z".to_string());
    record.total_files = 9;
    record.indexed_files = 9;
    record.analyzed_files = 6;
    record.total_chunks = 18;
    record.files_with_findings = 2;
    record.findings.clear();
    record.events.clear();
    record.checkpoints.clear();
    record.findings.push(task_state::AgentFindingRecord {
        id: Uuid::new_v4().to_string(),
        task_id: task_id.to_string(),
        vulnerability_type: "sql_injection".to_string(),
        severity: "critical".to_string(),
        title: "Critical SQL injection".to_string(),
        status: "verified".to_string(),
        is_verified: true,
        verdict: Some("confirmed".to_string()),
        authenticity: Some("confirmed".to_string()),
        created_at: "2026-04-12T11:05:00Z".to_string(),
        ..Default::default()
    });
    record.findings.push(task_state::AgentFindingRecord {
        id: Uuid::new_v4().to_string(),
        task_id: task_id.to_string(),
        vulnerability_type: "xss".to_string(),
        severity: "high".to_string(),
        title: "Pending reflected xss".to_string(),
        status: "pending".to_string(),
        is_verified: false,
        verdict: Some("likely".to_string()),
        authenticity: Some("likely".to_string()),
        created_at: "2026-04-12T11:06:00Z".to_string(),
        ..Default::default()
    });
    record.findings.push(task_state::AgentFindingRecord {
        id: Uuid::new_v4().to_string(),
        task_id: task_id.to_string(),
        vulnerability_type: "xss".to_string(),
        severity: "medium".to_string(),
        title: "Dismissed duplicate xss".to_string(),
        status: "false_positive".to_string(),
        is_verified: false,
        verdict: Some("false_positive".to_string()),
        authenticity: Some("false_positive".to_string()),
        created_at: "2026-04-12T11:07:00Z".to_string(),
        ..Default::default()
    });
    record.findings_count = 2;
    record.verified_count = 1;
    record.false_positive_count = 1;
    record.critical_count = 1;
    record.high_count = 1;
    record.medium_count = 0;
    record.low_count = 0;
    record.verified_critical_count = 1;
    record.verified_high_count = 0;
    record.verified_medium_count = 0;
    record.verified_low_count = 0;
    record.tool_calls_count = 5;
    record.tokens_used = 210;
    record.tool_evidence_protocol = Some("native_v1".to_string());
    record.events.push(task_state::AgentEventRecord {
        id: Uuid::new_v4().to_string(),
        task_id: task_id.to_string(),
        event_type: "phase_start".to_string(),
        phase: Some("analysis".to_string()),
        message: Some("analysis started".to_string()),
        tool_name: None,
        tool_input: None,
        tool_output: None,
        tool_duration_ms: None,
        finding_id: None,
        tokens_used: None,
        metadata: None,
        sequence: 1,
        timestamp: "2026-04-12T11:00:01Z".to_string(),
    });
    record.events.push(task_state::AgentEventRecord {
        id: Uuid::new_v4().to_string(),
        task_id: task_id.to_string(),
        event_type: "tool_call".to_string(),
        phase: Some("analysis".to_string()),
        message: Some("search codebase".to_string()),
        tool_name: Some("search_code".to_string()),
        tool_input: Some(json!({"pattern": "SELECT"})),
        tool_output: Some(json!({
            "result": "matched login.ts",
            "metadata": {
                "render_type": "analysis_summary",
                "display_command": "search_code",
                "command_chain": ["search_code"],
                "entries": [],
            }
        })),
        tool_duration_ms: Some(320),
        finding_id: None,
        tokens_used: Some(24),
        metadata: Some(json!({"agent": "analysis"})),
        sequence: 2,
        timestamp: "2026-04-12T11:00:05Z".to_string(),
    });
    record.events.push(task_state::AgentEventRecord {
        id: Uuid::new_v4().to_string(),
        task_id: task_id.to_string(),
        event_type: "finding".to_string(),
        phase: Some("analysis".to_string()),
        message: Some("captured critical sql injection".to_string()),
        tool_name: None,
        tool_input: None,
        tool_output: None,
        tool_duration_ms: None,
        finding_id: record.findings.first().map(|finding| finding.id.clone()),
        tokens_used: None,
        metadata: Some(json!({"severity": "critical"})),
        sequence: 3,
        timestamp: "2026-04-12T11:00:09Z".to_string(),
    });
    task_state::save_snapshot(state, &snapshot).await.unwrap();
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
    let create_json: Value = serde_json::from_slice(
        &to_bytes(create_response.into_body(), usize::MAX)
            .await
            .unwrap(),
    )
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
    let events_json: Value = serde_json::from_slice(
        &to_bytes(events_response.into_body(), usize::MAX)
            .await
            .unwrap(),
    )
    .unwrap();
    assert!(events_json
        .as_array()
        .is_some_and(|items| !items.is_empty()));

    let stream_response = app
        .clone()
        .oneshot(
            Request::get(format!(
                "/api/v1/agent-tasks/{task_id}/events?after_sequence=0"
            ))
            .body(Body::empty())
            .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(stream_response.status(), StatusCode::OK);
    assert_eq!(
        stream_response.headers()["content-type"],
        "text/event-stream"
    );

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
    let findings_json: Value = serde_json::from_slice(
        &to_bytes(findings_response.into_body(), usize::MAX)
            .await
            .unwrap(),
    )
    .unwrap();
    assert_eq!(findings_json.as_array().unwrap().len(), 2);

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
    let summary_json: Value = serde_json::from_slice(
        &to_bytes(summary_response.into_body(), usize::MAX)
            .await
            .unwrap(),
    )
    .unwrap();
    assert_eq!(summary_json["statistics"]["findings_count"], 2);
    assert_eq!(
        summary_json["vulnerability_types"]["sql_injection"]["total"],
        1
    );
    assert_eq!(summary_json["vulnerability_types"]["xss"]["total"], 1);

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
    let agent_tree_json: Value = serde_json::from_slice(
        &to_bytes(agent_tree_response.into_body(), usize::MAX)
            .await
            .unwrap(),
    )
    .unwrap();
    assert_eq!(agent_tree_json["total_agents"], 3);
    assert_eq!(agent_tree_json["nodes"].as_array().unwrap().len(), 3);

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
    let checkpoints_json: Value = serde_json::from_slice(
        &to_bytes(checkpoints_response.into_body(), usize::MAX)
            .await
            .unwrap(),
    )
    .unwrap();
    assert!(checkpoints_json.as_array().unwrap().len() >= 4);

    let report_response = app
        .clone()
        .oneshot(
            Request::get(format!(
                "/api/v1/agent-tasks/{task_id}/report?format=markdown"
            ))
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
async fn create_agent_task_snapshots_enabled_prompt_skill_runtime_in_audit_scope() {
    let state = AppState::from_config(isolated_test_config("agent-task-prompt-runtime-enabled"))
        .await
        .expect("state should build");
    let app = build_router(state);
    let project_id = create_project(&app).await;

    for request_body in [
        json!({
            "name": "Global Analysis Prompt",
            "content": "Global analysis instructions.",
            "scope": "global",
            "is_active": true
        }),
        json!({
            "name": "Agent Analysis Prompt",
            "content": "Agent-specific analysis instructions.",
            "scope": "agent_specific",
            "agent_key": "analysis",
            "is_active": true
        }),
    ] {
        let response = app
            .clone()
            .oneshot(
                Request::builder()
                    .method(Method::POST)
                    .uri("/api/v1/skills/prompt-skills")
                    .header("content-type", "application/json")
                    .body(Body::from(request_body.to_string()))
                    .unwrap(),
            )
            .await
            .unwrap();
        assert_eq!(response.status(), StatusCode::OK);
    }

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
                        "name": "prompt-runtime-enabled",
                        "description": "snapshot effective prompt skills when enabled",
                        "max_iterations": 2,
                        "use_prompt_skills": true,
                        "audit_scope": {
                            "custom_flag": true
                        }
                    })
                    .to_string(),
                ))
                .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(create_response.status(), StatusCode::OK);
    let create_json: Value = serde_json::from_slice(
        &to_bytes(create_response.into_body(), usize::MAX)
            .await
            .unwrap(),
    )
    .unwrap();

    assert_eq!(create_json["audit_scope"]["custom_flag"], true);
    let prompt_skill_runtime = &create_json["audit_scope"]["prompt_skill_runtime"];
    assert_eq!(
        prompt_skill_runtime["source"],
        "rust_prompt_effective_snapshot"
    );
    assert_eq!(prompt_skill_runtime["requested"], true);
    assert_eq!(prompt_skill_runtime["enabled"], true);

    let agent_keys = prompt_skill_runtime["agent_keys"].as_array().unwrap();
    assert_eq!(agent_keys.len(), 5);
    assert!(agent_keys
        .iter()
        .any(|agent_key| agent_key.as_str() == Some("analysis")));

    let effective_analysis = &prompt_skill_runtime["effective_by_agent"]["analysis"];
    assert_eq!(effective_analysis["runtime_ready"], true);
    assert_eq!(
        effective_analysis["reason"],
        "builtin_template+global_custom+agent_specific_custom"
    );

    let effective_content = effective_analysis["effective_content"].as_str().unwrap();
    let builtin_index = effective_content
        .find("围绕单风险点做证据闭环")
        .expect("builtin analysis prompt should be included");
    let global_index = effective_content
        .find("Global analysis instructions.")
        .expect("global analysis prompt should be included");
    let agent_index = effective_content
        .find("Agent-specific analysis instructions.")
        .expect("agent analysis prompt should be included");
    assert!(builtin_index < global_index);
    assert!(global_index < agent_index);
}

#[tokio::test]
async fn create_agent_task_snapshots_disabled_prompt_skill_runtime_in_audit_scope() {
    let state = AppState::from_config(isolated_test_config("agent-task-prompt-runtime-disabled"))
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
                        "name": "prompt-runtime-disabled",
                        "description": "snapshot effective prompt skills when disabled",
                        "max_iterations": 2,
                        "use_prompt_skills": false,
                        "audit_scope": {
                            "secondary_flag": "kept"
                        }
                    })
                    .to_string(),
                ))
                .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(create_response.status(), StatusCode::OK);
    let create_json: Value = serde_json::from_slice(
        &to_bytes(create_response.into_body(), usize::MAX)
            .await
            .unwrap(),
    )
    .unwrap();

    assert_eq!(create_json["audit_scope"]["secondary_flag"], "kept");
    let prompt_skill_runtime = &create_json["audit_scope"]["prompt_skill_runtime"];
    assert_eq!(
        prompt_skill_runtime["source"],
        "rust_prompt_effective_snapshot"
    );
    assert_eq!(prompt_skill_runtime["requested"], false);
    assert_eq!(prompt_skill_runtime["enabled"], false);
    assert_eq!(prompt_skill_runtime["reason"], "disabled_by_request");
    assert_eq!(prompt_skill_runtime["effective_by_agent"], json!({}));
}

#[tokio::test]
async fn create_agent_task_defaults_prompt_skill_runtime_to_disabled_when_flag_is_omitted() {
    let state = AppState::from_config(isolated_test_config(
        "agent-task-prompt-runtime-default-disabled",
    ))
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
                        "name": "prompt-runtime-default-disabled",
                        "description": "legacy default compatibility",
                        "max_iterations": 2,
                        "audit_scope": {
                            "custom_flag": true
                        }
                    })
                    .to_string(),
                ))
                .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(create_response.status(), StatusCode::OK);
    let create_json: Value = serde_json::from_slice(
        &to_bytes(create_response.into_body(), usize::MAX)
            .await
            .unwrap(),
    )
    .unwrap();

    let prompt_skill_runtime = &create_json["audit_scope"]["prompt_skill_runtime"];
    assert_eq!(prompt_skill_runtime["requested"], false);
    assert_eq!(prompt_skill_runtime["enabled"], false);
    assert_eq!(prompt_skill_runtime["reason"], "disabled_by_request");
    assert_eq!(prompt_skill_runtime["effective_by_agent"], json!({}));
}

#[tokio::test]
async fn create_agent_task_rejects_non_object_audit_scope() {
    let state = AppState::from_config(isolated_test_config("agent-task-invalid-audit-scope"))
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
                        "name": "invalid-audit-scope",
                        "description": "invalid audit scope contract",
                        "max_iterations": 2,
                        "use_prompt_skills": true,
                        "audit_scope": "not-an-object"
                    })
                    .to_string(),
                ))
                .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(create_response.status(), StatusCode::BAD_REQUEST);
    let error_json: Value = serde_json::from_slice(
        &to_bytes(create_response.into_body(), usize::MAX)
            .await
            .unwrap(),
    )
    .unwrap();
    assert_eq!(
        error_json["error"],
        "audit_scope must be an object when provided, got string"
    );
}

#[tokio::test]
async fn create_agent_task_rejects_null_audit_scope() {
    let state = AppState::from_config(isolated_test_config("agent-task-null-audit-scope"))
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
                        "name": "null-audit-scope",
                        "description": "null audit scope contract",
                        "max_iterations": 2,
                        "audit_scope": Value::Null
                    })
                    .to_string(),
                ))
                .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(create_response.status(), StatusCode::BAD_REQUEST);
    let error_json: Value = serde_json::from_slice(
        &to_bytes(create_response.into_body(), usize::MAX)
            .await
            .unwrap(),
    )
    .unwrap();
    assert_eq!(
        error_json["error"],
        "audit_scope must be an object when provided, got null"
    );
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
    let create_json: Value = serde_json::from_slice(
        &to_bytes(create_response.into_body(), usize::MAX)
            .await
            .unwrap(),
    )
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
    let markdown_body = String::from_utf8(
        to_bytes(markdown_response.into_body(), usize::MAX)
            .await
            .unwrap()
            .to_vec(),
    )
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
    let json_payload: Value = serde_json::from_slice(
        &to_bytes(json_response.into_body(), usize::MAX)
            .await
            .unwrap(),
    )
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
    let pdf_body = to_bytes(pdf_response.into_body(), usize::MAX)
        .await
        .unwrap();
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
    assert_eq!(
        finding_json_response.headers()["content-type"],
        "application/json"
    );
    let finding_json: Value = serde_json::from_slice(
        &to_bytes(finding_json_response.into_body(), usize::MAX)
            .await
            .unwrap(),
    )
    .unwrap();
    assert_eq!(
        finding_json["report_metadata"]["finding_id"],
        first_finding_id
    );
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
async fn agent_task_result_routes_support_filters_summary_and_checkpoint_queries() {
    let state = AppState::from_config(isolated_test_config("agent-task-results"))
        .await
        .expect("state should build");
    let app = build_router(state.clone());
    let project_id = create_project_with_name(&app, "结果面项目").await;

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
                        "name": "results-task",
                        "description": "result routes contract test",
                        "max_iterations": 2
                    })
                    .to_string(),
                ))
                .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(create_response.status(), StatusCode::OK);
    let create_json: Value = serde_json::from_slice(
        &to_bytes(create_response.into_body(), usize::MAX)
            .await
            .unwrap(),
    )
    .unwrap();
    let task_id = create_json["id"].as_str().unwrap().to_string();
    let (verified_id, pending_id, false_positive_id) =
        seed_agent_result_state(&state, &task_id).await;

    let visible_findings_response = app
        .clone()
        .oneshot(
            Request::get(format!(
                "/api/v1/agent-tasks/{task_id}/findings?include_false_positive=false&limit=10"
            ))
            .body(Body::empty())
            .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(visible_findings_response.status(), StatusCode::OK);
    let visible_findings: Value = serde_json::from_slice(
        &to_bytes(visible_findings_response.into_body(), usize::MAX)
            .await
            .unwrap(),
    )
    .unwrap();
    assert_eq!(visible_findings.as_array().unwrap().len(), 2);
    assert_eq!(visible_findings[0]["id"], verified_id);
    assert_eq!(visible_findings[1]["id"], pending_id);

    let verified_only_response = app
        .clone()
        .oneshot(
            Request::get(format!(
                "/api/v1/agent-tasks/{task_id}/findings?verified_only=true&include_false_positive=false"
            ))
            .body(Body::empty())
            .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(verified_only_response.status(), StatusCode::OK);
    let verified_only_json: Value = serde_json::from_slice(
        &to_bytes(verified_only_response.into_body(), usize::MAX)
            .await
            .unwrap(),
    )
    .unwrap();
    assert_eq!(verified_only_json.as_array().unwrap().len(), 1);
    assert_eq!(verified_only_json[0]["id"], verified_id);

    let severity_filtered_response = app
        .clone()
        .oneshot(
            Request::get(format!(
                "/api/v1/agent-tasks/{task_id}/findings?severity=medium&vulnerability_type=xss&include_false_positive=false"
            ))
            .body(Body::empty())
            .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(severity_filtered_response.status(), StatusCode::OK);
    let severity_filtered_json: Value = serde_json::from_slice(
        &to_bytes(severity_filtered_response.into_body(), usize::MAX)
            .await
            .unwrap(),
    )
    .unwrap();
    assert_eq!(severity_filtered_json.as_array().unwrap().len(), 1);
    assert_eq!(severity_filtered_json[0]["id"], pending_id);

    let hidden_false_positive_response = app
        .clone()
        .oneshot(
            Request::get(format!(
                "/api/v1/agent-tasks/{task_id}/findings/{false_positive_id}?include_false_positive=false"
            ))
            .body(Body::empty())
            .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(
        hidden_false_positive_response.status(),
        StatusCode::NOT_FOUND
    );

    let visible_false_positive_response = app
        .clone()
        .oneshot(
            Request::get(format!(
                "/api/v1/agent-tasks/{task_id}/findings/{false_positive_id}?include_false_positive=true"
            ))
            .body(Body::empty())
            .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(visible_false_positive_response.status(), StatusCode::OK);

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
    let summary_json: Value = serde_json::from_slice(
        &to_bytes(summary_response.into_body(), usize::MAX)
            .await
            .unwrap(),
    )
    .unwrap();
    assert_eq!(summary_json["statistics"]["findings_count"], 2);
    assert_eq!(summary_json["statistics"]["verified_count"], 1);
    assert_eq!(summary_json["statistics"]["false_positive_count"], 1);
    assert_eq!(summary_json["severity_distribution"]["high"], 1);
    assert_eq!(summary_json["severity_distribution"]["medium"], 1);
    assert_eq!(
        summary_json["vulnerability_types"]["sql_injection"]["total"],
        1
    );
    assert_eq!(
        summary_json["vulnerability_types"]["sql_injection"]["verified"],
        1
    );
    assert_eq!(summary_json["vulnerability_types"]["xss"]["total"], 1);
    assert_eq!(summary_json["vulnerability_types"]["xss"]["verified"], 0);

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
    let agent_tree_json: Value = serde_json::from_slice(
        &to_bytes(agent_tree_response.into_body(), usize::MAX)
            .await
            .unwrap(),
    )
    .unwrap();
    assert_eq!(agent_tree_json["total_agents"], 3);
    assert_eq!(agent_tree_json["verified_total_findings"], 1);
    assert_eq!(agent_tree_json["nodes"][0]["findings_count"], 2);
    assert_eq!(agent_tree_json["nodes"][0]["verified_findings_count"], 1);

    let checkpoints_response = app
        .clone()
        .oneshot(
            Request::get(format!(
                "/api/v1/agent-tasks/{task_id}/checkpoints?agent_id=verify-{task_id}&limit=1"
            ))
            .body(Body::empty())
            .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(checkpoints_response.status(), StatusCode::OK);
    let checkpoints_json: Value = serde_json::from_slice(
        &to_bytes(checkpoints_response.into_body(), usize::MAX)
            .await
            .unwrap(),
    )
    .unwrap();
    assert_eq!(checkpoints_json.as_array().unwrap().len(), 1);
    assert_eq!(checkpoints_json[0]["agent_id"], format!("verify-{task_id}"));
}

#[tokio::test]
async fn agent_task_lifecycle_routes_expose_defect_summary_and_paginated_events() {
    let state = AppState::from_config(isolated_test_config("agent-task-lifecycle"))
        .await
        .expect("state should build");
    let app = build_router(state.clone());
    let project_id = create_project_with_name(&app, "生命周期项目").await;

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
                        "name": "lifecycle-task",
                        "description": "lifecycle contract test",
                        "max_iterations": 3,
                        "verification_level": "analysis_with_poc_plan",
                        "target_files": ["src/auth/login.ts"],
                        "exclude_patterns": ["dist/**"]
                    })
                    .to_string(),
                ))
                .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(create_response.status(), StatusCode::OK);
    let create_json: Value = serde_json::from_slice(
        &to_bytes(create_response.into_body(), usize::MAX)
            .await
            .unwrap(),
    )
    .unwrap();
    let task_id = create_json["id"].as_str().unwrap().to_string();
    seed_agent_lifecycle_state(&state, &task_id).await;

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
    let list_json: Value = serde_json::from_slice(
        &to_bytes(list_response.into_body(), usize::MAX)
            .await
            .unwrap(),
    )
    .unwrap();
    let item = &list_json.as_array().unwrap()[0];
    assert_eq!(item["tool_evidence_protocol"], "native_v1");
    assert_eq!(item["verified_critical_count"], 1);
    assert_eq!(item["verified_high_count"], 0);
    assert_eq!(item["defect_summary"]["total_count"], 3);
    assert_eq!(item["defect_summary"]["status_counts"]["pending"], 1);
    assert_eq!(item["defect_summary"]["status_counts"]["verified"], 1);
    assert_eq!(item["defect_summary"]["status_counts"]["false_positive"], 1);

    let detail_response = app
        .clone()
        .oneshot(
            Request::get(format!("/api/v1/agent-tasks/{task_id}"))
                .body(Body::empty())
                .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(detail_response.status(), StatusCode::OK);
    let detail_json: Value = serde_json::from_slice(
        &to_bytes(detail_response.into_body(), usize::MAX)
            .await
            .unwrap(),
    )
    .unwrap();
    assert_eq!(detail_json["target_files"][0], "src/auth/login.ts");
    assert_eq!(detail_json["exclude_patterns"][0], "dist/**");
    assert_eq!(detail_json["verification_level"], "analysis_with_poc_plan");
    assert_eq!(
        detail_json["defect_summary"]["severity_counts"]["critical"],
        1
    );
    assert_eq!(detail_json["defect_summary"]["severity_counts"]["high"], 1);

    let paged_events_response = app
        .clone()
        .oneshot(
            Request::get(format!(
                "/api/v1/agent-tasks/{task_id}/events/list?after_sequence=1&limit=1"
            ))
            .body(Body::empty())
            .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(paged_events_response.status(), StatusCode::OK);
    let paged_events_json: Value = serde_json::from_slice(
        &to_bytes(paged_events_response.into_body(), usize::MAX)
            .await
            .unwrap(),
    )
    .unwrap();
    assert_eq!(paged_events_json.as_array().unwrap().len(), 1);
    assert_eq!(paged_events_json[0]["sequence"], 2);
    assert_eq!(paged_events_json[0]["tool_name"], "search_code");
    assert_eq!(
        paged_events_json[0]["tool_output"]["metadata"]["display_command"],
        "search_code"
    );
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
        "/api/v1/static-tasks/cache/repo-stats",
    ];

    for route in smoke_routes {
        let response = app
            .clone()
            .oneshot(Request::get(route).body(Body::empty()).unwrap())
            .await
            .unwrap();
        assert_eq!(
            response.status(),
            StatusCode::OK,
            "route should be rust-owned: {route}"
        );
    }

    let create_payloads = [(
        "/api/v1/static-tasks/tasks",
        json!({
            "project_id": project_id,
            "name": "opengrep task",
            "rule_ids": [],
            "target_path": "."
        }),
    )];

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
        assert_eq!(
            response.status(),
            StatusCode::OK,
            "create route should work: {route}"
        );
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
    assert!(
        opengrep_progress_json["status"] == "running"
            || opengrep_progress_json["status"] == "failed"
            || opengrep_progress_json["status"] == "completed",
        "unexpected status: {}",
        opengrep_progress_json["status"]
    );
    assert!(opengrep_progress_json["logs"]
        .as_array()
        .is_some_and(|logs| !logs.is_empty()));

    let follow_up_routes = [
        format!("/api/v1/static-tasks/tasks/{}", created_task_ids[0]),
        format!(
            "/api/v1/static-tasks/tasks/{}/findings?limit=20",
            created_task_ids[0]
        ),
    ];

    for route in follow_up_routes {
        let response = app
            .clone()
            .oneshot(Request::get(&route).body(Body::empty()).unwrap())
            .await
            .unwrap();
        assert_eq!(
            response.status(),
            StatusCode::OK,
            "follow-up route should work: {route}"
        );
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
    assert_eq!(opengrep_finding_detail.status(), StatusCode::OK);
    let opengrep_finding_detail_json: Value = serde_json::from_slice(
        &to_bytes(opengrep_finding_detail.into_body(), usize::MAX)
            .await
            .unwrap(),
    )
    .unwrap();
    assert!(opengrep_finding_detail_json.as_array().is_some());
}

#[tokio::test]
async fn opengrep_rule_batch_select_supports_rule_ids_keyword_and_current_state_filters() {
    let state = AppState::from_config(isolated_test_config("opengrep-rule-select"))
        .await
        .expect("state should build");
    let app = build_router(state);

    let create_rule = |name: &str,
                       is_active: bool,
                       source: &str,
                       language: &str,
                       severity: &str,
                       confidence: &str| {
        json!({
            "name": name,
            "pattern_yaml": format!("rules:\n  - id: {}\n    languages:\n      - python\n    severity: WARNING\n    message: demo\n    pattern: dangerous_call($X)", name.replace(' ', "-")),
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
                .body(Body::from(
                    create_rule("auth-alpha", false, "json", "python", "WARNING", "MEDIUM")
                        .to_string(),
                ))
                .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(alpha_response.status(), StatusCode::OK);
    let alpha_json: Value = serde_json::from_slice(
        &to_bytes(alpha_response.into_body(), usize::MAX)
            .await
            .unwrap(),
    )
    .unwrap();
    let alpha_rule_id = alpha_json["id"].as_str().unwrap().to_string();

    let beta_response = app
        .clone()
        .oneshot(
            Request::builder()
                .method(Method::POST)
                .uri("/api/v1/static-tasks/rules/upload/json")
                .header("content-type", "application/json")
                .body(Body::from(
                    create_rule("auth-beta", true, "upload", "javascript", "ERROR", "HIGH")
                        .to_string(),
                ))
                .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(beta_response.status(), StatusCode::OK);
    let beta_json: Value = serde_json::from_slice(
        &to_bytes(beta_response.into_body(), usize::MAX)
            .await
            .unwrap(),
    )
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
    let alpha_detail_json: Value = serde_json::from_slice(
        &to_bytes(alpha_detail.into_body(), usize::MAX)
            .await
            .unwrap(),
    )
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
        assert_eq!(
            response.status(),
            StatusCode::OK,
            "agent-test route should work: {route}"
        );
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

#[tokio::test]
async fn business_logic_agent_test_streams_use_bl_queue_snapshot_contract() {
    let state = AppState::from_config(isolated_test_config("agent-test-business-logic-events"))
        .await
        .expect("state should build");
    let app = build_router(state);

    let response = app
        .oneshot(
            Request::builder()
                .method(Method::POST)
                .uri("/api/v1/agent-test/business-logic-recon/run")
                .header("content-type", "application/json")
                .body(Body::from(
                    json!({
                        "project_path": "/tmp/demo-project",
                        "project_name": "demo-project",
                        "framework_hint": "fastapi",
                        "max_iterations": 4
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

    let queue_snapshot = events
        .iter()
        .find(|event| event["type"] == "queue_snapshot")
        .expect("queue_snapshot event missing");
    assert_eq!(
        queue_snapshot["data"]["bl_recon"]["label"],
        "业务逻辑风险点队列"
    );
    assert_eq!(
        queue_snapshot["data"]["bl_recon"]["peek"][0]["title"],
        "business_logic_recon-candidate"
    );

    let result = events
        .iter()
        .find(|event| event["type"] == "result")
        .expect("result event missing");
    assert_eq!(result["data"]["project_name"], "demo-project");
    assert_eq!(result["data"]["test_mode"], "business_logic_recon");
}

#[tokio::test]
async fn verification_agent_test_snapshot_preserves_duplicate_findings() {
    let state = AppState::from_config(isolated_test_config("agent-test-verification-events"))
        .await
        .expect("state should build");
    let app = build_router(state);
    let duplicate = json!({
        "file_path": "src/auth.rs",
        "line_start": 21,
        "title": "duplicate finding",
        "vulnerability_type": "sql_injection"
    });

    let response = app
        .oneshot(
            Request::builder()
                .method(Method::POST)
                .uri("/api/v1/agent-test/verification/run")
                .header("content-type", "application/json")
                .body(Body::from(
                    json!({
                        "project_path": "/tmp/demo-project",
                        "findings": [duplicate.clone(), duplicate]
                    })
                    .to_string(),
                ))
                .unwrap(),
        )
        .await
        .unwrap();

    assert_eq!(response.status(), StatusCode::OK);
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
            events.push(serde_json::from_str::<Value>(&line[6..]).unwrap());
        }
    }

    let queue_snapshot = events
        .iter()
        .find(|event| event["type"] == "queue_snapshot")
        .expect("queue_snapshot event missing");
    assert_eq!(queue_snapshot["data"]["vuln"]["size"], 2);
    assert_eq!(
        queue_snapshot["data"]["vuln"]["peek"]
            .as_array()
            .expect("peek should be an array")
            .len(),
        2
    );
}

#[tokio::test]
async fn business_logic_analysis_snapshot_uses_supplied_risk_point() {
    let state = AppState::from_config(isolated_test_config(
        "agent-test-business-logic-analysis-events",
    ))
    .await
    .expect("state should build");
    let app = build_router(state);
    let risk_point = json!({
        "title": "provided-business-logic-risk",
        "severity": "high",
        "description": "supplied by request",
        "file_path": "src/checkout.rs",
        "line_start": 77,
        "vulnerability_type": "business_logic_issue",
        "entry_function": "apply_discount",
        "source": "request.body.discount_code",
        "sink": "order.total",
        "input_surface": "http body",
        "trust_boundary": "checkout",
    });

    let response = app
        .oneshot(
            Request::builder()
                .method(Method::POST)
                .uri("/api/v1/agent-test/business-logic-analysis/run")
                .header("content-type", "application/json")
                .body(Body::from(
                    json!({
                        "project_path": "/tmp/demo-project",
                        "risk_point": risk_point,
                    })
                    .to_string(),
                ))
                .unwrap(),
        )
        .await
        .unwrap();

    assert_eq!(response.status(), StatusCode::OK);
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
            events.push(serde_json::from_str::<Value>(&line[6..]).unwrap());
        }
    }

    let queue_snapshot = events
        .iter()
        .find(|event| event["type"] == "queue_snapshot")
        .expect("queue_snapshot event missing");
    assert_eq!(
        queue_snapshot["data"]["bl_recon"]["peek"][0]["title"],
        "provided-business-logic-risk"
    );
    assert_eq!(
        queue_snapshot["data"]["bl_recon"]["peek"][0]["file_path"],
        "src/checkout.rs"
    );
}
