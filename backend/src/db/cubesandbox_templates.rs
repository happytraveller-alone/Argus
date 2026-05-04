use anyhow::{Context, Result};
use serde::{Deserialize, Serialize};
use sqlx::Row;
use time::{format_description::well_known::Rfc3339, OffsetDateTime};
use uuid::Uuid;

use crate::state::AppState;

#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum TemplateKind {
    CodeqlCpp,
    Opengrep,
}

impl TemplateKind {
    pub fn as_str(self) -> &'static str {
        match self {
            Self::CodeqlCpp => "codeql_cpp",
            Self::Opengrep => "opengrep",
        }
    }

    pub fn from_str(value: &str) -> Result<Self> {
        match value {
            "codeql_cpp" => Ok(Self::CodeqlCpp),
            "opengrep" => Ok(Self::Opengrep),
            other => anyhow::bail!("unknown cubesandbox template kind: {other}"),
        }
    }
}

#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum TemplateStatus {
    Pending,
    Building,
    Ready,
    Failed,
    Invalidated,
}

impl TemplateStatus {
    pub fn as_str(self) -> &'static str {
        match self {
            Self::Pending => "pending",
            Self::Building => "building",
            Self::Ready => "ready",
            Self::Failed => "failed",
            Self::Invalidated => "invalidated",
        }
    }

    pub fn from_str(value: &str) -> Result<Self> {
        match value {
            "pending" => Ok(Self::Pending),
            "building" => Ok(Self::Building),
            "ready" => Ok(Self::Ready),
            "failed" => Ok(Self::Failed),
            "invalidated" => Ok(Self::Invalidated),
            other => anyhow::bail!("unknown cubesandbox template status: {other}"),
        }
    }

    pub fn is_terminal_inactive(self) -> bool {
        matches!(self, Self::Failed | Self::Invalidated)
    }
}

#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct CubesandboxTemplateRecord {
    pub id: String,
    pub kind: TemplateKind,
    pub status: TemplateStatus,
    pub template_id: Option<String>,
    pub artifact_id: Option<String>,
    pub job_id: Option<String>,
    pub image_ref: String,
    pub error_message: Option<String>,
    pub build_log_tail: String,
    pub created_at: String,
    pub updated_at: String,
    pub ready_at: Option<String>,
}

const BUILD_LOG_TAIL_LIMIT: usize = 4 * 1024;

pub async fn get_active(
    state: &AppState,
    kind: TemplateKind,
) -> Result<Option<CubesandboxTemplateRecord>> {
    let Some(pool) = state.db_pool.as_ref() else {
        return Ok(None);
    };
    let row = sqlx::query(
        r#"
        select id, kind, status, template_id, artifact_id, job_id, image_ref,
            error_message, build_log_tail, created_at, updated_at, ready_at
        from rust_cubesandbox_templates
        where kind = $1
          and status in ('pending', 'building', 'ready')
        order by updated_at desc, created_at desc
        limit 1
        "#,
    )
    .bind(kind.as_str())
    .fetch_optional(pool)
    .await?;
    row.map(record_from_row).transpose()
}

pub async fn list_history(
    state: &AppState,
    kind: TemplateKind,
    limit: i64,
) -> Result<Vec<CubesandboxTemplateRecord>> {
    let Some(pool) = state.db_pool.as_ref() else {
        return Ok(Vec::new());
    };
    let rows = sqlx::query(
        r#"
        select id, kind, status, template_id, artifact_id, job_id, image_ref,
            error_message, build_log_tail, created_at, updated_at, ready_at
        from rust_cubesandbox_templates
        where kind = $1
        order by updated_at desc, created_at desc
        limit $2
        "#,
    )
    .bind(kind.as_str())
    .bind(limit.max(1))
    .fetch_all(pool)
    .await?;
    rows.into_iter().map(record_from_row).collect()
}

pub async fn insert_pending(
    state: &AppState,
    kind: TemplateKind,
    image_ref: &str,
) -> Result<CubesandboxTemplateRecord> {
    let pool = state
        .db_pool
        .as_ref()
        .context("database pool is not configured")?;
    let id = Uuid::new_v4();
    sqlx::query(
        r#"
        insert into rust_cubesandbox_templates
            (id, kind, status, image_ref, build_log_tail)
        values ($1, $2, 'pending', $3, '')
        "#,
    )
    .bind(id)
    .bind(kind.as_str())
    .bind(image_ref)
    .execute(pool)
    .await?;
    load_by_id(state, &id.to_string())
        .await?
        .context("inserted template record disappeared")
}

pub async fn update_to_building(
    state: &AppState,
    id: &str,
    job_id: Option<&str>,
) -> Result<Option<CubesandboxTemplateRecord>> {
    let Some(pool) = state.db_pool.as_ref() else {
        return Ok(None);
    };
    sqlx::query(
        r#"
        update rust_cubesandbox_templates
        set status = 'building',
            job_id = coalesce($2, job_id),
            updated_at = now()
        where id = $1
        "#,
    )
    .bind(parse_uuid(id)?)
    .bind(job_id)
    .execute(pool)
    .await?;
    load_by_id(state, id).await
}

pub async fn update_to_ready(
    state: &AppState,
    id: &str,
    template_id: &str,
    artifact_id: Option<&str>,
) -> Result<Option<CubesandboxTemplateRecord>> {
    let Some(pool) = state.db_pool.as_ref() else {
        return Ok(None);
    };
    sqlx::query(
        r#"
        update rust_cubesandbox_templates
        set status = 'ready',
            template_id = $2,
            artifact_id = $3,
            error_message = null,
            ready_at = now(),
            updated_at = now()
        where id = $1
        "#,
    )
    .bind(parse_uuid(id)?)
    .bind(template_id)
    .bind(artifact_id)
    .execute(pool)
    .await?;
    load_by_id(state, id).await
}

pub async fn update_to_failed(
    state: &AppState,
    id: &str,
    error: &str,
) -> Result<Option<CubesandboxTemplateRecord>> {
    let Some(pool) = state.db_pool.as_ref() else {
        return Ok(None);
    };
    sqlx::query(
        r#"
        update rust_cubesandbox_templates
        set status = 'failed',
            error_message = $2,
            updated_at = now()
        where id = $1
        "#,
    )
    .bind(parse_uuid(id)?)
    .bind(error)
    .execute(pool)
    .await?;
    load_by_id(state, id).await
}

pub async fn mark_invalidated(state: &AppState, kind: TemplateKind) -> Result<u64> {
    let Some(pool) = state.db_pool.as_ref() else {
        return Ok(0);
    };
    let result = sqlx::query(
        r#"
        update rust_cubesandbox_templates
        set status = 'invalidated', updated_at = now()
        where kind = $1
          and status in ('pending', 'building', 'ready')
        "#,
    )
    .bind(kind.as_str())
    .execute(pool)
    .await?;
    Ok(result.rows_affected())
}

pub async fn append_build_log(state: &AppState, id: &str, line: &str) -> Result<()> {
    let Some(pool) = state.db_pool.as_ref() else {
        return Ok(());
    };
    let current = load_by_id(state, id).await?;
    let mut combined = current
        .as_ref()
        .map(|record| record.build_log_tail.clone())
        .unwrap_or_default();
    if !combined.is_empty() && !combined.ends_with('\n') {
        combined.push('\n');
    }
    combined.push_str(line);
    if combined.len() > BUILD_LOG_TAIL_LIMIT {
        let mut start = combined.len().saturating_sub(BUILD_LOG_TAIL_LIMIT);
        while !combined.is_char_boundary(start) {
            start += 1;
        }
        combined = combined[start..].to_string();
    }
    sqlx::query(
        r#"
        update rust_cubesandbox_templates
        set build_log_tail = $2, updated_at = now()
        where id = $1
        "#,
    )
    .bind(parse_uuid(id)?)
    .bind(&combined)
    .execute(pool)
    .await?;
    Ok(())
}

pub async fn load_by_id(state: &AppState, id: &str) -> Result<Option<CubesandboxTemplateRecord>> {
    let Some(pool) = state.db_pool.as_ref() else {
        return Ok(None);
    };
    let row = sqlx::query(
        r#"
        select id, kind, status, template_id, artifact_id, job_id, image_ref,
            error_message, build_log_tail, created_at, updated_at, ready_at
        from rust_cubesandbox_templates
        where id = $1
        "#,
    )
    .bind(parse_uuid(id)?)
    .fetch_optional(pool)
    .await?;
    row.map(record_from_row).transpose()
}

fn record_from_row(row: sqlx::postgres::PgRow) -> Result<CubesandboxTemplateRecord> {
    let kind: String = row.try_get("kind")?;
    let status: String = row.try_get("status")?;
    Ok(CubesandboxTemplateRecord {
        id: row.try_get::<Uuid, _>("id")?.to_string(),
        kind: TemplateKind::from_str(&kind)?,
        status: TemplateStatus::from_str(&status)?,
        template_id: row.try_get("template_id")?,
        artifact_id: row.try_get("artifact_id")?,
        job_id: row.try_get("job_id")?,
        image_ref: row.try_get("image_ref")?,
        error_message: row.try_get("error_message")?,
        build_log_tail: row.try_get("build_log_tail")?,
        created_at: format_timestamp(row.try_get("created_at")?),
        updated_at: format_timestamp(row.try_get("updated_at")?),
        ready_at: row
            .try_get::<Option<OffsetDateTime>, _>("ready_at")?
            .map(format_timestamp),
    })
}

fn parse_uuid(value: &str) -> Result<Uuid> {
    value
        .parse::<Uuid>()
        .with_context(|| format!("invalid uuid: {value}"))
}

fn format_timestamp(value: OffsetDateTime) -> String {
    value
        .format(&Rfc3339)
        .unwrap_or_else(|_| value.unix_timestamp().to_string())
}
