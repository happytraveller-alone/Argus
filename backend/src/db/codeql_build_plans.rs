use anyhow::{Context, Result};
use serde_json::Value;
use sqlx::Row;
use time::{format_description::well_known::Rfc3339, OffsetDateTime};
use uuid::Uuid;

use crate::{db::task_state::CodeqlBuildPlanRecord, state::AppState};

pub async fn upsert_accepted_build_plan(
    state: &AppState,
    record: &CodeqlBuildPlanRecord,
) -> Result<Option<CodeqlBuildPlanRecord>> {
    let Some(pool) = state.db_pool.as_ref() else {
        return Ok(None);
    };

    sqlx::query(
        r#"
        update rust_codeql_build_plans
        set status = 'superseded', updated_at = now()
        where project_id = $1
          and language = $2
          and status = 'accepted'
          and id <> $3
        "#,
    )
    .bind(parse_uuid(&record.project_id)?)
    .bind(&record.language)
    .bind(parse_uuid(&record.id)?)
    .execute(pool)
    .await?;

    sqlx::query(
        r#"
        insert into rust_codeql_build_plans (
            id, project_id, language, target_path, source_fingerprint,
            dependency_fingerprint, build_mode, commands_json, working_directory,
            query_suite, status, llm_model, evidence_json, created_at, updated_at
        )
        values ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15)
        on conflict (id) do update
        set
            project_id = excluded.project_id,
            language = excluded.language,
            target_path = excluded.target_path,
            source_fingerprint = excluded.source_fingerprint,
            dependency_fingerprint = excluded.dependency_fingerprint,
            build_mode = excluded.build_mode,
            commands_json = excluded.commands_json,
            working_directory = excluded.working_directory,
            query_suite = excluded.query_suite,
            status = excluded.status,
            llm_model = excluded.llm_model,
            evidence_json = excluded.evidence_json,
            updated_at = excluded.updated_at
        "#,
    )
    .bind(parse_uuid(&record.id)?)
    .bind(parse_uuid(&record.project_id)?)
    .bind(&record.language)
    .bind(&record.target_path)
    .bind(&record.source_fingerprint)
    .bind(&record.dependency_fingerprint)
    .bind(&record.build_mode)
    .bind(serde_json::to_value(&record.commands).context("serialize CodeQL commands")?)
    .bind(&record.working_directory)
    .bind(&record.query_suite)
    .bind(&record.status)
    .bind(&record.llm_model)
    .bind(&record.evidence_json)
    .bind(parse_timestamp(&record.created_at)?)
    .bind(match &record.updated_at {
        Some(value) => parse_timestamp(value)?,
        None => OffsetDateTime::now_utc(),
    })
    .execute(pool)
    .await?;

    load_build_plan_by_id(state, &record.id).await
}

pub async fn load_active_project_build_plan(
    state: &AppState,
    project_id: &str,
    language: &str,
) -> Result<Option<CodeqlBuildPlanRecord>> {
    let Some(pool) = state.db_pool.as_ref() else {
        return Ok(None);
    };
    let rows = sqlx::query(
        r#"
        select id, project_id, language, target_path, source_fingerprint,
            dependency_fingerprint, build_mode, commands_json, working_directory,
            query_suite, status, llm_model, evidence_json, created_at, updated_at
        from rust_codeql_build_plans
        where project_id = $1
          and language = $2
          and status = 'accepted'
        order by updated_at desc, created_at desc
        limit 2
        "#,
    )
    .bind(parse_uuid(project_id)?)
    .bind(language)
    .fetch_all(pool)
    .await?;

    if rows.len() > 1 {
        anyhow::bail!(
            "ambiguous active CodeQL build plans for project {project_id} language {language}"
        );
    }
    rows.into_iter().next().map(record_from_row).transpose()
}

pub async fn reset_active_project_build_plan(
    state: &AppState,
    project_id: &str,
    language: &str,
) -> Result<u64> {
    let Some(pool) = state.db_pool.as_ref() else {
        return Ok(0);
    };
    let result = sqlx::query(
        r#"
        update rust_codeql_build_plans
        set status = 'reset', updated_at = now()
        where project_id = $1
          and language = $2
          and status = 'accepted'
        "#,
    )
    .bind(parse_uuid(project_id)?)
    .bind(language)
    .execute(pool)
    .await?;
    Ok(result.rows_affected())
}

pub async fn load_build_plan_by_id(
    state: &AppState,
    id: &str,
) -> Result<Option<CodeqlBuildPlanRecord>> {
    let Some(pool) = state.db_pool.as_ref() else {
        return Ok(None);
    };
    let row = sqlx::query(
        r#"
        select id, project_id, language, target_path, source_fingerprint,
            dependency_fingerprint, build_mode, commands_json, working_directory,
            query_suite, status, llm_model, evidence_json, created_at, updated_at
        from rust_codeql_build_plans
        where id = $1
        "#,
    )
    .bind(parse_uuid(id)?)
    .fetch_optional(pool)
    .await?;

    row.map(record_from_row).transpose()
}

fn record_from_row(row: sqlx::postgres::PgRow) -> Result<CodeqlBuildPlanRecord> {
    let commands_json: Value = row.try_get("commands_json")?;
    let commands = serde_json::from_value(commands_json).context("parse CodeQL commands_json")?;
    Ok(CodeqlBuildPlanRecord {
        id: row.try_get::<Uuid, _>("id")?.to_string(),
        project_id: row.try_get::<Uuid, _>("project_id")?.to_string(),
        language: row.try_get("language")?,
        target_path: row.try_get("target_path")?,
        source_fingerprint: row.try_get("source_fingerprint")?,
        dependency_fingerprint: row.try_get("dependency_fingerprint")?,
        build_mode: row.try_get("build_mode")?,
        commands,
        working_directory: row.try_get("working_directory")?,
        query_suite: row.try_get("query_suite")?,
        status: row.try_get("status")?,
        llm_model: row.try_get("llm_model")?,
        evidence_json: row.try_get("evidence_json")?,
        created_at: format_timestamp(row.try_get("created_at")?),
        updated_at: row
            .try_get::<Option<OffsetDateTime>, _>("updated_at")?
            .map(format_timestamp),
    })
}

fn parse_uuid(value: &str) -> Result<Uuid> {
    value
        .parse::<Uuid>()
        .with_context(|| format!("invalid uuid: {value}"))
}

fn parse_timestamp(value: &str) -> Result<OffsetDateTime> {
    OffsetDateTime::parse(value, &Rfc3339).with_context(|| format!("invalid timestamp: {value}"))
}

fn format_timestamp(value: OffsetDateTime) -> String {
    value
        .format(&Rfc3339)
        .unwrap_or_else(|_| value.unix_timestamp().to_string())
}
