use axum::{
    body::{to_bytes, Body},
    http::{Method, Request, StatusCode},
};
use backend_rust::{app::build_router, config::AppConfig, state::AppState};
use serde_json::{json, Value};
use tower::util::ServiceExt;
use uuid::Uuid;

#[tokio::test]
async fn skills_catalog_and_prompt_skill_crud_are_rust_owned() {
    let config = isolated_test_config("skills-api");
    let state = AppState::from_config(config)
        .await
        .expect("state should build");
    let app = build_router(state);

    let catalog_response = app
        .clone()
        .oneshot(
            Request::get("/api/v1/skills/catalog?limit=200")
                .body(Body::empty())
                .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(catalog_response.status(), StatusCode::OK);
    let catalog_json: Value = serde_json::from_slice(
        &to_bytes(catalog_response.into_body(), usize::MAX)
            .await
            .unwrap(),
    )
    .unwrap();
    assert!(catalog_json["items"].as_array().unwrap().len() >= 1);

    let prompt_list_response = app
        .clone()
        .oneshot(
            Request::get("/api/v1/skills/prompt-skills")
                .body(Body::empty())
                .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(prompt_list_response.status(), StatusCode::OK);
    let prompt_list_json: Value = serde_json::from_slice(
        &to_bytes(prompt_list_response.into_body(), usize::MAX)
            .await
            .unwrap(),
    )
    .unwrap();
    assert!(prompt_list_json["builtin_items"].as_array().unwrap().len() >= 1);

    let create_response = app
        .clone()
        .oneshot(
            Request::builder()
                .method(Method::POST)
                .uri("/api/v1/skills/prompt-skills")
                .header("content-type", "application/json")
                .body(Body::from(
                    json!({
                        "name": "Custom Prompt",
                        "content": "focus on evidence",
                        "scope": "global",
                        "is_active": true
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
    let prompt_skill_id = create_json["id"].as_str().unwrap().to_string();

    let update_response = app
        .clone()
        .oneshot(
            Request::builder()
                .method(Method::PUT)
                .uri(format!("/api/v1/skills/prompt-skills/{prompt_skill_id}"))
                .header("content-type", "application/json")
                .body(Body::from(
                    json!({
                        "name": "Custom Prompt Updated",
                        "content": "focus on stronger evidence",
                        "scope": "agent_specific",
                        "agent_key": "analysis",
                        "is_active": true
                    })
                    .to_string(),
                ))
                .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(update_response.status(), StatusCode::OK);

    let builtin_update_response = app
        .clone()
        .oneshot(
            Request::builder()
                .method(Method::PUT)
                .uri("/api/v1/skills/prompt-skills/builtin/analysis")
                .header("content-type", "application/json")
                .body(Body::from(
                    json!({
                        "is_active": false
                    })
                    .to_string(),
                ))
                .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(builtin_update_response.status(), StatusCode::OK);

    let resource_response = app
        .clone()
        .oneshot(
            Request::get(format!(
                "/api/v1/skills/resources/prompt-custom/{prompt_skill_id}"
            ))
            .body(Body::empty())
            .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(resource_response.status(), StatusCode::OK);
    let resource_json: Value = serde_json::from_slice(
        &to_bytes(resource_response.into_body(), usize::MAX)
            .await
            .unwrap(),
    )
    .unwrap();
    assert_eq!(resource_json["tool_type"], "prompt-custom");

    let delete_response = app
        .clone()
        .oneshot(
            Request::builder()
                .method(Method::DELETE)
                .uri(format!("/api/v1/skills/prompt-skills/{prompt_skill_id}"))
                .body(Body::empty())
                .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(delete_response.status(), StatusCode::OK);
}

#[tokio::test]
async fn default_skills_catalog_exposes_prompt_effective_entries() {
    let config = isolated_test_config("skills-effective-catalog");
    let state = AppState::from_config(config)
        .await
        .expect("state should build");
    let app = build_router(state);

    let catalog_response = app
        .oneshot(
            Request::get("/api/v1/skills/catalog?limit=200")
                .body(Body::empty())
                .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(catalog_response.status(), StatusCode::OK);
    let catalog_json: Value = serde_json::from_slice(
        &to_bytes(catalog_response.into_body(), usize::MAX)
            .await
            .unwrap(),
    )
    .unwrap();
    let items = catalog_json["items"].as_array().unwrap();

    let prompt_items: Vec<&Value> = items
        .iter()
        .filter(|item| item["namespace"] == "prompt" && item["source"] == "prompt_effective")
        .collect();
    assert_eq!(prompt_items.len(), 6);

    for agent_key in [
        "recon",
        "business_logic_recon",
        "analysis",
        "business_logic_analysis",
        "verification",
        "report",
    ] {
        let skill_id = format!("prompt-{agent_key}@effective");
        let item = prompt_items
            .iter()
            .find(|item| item["skill_id"] == skill_id)
            .unwrap_or_else(|| panic!("missing prompt-effective item for {agent_key}"));
        assert_eq!(item["kind"], "prompt");
        assert_eq!(item["namespace"], "prompt");
        assert_eq!(item["source"], "prompt_effective");
        assert_eq!(item["load_mode"], "summary_only");
        if agent_key != "report" {
            assert_eq!(item["runtime_ready"], true);
        }
        assert_eq!(item["tool_type"], "");
        assert_eq!(item["tool_id"], "");
        assert_eq!(item["name"], skill_id);
        assert!(item["selection_label"]
            .as_str()
            .unwrap()
            .contains(agent_key));
        assert!(item["display_name"].as_str().unwrap().contains("Prompt"));
        assert!(!item["summary"]
            .as_str()
            .unwrap()
            .contains("围绕单风险点做证据闭环"));
        assert!(item["reason"].as_str().unwrap().len() > 0);
    }

    assert!(items
        .iter()
        .all(|item| item["tool_type"] != "prompt-builtin"));
    assert!(items
        .iter()
        .all(|item| item["tool_type"] != "prompt-custom"));
}

#[tokio::test]
async fn external_tools_catalog_keeps_builtin_and_custom_prompt_resources() {
    let config = isolated_test_config("skills-external-tools-catalog");
    let state = AppState::from_config(config)
        .await
        .expect("state should build");
    let app = build_router(state);

    let create_response = app
        .clone()
        .oneshot(
            Request::builder()
                .method(Method::POST)
                .uri("/api/v1/skills/prompt-skills")
                .header("content-type", "application/json")
                .body(Body::from(
                    json!({
                        "name": "Analysis Custom Prompt",
                        "content": "global prompt custom body",
                        "scope": "global",
                        "is_active": true
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
    let prompt_skill_id = create_json["id"].as_str().unwrap();

    let catalog_response = app
        .oneshot(
            Request::get("/api/v1/skills/catalog?resource_mode=external_tools&limit=200")
                .body(Body::empty())
                .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(catalog_response.status(), StatusCode::OK);
    let catalog_json: Value = serde_json::from_slice(
        &to_bytes(catalog_response.into_body(), usize::MAX)
            .await
            .unwrap(),
    )
    .unwrap();
    let items = catalog_json["items"].as_array().unwrap();

    let builtin_item = items
        .iter()
        .find(|item| item["tool_type"] == "prompt-builtin" && item["tool_id"] == "analysis")
        .expect("builtin prompt resource should exist");
    assert_eq!(builtin_item["resource_kind_label"], "Builtin Prompt Skill");
    assert_eq!(builtin_item["tool_id"], "analysis");

    let custom_item = items
        .iter()
        .find(|item| item["tool_type"] == "prompt-custom" && item["tool_id"] == prompt_skill_id)
        .expect("custom prompt resource should exist");
    assert_eq!(custom_item["resource_kind_label"], "Custom Prompt Skill");
    assert_eq!(custom_item["name"], "Analysis Custom Prompt");
}

#[tokio::test]
async fn prompt_effective_detail_merges_builtin_global_and_agent_specific_sources() {
    let config = isolated_test_config("skills-effective-detail");
    let state = AppState::from_config(config)
        .await
        .expect("state should build");
    let app = build_router(state);

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
        json!({
            "name": "Inactive Analysis Prompt",
            "content": "Should not appear.",
            "scope": "agent_specific",
            "agent_key": "analysis",
            "is_active": false
        }),
        json!({
            "name": "Empty Analysis Prompt",
            "content": "   ",
            "scope": "global",
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

    let detail_response = app
        .oneshot(
            Request::get("/api/v1/skills/prompt-analysis@effective")
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

    assert_eq!(detail_json["skill_id"], "prompt-analysis@effective");
    assert_eq!(detail_json["kind"], "prompt");
    assert_eq!(detail_json["source"], "prompt_effective");
    assert_eq!(detail_json["agent_key"], "analysis");
    assert_eq!(detail_json["runtime_ready"], true);
    assert_eq!(detail_json["load_mode"], "full");
    assert_eq!(
        detail_json["reason"],
        "builtin_template+global_custom+agent_specific_custom"
    );

    let effective_content = detail_json["effective_content"].as_str().unwrap();
    let builtin_index = effective_content
        .find("围绕单风险点做证据闭环")
        .expect("builtin template should be included");
    let global_index = effective_content
        .find("Global analysis instructions.")
        .expect("global custom prompt should be included");
    let agent_index = effective_content
        .find("Agent-specific analysis instructions.")
        .expect("agent specific prompt should be included");
    assert!(builtin_index < global_index);
    assert!(global_index < agent_index);
    assert!(!effective_content.contains("Should not appear."));

    let prompt_sources = detail_json["prompt_sources"].as_array().unwrap();
    assert_eq!(prompt_sources.len(), 3);
    assert_eq!(prompt_sources[0]["source"], "builtin_template");
    assert_eq!(prompt_sources[1]["source"], "global_custom");
    assert_eq!(prompt_sources[2]["source"], "agent_specific_custom");
}

#[tokio::test]
async fn prompt_effective_detail_stays_visible_when_no_active_sources_exist() {
    let config = isolated_test_config("skills-effective-detail-disabled");
    let state = AppState::from_config(config)
        .await
        .expect("state should build");
    let app = build_router(state);

    let builtin_update_response = app
        .clone()
        .oneshot(
            Request::builder()
                .method(Method::PUT)
                .uri("/api/v1/skills/prompt-skills/builtin/verification")
                .header("content-type", "application/json")
                .body(Body::from(
                    json!({
                        "is_active": false
                    })
                    .to_string(),
                ))
                .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(builtin_update_response.status(), StatusCode::OK);

    let detail_response = app
        .oneshot(
            Request::get("/api/v1/skills/prompt-verification@effective")
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

    assert_eq!(detail_json["skill_id"], "prompt-verification@effective");
    assert_eq!(detail_json["runtime_ready"], false);
    assert_eq!(detail_json["reason"], "no_active_prompt_sources");
    assert_eq!(detail_json["effective_content"], "");
    assert_eq!(detail_json["prompt_sources"].as_array().unwrap().len(), 0);
}

#[tokio::test]
async fn skills_pagination_total_counts_all_matches_before_paging() {
    let config = isolated_test_config("skills-pagination-total");
    let state = AppState::from_config(config)
        .await
        .expect("state should build");
    let app = build_router(state);

    for name in ["Prompt One", "Prompt Two"] {
        let response = app
            .clone()
            .oneshot(
                Request::builder()
                    .method(Method::POST)
                    .uri("/api/v1/skills/prompt-skills")
                    .header("content-type", "application/json")
                    .body(Body::from(
                        json!({
                            "name": name,
                            "content": format!("{name} content"),
                            "scope": "global",
                            "is_active": true
                        })
                        .to_string(),
                    ))
                    .unwrap(),
            )
            .await
            .unwrap();
        assert_eq!(response.status(), StatusCode::OK);
    }

    let prompt_list_response = app
        .clone()
        .oneshot(
            Request::get("/api/v1/skills/prompt-skills?limit=1&offset=0")
                .body(Body::empty())
                .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(prompt_list_response.status(), StatusCode::OK);
    let prompt_list_json: Value = serde_json::from_slice(
        &to_bytes(prompt_list_response.into_body(), usize::MAX)
            .await
            .unwrap(),
    )
    .unwrap();
    assert_eq!(prompt_list_json["total"], 2);
    assert_eq!(prompt_list_json["items"].as_array().unwrap().len(), 1);

    let catalog_response = app
        .oneshot(
            Request::get("/api/v1/skills/catalog?limit=1&offset=0")
                .body(Body::empty())
                .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(catalog_response.status(), StatusCode::OK);
    let catalog_json: Value = serde_json::from_slice(
        &to_bytes(catalog_response.into_body(), usize::MAX)
            .await
            .unwrap(),
    )
    .unwrap();
    assert!(catalog_json["total"].as_u64().unwrap() > 1);
    assert_eq!(catalog_json["items"].as_array().unwrap().len(), 1);
}

#[tokio::test]
async fn skill_detail_and_test_streams_are_available() {
    let config = isolated_test_config("skills-stream");
    let state = AppState::from_config(config)
        .await
        .expect("state should build");
    let app = build_router(state);

    let catalog_response = app
        .clone()
        .oneshot(
            Request::get("/api/v1/skills/catalog?limit=20")
                .body(Body::empty())
                .unwrap(),
        )
        .await
        .unwrap();
    let catalog_json: Value = serde_json::from_slice(
        &to_bytes(catalog_response.into_body(), usize::MAX)
            .await
            .unwrap(),
    )
    .unwrap();
    let skill_id = catalog_json["items"][0]["skill_id"]
        .as_str()
        .unwrap()
        .to_string();

    let detail_response = app
        .clone()
        .oneshot(
            Request::get(format!("/api/v1/skills/{skill_id}"))
                .body(Body::empty())
                .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(detail_response.status(), StatusCode::OK);

    let test_response = app
        .clone()
        .oneshot(
            Request::builder()
                .method(Method::POST)
                .uri(format!("/api/v1/skills/{skill_id}/test"))
                .header("content-type", "application/json")
                .body(Body::from(
                    json!({
                        "prompt": "run a smoke test",
                        "max_iterations": 2
                    })
                    .to_string(),
                ))
                .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(test_response.status(), StatusCode::OK);
    assert_eq!(test_response.headers()["content-type"], "text/event-stream");
    let test_body = String::from_utf8(
        to_bytes(test_response.into_body(), usize::MAX)
            .await
            .unwrap()
            .to_vec(),
    )
    .unwrap();
    assert!(test_body.contains("\"type\":\"result\""));

    let tool_test_response = app
        .oneshot(
            Request::builder()
                .method(Method::POST)
                .uri(format!("/api/v1/skills/{skill_id}/tool-test"))
                .header("content-type", "application/json")
                .body(Body::from(
                    json!({
                        "project_name": "libplist",
                        "file_path": "src/a.c",
                        "function_name": "main",
                        "line_start": 1,
                        "line_end": 2,
                        "tool_input": {"mode": "smoke"}
                    })
                    .to_string(),
                ))
                .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(tool_test_response.status(), StatusCode::OK);
}

fn isolated_test_config(scope: &str) -> AppConfig {
    let mut config = AppConfig::for_tests();
    config.zip_storage_path =
        std::env::temp_dir().join(format!("argus-rust-{scope}-{}", Uuid::new_v4()));
    config
}
