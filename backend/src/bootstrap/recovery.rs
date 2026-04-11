use anyhow::Result;
use sqlx::PgPool;

use crate::state::{AppState, BootstrapStatus, RecoveryTaskStatus, StartupRecoveryStatus};

const INTERRUPTED_ERROR_MESSAGE: &str = "服务中断，任务被自动标记为中断";

struct RecoverySpec {
    name: &'static str,
    table: &'static str,
    recoverable_statuses: &'static [&'static str],
    has_completed_at: bool,
    has_error_message: bool,
    has_error_count: bool,
}

const RECOVERY_SPECS: &[RecoverySpec] = &[
    RecoverySpec {
        name: "agent",
        table: "agent_tasks",
        recoverable_statuses: &[
            "pending",
            "initializing",
            "running",
            "planning",
            "indexing",
            "analyzing",
            "verifying",
            "reporting",
        ],
        has_completed_at: true,
        has_error_message: true,
        has_error_count: false,
    },
    RecoverySpec {
        name: "opengrep",
        table: "opengrep_scan_tasks",
        recoverable_statuses: &["pending", "running"],
        has_completed_at: false,
        has_error_message: false,
        has_error_count: true,
    },
    RecoverySpec {
        name: "gitleaks",
        table: "gitleaks_scan_tasks",
        recoverable_statuses: &["pending", "running"],
        has_completed_at: false,
        has_error_message: true,
        has_error_count: false,
    },
    RecoverySpec {
        name: "bandit",
        table: "bandit_scan_tasks",
        recoverable_statuses: &["pending", "running"],
        has_completed_at: false,
        has_error_message: true,
        has_error_count: false,
    },
    RecoverySpec {
        name: "phpstan",
        table: "phpstan_scan_tasks",
        recoverable_statuses: &["pending", "running"],
        has_completed_at: false,
        has_error_message: true,
        has_error_count: false,
    },
    RecoverySpec {
        name: "pmd",
        table: "pmd_scan_tasks",
        recoverable_statuses: &["pending", "running"],
        has_completed_at: false,
        has_error_message: true,
        has_error_count: false,
    },
];

pub async fn run(state: &AppState, database_reachable: bool) -> Result<StartupRecoveryStatus> {
    if !state.config.startup_recovery_enabled {
        return Ok(StartupRecoveryStatus {
            status: "skipped".to_string(),
            tasks: Vec::new(),
            error: None,
        });
    }

    let Some(pool) = &state.db_pool else {
        return Ok(StartupRecoveryStatus {
            status: "skipped".to_string(),
            tasks: Vec::new(),
            error: None,
        });
    };

    if !database_reachable {
        return Ok(StartupRecoveryStatus {
            status: "skipped".to_string(),
            tasks: Vec::new(),
            error: Some("database not reachable for startup recovery".to_string()),
        });
    }

    let present_tables = fetch_present_tables(pool).await?;
    let mut tasks = Vec::with_capacity(RECOVERY_SPECS.len());

    for spec in RECOVERY_SPECS {
        let table_present = present_tables.iter().any(|name| name == spec.table);
        if !table_present {
            tasks.push(RecoveryTaskStatus {
                name: spec.name.to_string(),
                table_present: false,
                recovered: 0,
            });
            continue;
        }

        let recovered = execute_recovery_update(pool, spec).await?;
        tasks.push(RecoveryTaskStatus {
            name: spec.name.to_string(),
            table_present: true,
            recovered,
        });
    }

    Ok(StartupRecoveryStatus {
        status: BootstrapStatus::Ok.as_str().to_string(),
        tasks,
        error: None,
    })
}

async fn fetch_present_tables(pool: &PgPool) -> Result<Vec<String>> {
    Ok(sqlx::query_scalar::<_, String>(
        "SELECT table_name
         FROM information_schema.tables
         WHERE table_schema = 'public'
           AND table_name IN (
             'agent_tasks',
             'opengrep_scan_tasks',
             'gitleaks_scan_tasks',
             'bandit_scan_tasks',
             'phpstan_scan_tasks',
             'pmd_scan_tasks'
           )",
    )
    .fetch_all(pool)
    .await?)
}

async fn execute_recovery_update(pool: &PgPool, spec: &RecoverySpec) -> Result<u64> {
    let query = build_recovery_update_sql(spec);
    let result = sqlx::query(&query)
        .bind(INTERRUPTED_ERROR_MESSAGE)
        .execute(pool)
        .await?;
    Ok(result.rows_affected())
}

fn build_recovery_update_sql(spec: &RecoverySpec) -> String {
    let mut assignments = vec!["status = 'interrupted'".to_string()];
    if spec.has_completed_at {
        assignments.push("completed_at = COALESCE(completed_at, NOW())".to_string());
    }
    if spec.has_error_message {
        assignments.push("error_message = COALESCE(NULLIF(error_message, ''), $1)".to_string());
    }
    if spec.has_error_count {
        assignments.push("error_count = COALESCE(error_count, 0) + 1".to_string());
    }

    let statuses = spec
        .recoverable_statuses
        .iter()
        .map(|status| format!("'{status}'"))
        .collect::<Vec<_>>()
        .join(", ");

    format!(
        "UPDATE {} SET {} WHERE lower(status) IN ({})",
        spec.table,
        assignments.join(", "),
        statuses
    )
}

#[cfg(test)]
mod tests {
    use super::{build_recovery_update_sql, RECOVERY_SPECS};

    #[test]
    fn recovery_specs_cover_all_startup_task_families() {
        let names = RECOVERY_SPECS
            .iter()
            .map(|spec| spec.name)
            .collect::<Vec<_>>();
        assert_eq!(
            names,
            vec!["agent", "opengrep", "gitleaks", "bandit", "phpstan", "pmd"]
        );
    }

    #[test]
    fn recovery_sql_includes_optional_columns_only_when_needed() {
        let agent_sql = build_recovery_update_sql(&RECOVERY_SPECS[0]);
        assert!(agent_sql.contains("completed_at = COALESCE(completed_at, NOW())"));
        assert!(agent_sql.contains("error_message = COALESCE(NULLIF(error_message, ''), $1)"));

        let opengrep_sql = build_recovery_update_sql(&RECOVERY_SPECS[1]);
        assert!(opengrep_sql.contains("error_count = COALESCE(error_count, 0) + 1"));
        assert!(!opengrep_sql.contains("completed_at = COALESCE(completed_at, NOW())"));
    }
}
