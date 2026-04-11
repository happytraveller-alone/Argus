mod init;
mod legacy_mirror_schema;
mod legacy_schema;
mod preflight;
mod recovery;

use std::time::Duration;

use anyhow::{anyhow, Result};
use sqlx::postgres::PgPoolOptions;
use sqlx::PgPool;
use tokio::time::timeout;

use crate::config::AppConfig;
use crate::state::{
    AppState, BootstrapReport, BootstrapStatus, DatabaseBootstrapStatus,
    LegacySchemaBootstrapStatus,
};

const REQUIRED_RUST_TABLES: &[&str] = &[
    "system_configs",
    "rust_projects",
    "rust_project_archives",
    "rust_scan_rule_assets",
];

pub async fn run(state: &AppState) -> Result<BootstrapReport> {
    let report = build_report(state).await;
    state.set_bootstrap(report.clone()).await;
    if report.file_store.status == BootstrapStatus::Error.as_str() {
        return Err(anyhow!(
            "bootstrap failed to initialize file storage root: {}",
            report
                .file_store
                .error
                .as_deref()
                .unwrap_or("unknown file storage error")
        ));
    }
    Ok(report)
}

async fn build_report(state: &AppState) -> BootstrapReport {
    let mut report = BootstrapReport::new();
    let legacy_expectation = legacy_schema::LegacySchemaExpectation::load_from_repo();

    // 1) Ensure file store root exists.
    let zip_root = state.config.zip_storage_path.clone();
    report.file_store.root = zip_root.to_string_lossy().to_string();
    match tokio::fs::create_dir_all(&zip_root).await {
        Ok(()) => {
            report.file_store.status = BootstrapStatus::Ok.as_str().to_string();
        }
        Err(err) => {
            report.file_store.status = BootstrapStatus::Error.as_str().to_string();
            report.file_store.error = Some(err.to_string());
            report.overall = BootstrapStatus::Error.as_str().to_string();
            return report;
        }
    }

    // 2) DB checks.
    match state.db_pool.as_ref() {
        None => {
            report.database = DatabaseBootstrapStatus::file_mode(legacy_status_for_file_mode(
                &legacy_expectation,
            ));
        }
        Some(pool) => {
            report.database = check_database(state, pool, &legacy_expectation).await;
            if report.database.status != BootstrapStatus::Ok.as_str() {
                // Non-fatal for now: we still want the server to start so /health can report.
                report.overall = BootstrapStatus::Degraded.as_str().to_string();
            }
        }
    }
    if report.database.legacy_schema.status == BootstrapStatus::Error.as_str() {
        report.overall = BootstrapStatus::Degraded.as_str().to_string();
        if report.database.status == "skipped" {
            report.database.status = BootstrapStatus::Degraded.as_str().to_string();
        }
        if report.database.error.is_none() {
            report.database.error = report.database.legacy_schema.error.clone();
        }
    }

    let rust_db_ready =
        report.database.mode == "db" && report.database.status == BootstrapStatus::Ok.as_str();
    let database_reachable = report.database.mode == "db"
        && matches!(report.database.status.as_str(), "ok" | "degraded");

    report.init = match init::run(state, rust_db_ready).await {
        Ok(status) => status,
        Err(error) => {
            report.overall = BootstrapStatus::Degraded.as_str().to_string();
            crate::state::StartupInitStatus {
                status: BootstrapStatus::Error.as_str().to_string(),
                policy: crate::state::StartupInitPolicy::default(),
                actions: Vec::new(),
                error: Some(error.to_string()),
            }
        }
    };
    if report.init.status == BootstrapStatus::Error.as_str() {
        report.overall = BootstrapStatus::Degraded.as_str().to_string();
    }

    report.recovery = match recovery::run(state, database_reachable).await {
        Ok(status) => status,
        Err(error) => {
            report.overall = BootstrapStatus::Degraded.as_str().to_string();
            crate::state::StartupRecoveryStatus {
                status: BootstrapStatus::Error.as_str().to_string(),
                tasks: Vec::new(),
                error: Some(error.to_string()),
            }
        }
    };
    if report.recovery.status == BootstrapStatus::Error.as_str() {
        report.overall = BootstrapStatus::Degraded.as_str().to_string();
    }

    report.preflight = match preflight::run(state).await {
        Ok(status) => status,
        Err(error) => {
            report.overall = BootstrapStatus::Degraded.as_str().to_string();
            crate::state::RunnerPreflightStatus {
                status: BootstrapStatus::Error.as_str().to_string(),
                enabled: state.config.runner_preflight_enabled,
                strict: state.config.runner_preflight_strict,
                checks: Vec::new(),
                error: Some(error.to_string()),
            }
        }
    };
    if report.preflight.status != BootstrapStatus::Ok.as_str()
        && report.preflight.status != "skipped"
    {
        report.overall = BootstrapStatus::Degraded.as_str().to_string();
    }

    report
}

async fn check_database(
    state: &AppState,
    pool: &PgPool,
    legacy_expectation: &legacy_schema::LegacySchemaExpectation,
) -> DatabaseBootstrapStatus {
    let mut status =
        DatabaseBootstrapStatus::db_mode(legacy_status_for_db_mode(legacy_expectation));
    let config = state.config.as_ref();
    status.checked_tables = REQUIRED_RUST_TABLES
        .iter()
        .map(|name| (*name).to_string())
        .collect();
    if status.legacy_schema.status == BootstrapStatus::Error.as_str() {
        let legacy_error = status
            .legacy_schema
            .error
            .clone()
            .unwrap_or_else(|| "failed to inspect legacy migration files".to_string());
        mark_database_degraded(&mut status, legacy_error);
    }

    // Connectivity: run a trivial query, but never hang startup forever.
    let connectivity = timeout(
        Duration::from_secs(2),
        sqlx::query_scalar::<_, i64>("SELECT 1").fetch_one(pool),
    )
    .await;

    let _one = match connectivity {
        Ok(Ok(value)) => value,
        Ok(Err(err)) => {
            status.status = BootstrapStatus::Error.as_str().to_string();
            status.error = Some(err.to_string());
            if status.legacy_schema.status == BootstrapStatus::NotRun.as_str() {
                status.legacy_schema.status = status.status.clone();
                status.legacy_schema.error = status.error.clone();
            }
            return status;
        }
        Err(_) => {
            status.status = "timeout".to_string();
            status.error = Some("connectivity check timed out".to_string());
            if status.legacy_schema.status == BootstrapStatus::NotRun.as_str() {
                status.legacy_schema.status = status.status.clone();
                status.legacy_schema.error = status.error.clone();
            }
            return status;
        }
    };

    let rust_tables = timeout(
        Duration::from_secs(2),
        sqlx::query_scalar::<_, String>(
            "SELECT table_name
             FROM information_schema.tables
             WHERE table_schema = 'public'
               AND table_name IN ('system_configs', 'rust_projects', 'rust_project_archives', 'rust_scan_rule_assets')",
        )
        .fetch_all(pool),
    )
    .await;

    let present_tables = match rust_tables {
        Ok(Ok(rows)) => rows,
        Ok(Err(err)) => {
            status.status = BootstrapStatus::Error.as_str().to_string();
            status.error = Some(err.to_string());
            if status.legacy_schema.status == BootstrapStatus::NotRun.as_str() {
                status.legacy_schema.status = status.status.clone();
                status.legacy_schema.error = status.error.clone();
            }
            return status;
        }
        Err(_) => {
            status.status = "timeout".to_string();
            status.error = Some("database table inventory check timed out".to_string());
            if status.legacy_schema.status == BootstrapStatus::NotRun.as_str() {
                status.legacy_schema.status = status.status.clone();
                status.legacy_schema.error = status.error.clone();
            }
            return status;
        }
    };

    let missing_rust_tables = missing_required_tables(&present_tables);
    status.missing_tables = missing_rust_tables
        .iter()
        .map(|name| (*name).to_string())
        .collect();

    if !missing_rust_tables.is_empty() {
        mark_database_degraded(
            &mut status,
            format!(
                "missing required rust tables: {}",
                missing_rust_tables.join(", ")
            ),
        );
    }

    if config.python_alembic_enabled {
        inspect_legacy_schema_versions(config, pool, &mut status).await;
    } else {
        let mut skipped = LegacySchemaBootstrapStatus::skipped(
            legacy_expectation.versions_dir.clone(),
            legacy_expectation.expected_heads.clone(),
        );
        if let Some(error) = &legacy_expectation.error {
            skipped = skipped.with_error(BootstrapStatus::Error.as_str(), error.clone());
        }
        status.legacy_schema = skipped;
    }
    if status.status == BootstrapStatus::NotRun.as_str() {
        status.status = BootstrapStatus::Ok.as_str().to_string();
    }

    status
}

fn legacy_status_for_file_mode(
    expectation: &legacy_schema::LegacySchemaExpectation,
) -> LegacySchemaBootstrapStatus {
    let mut status = LegacySchemaBootstrapStatus::skipped(
        expectation.versions_dir.clone(),
        expectation.expected_heads.clone(),
    );
    if let Some(error) = &expectation.error {
        status = status.with_error(BootstrapStatus::Error.as_str(), error.clone());
    }
    status
}

fn legacy_status_for_db_mode(
    expectation: &legacy_schema::LegacySchemaExpectation,
) -> LegacySchemaBootstrapStatus {
    let mut status = LegacySchemaBootstrapStatus::db_not_run(
        expectation.versions_dir.clone(),
        expectation.expected_heads.clone(),
    );
    if let Some(error) = &expectation.error {
        status = status.with_error(BootstrapStatus::Error.as_str(), error.clone());
    }
    status
}

async fn inspect_legacy_schema_versions(
    config: &AppConfig,
    rust_pool: &PgPool,
    status: &mut DatabaseBootstrapStatus,
) {
    if status.legacy_schema.status == BootstrapStatus::Error.as_str() {
        return;
    }

    let rust_db_url = config.resolved_rust_database_url();
    let mut python_pool: Option<PgPool> = None;

    if let Some(python_url) = config.python_database_url.as_ref() {
        if rust_db_url
            .as_ref()
            .map_or(true, |rust_url| python_url != rust_url)
        {
            match PgPoolOptions::new()
                .max_connections(1)
                .connect_lazy(python_url)
            {
                Ok(pool) => {
                    python_pool = Some(pool);
                }
                Err(err) => {
                    status.legacy_schema.status = BootstrapStatus::Error.as_str().to_string();
                    status.legacy_schema.matches_expected_heads = None;
                    status.legacy_schema.current_versions.clear();
                    let detail = format!(
                        "failed to open python database for legacy schema inspection: {err}"
                    );
                    status.legacy_schema.error = Some(detail.clone());
                    mark_database_degraded(status, detail);
                    return;
                }
            }
        }
    }

    let query_pool: &PgPool = python_pool.as_ref().unwrap_or(rust_pool);

    let versions_result = timeout(
        Duration::from_secs(2),
        sqlx::query_scalar::<_, String>(
            "SELECT version_num
             FROM alembic_version
             ORDER BY version_num",
        )
        .fetch_all(query_pool),
    )
    .await;

    match versions_result {
        Ok(Ok(current_versions)) => apply_legacy_schema_comparison(status, current_versions),
        Ok(Err(err)) => {
            status.legacy_schema.status = BootstrapStatus::Degraded.as_str().to_string();
            status.legacy_schema.matches_expected_heads = None;
            let detail = format!("failed to read alembic_version: {err}");
            status.legacy_schema.error = Some(detail.clone());
            mark_database_degraded(status, detail);
        }
        Err(_) => {
            status.legacy_schema.status = "timeout".to_string();
            status.legacy_schema.matches_expected_heads = None;
            let detail = "legacy schema version query timed out".to_string();
            status.legacy_schema.error = Some(detail.clone());
            mark_database_degraded(status, detail);
        }
    }
}

fn apply_legacy_schema_comparison(
    status: &mut DatabaseBootstrapStatus,
    current_versions: Vec<String>,
) {
    let mut normalized_versions = current_versions;
    normalized_versions.sort();
    normalized_versions.dedup();

    let matches_expected =
        same_versions(&status.legacy_schema.expected_heads, &normalized_versions);
    status.legacy_schema.current_versions = normalized_versions.clone();
    status.legacy_schema.matches_expected_heads = Some(matches_expected);

    if matches_expected {
        status.legacy_schema.status = BootstrapStatus::Ok.as_str().to_string();
        status.legacy_schema.error = None;
        return;
    }

    status.legacy_schema.status = BootstrapStatus::Degraded.as_str().to_string();
    let detail = format!(
        "legacy schema revision mismatch: expected heads {:?}, got {:?}",
        status.legacy_schema.expected_heads, normalized_versions
    );
    status.legacy_schema.error = Some(detail.clone());
    mark_database_degraded(status, detail);
}

fn same_versions(expected: &[String], current: &[String]) -> bool {
    let mut expected_sorted = expected.to_vec();
    let mut current_sorted = current.to_vec();
    expected_sorted.sort();
    expected_sorted.dedup();
    current_sorted.sort();
    current_sorted.dedup();
    expected_sorted == current_sorted
}

fn mark_database_degraded(status: &mut DatabaseBootstrapStatus, message: String) {
    if status.status == BootstrapStatus::Error.as_str() || status.status == "timeout" {
        return;
    }
    status.status = BootstrapStatus::Degraded.as_str().to_string();
    if status.error.is_none() {
        status.error = Some(message);
    }
}

fn missing_required_tables(present_tables: &[String]) -> Vec<&'static str> {
    REQUIRED_RUST_TABLES
        .iter()
        .copied()
        .filter(|required| !present_tables.iter().any(|present| present == required))
        .collect()
}

#[cfg(test)]
mod tests {
    use std::{
        fs,
        path::Path,
        time::{SystemTime, UNIX_EPOCH},
    };

    use crate::state::{BootstrapStatus, DatabaseBootstrapStatus, LegacySchemaBootstrapStatus};

    use super::{apply_legacy_schema_comparison, missing_required_tables};

    #[test]
    fn migration_identity_parser_supports_plain_and_typed_assignments() {
        let plain = r#"
revision = "rev_plain"
down_revision = "prev_plain"
"#;
        let typed = r#"
from typing import Sequence, Union
revision: str = "rev_typed"
down_revision: Union[str, Sequence[str], None] = "prev_typed"
"#;

        let plain_identity = super::legacy_schema::parse_migration_identity(plain)
            .expect("plain assignment should be parsed");
        assert_eq!(plain_identity.revision, "rev_plain");
        assert_eq!(plain_identity.down_revisions, vec!["prev_plain"]);

        let typed_identity = super::legacy_schema::parse_migration_identity(typed)
            .expect("typed assignment should be parsed");
        assert_eq!(typed_identity.revision, "rev_typed");
        assert_eq!(typed_identity.down_revisions, vec!["prev_typed"]);
    }

    #[test]
    fn migration_head_resolution_returns_leaf_revision() {
        let versions_dir = unique_versions_dir("legacy-head-");
        fs::create_dir_all(&versions_dir).expect("should create temp versions dir");
        fs::write(
            versions_dir.join("0001_base.py"),
            r#"
revision = "base"
down_revision = None
"#,
        )
        .expect("should write base migration");
        fs::write(
            versions_dir.join("0002_mid.py"),
            r#"
revision = "mid"
down_revision: Union[str, Sequence[str], None] = "base"
"#,
        )
        .expect("should write mid migration");
        fs::write(
            versions_dir.join("0003_head.py"),
            r#"
revision: str = "head"
down_revision = "mid"
"#,
        )
        .expect("should write head migration");

        let heads = super::legacy_schema::resolve_expected_heads_from_versions_dir(Path::new(
            &versions_dir,
        ))
        .expect("head resolution should succeed");
        assert_eq!(heads, vec!["head".to_string()]);

        let _ = fs::remove_dir_all(&versions_dir);
    }

    #[test]
    fn migration_head_resolution_supports_multiline_down_revision_merges() {
        let versions_dir = unique_versions_dir("legacy-multiline-");
        fs::create_dir_all(&versions_dir).expect("should create temp versions dir");
        fs::write(
            versions_dir.join("0001_base.py"),
            r#"
revision = "base"
down_revision = None
"#,
        )
        .expect("should write base migration");
        fs::write(
            versions_dir.join("0002_left.py"),
            r#"
revision = "left"
down_revision = "base"
"#,
        )
        .expect("should write left branch");
        fs::write(
            versions_dir.join("0003_right.py"),
            r#"
revision = "right"
down_revision = "base"
"#,
        )
        .expect("should write right branch");
        fs::write(
            versions_dir.join("0004_merge.py"),
            r#"
from typing import Sequence, Union
revision: str = "merge"
down_revision: Union[str, Sequence[str], None] = (
    "left",
    "right",
)
"#,
        )
        .expect("should write merge migration");

        let heads = super::legacy_schema::resolve_expected_heads_from_versions_dir(Path::new(
            &versions_dir,
        ))
        .expect("head resolution should succeed");
        assert_eq!(heads, vec!["merge".to_string()]);

        let _ = fs::remove_dir_all(&versions_dir);
    }

    #[test]
    fn migration_parser_rejects_non_none_down_revision_without_string_literals() {
        let invalid = r#"
revision = "head"
down_revision = (
    PARENT_REVISION,
)
"#;
        let error = super::legacy_schema::parse_migration_identity(invalid)
            .expect_err("non-None down_revision without string literal must fail");
        assert!(error
            .to_string()
            .contains("down_revision assignment must contain at least one string literal or None"));
    }

    #[test]
    fn legacy_schema_comparison_marks_ok_when_current_versions_match_expected_heads() {
        let mut status = DatabaseBootstrapStatus::db_mode(LegacySchemaBootstrapStatus::db_not_run(
            "backend_old/alembic/versions".to_string(),
            vec!["head_b".to_string(), "head_a".to_string()],
        ));
        apply_legacy_schema_comparison(
            &mut status,
            vec![
                "head_a".to_string(),
                "head_b".to_string(),
                "head_b".to_string(),
            ],
        );

        assert_eq!(status.legacy_schema.status, BootstrapStatus::Ok.as_str());
        assert_eq!(status.legacy_schema.matches_expected_heads, Some(true));
        assert_eq!(
            status.legacy_schema.current_versions,
            vec!["head_a".to_string(), "head_b".to_string()]
        );
        assert!(status.legacy_schema.error.is_none());
    }

    #[test]
    fn legacy_schema_comparison_marks_degraded_when_current_versions_are_missing() {
        let mut status = DatabaseBootstrapStatus::db_mode(LegacySchemaBootstrapStatus::db_not_run(
            "backend_old/alembic/versions".to_string(),
            vec!["expected_head".to_string()],
        ));
        apply_legacy_schema_comparison(&mut status, Vec::new());

        assert_eq!(
            status.legacy_schema.status,
            BootstrapStatus::Degraded.as_str()
        );
        assert_eq!(status.legacy_schema.matches_expected_heads, Some(false));
        assert!(status.legacy_schema.current_versions.is_empty());
        assert_eq!(status.status, BootstrapStatus::Degraded.as_str());
    }

    #[test]
    fn legacy_schema_comparison_marks_degraded_when_current_versions_mismatch() {
        let mut status = DatabaseBootstrapStatus::db_mode(LegacySchemaBootstrapStatus::db_not_run(
            "backend_old/alembic/versions".to_string(),
            vec!["expected_head".to_string()],
        ));
        apply_legacy_schema_comparison(&mut status, vec!["unexpected_head".to_string()]);

        assert_eq!(
            status.legacy_schema.status,
            BootstrapStatus::Degraded.as_str()
        );
        assert_eq!(status.legacy_schema.matches_expected_heads, Some(false));
        assert_eq!(
            status.legacy_schema.current_versions,
            vec!["unexpected_head".to_string()]
        );
        assert_eq!(status.status, BootstrapStatus::Degraded.as_str());
    }

    #[test]
    fn missing_required_tables_reports_exact_rust_dependencies() {
        let present = vec!["system_configs".to_string()];
        let missing = missing_required_tables(&present);
        assert_eq!(
            missing,
            vec![
                "rust_projects",
                "rust_project_archives",
                "rust_scan_rule_assets"
            ]
        );
    }

    #[test]
    fn missing_required_tables_is_empty_when_all_rust_tables_exist() {
        let present = vec![
            "system_configs".to_string(),
            "rust_projects".to_string(),
            "rust_project_archives".to_string(),
            "rust_scan_rule_assets".to_string(),
        ];
        assert!(missing_required_tables(&present).is_empty());
    }

    fn unique_versions_dir(prefix: &str) -> std::path::PathBuf {
        let mut dir = std::env::temp_dir();
        let nanos = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .expect("time should be monotonic")
            .as_nanos();
        dir.push(format!("{}{}", prefix, nanos));
        dir
    }
}
