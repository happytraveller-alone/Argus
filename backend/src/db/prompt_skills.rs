use std::collections::BTreeMap;

use anyhow::Result;
use serde::{Deserialize, Serialize};
use serde_json::Value;
use sqlx::{PgPool, Postgres, Row, Transaction};
use time::{format_description::well_known::Rfc3339, OffsetDateTime};

use crate::state::AppState;

const RUST_PROMPT_SKILL_OWNER_ID: &str = "bootstrap-user";
const LEGACY_PROMPT_SKILL_BUILTIN_STATE_CONFIG_KEY: &str = "promptSkillBuiltinState";

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct StoredPromptSkillRecord {
    pub id: String,
    pub name: String,
    pub content: String,
    pub scope: String,
    pub agent_key: Option<String>,
    pub is_active: bool,
    pub created_at: String,
    pub updated_at: Option<String>,
}

pub type LegacyPromptSkillRecord = StoredPromptSkillRecord;

#[derive(Debug, Clone, PartialEq, Eq, Default)]
pub struct LegacyBuiltinPromptState {
    pub values: BTreeMap<String, bool>,
}

#[derive(Debug, Clone, PartialEq, Eq, Default)]
pub struct RustPromptSkillSnapshot {
    pub prompt_skill_count: usize,
    pub builtin_state_count: usize,
}

#[derive(Debug, Clone, PartialEq, Eq, Default)]
pub struct CompatBackfillPlan {
    pub prompt_skills_to_import: Vec<LegacyPromptSkillRecord>,
    pub builtin_state_to_import: Option<LegacyBuiltinPromptState>,
}

#[derive(Debug, Clone, PartialEq, Eq, Default)]
pub struct CompatBackfillSummary {
    pub imported_prompt_skill_count: usize,
    pub imported_builtin_state_count: usize,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct PromptSkillOwnerContext {
    pub rust_owner_id: String,
    pub legacy_user_id: Option<String>,
}

pub async fn load_prompt_skills(state: &AppState) -> Result<Vec<StoredPromptSkillRecord>> {
    let pool = state.db_pool.as_ref().expect("db_pool checked");
    let owner = resolve_owner_context(pool).await?;
    load_rust_prompt_skills(pool, &owner).await
}

pub async fn load_prompt_skill(
    state: &AppState,
    prompt_skill_id: &str,
) -> Result<Option<StoredPromptSkillRecord>> {
    let pool = state.db_pool.as_ref().expect("db_pool checked");
    let owner = resolve_owner_context(pool).await?;
    load_single_rust_prompt_skill(pool, &owner, prompt_skill_id).await
}

pub async fn create_prompt_skill(
    state: &AppState,
    record: &StoredPromptSkillRecord,
) -> Result<StoredPromptSkillRecord> {
    let pool = state.db_pool.as_ref().expect("db_pool checked");
    let owner = resolve_owner_context(pool).await?;
    let mut tx = pool.begin().await?;
    insert_rust_prompt_skill(&mut tx, &owner, record).await?;
    upsert_legacy_prompt_skill(&mut tx, &owner, record).await?;
    tx.commit().await?;
    Ok(record.clone())
}

pub async fn update_prompt_skill(
    state: &AppState,
    record: &StoredPromptSkillRecord,
) -> Result<Option<StoredPromptSkillRecord>> {
    let pool = state.db_pool.as_ref().expect("db_pool checked");
    let owner = resolve_owner_context(pool).await?;
    let mut tx = pool.begin().await?;
    if !update_rust_prompt_skill(&mut tx, &owner, record).await? {
        tx.rollback().await?;
        return Ok(None);
    }
    upsert_legacy_prompt_skill(&mut tx, &owner, record).await?;
    tx.commit().await?;
    Ok(Some(record.clone()))
}

pub async fn delete_prompt_skill(state: &AppState, prompt_skill_id: &str) -> Result<bool> {
    let pool = state.db_pool.as_ref().expect("db_pool checked");
    let owner = resolve_owner_context(pool).await?;
    let mut tx = pool.begin().await?;
    let deleted = delete_rust_prompt_skill(&mut tx, &owner, prompt_skill_id).await?;
    if !deleted {
        tx.rollback().await?;
        return Ok(false);
    }
    delete_legacy_prompt_skill(&mut tx, &owner, prompt_skill_id).await?;
    tx.commit().await?;
    Ok(true)
}

pub async fn load_builtin_prompt_state(
    state: &AppState,
    supported_agent_keys: &[&str],
) -> Result<BTreeMap<String, bool>> {
    let pool = state.db_pool.as_ref().expect("db_pool checked");
    let owner = resolve_owner_context(pool).await?;
    load_rust_builtin_prompt_state(pool, &owner, supported_agent_keys).await
}

pub async fn set_builtin_prompt_state(
    state: &AppState,
    agent_key: &str,
    is_active: bool,
    supported_agent_keys: &[&str],
) -> Result<()> {
    let pool = state.db_pool.as_ref().expect("db_pool checked");
    let owner = resolve_owner_context(pool).await?;
    let mut tx = pool.begin().await?;
    upsert_rust_builtin_prompt_state(&mut tx, &owner, agent_key, is_active).await?;
    upsert_legacy_builtin_prompt_state(
        &mut tx,
        &owner,
        agent_key,
        is_active,
        supported_agent_keys,
    )
    .await?;
    tx.commit().await?;
    Ok(())
}

pub async fn compat_backfill_from_legacy_if_empty(
    state: &AppState,
    supported_agent_keys: &[&str],
) -> Result<CompatBackfillSummary> {
    let pool = state.db_pool.as_ref().expect("db_pool checked");
    let owner = resolve_owner_context(pool).await?;
    let snapshot = load_rust_prompt_skill_snapshot(pool, &owner).await?;
    let legacy_prompt_skills = if snapshot.prompt_skill_count == 0 {
        load_legacy_prompt_skills(pool, &owner).await?
    } else {
        Vec::new()
    };
    let legacy_builtin_state = if snapshot.builtin_state_count == 0 {
        load_legacy_builtin_prompt_state(pool, &owner, supported_agent_keys).await?
    } else {
        None
    };
    let plan = build_compat_backfill_plan(
        &snapshot,
        &legacy_prompt_skills,
        legacy_builtin_state.as_ref(),
    );
    if plan.prompt_skills_to_import.is_empty() && plan.builtin_state_to_import.is_none() {
        return Ok(CompatBackfillSummary::default());
    }

    let mut summary = CompatBackfillSummary::default();
    let mut tx = pool.begin().await?;

    let prompt_skill_count = count_rows(
        &mut *tx,
        &owner.rust_owner_id,
        "select count(*) from rust_prompt_skills where owner_id = $1",
    )
    .await?;
    if prompt_skill_count == 0 {
        for item in &plan.prompt_skills_to_import {
            insert_rust_prompt_skill(&mut tx, &owner, item).await?;
        }
        summary.imported_prompt_skill_count = plan.prompt_skills_to_import.len();
    }

    let builtin_state_count = count_rows(
        &mut *tx,
        &owner.rust_owner_id,
        "select count(*) from rust_prompt_skill_builtin_states where owner_id = $1",
    )
    .await?;
    if builtin_state_count == 0 {
        if let Some(builtin_state) = &plan.builtin_state_to_import {
            for (agent_key, is_active) in &builtin_state.values {
                upsert_rust_builtin_prompt_state(&mut tx, &owner, agent_key, *is_active).await?;
            }
            summary.imported_builtin_state_count = builtin_state.values.len();
        }
    }

    tx.commit().await?;
    Ok(summary)
}

pub fn build_compat_backfill_plan(
    rust_snapshot: &RustPromptSkillSnapshot,
    legacy_prompt_skills: &[LegacyPromptSkillRecord],
    legacy_builtin_state: Option<&LegacyBuiltinPromptState>,
) -> CompatBackfillPlan {
    CompatBackfillPlan {
        prompt_skills_to_import: if rust_snapshot.prompt_skill_count == 0 {
            legacy_prompt_skills.to_vec()
        } else {
            Vec::new()
        },
        builtin_state_to_import: if rust_snapshot.builtin_state_count == 0 {
            legacy_builtin_state.cloned()
        } else {
            None
        },
    }
}

pub async fn resolve_owner_context(pool: &PgPool) -> Result<PromptSkillOwnerContext> {
    let legacy_user_id = resolve_first_legacy_user_id(pool).await?;
    Ok(prompt_skill_owner_context(legacy_user_id.as_deref()))
}

fn prompt_skill_owner_context(legacy_user_id: Option<&str>) -> PromptSkillOwnerContext {
    PromptSkillOwnerContext {
        rust_owner_id: RUST_PROMPT_SKILL_OWNER_ID.to_string(),
        legacy_user_id: legacy_user_id.map(str::to_string),
    }
}

async fn load_rust_prompt_skills(
    pool: &PgPool,
    owner: &PromptSkillOwnerContext,
) -> Result<Vec<StoredPromptSkillRecord>> {
    let rows = sqlx::query(
        r#"
        select id, name, content, scope, agent_key, is_active, created_at, updated_at
        from rust_prompt_skills
        where owner_id = $1
        order by created_at desc, id desc
        "#,
    )
    .bind(&owner.rust_owner_id)
    .fetch_all(pool)
    .await?;

    Ok(rows
        .into_iter()
        .map(|row| StoredPromptSkillRecord {
            id: row.try_get("id").unwrap_or_default(),
            name: row.try_get("name").unwrap_or_default(),
            content: row.try_get("content").unwrap_or_default(),
            scope: row.try_get("scope").unwrap_or_default(),
            agent_key: row.try_get("agent_key").unwrap_or(None),
            is_active: row.try_get("is_active").unwrap_or(true),
            created_at: format_timestamp(
                row.try_get::<Option<OffsetDateTime>, _>("created_at")
                    .unwrap_or(None),
            ),
            updated_at: row
                .try_get::<Option<OffsetDateTime>, _>("updated_at")
                .unwrap_or(None)
                .map(|value| format_timestamp(Some(value))),
        })
        .collect())
}

async fn load_single_rust_prompt_skill(
    pool: &PgPool,
    owner: &PromptSkillOwnerContext,
    prompt_skill_id: &str,
) -> Result<Option<StoredPromptSkillRecord>> {
    let row = sqlx::query(
        r#"
        select id, name, content, scope, agent_key, is_active, created_at, updated_at
        from rust_prompt_skills
        where owner_id = $1 and id = $2
        "#,
    )
    .bind(&owner.rust_owner_id)
    .bind(prompt_skill_id)
    .fetch_optional(pool)
    .await?;
    Ok(row.map(map_row_to_prompt_skill))
}

async fn load_rust_prompt_skill_snapshot(
    pool: &PgPool,
    owner: &PromptSkillOwnerContext,
) -> Result<RustPromptSkillSnapshot> {
    Ok(RustPromptSkillSnapshot {
        prompt_skill_count: count_rows(
            pool,
            &owner.rust_owner_id,
            "select count(*) from rust_prompt_skills where owner_id = $1",
        )
        .await?,
        builtin_state_count: count_rows(
            pool,
            &owner.rust_owner_id,
            "select count(*) from rust_prompt_skill_builtin_states where owner_id = $1",
        )
        .await?,
    })
}

async fn load_legacy_prompt_skills(
    pool: &PgPool,
    owner: &PromptSkillOwnerContext,
) -> Result<Vec<LegacyPromptSkillRecord>> {
    let Some(user_id) = owner.legacy_user_id.as_ref() else {
        return Ok(Vec::new());
    };
    let rows = sqlx::query(
        r#"
        select id, name, content, scope, agent_key, is_active, created_at, updated_at
        from prompt_skills
        where user_id = $1
        order by created_at desc, id desc
        "#,
    )
    .bind(user_id)
        .fetch_all(pool)
        .await?;

    Ok(rows.into_iter().map(map_row_to_prompt_skill).collect())
}

async fn load_legacy_builtin_prompt_state(
    pool: &PgPool,
    owner: &PromptSkillOwnerContext,
    supported_agent_keys: &[&str],
) -> Result<Option<LegacyBuiltinPromptState>> {
    let Some(user_id) = owner.legacy_user_id.as_ref() else {
        return Ok(None);
    };
    let row = sqlx::query("select other_config from user_configs where user_id = $1")
        .bind(user_id)
        .fetch_optional(pool)
        .await?;
    let Some(row) = row else {
        return Ok(None);
    };
    let raw: String = row.try_get("other_config").unwrap_or_else(|_| "{}".to_string());
    let parsed: Value = serde_json::from_str(&raw).unwrap_or(Value::Null);
    let Some(map) = parsed
        .get(LEGACY_PROMPT_SKILL_BUILTIN_STATE_CONFIG_KEY)
        .and_then(Value::as_object)
    else {
        return Ok(None);
    };

    let mut values = BTreeMap::new();
    for agent_key in supported_agent_keys {
        if let Some(is_active) = map.get(*agent_key).and_then(Value::as_bool) {
            values.insert((*agent_key).to_string(), is_active);
        }
    }
    if values.is_empty() {
        return Ok(None);
    }
    Ok(Some(LegacyBuiltinPromptState { values }))
}

async fn resolve_first_legacy_user_id(pool: &PgPool) -> Result<Option<String>> {
    let user_id = sqlx::query_scalar("select id from users order by created_at asc limit 1")
        .fetch_optional(pool)
        .await?;
    Ok(user_id)
}

async fn count_rows<'e, E>(executor: E, owner_id: &str, sql: &str) -> Result<usize>
where
    E: sqlx::Executor<'e, Database = sqlx::Postgres>,
{
    let count = sqlx::query_scalar::<_, i64>(sql)
        .bind(owner_id)
        .fetch_one(executor)
        .await?;
    Ok(count.max(0) as usize)
}

async fn insert_rust_prompt_skill(
    tx: &mut Transaction<'_, Postgres>,
    owner: &PromptSkillOwnerContext,
    item: &StoredPromptSkillRecord,
) -> Result<()> {
    sqlx::query(
        r#"
        insert into rust_prompt_skills (
            owner_id,
            id,
            name,
            content,
            scope,
            agent_key,
            is_active,
            created_at,
            updated_at
        )
        values ($1, $2, $3, $4, $5, $6, $7, $8, $9)
        "#,
    )
    .bind(&owner.rust_owner_id)
    .bind(&item.id)
    .bind(&item.name)
    .bind(&item.content)
    .bind(&item.scope)
    .bind(&item.agent_key)
    .bind(item.is_active)
    .bind(parse_timestamp(Some(item.created_at.as_str())))
    .bind(item.updated_at.as_deref().map(|value| parse_timestamp(Some(value))))
    .execute(&mut **tx)
    .await?;
    Ok(())
}

async fn update_rust_prompt_skill(
    tx: &mut Transaction<'_, Postgres>,
    owner: &PromptSkillOwnerContext,
    item: &StoredPromptSkillRecord,
) -> Result<bool> {
    let rows_affected = sqlx::query(
        r#"
        update rust_prompt_skills
        set name = $3,
            content = $4,
            scope = $5,
            agent_key = $6,
            is_active = $7,
            updated_at = $8
        where owner_id = $1 and id = $2
        "#,
    )
    .bind(&owner.rust_owner_id)
    .bind(&item.id)
    .bind(&item.name)
    .bind(&item.content)
    .bind(&item.scope)
    .bind(&item.agent_key)
    .bind(item.is_active)
    .bind(item.updated_at.as_deref().map(|value| parse_timestamp(Some(value))))
    .execute(&mut **tx)
    .await?
    .rows_affected();
    Ok(rows_affected > 0)
}

async fn delete_rust_prompt_skill(
    tx: &mut Transaction<'_, Postgres>,
    owner: &PromptSkillOwnerContext,
    prompt_skill_id: &str,
) -> Result<bool> {
    let rows_affected = sqlx::query(
        "delete from rust_prompt_skills where owner_id = $1 and id = $2",
    )
    .bind(&owner.rust_owner_id)
    .bind(prompt_skill_id)
    .execute(&mut **tx)
    .await?
    .rows_affected();
    Ok(rows_affected > 0)
}

async fn load_rust_builtin_prompt_state(
    pool: &PgPool,
    owner: &PromptSkillOwnerContext,
    supported_agent_keys: &[&str],
) -> Result<BTreeMap<String, bool>> {
    let mut values = default_builtin_prompt_state(supported_agent_keys);
    let rows = sqlx::query(
        r#"
        select agent_key, is_active
        from rust_prompt_skill_builtin_states
        where owner_id = $1
        "#,
    )
    .bind(&owner.rust_owner_id)
    .fetch_all(pool)
    .await?;
    for row in rows {
        let agent_key: String = row.try_get("agent_key").unwrap_or_default();
        let is_active: bool = row.try_get("is_active").unwrap_or(true);
        values.insert(agent_key, is_active);
    }
    Ok(values)
}

async fn upsert_rust_builtin_prompt_state(
    tx: &mut Transaction<'_, Postgres>,
    owner: &PromptSkillOwnerContext,
    agent_key: &str,
    is_active: bool,
) -> Result<()> {
    sqlx::query(
        r#"
        insert into rust_prompt_skill_builtin_states (owner_id, agent_key, is_active, updated_at)
        values ($1, $2, $3, now())
        on conflict (owner_id, agent_key) do update
        set is_active = excluded.is_active,
            updated_at = now()
        "#,
    )
    .bind(&owner.rust_owner_id)
    .bind(agent_key)
    .bind(is_active)
    .execute(&mut **tx)
    .await?;
    Ok(())
}

async fn upsert_legacy_prompt_skill(
    tx: &mut Transaction<'_, Postgres>,
    owner: &PromptSkillOwnerContext,
    item: &StoredPromptSkillRecord,
) -> Result<()> {
    let Some(legacy_user_id) = owner.legacy_user_id.as_ref() else {
        return Ok(());
    };
    sqlx::query(
        r#"
        insert into prompt_skills (id, user_id, name, content, scope, agent_key, is_active, created_at, updated_at)
        values ($1, $2, $3, $4, $5, $6, $7, $8, $9)
        on conflict (id) do update
        set user_id = excluded.user_id,
            name = excluded.name,
            content = excluded.content,
            scope = excluded.scope,
            agent_key = excluded.agent_key,
            is_active = excluded.is_active,
            created_at = excluded.created_at,
            updated_at = excluded.updated_at
        "#,
    )
    .bind(&item.id)
    .bind(legacy_user_id)
    .bind(&item.name)
    .bind(&item.content)
    .bind(&item.scope)
    .bind(&item.agent_key)
    .bind(item.is_active)
    .bind(parse_timestamp(Some(item.created_at.as_str())))
    .bind(item.updated_at.as_deref().map(|value| parse_timestamp(Some(value))))
    .execute(&mut **tx)
    .await?;
    Ok(())
}

async fn delete_legacy_prompt_skill(
    tx: &mut Transaction<'_, Postgres>,
    owner: &PromptSkillOwnerContext,
    prompt_skill_id: &str,
) -> Result<()> {
    let Some(legacy_user_id) = owner.legacy_user_id.as_ref() else {
        return Ok(());
    };
    sqlx::query("delete from prompt_skills where id = $1 and user_id = $2")
        .bind(prompt_skill_id)
        .bind(legacy_user_id)
        .execute(&mut **tx)
        .await?;
    Ok(())
}

async fn upsert_legacy_builtin_prompt_state(
    tx: &mut Transaction<'_, Postgres>,
    owner: &PromptSkillOwnerContext,
    agent_key: &str,
    is_active: bool,
    supported_agent_keys: &[&str],
) -> Result<()> {
    let Some(legacy_user_id) = owner.legacy_user_id.as_ref() else {
        return Ok(());
    };
    let row = sqlx::query("select id, llm_config, other_config from user_configs where user_id = $1")
        .bind(legacy_user_id)
        .fetch_optional(&mut **tx)
        .await?;
    let mut other_config = row
        .as_ref()
        .and_then(|row| row.try_get::<String, _>("other_config").ok())
        .and_then(|raw| serde_json::from_str::<Value>(&raw).ok())
        .unwrap_or_else(|| Value::Object(Default::default()));
    if !other_config.is_object() {
        other_config = Value::Object(Default::default());
    }
    let mut builtin_state = extract_builtin_state_map(other_config.get(LEGACY_PROMPT_SKILL_BUILTIN_STATE_CONFIG_KEY), supported_agent_keys);
    builtin_state.insert(agent_key.to_string(), is_active);
    other_config[LEGACY_PROMPT_SKILL_BUILTIN_STATE_CONFIG_KEY] = serde_json::json!(builtin_state);
    let llm_config = row
        .as_ref()
        .and_then(|row| row.try_get::<String, _>("llm_config").ok())
        .unwrap_or_else(|| "{}".to_string());

    match row {
        Some(row) => {
            let config_id: String = row.try_get("id").unwrap_or_default();
            sqlx::query("update user_configs set other_config = $1, llm_config = $2, updated_at = now() where id = $3")
                .bind(other_config.to_string())
                .bind(llm_config)
                .bind(config_id)
                .execute(&mut **tx)
                .await?;
        }
        None => {
            sqlx::query(
                "insert into user_configs (id, user_id, llm_config, other_config) values ($1, $2, $3, $4)",
            )
            .bind(format!("rust-prompt-config-{legacy_user_id}"))
            .bind(legacy_user_id)
            .bind("{}")
            .bind(other_config.to_string())
            .execute(&mut **tx)
            .await?;
        }
    }
    Ok(())
}

fn extract_builtin_state_map(
    raw_value: Option<&Value>,
    supported_agent_keys: &[&str],
) -> BTreeMap<String, bool> {
    let mut values = BTreeMap::new();
    let Some(map) = raw_value.and_then(Value::as_object) else {
        return values;
    };
    for agent_key in supported_agent_keys {
        if let Some(is_active) = map.get(*agent_key).and_then(Value::as_bool) {
            values.insert((*agent_key).to_string(), is_active);
        }
    }
    values
}

fn map_row_to_prompt_skill(row: sqlx::postgres::PgRow) -> StoredPromptSkillRecord {
    StoredPromptSkillRecord {
        id: row.try_get("id").unwrap_or_default(),
        name: row.try_get("name").unwrap_or_default(),
        content: row.try_get("content").unwrap_or_default(),
        scope: row.try_get("scope").unwrap_or_else(|_| "global".to_string()),
        agent_key: row.try_get("agent_key").unwrap_or(None),
        is_active: row.try_get("is_active").unwrap_or(true),
        created_at: format_timestamp(
            row.try_get::<Option<OffsetDateTime>, _>("created_at")
                .unwrap_or(None),
        ),
        updated_at: row
            .try_get::<Option<OffsetDateTime>, _>("updated_at")
            .unwrap_or(None)
            .map(|value| format_timestamp(Some(value))),
    }
}

fn default_builtin_prompt_state(supported_agent_keys: &[&str]) -> BTreeMap<String, bool> {
    supported_agent_keys
        .iter()
        .map(|agent_key| ((*agent_key).to_string(), true))
        .collect()
}

fn parse_timestamp(value: Option<&str>) -> OffsetDateTime {
    value
        .and_then(|item| OffsetDateTime::parse(item, &Rfc3339).ok())
        .unwrap_or_else(OffsetDateTime::now_utc)
}

fn format_timestamp(value: Option<OffsetDateTime>) -> String {
    value
        .and_then(|item| item.format(&Rfc3339).ok())
        .unwrap_or_else(|| {
            OffsetDateTime::now_utc()
                .format(&Rfc3339)
                .unwrap_or_else(|_| OffsetDateTime::now_utc().unix_timestamp().to_string())
        })
}

#[cfg(test)]
mod tests {
    use std::collections::BTreeMap;
    use serde_json::json;

    use super::{
        build_compat_backfill_plan, extract_builtin_state_map, prompt_skill_owner_context,
        CompatBackfillPlan, LegacyBuiltinPromptState, LegacyPromptSkillRecord,
        PromptSkillOwnerContext, RustPromptSkillSnapshot,
    };

    fn legacy_prompt(id: &str) -> LegacyPromptSkillRecord {
        LegacyPromptSkillRecord {
            id: id.to_string(),
            name: format!("Prompt {id}"),
            content: format!("Content {id}"),
            scope: "global".to_string(),
            agent_key: None,
            is_active: true,
            created_at: "2026-04-15T00:00:00Z".to_string(),
            updated_at: Some("2026-04-15T00:00:01Z".to_string()),
        }
    }

    #[test]
    fn backfill_plan_imports_legacy_data_when_rust_native_store_is_empty() {
        let legacy_builtin = LegacyBuiltinPromptState {
            values: BTreeMap::from([
                ("analysis".to_string(), false),
                ("verification".to_string(), true),
            ]),
        };

        let plan = build_compat_backfill_plan(
            &RustPromptSkillSnapshot::default(),
            &[legacy_prompt("legacy-1"), legacy_prompt("legacy-2")],
            Some(&legacy_builtin),
        );

        assert_eq!(
            plan,
            CompatBackfillPlan {
                prompt_skills_to_import: vec![legacy_prompt("legacy-1"), legacy_prompt("legacy-2")],
                builtin_state_to_import: Some(legacy_builtin),
            }
        );
    }

    #[test]
    fn backfill_plan_does_not_override_existing_rust_native_data() {
        let legacy_builtin = LegacyBuiltinPromptState {
            values: BTreeMap::from([("analysis".to_string(), false)]),
        };
        let snapshot = RustPromptSkillSnapshot {
            prompt_skill_count: 1,
            builtin_state_count: 2,
        };

        let plan =
            build_compat_backfill_plan(&snapshot, &[legacy_prompt("legacy-1")], Some(&legacy_builtin));

        assert_eq!(
            plan,
            CompatBackfillPlan {
                prompt_skills_to_import: Vec::new(),
                builtin_state_to_import: None,
            }
        );
    }

    #[test]
    fn backfill_plan_treats_prompt_and_builtin_stores_independently() {
        let legacy_builtin = LegacyBuiltinPromptState {
            values: BTreeMap::from([("analysis".to_string(), false)]),
        };
        let snapshot = RustPromptSkillSnapshot {
            prompt_skill_count: 2,
            builtin_state_count: 0,
        };

        let plan =
            build_compat_backfill_plan(&snapshot, &[legacy_prompt("legacy-1")], Some(&legacy_builtin));

        assert_eq!(plan.prompt_skills_to_import, Vec::<LegacyPromptSkillRecord>::new());
        assert_eq!(plan.builtin_state_to_import, Some(legacy_builtin));
    }

    #[test]
    fn owner_context_uses_bootstrap_owner_and_optional_legacy_user() {
        assert_eq!(
            prompt_skill_owner_context(Some("legacy-user-1")),
            PromptSkillOwnerContext {
                rust_owner_id: "bootstrap-user".to_string(),
                legacy_user_id: Some("legacy-user-1".to_string()),
            }
        );
        assert_eq!(
            prompt_skill_owner_context(None),
            PromptSkillOwnerContext {
                rust_owner_id: "bootstrap-user".to_string(),
                legacy_user_id: None,
            }
        );
    }

    #[test]
    fn extract_builtin_state_map_filters_to_supported_agent_keys() {
        let raw = json!({
            "analysis": false,
            "verification": true,
            "unknown": false,
            "recon": "invalid"
        });

        let values =
            extract_builtin_state_map(Some(&raw), &["analysis", "verification", "recon"]);

        assert_eq!(
            values,
            BTreeMap::from([
                ("analysis".to_string(), false),
                ("verification".to_string(), true),
            ])
        );
    }
}
