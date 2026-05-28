use axum::{
    body::{to_bytes, Body},
    http::{Request, StatusCode},
};
use backend_rust::{
    app::build_router, bootstrap, config::AppConfig, db::cwe_catalog,
    runtime::shutdown::ShutdownGate, state::AppState,
};
use serde_json::Value;
use sqlx::{postgres::PgPoolOptions, PgPool};
use tower::util::ServiceExt;
use uuid::Uuid;

async fn optional_test_pool(scope: &str) -> Option<PgPool> {
    let explicit_test_db = std::env::var("ARGUS_TEST_DATABASE_URL").ok();
    let must_use_db = explicit_test_db.is_some();
    let base_url = explicit_test_db
        .or_else(|| std::env::var("RUST_DATABASE_URL").ok())
        .or_else(|| std::env::var("DATABASE_URL").ok())?;
    let database_name = format!("argus_cwe_catalog_{}_{}", scope, Uuid::new_v4().simple());
    let admin_pool = match PgPoolOptions::new()
        .max_connections(1)
        .connect(&base_url)
        .await
    {
        Ok(pool) => pool,
        Err(error) => {
            if must_use_db {
                panic!("cannot connect to explicit ARGUS_TEST_DATABASE_URL: {error}");
            }
            eprintln!("skipping CWE catalog DB test: cannot connect to test database: {error}");
            return None;
        }
    };

    if let Err(error) = sqlx::query(&format!(r#"create database "{database_name}""#))
        .execute(&admin_pool)
        .await
    {
        if must_use_db {
            panic!("cannot create isolated CWE catalog test database: {error}");
        }
        eprintln!("skipping CWE catalog DB test: cannot create isolated database: {error}");
        return None;
    }
    admin_pool.close().await;

    let database_url = match replace_database_name(&base_url, &database_name) {
        Some(url) => url,
        None => {
            if must_use_db {
                panic!("unsupported ARGUS_TEST_DATABASE_URL shape");
            }
            eprintln!("skipping CWE catalog DB test: unsupported database URL shape");
            return None;
        }
    };
    match PgPoolOptions::new()
        .max_connections(2)
        .connect(&database_url)
        .await
    {
        Ok(pool) => Some(pool),
        Err(error) => {
            if must_use_db {
                panic!("cannot connect to isolated CWE catalog test database: {error}");
            }
            eprintln!("skipping CWE catalog DB test: cannot connect to isolated database: {error}");
            None
        }
    }
}

fn replace_database_name(base_url: &str, database_name: &str) -> Option<String> {
    let query_start = base_url.find('?').unwrap_or(base_url.len());
    let (without_query, query) = base_url.split_at(query_start);
    let slash = without_query.rfind('/')?;
    Some(format!(
        "{}/{}{}",
        &without_query[..slash],
        database_name,
        query
    ))
}

async fn bootstrap_schema(pool: &PgPool) {
    let mut config = AppConfig::for_tests();
    config.rust_database_url = None;
    let mut state = AppState::from_config(config).await.expect("state");
    state.db_pool = Some(pool.clone());
    bootstrap::run(&state).await.expect("bootstrap should run");
}

#[tokio::test]
async fn cwe_catalog_seed_sync_inserts_and_preserves_existing_chinese_names() {
    let Some(pool) = optional_test_pool("sync").await else {
        return;
    };
    bootstrap_schema(&pool).await;

    let first = cwe_catalog::ensure_initialized_with_pool(&pool)
        .await
        .expect("first sync");
    assert_eq!(first.discovered, 969);
    assert_eq!(first.active_total, 969);
    assert_eq!(first.inserted + first.skipped + first.updated, 969);

    let cwe_89 = cwe_catalog::lookup_active_entry(&pool, "89")
        .await
        .expect("lookup")
        .expect("CWE-89 should exist");
    assert_eq!(cwe_89.id, "CWE-89");
    assert_eq!(cwe_89.name_zh, "SQL注入");
    assert_eq!(cwe_89.source_version, "4.20");
    assert_eq!(cwe_89.source_date, "2026-04-30");
    assert_eq!(cwe_89.source_sha256, cwe_catalog::bundled_seed_sha256());
    assert_eq!(cwe_89.translation_reviewed_at, "2026-05-28T10:58:05Z");

    sqlx::query("update rust_cwe_catalog set name_zh = $1 where cwe_id = 'CWE-89'")
        .bind("自定义SQL注入")
        .execute(&pool)
        .await
        .expect("custom zh update");

    let second = cwe_catalog::ensure_initialized_with_pool(&pool)
        .await
        .expect("second sync");
    assert_eq!(second.discovered, 969);
    assert_eq!(second.active_total, 969);
    assert!(
        second.skipped >= 968,
        "second sync should mostly skip: {second:?}"
    );

    let preserved = cwe_catalog::lookup_active_entry(&pool, "cwe_89")
        .await
        .expect("lookup")
        .expect("CWE-89 should exist");
    assert_eq!(preserved.name_zh, "自定义SQL注入");
    assert!(preserved.name_en_official.contains("SQL Command"));
    assert_eq!(preserved.source_sha256, cwe_catalog::bundled_seed_sha256());
}

#[tokio::test]
async fn cwe_catalog_api_lists_searches_and_looks_up_entries() {
    let Some(pool) = optional_test_pool("api").await else {
        return;
    };
    bootstrap_schema(&pool).await;
    cwe_catalog::ensure_initialized_with_pool(&pool)
        .await
        .expect("sync");

    let mut config = AppConfig::for_tests();
    config.rust_database_url = None;
    let mut state = AppState::from_config(config).await.expect("state");
    state.db_pool = Some(pool);
    let app = build_router(state, ShutdownGate::default());

    let list_response = app
        .clone()
        .oneshot(
            Request::get("/api/v1/cwe-catalog?limit=1000")
                .body(Body::empty())
                .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(list_response.status(), StatusCode::OK);
    let list_payload: Value = serde_json::from_slice(
        &to_bytes(list_response.into_body(), usize::MAX)
            .await
            .unwrap(),
    )
    .unwrap();
    assert_eq!(list_payload["total"], 969);
    assert_eq!(list_payload["data"].as_array().unwrap().len(), 969);
    assert_eq!(list_payload["sourceVersion"], "4.20");
    assert_eq!(list_payload["sourceDate"], "2026-04-30");

    for path in [
        "/api/v1/cwe-catalog/CWE-89",
        "/api/v1/cwe-catalog/89",
        "/api/v1/cwe-catalog/cwe_89",
    ] {
        let response = app
            .clone()
            .oneshot(Request::get(path).body(Body::empty()).unwrap())
            .await
            .unwrap();
        assert_eq!(response.status(), StatusCode::OK, "{path}");
        let payload: Value =
            serde_json::from_slice(&to_bytes(response.into_body(), usize::MAX).await.unwrap())
                .unwrap();
        assert_eq!(payload["id"], "CWE-89");
        assert_eq!(payload["numericId"], 89);
        assert_eq!(payload["nameZh"], "SQL注入");
    }

    let search_response = app
        .clone()
        .oneshot(
            Request::get("/api/v1/cwe-catalog?keyword=注入&limit=1000")
                .body(Body::empty())
                .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(search_response.status(), StatusCode::OK);
    let search_payload: Value = serde_json::from_slice(
        &to_bytes(search_response.into_body(), usize::MAX)
            .await
            .unwrap(),
    )
    .unwrap();
    let ids = search_payload["data"]
        .as_array()
        .unwrap()
        .iter()
        .filter_map(|item| item["id"].as_str())
        .collect::<Vec<_>>();
    assert!(ids.contains(&"CWE-89"));

    let unknown = app
        .clone()
        .oneshot(
            Request::get("/api/v1/cwe-catalog/CWE-999999")
                .body(Body::empty())
                .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(unknown.status(), StatusCode::NOT_FOUND);
}
