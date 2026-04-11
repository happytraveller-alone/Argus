mod init;
mod preflight;
mod recovery;

use std::time::Duration;

use anyhow::{anyhow, Result};
use sqlx::PgPool;
use tokio::time::timeout;

use crate::state::{AppState, BootstrapReport, BootstrapStatus, DatabaseBootstrapStatus};

const REQUIRED_RUST_TABLES: &[&str] = &["system_configs", "rust_projects", "rust_project_archives"];

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
            report.database = DatabaseBootstrapStatus::file_mode();
        }
        Some(pool) => {
            report.database = check_database(pool).await;
            if report.database.status != BootstrapStatus::Ok.as_str() {
                // Non-fatal for now: we still want the server to start so /health can report.
                report.overall = BootstrapStatus::Degraded.as_str().to_string();
            }
        }
    }

    let rust_db_ready = report.database.mode == "db"
        && report.database.status == BootstrapStatus::Ok.as_str();
    let database_reachable = report.database.mode == "db"
        && matches!(
            report.database.status.as_str(),
            "ok" | "degraded"
        );

    report.init = match init::run(state, rust_db_ready).await {
        Ok(status) => status,
        Err(error) => {
            report.overall = BootstrapStatus::Degraded.as_str().to_string();
            crate::state::StartupInitStatus {
                status: BootstrapStatus::Error.as_str().to_string(),
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

    report.preflight = match preflight::run(&state.config).await {
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

async fn check_database(pool: &PgPool) -> DatabaseBootstrapStatus {
    let mut status = DatabaseBootstrapStatus::db_mode();
    status.checked_tables = REQUIRED_RUST_TABLES.iter().map(|name| (*name).to_string()).collect();

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
            return status;
        }
        Err(_) => {
            status.status = "timeout".to_string();
            status.error = Some("connectivity check timed out".to_string());
            return status;
        }
    };

    let rust_tables = timeout(
        Duration::from_secs(2),
        sqlx::query_scalar::<_, String>(
            "SELECT table_name
             FROM information_schema.tables
             WHERE table_schema = 'public'
               AND table_name IN ('system_configs', 'rust_projects', 'rust_project_archives')",
        )
        .fetch_all(pool),
    )
    .await;

    let present_tables = match rust_tables {
        Ok(Ok(rows)) => rows,
        Ok(Err(err)) => {
            status.status = BootstrapStatus::Error.as_str().to_string();
            status.error = Some(err.to_string());
            return status;
        }
        Err(_) => {
            status.status = "timeout".to_string();
            status.error = Some("database table inventory check timed out".to_string());
            return status;
        }
    };

    let missing_rust_tables = missing_required_tables(&present_tables);
    status.missing_tables = missing_rust_tables.iter().map(|name| (*name).to_string()).collect();

    if !missing_rust_tables.is_empty() {
        status.status = BootstrapStatus::Degraded.as_str().to_string();
        status.error = Some(format!(
            "missing required rust tables: {}",
            missing_rust_tables.join(", ")
        ));
        return status;
    }
    status.status = BootstrapStatus::Ok.as_str().to_string();

    status
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
    use super::missing_required_tables;

    #[test]
    fn missing_required_tables_reports_exact_rust_dependencies() {
        let present = vec!["system_configs".to_string()];
        let missing = missing_required_tables(&present);
        assert_eq!(missing, vec!["rust_projects", "rust_project_archives"]);
    }

    #[test]
    fn missing_required_tables_is_empty_when_all_rust_tables_exist() {
        let present = vec![
            "system_configs".to_string(),
            "rust_projects".to_string(),
            "rust_project_archives".to_string(),
        ];
        assert!(missing_required_tables(&present).is_empty());
    }
}
