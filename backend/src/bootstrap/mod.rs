mod init;
mod legacy_mirror_schema;
mod preflight;
mod recovery;

use std::time::Duration;

use anyhow::{anyhow, Result};
use sqlx::PgPool;
use tokio::time::timeout;

use crate::state::{
    AppState, BootstrapReport, BootstrapStatus, DatabaseBootstrapStatus, RecoveryTaskStatus,
};

const REQUIRED_RUST_TABLES: &[&str] = &[
    "system_configs",
    "rust_projects",
    "rust_project_archives",
    "rust_scan_rule_assets",
    "rust_prompt_skills",
    "rust_prompt_skill_builtin_states",
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
    match state
        .cube_sandbox_task_manager
        .reconcile_orphans(state)
        .await
    {
        Ok(()) => report.recovery.tasks.push(RecoveryTaskStatus {
            name: "cubesandbox_tasks".to_string(),
            table_present: true,
            recovered: 0,
        }),
        Err(error) => {
            report.overall = BootstrapStatus::Degraded.as_str().to_string();
            report.recovery.status = BootstrapStatus::Degraded.as_str().to_string();
            report.recovery.error =
                Some(format!("CubeSandbox orphan reconciliation failed: {error}"));
        }
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

async fn check_database(pool: &PgPool) -> DatabaseBootstrapStatus {
    let mut status = DatabaseBootstrapStatus::db_mode();
    status.checked_tables = REQUIRED_RUST_TABLES
        .iter()
        .map(|name| (*name).to_string())
        .collect();

    // Connectivity: run a trivial query, but never hang startup forever.
    if let Err(err) = ensure_rust_schema(pool).await {
        status.status = BootstrapStatus::Error.as_str().to_string();
        status.error = Some(format!("failed to ensure rust schema: {err}"));
        return status;
    }

    let connectivity = timeout(
        Duration::from_secs(2),
        sqlx::query_scalar::<_, i32>("SELECT 1").fetch_one(pool),
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
               AND table_name IN (
                    'system_configs',
                    'rust_projects',
                    'rust_project_archives',
                    'rust_scan_rule_assets',
                    'rust_prompt_skills',
                    'rust_prompt_skill_builtin_states'
               )",
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
    if status.status == BootstrapStatus::NotRun.as_str() {
        status.status = BootstrapStatus::Ok.as_str().to_string();
    }

    status
}

async fn ensure_rust_schema(pool: &PgPool) -> Result<()> {
    sqlx::query(
        r#"
        create table if not exists system_configs (
            id text primary key,
            llm_config_json jsonb not null default '{}'::jsonb,
            other_config_json jsonb not null default '{}'::jsonb,
            llm_test_metadata_json jsonb not null default '{}'::jsonb,
            created_at timestamptz not null default now(),
            updated_at timestamptz not null default now()
        )
        "#,
    )
    .execute(pool)
    .await?;

    sqlx::query(
        r#"
        alter table system_configs
        add column if not exists llm_test_metadata_json jsonb not null default '{}'::jsonb
        "#,
    )
    .execute(pool)
    .await?;

    sqlx::query(
        r#"
        create table if not exists rust_projects (
            id uuid primary key,
            name text not null,
            description text not null default '',
            source_type text not null default 'zip',
            repository_type text not null default 'other',
            default_branch text not null default 'main',
            programming_languages_json jsonb not null default '[]'::jsonb,
            is_active boolean not null default true,
            language_info_json jsonb not null default '{}'::jsonb,
            info_status text not null default 'pending',
            created_at timestamptz not null default now(),
            updated_at timestamptz not null default now()
        )
        "#,
    )
    .execute(pool)
    .await?;

    sqlx::query(
        r#"
        create table if not exists rust_project_archives (
            project_id uuid primary key references rust_projects(id) on delete cascade,
            original_filename text not null,
            storage_path text not null,
            sha256 text not null,
            file_size bigint not null default 0,
            uploaded_at timestamptz not null default now()
        )
        "#,
    )
    .execute(pool)
    .await?;

    sqlx::query(
        r#"
        create table if not exists rust_scan_rule_assets (
            engine text not null,
            source_kind text not null,
            asset_path text not null,
            file_format text not null,
            sha256 text not null,
            content text not null,
            metadata_json jsonb not null default '{}'::jsonb,
            is_active boolean not null default true,
            created_at timestamptz not null default now(),
            updated_at timestamptz not null default now(),
            primary key (engine, source_kind, asset_path)
        )
        "#,
    )
    .execute(pool)
    .await?;

    sqlx::query(
        r#"
        create index if not exists ix_rust_scan_rule_assets_engine_kind
            on rust_scan_rule_assets (engine, source_kind, is_active)
        "#,
    )
    .execute(pool)
    .await?;

    sqlx::query(
        r#"
        create table if not exists rust_codeql_build_plans (
            id uuid primary key,
            project_id uuid not null references rust_projects(id) on delete cascade,
            language text not null,
            target_path text not null default '.',
            source_fingerprint text not null,
            dependency_fingerprint text not null,
            build_mode text not null,
            commands_json jsonb not null default '[]'::jsonb,
            working_directory text not null default '.',
            query_suite text,
            status text not null default 'candidate',
            llm_model text,
            evidence_json jsonb not null default '{}'::jsonb,
            created_at timestamptz not null default now(),
            updated_at timestamptz not null default now()
        )
        "#,
    )
    .execute(pool)
    .await?;

    sqlx::query(
        r#"
        create index if not exists ix_rust_codeql_build_plans_lookup
            on rust_codeql_build_plans (project_id, language, target_path, status)
        "#,
    )
    .execute(pool)
    .await?;

    sqlx::query(
        r#"
        create table if not exists rust_prompt_skills (
            owner_id text not null,
            id text not null,
            name text not null default '',
            content text not null default '',
            scope text not null default 'global',
            agent_key text,
            is_active boolean not null default true,
            created_at timestamptz not null default now(),
            updated_at timestamptz,
            primary key (owner_id, id)
        )
        "#,
    )
    .execute(pool)
    .await?;

    sqlx::query(
        r#"
        create index if not exists ix_rust_prompt_skills_owner_scope_agent
            on rust_prompt_skills (owner_id, scope, agent_key, created_at desc)
        "#,
    )
    .execute(pool)
    .await?;

    sqlx::query(
        r#"
        create table if not exists rust_prompt_skill_builtin_states (
            owner_id text not null,
            agent_key text not null,
            is_active boolean not null default true,
            updated_at timestamptz not null default now(),
            primary key (owner_id, agent_key)
        )
        "#,
    )
    .execute(pool)
    .await?;

    Ok(())
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
    use super::{mark_database_degraded, missing_required_tables};
    use crate::state::{BootstrapStatus, DatabaseBootstrapStatus};

    #[test]
    fn mark_database_degraded_sets_first_non_fatal_error() {
        let mut status = DatabaseBootstrapStatus::db_mode();

        mark_database_degraded(&mut status, "missing required rust tables".to_string());

        assert_eq!(status.status, BootstrapStatus::Degraded.as_str());
        assert_eq!(
            status.error.as_deref(),
            Some("missing required rust tables")
        );
    }

    #[test]
    fn mark_database_degraded_preserves_existing_error_message() {
        let mut status = DatabaseBootstrapStatus::db_mode();
        status.error = Some("existing error".to_string());

        mark_database_degraded(&mut status, "new error".to_string());

        assert_eq!(status.status, BootstrapStatus::Degraded.as_str());
        assert_eq!(status.error.as_deref(), Some("existing error"));
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
                "rust_scan_rule_assets",
                "rust_prompt_skills",
                "rust_prompt_skill_builtin_states",
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
            "rust_prompt_skills".to_string(),
            "rust_prompt_skill_builtin_states".to_string(),
        ];
        assert!(missing_required_tables(&present).is_empty());
    }
}
