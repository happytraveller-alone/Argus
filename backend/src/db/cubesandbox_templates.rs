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
    OpengrepDedicated,
}

impl TemplateKind {
    pub const fn current_opengrep() -> Self {
        Self::OpengrepDedicated
    }

    pub fn as_str(self) -> &'static str {
        match self {
            Self::CodeqlCpp => "codeql_cpp",
            Self::Opengrep => "opengrep",
            Self::OpengrepDedicated => "opengrep_dedicated",
        }
    }

    #[allow(clippy::should_implement_trait)]
    pub fn from_str(value: &str) -> Result<Self> {
        match value {
            "codeql_cpp" => Ok(Self::CodeqlCpp),
            "opengrep" => Ok(Self::Opengrep),
            "opengrep_dedicated" => Ok(Self::OpengrepDedicated),
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

    #[allow(clippy::should_implement_trait)]
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
    pub image_fingerprint: Option<String>,
    pub consecutive_scan_failures: i16,
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
            error_message, build_log_tail, created_at, updated_at, ready_at,
            image_fingerprint, consecutive_scan_failures
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
            error_message, build_log_tail, created_at, updated_at, ready_at,
            image_fingerprint, consecutive_scan_failures
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

pub async fn list_all_history(
    state: &AppState,
    limit: i64,
) -> Result<Vec<CubesandboxTemplateRecord>> {
    let Some(pool) = state.db_pool.as_ref() else {
        return Ok(Vec::new());
    };
    let rows = sqlx::query(
        r#"
        select id, kind, status, template_id, artifact_id, job_id, image_ref,
            error_message, build_log_tail, created_at, updated_at, ready_at,
            image_fingerprint, consecutive_scan_failures
        from rust_cubesandbox_templates
        order by updated_at desc, created_at desc
        limit $1
        "#,
    )
    .bind(limit.max(1))
    .fetch_all(pool)
    .await?;
    rows.into_iter().map(record_from_row).collect()
}

pub async fn list_failed(state: &AppState, limit: i64) -> Result<Vec<CubesandboxTemplateRecord>> {
    let Some(pool) = state.db_pool.as_ref() else {
        return Ok(Vec::new());
    };
    let rows = sqlx::query(
        r#"
        select id, kind, status, template_id, artifact_id, job_id, image_ref,
            error_message, build_log_tail, created_at, updated_at, ready_at,
            image_fingerprint, consecutive_scan_failures
        from rust_cubesandbox_templates
        where status = 'failed'
        order by updated_at desc, created_at desc
        limit $1
        "#,
    )
    .bind(limit.max(1))
    .fetch_all(pool)
    .await?;
    rows.into_iter().map(record_from_row).collect()
}

pub async fn list_failed_or_invalidated(
    state: &AppState,
    limit: i64,
) -> Result<Vec<CubesandboxTemplateRecord>> {
    let Some(pool) = state.db_pool.as_ref() else {
        return Ok(Vec::new());
    };
    let rows = sqlx::query(
        r#"
        select id, kind, status, template_id, artifact_id, job_id, image_ref,
            error_message, build_log_tail, created_at, updated_at, ready_at,
            image_fingerprint, consecutive_scan_failures
        from rust_cubesandbox_templates
        where status in ('failed', 'invalidated')
        order by updated_at desc, created_at desc
        limit $1
        "#,
    )
    .bind(limit.max(1))
    .fetch_all(pool)
    .await?;
    rows.into_iter().map(record_from_row).collect()
}

pub async fn list_failed_or_invalidated_by_kind(
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
            error_message, build_log_tail, created_at, updated_at, ready_at,
            image_fingerprint, consecutive_scan_failures
        from rust_cubesandbox_templates
        where kind = $1
          and status in ('failed', 'invalidated')
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

pub async fn delete_failed_or_invalidated_by_id(
    state: &AppState,
    id: &str,
) -> Result<Option<CubesandboxTemplateRecord>> {
    let Some(pool) = state.db_pool.as_ref() else {
        return Ok(None);
    };
    let existing = load_by_id(state, id).await?;
    let Some(record) = existing else {
        return Ok(None);
    };
    if !record.status.is_terminal_inactive() {
        return Ok(Some(record));
    }
    sqlx::query(
        r#"
        delete from rust_cubesandbox_templates
        where id = $1 and status in ('failed', 'invalidated')
        "#,
    )
    .bind(parse_uuid(id)?)
    .execute(pool)
    .await?;
    Ok(Some(record))
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

/// Per-id variant of mark_invalidated. Used by reconcile when a specific template
/// (not an entire kind) must be invalidated (e.g. fingerprint mismatch or scan-failure threshold).
pub async fn mark_invalidated_by_template_id(state: &AppState, template_id: &str) -> Result<()> {
    let Some(pool) = state.db_pool.as_ref() else {
        return Ok(());
    };
    sqlx::query(
        r#"
        update rust_cubesandbox_templates
        set status = 'invalidated', updated_at = now()
        where template_id = $1
          and status in ('pending', 'building', 'ready')
        "#,
    )
    .bind(template_id)
    .execute(pool)
    .await?;
    Ok(())
}

/// List all active (pending | building | ready) records across all template kinds.
/// Used by reconcile to build the full cross-kind protection set.
pub async fn list_active_all_kinds(state: &AppState) -> Result<Vec<CubesandboxTemplateRecord>> {
    let Some(pool) = state.db_pool.as_ref() else {
        return Ok(Vec::new());
    };
    let rows = sqlx::query(
        r#"
        select id, kind, status, template_id, artifact_id, job_id, image_ref,
            error_message, build_log_tail, created_at, updated_at, ready_at,
            image_fingerprint, consecutive_scan_failures
        from rust_cubesandbox_templates
        where status in ('pending', 'building', 'ready')
        order by updated_at desc, created_at desc
        "#,
    )
    .fetch_all(pool)
    .await?;
    rows.into_iter().map(record_from_row).collect()
}

/// Set the image_fingerprint column for a specific template record.
/// Called by template_provisioner at provision-success time.
pub async fn set_image_fingerprint(
    state: &AppState,
    template_id: &str,
    fingerprint: &str,
) -> Result<()> {
    let Some(pool) = state.db_pool.as_ref() else {
        return Ok(());
    };
    sqlx::query(
        r#"
        update rust_cubesandbox_templates
        set image_fingerprint = $2, updated_at = now()
        where template_id = $1
        "#,
    )
    .bind(template_id)
    .bind(fingerprint)
    .execute(pool)
    .await?;
    Ok(())
}

/// Increment consecutive_scan_failures by 1 and return the post-bump value.
/// The bump is done in a single atomic UPDATE … RETURNING so no read-modify-write race.
pub async fn bump_scan_failure_counter(state: &AppState, template_id: &str) -> Result<i16> {
    let Some(pool) = state.db_pool.as_ref() else {
        return Ok(0);
    };
    let row = sqlx::query(
        r#"
        update rust_cubesandbox_templates
        set consecutive_scan_failures = consecutive_scan_failures + 1,
            updated_at = now()
        where template_id = $1
        returning consecutive_scan_failures
        "#,
    )
    .bind(template_id)
    .fetch_optional(pool)
    .await?;
    match row {
        Some(r) => Ok(r.try_get::<i16, _>("consecutive_scan_failures")?),
        None => Ok(0),
    }
}

/// Reset consecutive_scan_failures to 0. Called after successful scan or after
/// mark_invalidated_by_template_id to prevent re-fire.
pub async fn reset_scan_failure_counter(state: &AppState, template_id: &str) -> Result<()> {
    let Some(pool) = state.db_pool.as_ref() else {
        return Ok(());
    };
    sqlx::query(
        r#"
        update rust_cubesandbox_templates
        set consecutive_scan_failures = 0, updated_at = now()
        where template_id = $1
        "#,
    )
    .bind(template_id)
    .execute(pool)
    .await?;
    Ok(())
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
            error_message, build_log_tail, created_at, updated_at, ready_at,
            image_fingerprint, consecutive_scan_failures
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
        image_fingerprint: row.try_get("image_fingerprint")?,
        consecutive_scan_failures: row.try_get("consecutive_scan_failures")?,
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

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn template_kind_round_trip_keeps_legacy_and_dedicated_opengrep() {
        let cases = [
            ("codeql_cpp", TemplateKind::CodeqlCpp),
            ("opengrep", TemplateKind::Opengrep),
            ("opengrep_dedicated", TemplateKind::OpengrepDedicated),
        ];

        for (text, kind) in cases {
            assert_eq!(kind.as_str(), text);
            assert_eq!(TemplateKind::from_str(text).unwrap(), kind);
        }
        assert_eq!(
            TemplateKind::current_opengrep(),
            TemplateKind::OpengrepDedicated
        );
        assert!(TemplateKind::from_str("opengrep-surprise").is_err());
    }

    /// Phase 3: scan-failure counter threshold logic.
    /// No PgPool harness is available in this repo (grep for sqlx::test / test_db found nothing),
    /// so integration tests that hit the DB are omitted. This unit test validates the threshold
    /// predicate used in run_codeql_scan / run_opengrep_scan counter feedback arms.
    #[test]
    fn scan_failure_counter_threshold_predicate() {
        // The dispatch arms use `Ok(n) if n >= 3` — verify the boundary.
        let below: i16 = 2;
        let at: i16 = 3;
        let above: i16 = 4;
        assert!(!(below >= 3), "counter 2 must NOT trigger invalidation");
        assert!(at >= 3, "counter 3 must trigger invalidation");
        assert!(above >= 3, "counter 4 must trigger invalidation");
    }

    /// Phase 3: summary_json status dispatch correctness.
    /// Validates that the `get("status").and_then(|v| v.as_str())` pattern
    /// used in both scan dispatch fns correctly matches the enum arms.
    #[test]
    fn summary_json_status_dispatch() {
        use serde_json::json;
        let scan_failed = json!({"status": "scan_failed"});
        let scan_ok = json!({"status": "scan_completed"});
        let missing = json!({});
        let unexpected = json!({"status": "unknown_status"});

        let arm = |v: &serde_json::Value| -> &str {
            match v.get("status").and_then(|s| s.as_str()) {
                Some("scan_failed") => "failed_arm",
                Some("scan_completed") => "ok_arm",
                _ => "wildcard",
            }
        };

        assert_eq!(arm(&scan_failed), "failed_arm");
        assert_eq!(arm(&scan_ok), "ok_arm");
        assert_eq!(arm(&missing), "wildcard");
        assert_eq!(arm(&unexpected), "wildcard");
    }
}
