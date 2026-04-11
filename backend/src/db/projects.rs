use std::{collections::BTreeMap, io::ErrorKind, path::PathBuf, str::FromStr};

use anyhow::{Context, Result};
use serde_json::{json, Value};
use sqlx::Row;
use time::{format_description::well_known::Rfc3339, OffsetDateTime};
use tokio::fs;
use uuid::Uuid;

use crate::state::{AppState, StoredProject, StoredProjectArchive};

const PROJECTS_FILE_NAME: &str = "rust-projects.json";

pub async fn ensure_initialized(state: &AppState) -> Result<bool> {
    if state.db_pool.is_some() {
        return Ok(false);
    }

    let _guard = state.file_store_lock.lock().await;
    let path = projects_file_path(state);
    match fs::metadata(&path).await {
        Ok(_) => Ok(false),
        Err(error) if error.kind() == ErrorKind::NotFound => {
            save_projects_unlocked(state, &BTreeMap::new()).await?;
            Ok(true)
        }
        Err(error) => Err(error.into()),
    }
}

pub async fn create_project(state: &AppState, project: StoredProject) -> Result<StoredProject> {
    if state.db_pool.is_some() {
        create_project_db(state, project).await
    } else {
        create_project_file(state, project).await
    }
}

pub async fn list_projects(state: &AppState) -> Result<Vec<StoredProject>> {
    if state.db_pool.is_some() {
        list_projects_db(state).await
    } else {
        list_projects_file(state).await
    }
}

pub async fn get_project(state: &AppState, project_id: &str) -> Result<Option<StoredProject>> {
    if state.db_pool.is_some() {
        get_project_db(state, project_id).await
    } else {
        get_project_file(state, project_id).await
    }
}

pub async fn update_project(state: &AppState, project: StoredProject) -> Result<StoredProject> {
    if state.db_pool.is_some() {
        update_project_db(state, project).await
    } else {
        update_project_file(state, project).await
    }
}

pub async fn delete_project(state: &AppState, project_id: &str) -> Result<Option<StoredProject>> {
    if state.db_pool.is_some() {
        delete_project_db(state, project_id).await
    } else {
        delete_project_file(state, project_id).await
    }
}

pub async fn save_archive(
    state: &AppState,
    project_id: &str,
    archive: StoredProjectArchive,
) -> Result<Option<StoredProject>> {
    if state.db_pool.is_some() {
        save_archive_db(state, project_id, archive).await
    } else {
        save_archive_file(state, project_id, archive).await
    }
}

pub async fn clear_archive(state: &AppState, project_id: &str) -> Result<Option<StoredProject>> {
    if state.db_pool.is_some() {
        clear_archive_db(state, project_id).await
    } else {
        clear_archive_file(state, project_id).await
    }
}

pub async fn replace_all(
    state: &AppState,
    projects: BTreeMap<String, StoredProject>,
) -> Result<()> {
    if state.db_pool.is_some() {
        replace_all_db(state, projects).await
    } else {
        replace_all_file(state, projects).await
    }
}

async fn create_project_db(state: &AppState, project: StoredProject) -> Result<StoredProject> {
    let pool = state.db_pool.as_ref().expect("db_pool checked");
    let project_id = parse_uuid(&project.id)?;
    sqlx::query(
        r#"
        insert into rust_projects (
            id, name, description, source_type, repository_type, default_branch,
            programming_languages_json, is_active, language_info_json, info_status,
            created_at, updated_at
        )
        values ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)
        "#,
    )
    .bind(project_id)
    .bind(&project.name)
    .bind(&project.description)
    .bind(&project.source_type)
    .bind(&project.repository_type)
    .bind(&project.default_branch)
    .bind(parse_json_or_default(
        &project.programming_languages_json,
        json!([]),
    ))
    .bind(project.is_active)
    .bind(parse_json_or_default(&project.language_info, json!({})))
    .bind(&project.info_status)
    .bind(parse_timestamp(&project.created_at)?)
    .bind(parse_timestamp(&project.updated_at)?)
    .execute(pool)
    .await?;
    if let Some(archive) = project.archive.clone() {
        upsert_archive_row(pool, &project.id, &archive).await?;
    }
    Ok(project)
}

async fn list_projects_db(state: &AppState) -> Result<Vec<StoredProject>> {
    let pool = state.db_pool.as_ref().expect("db_pool checked");
    let rows = sqlx::query(
        r#"
        select
            p.id,
            p.name,
            p.description,
            p.source_type,
            p.repository_type,
            p.default_branch,
            p.programming_languages_json,
            p.is_active,
            p.language_info_json,
            p.info_status,
            p.created_at,
            p.updated_at,
            a.original_filename,
            a.storage_path,
            a.sha256,
            a.file_size,
            a.uploaded_at
        from rust_projects p
        left join rust_project_archives a on a.project_id = p.id
        order by p.created_at desc
        "#,
    )
    .fetch_all(pool)
    .await?;
    rows.into_iter().map(stored_project_from_row).collect()
}

async fn get_project_db(state: &AppState, project_id: &str) -> Result<Option<StoredProject>> {
    let pool = state.db_pool.as_ref().expect("db_pool checked");
    let project_id = parse_uuid(project_id)?;
    let row = sqlx::query(
        r#"
        select
            p.id,
            p.name,
            p.description,
            p.source_type,
            p.repository_type,
            p.default_branch,
            p.programming_languages_json,
            p.is_active,
            p.language_info_json,
            p.info_status,
            p.created_at,
            p.updated_at,
            a.original_filename,
            a.storage_path,
            a.sha256,
            a.file_size,
            a.uploaded_at
        from rust_projects p
        left join rust_project_archives a on a.project_id = p.id
        where p.id = $1
        "#,
    )
    .bind(project_id)
    .fetch_optional(pool)
    .await?;
    row.map(stored_project_from_row).transpose()
}

async fn update_project_db(state: &AppState, project: StoredProject) -> Result<StoredProject> {
    let pool = state.db_pool.as_ref().expect("db_pool checked");
    let project_id = parse_uuid(&project.id)?;
    sqlx::query(
        r#"
        update rust_projects
        set
            name = $2,
            description = $3,
            source_type = $4,
            repository_type = $5,
            default_branch = $6,
            programming_languages_json = $7,
            is_active = $8,
            language_info_json = $9,
            info_status = $10,
            updated_at = $11
        where id = $1
        "#,
    )
    .bind(project_id)
    .bind(&project.name)
    .bind(&project.description)
    .bind(&project.source_type)
    .bind(&project.repository_type)
    .bind(&project.default_branch)
    .bind(parse_json_or_default(
        &project.programming_languages_json,
        json!([]),
    ))
    .bind(project.is_active)
    .bind(parse_json_or_default(&project.language_info, json!({})))
    .bind(&project.info_status)
    .bind(parse_timestamp(&project.updated_at)?)
    .execute(pool)
    .await?;

    match project.archive.clone() {
        Some(archive) => upsert_archive_row(pool, &project.id, &archive).await?,
        None => {
            sqlx::query("delete from rust_project_archives where project_id = $1")
                .bind(project_id)
                .execute(pool)
                .await?;
        }
    }
    Ok(project)
}

async fn delete_project_db(state: &AppState, project_id: &str) -> Result<Option<StoredProject>> {
    let current = get_project_db(state, project_id).await?;
    let Some(project) = current else {
        return Ok(None);
    };
    let pool = state.db_pool.as_ref().expect("db_pool checked");
    let project_id = parse_uuid(project_id)?;
    sqlx::query("delete from rust_projects where id = $1")
        .bind(project_id)
        .execute(pool)
        .await?;
    Ok(Some(project))
}

async fn save_archive_db(
    state: &AppState,
    project_id: &str,
    archive: StoredProjectArchive,
) -> Result<Option<StoredProject>> {
    let Some(mut project) = get_project_db(state, project_id).await? else {
        return Ok(None);
    };
    let pool = state.db_pool.as_ref().expect("db_pool checked");
    upsert_archive_row(pool, project_id, &archive).await?;
    project.archive = Some(archive);
    Ok(Some(project))
}

async fn clear_archive_db(state: &AppState, project_id: &str) -> Result<Option<StoredProject>> {
    let Some(mut project) = get_project_db(state, project_id).await? else {
        return Ok(None);
    };
    let pool = state.db_pool.as_ref().expect("db_pool checked");
    sqlx::query("delete from rust_project_archives where project_id = $1")
        .bind(parse_uuid(project_id)?)
        .execute(pool)
        .await?;
    project.archive = None;
    Ok(Some(project))
}

async fn replace_all_db(state: &AppState, projects: BTreeMap<String, StoredProject>) -> Result<()> {
    let pool = state.db_pool.as_ref().expect("db_pool checked");
    sqlx::query("delete from rust_project_archives")
        .execute(pool)
        .await?;
    sqlx::query("delete from rust_projects")
        .execute(pool)
        .await?;
    for project in projects.into_values() {
        create_project_db(state, project).await?;
    }
    Ok(())
}

async fn upsert_archive_row(
    pool: &sqlx::PgPool,
    project_id: &str,
    archive: &StoredProjectArchive,
) -> Result<()> {
    sqlx::query(
        r#"
        insert into rust_project_archives (
            project_id, original_filename, storage_path, sha256, file_size, uploaded_at
        )
        values ($1, $2, $3, $4, $5, $6)
        on conflict (project_id) do update
        set
            original_filename = excluded.original_filename,
            storage_path = excluded.storage_path,
            sha256 = excluded.sha256,
            file_size = excluded.file_size,
            uploaded_at = excluded.uploaded_at
        "#,
    )
    .bind(parse_uuid(project_id)?)
    .bind(&archive.original_filename)
    .bind(&archive.storage_path)
    .bind(&archive.sha256)
    .bind(archive.file_size)
    .bind(parse_timestamp(&archive.uploaded_at)?)
    .execute(pool)
    .await?;
    Ok(())
}

fn stored_project_from_row(row: sqlx::postgres::PgRow) -> Result<StoredProject> {
    let archive = match row.try_get::<Option<String>, _>("original_filename")? {
        Some(original_filename) => Some(StoredProjectArchive {
            original_filename,
            storage_path: row.try_get("storage_path")?,
            sha256: row.try_get("sha256")?,
            file_size: row.try_get("file_size")?,
            uploaded_at: format_timestamp(row.try_get("uploaded_at")?),
        }),
        None => None,
    };

    Ok(StoredProject {
        id: row.try_get::<Uuid, _>("id")?.to_string(),
        name: row.try_get("name")?,
        description: row.try_get("description")?,
        source_type: row.try_get("source_type")?,
        repository_type: row.try_get("repository_type")?,
        default_branch: row.try_get("default_branch")?,
        programming_languages_json: row
            .try_get::<Value, _>("programming_languages_json")?
            .to_string(),
        is_active: row.try_get("is_active")?,
        created_at: format_timestamp(row.try_get("created_at")?),
        updated_at: format_timestamp(row.try_get("updated_at")?),
        language_info: row.try_get::<Value, _>("language_info_json")?.to_string(),
        info_status: row.try_get("info_status")?,
        archive,
    })
}

async fn create_project_file(state: &AppState, project: StoredProject) -> Result<StoredProject> {
    let _guard = state.file_store_lock.lock().await;
    let mut projects = load_projects_unlocked(state).await?;
    projects.insert(project.id.clone(), project.clone());
    save_projects_unlocked(state, &projects).await?;
    Ok(project)
}

async fn list_projects_file(state: &AppState) -> Result<Vec<StoredProject>> {
    let _guard = state.file_store_lock.lock().await;
    let projects = load_projects_unlocked(state).await?;
    Ok(projects.into_values().collect())
}

async fn get_project_file(state: &AppState, project_id: &str) -> Result<Option<StoredProject>> {
    let _guard = state.file_store_lock.lock().await;
    let projects = load_projects_unlocked(state).await?;
    Ok(projects.get(project_id).cloned())
}

async fn update_project_file(state: &AppState, project: StoredProject) -> Result<StoredProject> {
    let _guard = state.file_store_lock.lock().await;
    let mut projects = load_projects_unlocked(state).await?;
    projects.insert(project.id.clone(), project.clone());
    save_projects_unlocked(state, &projects).await?;
    Ok(project)
}

async fn delete_project_file(state: &AppState, project_id: &str) -> Result<Option<StoredProject>> {
    let _guard = state.file_store_lock.lock().await;
    let mut projects = load_projects_unlocked(state).await?;
    let removed = projects.remove(project_id);
    save_projects_unlocked(state, &projects).await?;
    Ok(removed)
}

async fn save_archive_file(
    state: &AppState,
    project_id: &str,
    archive: StoredProjectArchive,
) -> Result<Option<StoredProject>> {
    let _guard = state.file_store_lock.lock().await;
    let mut projects = load_projects_unlocked(state).await?;
    if let Some(project) = projects.get_mut(project_id) {
        project.archive = Some(archive);
        let updated = project.clone();
        save_projects_unlocked(state, &projects).await?;
        return Ok(Some(updated));
    }
    Ok(None)
}

async fn clear_archive_file(state: &AppState, project_id: &str) -> Result<Option<StoredProject>> {
    let _guard = state.file_store_lock.lock().await;
    let mut projects = load_projects_unlocked(state).await?;
    if let Some(project) = projects.get_mut(project_id) {
        project.archive = None;
        let updated = project.clone();
        save_projects_unlocked(state, &projects).await?;
        return Ok(Some(updated));
    }
    Ok(None)
}

async fn replace_all_file(
    state: &AppState,
    projects: BTreeMap<String, StoredProject>,
) -> Result<()> {
    let _guard = state.file_store_lock.lock().await;
    save_projects_unlocked(state, &projects).await
}

async fn load_projects_unlocked(state: &AppState) -> Result<BTreeMap<String, StoredProject>> {
    let path = projects_file_path(state);
    let raw = match fs::read_to_string(&path).await {
        Ok(raw) => raw,
        Err(error) if error.kind() == ErrorKind::NotFound => return Ok(BTreeMap::new()),
        Err(error) => return Err(error.into()),
    };
    serde_json::from_str(&raw).with_context(|| {
        format!(
            "failed to parse file-backed projects store: {}",
            path.display()
        )
    })
}

async fn save_projects_unlocked(
    state: &AppState,
    projects: &BTreeMap<String, StoredProject>,
) -> Result<()> {
    ensure_file_storage_root(state).await?;
    let path = projects_file_path(state);
    let tmp_path = path.with_extension("tmp");
    let bytes = serde_json::to_vec(projects)?;
    fs::write(&tmp_path, bytes).await?;
    fs::rename(&tmp_path, &path).await?;
    Ok(())
}

fn projects_file_path(state: &AppState) -> PathBuf {
    state.config.zip_storage_path.join(PROJECTS_FILE_NAME)
}

async fn ensure_file_storage_root(state: &AppState) -> Result<()> {
    fs::create_dir_all(&state.config.zip_storage_path).await?;
    Ok(())
}

fn parse_uuid(value: &str) -> Result<Uuid> {
    Uuid::from_str(value).with_context(|| format!("invalid uuid: {value}"))
}

fn parse_timestamp(value: &str) -> Result<OffsetDateTime> {
    OffsetDateTime::parse(value, &Rfc3339).with_context(|| format!("invalid timestamp: {value}"))
}

fn format_timestamp(value: OffsetDateTime) -> String {
    value
        .format(&Rfc3339)
        .unwrap_or_else(|_| value.unix_timestamp().to_string())
}

fn parse_json_or_default(raw: &str, default: Value) -> Value {
    serde_json::from_str(raw).unwrap_or(default)
}
