use std::{
    collections::{BTreeMap, BTreeSet},
    io::Cursor,
    path::{Path, PathBuf},
};

use axum::{
    body::Body,
    extract::{Multipart, Path as AxumPath, Query, State},
    http::{header, HeaderValue, StatusCode},
    response::Response,
    routing::{get, post},
    Json, Router,
};
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use sha2::{Digest, Sha256};
use time::{format_description::well_known::Rfc3339, OffsetDateTime};
use tokio::fs;
use uuid::Uuid;
use zip::ZipArchive;

use crate::{
    db::projects,
    error::ApiError,
    state::{AppState, StoredProject, StoredProjectArchive},
};

#[derive(Debug, Clone, Deserialize)]
pub struct ProjectListQuery {
    pub skip: Option<usize>,
    pub limit: Option<usize>,
    pub include_metrics: Option<bool>,
}

#[derive(Debug, Clone, Deserialize)]
pub struct ProjectMutationRequest {
    pub name: String,
    pub description: Option<String>,
    pub source_type: Option<String>,
    pub repository_url: Option<String>,
    pub repository_type: Option<String>,
    pub default_branch: Option<String>,
    pub programming_languages: Option<Vec<String>>,
}

#[derive(Debug, Clone, Deserialize)]
pub struct ProjectUpdateRequest {
    pub name: Option<String>,
    pub description: Option<String>,
    pub source_type: Option<String>,
    pub repository_url: Option<String>,
    pub repository_type: Option<String>,
    pub default_branch: Option<String>,
    pub programming_languages: Option<Vec<String>>,
}

#[derive(Debug, Clone, Serialize)]
pub struct ProjectManagementMetricsResponse {
    pub archive_size_bytes: Option<i64>,
    pub archive_original_filename: Option<String>,
    pub archive_uploaded_at: Option<String>,
    pub total_tasks: i64,
    pub completed_tasks: i64,
    pub running_tasks: i64,
    pub agent_tasks: i64,
    pub opengrep_tasks: i64,
    pub gitleaks_tasks: i64,
    pub bandit_tasks: i64,
    pub phpstan_tasks: i64,
    pub critical: i64,
    pub high: i64,
    pub medium: i64,
    pub low: i64,
    pub verified_critical: i64,
    pub verified_high: i64,
    pub verified_medium: i64,
    pub verified_low: i64,
    pub last_completed_task_at: Option<String>,
    pub status: String,
    pub error_message: Option<String>,
    pub created_at: String,
    pub updated_at: String,
}

#[derive(Debug, Clone, Serialize)]
pub struct ProjectResponse {
    pub id: String,
    pub name: String,
    pub description: String,
    pub source_type: String,
    pub repository_type: String,
    pub default_branch: String,
    pub programming_languages: String,
    pub is_active: bool,
    pub created_at: String,
    pub updated_at: String,
    pub management_metrics: Option<ProjectManagementMetricsResponse>,
}

#[derive(Debug, Clone, Serialize)]
pub struct ProjectInfoResponse {
    pub project_id: String,
    pub language_info: String,
    pub description: String,
    pub status: String,
}

#[derive(Debug, Clone, Serialize)]
pub struct ZipFileMetaResponse {
    pub has_file: bool,
    pub original_filename: Option<String>,
    pub file_size: Option<i64>,
    pub uploaded_at: Option<String>,
}

#[derive(Debug, Clone, Serialize)]
pub struct ProjectDescriptionGenerateResponse {
    pub description: String,
    pub language_info: String,
    pub source: String,
}

#[derive(Debug, Clone, Serialize)]
pub struct ArchiveUploadResponse {
    pub message: String,
    pub original_filename: String,
    pub file_size: i64,
    pub detected_languages: Vec<String>,
}

pub fn router() -> Router<AppState> {
    Router::new()
        .route("/", post(create_project).get(list_projects))
        .route("/create-with-zip", post(create_project_with_zip))
        .route(
            "/description/generate",
            post(generate_project_description_preview),
        )
        .route("/info/{id}", get(get_project_info))
        .route(
            "/{id}",
            get(get_project).put(update_project).delete(delete_project),
        )
        .route("/{id}/archive", get(download_project_archive))
        .route(
            "/{id}/zip",
            get(get_project_zip_info)
                .post(upload_project_zip)
                .delete(delete_project_zip),
        )
        .route(
            "/{id}/description/generate",
            post(generate_project_description_for_project),
        )
}

pub async fn create_project(
    State(state): State<AppState>,
    Json(payload): Json<ProjectMutationRequest>,
) -> Result<Json<ProjectResponse>, ApiError> {
    validate_project_payload(
        payload.source_type.as_deref(),
        payload.repository_url.as_deref(),
    )?;
    let now = now_rfc3339();
    let programming_languages = payload.programming_languages.unwrap_or_default();
    let project = StoredProject {
        id: Uuid::new_v4().to_string(),
        name: payload.name,
        description: payload.description.unwrap_or_default(),
        source_type: "zip".to_string(),
        repository_type: payload
            .repository_type
            .unwrap_or_else(|| "other".to_string()),
        default_branch: payload.default_branch.unwrap_or_else(|| "main".to_string()),
        programming_languages_json: serde_json::to_string(&programming_languages)
            .map_err(|error| ApiError::Internal(error.to_string()))?,
        is_active: true,
        created_at: now.clone(),
        updated_at: now,
        language_info: empty_language_info_string(),
        info_status: "pending".to_string(),
        archive: None,
    };

    let project = projects::create_project(&state, project)
        .await
        .map_err(internal_error)?;
    sync_python_project_mirror(&state, &project).await?;
    Ok(Json(to_project_response(&project, true)))
}

pub async fn list_projects(
    State(state): State<AppState>,
    Query(query): Query<ProjectListQuery>,
) -> Result<Json<Vec<ProjectResponse>>, ApiError> {
    let mut items = projects::list_projects(&state)
        .await
        .map_err(internal_error)?;
    items.sort_by(|left, right| right.created_at.cmp(&left.created_at));

    let skip = query.skip.unwrap_or(0);
    let limit = query.limit.unwrap_or(items.len());
    let include_metrics = query.include_metrics.unwrap_or(false);

    let response = items
        .into_iter()
        .skip(skip)
        .take(limit)
        .map(|project| to_project_response(&project, include_metrics))
        .collect();
    Ok(Json(response))
}

pub async fn get_project(
    State(state): State<AppState>,
    AxumPath(project_id): AxumPath<String>,
) -> Result<Json<ProjectResponse>, ApiError> {
    let project = require_project(&state, &project_id).await?;
    Ok(Json(to_project_response(&project, true)))
}

pub async fn update_project(
    State(state): State<AppState>,
    AxumPath(project_id): AxumPath<String>,
    Json(payload): Json<ProjectUpdateRequest>,
) -> Result<Json<ProjectResponse>, ApiError> {
    let mut project = require_project(&state, &project_id).await?;
    validate_project_payload(
        payload.source_type.as_deref(),
        payload.repository_url.as_deref(),
    )?;

    if let Some(name) = payload.name {
        project.name = name;
    }
    if let Some(description) = payload.description {
        project.description = description;
    }
    if let Some(repository_type) = payload.repository_type {
        project.repository_type = repository_type;
    }
    if let Some(default_branch) = payload.default_branch {
        project.default_branch = default_branch;
    }
    if let Some(programming_languages) = payload.programming_languages {
        project.programming_languages_json = serde_json::to_string(&programming_languages)
            .map_err(|error| ApiError::Internal(error.to_string()))?;
    }
    project.updated_at = now_rfc3339();

    let project = projects::update_project(&state, project)
        .await
        .map_err(internal_error)?;
    sync_python_project_mirror(&state, &project).await?;
    Ok(Json(to_project_response(&project, true)))
}

pub async fn delete_project(
    State(state): State<AppState>,
    AxumPath(project_id): AxumPath<String>,
) -> Result<StatusCode, ApiError> {
    let deleted = projects::delete_project(&state, &project_id)
        .await
        .map_err(internal_error)?;
    let Some(project) = deleted else {
        return Err(ApiError::NotFound("project not found".to_string()));
    };

    if let Some(archive) = project.archive {
        delete_archive_files(&archive.storage_path).await?;
    }
    delete_python_project_mirror(&state, &project_id).await?;
    Ok(StatusCode::NO_CONTENT)
}

pub async fn get_project_info(
    State(state): State<AppState>,
    AxumPath(project_id): AxumPath<String>,
) -> Result<Json<ProjectInfoResponse>, ApiError> {
    let project = require_project(&state, &project_id).await?;
    Ok(Json(ProjectInfoResponse {
        project_id: project.id,
        language_info: project.language_info,
        description: project.description,
        status: project.info_status,
    }))
}

pub async fn create_project_with_zip(
    State(state): State<AppState>,
    multipart: Multipart,
) -> Result<Json<ProjectResponse>, ApiError> {
    let parsed = parse_project_upload_multipart(multipart).await?;
    let mut project = StoredProject {
        id: Uuid::new_v4().to_string(),
        name: parsed.name,
        description: parsed.description.unwrap_or_default(),
        source_type: "zip".to_string(),
        repository_type: "other".to_string(),
        default_branch: parsed.default_branch.unwrap_or_else(|| "main".to_string()),
        programming_languages_json: "[]".to_string(),
        is_active: true,
        created_at: now_rfc3339(),
        updated_at: now_rfc3339(),
        language_info: empty_language_info_string(),
        info_status: "pending".to_string(),
        archive: None,
    };

    apply_archive_to_project(&state, &mut project, parsed.file_name, parsed.file_bytes).await?;
    let project = projects::create_project(&state, project)
        .await
        .map_err(internal_error)?;
    sync_python_project_mirror(&state, &project).await?;
    Ok(Json(to_project_response(&project, true)))
}

pub async fn get_project_zip_info(
    State(state): State<AppState>,
    AxumPath(project_id): AxumPath<String>,
) -> Result<Json<ZipFileMetaResponse>, ApiError> {
    let project = require_project(&state, &project_id).await?;
    let archive = project.archive.clone();
    Ok(Json(ZipFileMetaResponse {
        has_file: archive.is_some(),
        original_filename: archive.as_ref().map(|item| item.original_filename.clone()),
        file_size: archive.as_ref().map(|item| item.file_size),
        uploaded_at: archive.as_ref().map(|item| item.uploaded_at.clone()),
    }))
}

pub async fn upload_project_zip(
    State(state): State<AppState>,
    AxumPath(project_id): AxumPath<String>,
    multipart: Multipart,
) -> Result<Json<ArchiveUploadResponse>, ApiError> {
    let parsed = parse_zip_only_multipart(multipart).await?;
    let mut project = require_project(&state, &project_id).await?;
    let detected_languages = apply_archive_to_project(
        &state,
        &mut project,
        parsed.file_name.clone(),
        parsed.file_bytes,
    )
    .await?;
    let project = projects::update_project(&state, project)
        .await
        .map_err(internal_error)?;
    sync_python_project_mirror(&state, &project).await?;

    Ok(Json(ArchiveUploadResponse {
        message: "文件上传成功（已由 Rust 网关接管）".to_string(),
        original_filename: parsed.file_name,
        file_size: project
            .archive
            .as_ref()
            .map(|item| item.file_size)
            .unwrap_or_default(),
        detected_languages,
    }))
}

pub async fn delete_project_zip(
    State(state): State<AppState>,
    AxumPath(project_id): AxumPath<String>,
) -> Result<StatusCode, ApiError> {
    let project = require_project(&state, &project_id).await?;
    if let Some(archive) = &project.archive {
        delete_archive_files(&archive.storage_path).await?;
    }

    let mut project = project;
    project.archive = None;
    project.language_info = empty_language_info_string();
    project.info_status = "pending".to_string();
    project.updated_at = now_rfc3339();
    let project = projects::update_project(&state, project)
        .await
        .map_err(internal_error)?;
    sync_python_project_mirror(&state, &project).await?;
    Ok(StatusCode::NO_CONTENT)
}

pub async fn download_project_archive(
    State(state): State<AppState>,
    AxumPath(project_id): AxumPath<String>,
) -> Result<Response, ApiError> {
    let project = require_project(&state, &project_id).await?;
    let archive = project
        .archive
        .ok_or_else(|| ApiError::NotFound("archive not found".to_string()))?;
    let bytes = fs::read(&archive.storage_path)
        .await
        .map_err(|error| ApiError::NotFound(format!("archive not found: {error}")))?;

    let mut response = Response::new(Body::from(bytes));
    *response.status_mut() = StatusCode::OK;
    response.headers_mut().insert(
        header::CONTENT_TYPE,
        HeaderValue::from_static("application/zip"),
    );
    response.headers_mut().insert(
        header::CONTENT_DISPOSITION,
        HeaderValue::from_str(&format!(
            "attachment; filename=\"{}\"",
            archive.original_filename
        ))
        .map_err(|error| ApiError::Internal(error.to_string()))?,
    );
    Ok(response)
}

pub async fn generate_project_description_preview(
    multipart: Multipart,
) -> Result<Json<ProjectDescriptionGenerateResponse>, ApiError> {
    let parsed = parse_description_preview_multipart(multipart).await?;
    let analyzed = analyze_archive(&parsed.file_name, &parsed.file_bytes)?;
    Ok(Json(ProjectDescriptionGenerateResponse {
        description: build_description(
            parsed.project_name.as_deref().unwrap_or(&parsed.file_name),
            &analyzed.languages,
        ),
        language_info: analyzed.language_info_string,
        source: "static".to_string(),
    }))
}

pub async fn generate_project_description_for_project(
    State(state): State<AppState>,
    AxumPath(project_id): AxumPath<String>,
) -> Result<Json<ProjectDescriptionGenerateResponse>, ApiError> {
    let mut project = require_project(&state, &project_id).await?;
    let archive = project
        .archive
        .clone()
        .ok_or_else(|| ApiError::NotFound("archive not found".to_string()))?;
    let bytes = fs::read(&archive.storage_path)
        .await
        .map_err(|error| ApiError::NotFound(format!("archive not found: {error}")))?;
    let analyzed = analyze_archive(&archive.original_filename, &bytes)?;
    project.description = build_description(&project.name, &analyzed.languages);
    project.language_info = analyzed.language_info_string.clone();
    project.info_status = "completed".to_string();
    project.updated_at = now_rfc3339();
    let project = projects::update_project(&state, project)
        .await
        .map_err(internal_error)?;
    sync_python_project_mirror(&state, &project).await?;

    Ok(Json(ProjectDescriptionGenerateResponse {
        description: project.description,
        language_info: project.language_info,
        source: "static".to_string(),
    }))
}

#[derive(Debug)]
struct ParsedUpload {
    name: String,
    description: Option<String>,
    default_branch: Option<String>,
    file_name: String,
    file_bytes: Vec<u8>,
}

#[derive(Debug)]
struct DescriptionPreviewUpload {
    project_name: Option<String>,
    file_name: String,
    file_bytes: Vec<u8>,
}

#[derive(Debug)]
struct ParsedArchiveAnalysis {
    languages: Vec<String>,
    language_info_string: String,
}

async fn parse_project_upload_multipart(
    mut multipart: Multipart,
) -> Result<ParsedUpload, ApiError> {
    let mut name = None;
    let mut description = None;
    let mut default_branch = None;
    let mut file_name = None;
    let mut file_bytes = None;

    while let Some(field) = multipart
        .next_field()
        .await
        .map_err(|error| ApiError::BadRequest(error.to_string()))?
    {
        match field.name().unwrap_or_default() {
            "name" => {
                name = Some(
                    field
                        .text()
                        .await
                        .map_err(|error| ApiError::BadRequest(error.to_string()))?,
                )
            }
            "description" => {
                description = Some(
                    field
                        .text()
                        .await
                        .map_err(|error| ApiError::BadRequest(error.to_string()))?,
                )
            }
            "default_branch" => {
                default_branch = Some(
                    field
                        .text()
                        .await
                        .map_err(|error| ApiError::BadRequest(error.to_string()))?,
                )
            }
            "file" => {
                file_name = field.file_name().map(str::to_string);
                file_bytes = Some(
                    field
                        .bytes()
                        .await
                        .map_err(|error| ApiError::BadRequest(error.to_string()))?
                        .to_vec(),
                );
            }
            _ => {}
        }
    }

    Ok(ParsedUpload {
        name: name.ok_or_else(|| ApiError::BadRequest("name is required".to_string()))?,
        description,
        default_branch,
        file_name: file_name.ok_or_else(|| ApiError::BadRequest("file is required".to_string()))?,
        file_bytes: file_bytes
            .ok_or_else(|| ApiError::BadRequest("file is required".to_string()))?,
    })
}

async fn parse_zip_only_multipart(
    mut multipart: Multipart,
) -> Result<DescriptionPreviewUpload, ApiError> {
    let mut file_name = None;
    let mut file_bytes = None;
    while let Some(field) = multipart
        .next_field()
        .await
        .map_err(|error| ApiError::BadRequest(error.to_string()))?
    {
        if field.name().unwrap_or_default() == "file" {
            file_name = field.file_name().map(str::to_string);
            file_bytes = Some(
                field
                    .bytes()
                    .await
                    .map_err(|error| ApiError::BadRequest(error.to_string()))?
                    .to_vec(),
            );
        }
    }
    Ok(DescriptionPreviewUpload {
        project_name: None,
        file_name: file_name.ok_or_else(|| ApiError::BadRequest("file is required".to_string()))?,
        file_bytes: file_bytes
            .ok_or_else(|| ApiError::BadRequest("file is required".to_string()))?,
    })
}

async fn parse_description_preview_multipart(
    mut multipart: Multipart,
) -> Result<DescriptionPreviewUpload, ApiError> {
    let mut project_name = None;
    let mut file_name = None;
    let mut file_bytes = None;
    while let Some(field) = multipart
        .next_field()
        .await
        .map_err(|error| ApiError::BadRequest(error.to_string()))?
    {
        match field.name().unwrap_or_default() {
            "project_name" => {
                project_name = Some(
                    field
                        .text()
                        .await
                        .map_err(|error| ApiError::BadRequest(error.to_string()))?,
                )
            }
            "file" => {
                file_name = field.file_name().map(str::to_string);
                file_bytes = Some(
                    field
                        .bytes()
                        .await
                        .map_err(|error| ApiError::BadRequest(error.to_string()))?
                        .to_vec(),
                );
            }
            _ => {}
        }
    }
    Ok(DescriptionPreviewUpload {
        project_name,
        file_name: file_name.ok_or_else(|| ApiError::BadRequest("file is required".to_string()))?,
        file_bytes: file_bytes
            .ok_or_else(|| ApiError::BadRequest("file is required".to_string()))?,
    })
}

async fn require_project(state: &AppState, project_id: &str) -> Result<StoredProject, ApiError> {
    projects::get_project(state, project_id)
        .await
        .map_err(internal_error)?
        .ok_or_else(|| ApiError::NotFound("project not found".to_string()))
}

async fn apply_archive_to_project(
    state: &AppState,
    project: &mut StoredProject,
    file_name: String,
    file_bytes: Vec<u8>,
) -> Result<Vec<String>, ApiError> {
    let analyzed = analyze_archive(&file_name, &file_bytes)?;
    let archive = persist_archive(state, &project.id, &file_name, &file_bytes).await?;
    project.archive = Some(archive);
    project.description = build_description(&project.name, &analyzed.languages);
    project.programming_languages_json = serde_json::to_string(&analyzed.languages)
        .map_err(|error| ApiError::Internal(error.to_string()))?;
    project.language_info = analyzed.language_info_string;
    project.info_status = "completed".to_string();
    project.updated_at = now_rfc3339();
    Ok(analyzed.languages)
}

async fn persist_archive(
    state: &AppState,
    project_id: &str,
    file_name: &str,
    file_bytes: &[u8],
) -> Result<StoredProjectArchive, ApiError> {
    let storage_root = &state.config.zip_storage_path;
    fs::create_dir_all(storage_root)
        .await
        .map_err(|error| ApiError::Internal(error.to_string()))?;

    let storage_path = storage_root.join(format!("{project_id}.zip"));
    fs::write(&storage_path, file_bytes)
        .await
        .map_err(|error| ApiError::Internal(error.to_string()))?;

    let uploaded_at = now_rfc3339();
    let file_size = file_bytes.len() as i64;
    let sha256 = hex_digest(file_bytes);
    let meta_path = storage_root.join(format!("{project_id}.meta"));
    let meta_json = json!({
        "original_filename": file_name,
        "file_size": file_size,
        "uploaded_at": uploaded_at,
        "project_id": project_id
    });
    fs::write(&meta_path, meta_json.to_string())
        .await
        .map_err(|error| ApiError::Internal(error.to_string()))?;

    Ok(StoredProjectArchive {
        original_filename: file_name.to_string(),
        storage_path: storage_path.display().to_string(),
        sha256,
        file_size,
        uploaded_at,
    })
}

fn analyze_archive(file_name: &str, file_bytes: &[u8]) -> Result<ParsedArchiveAnalysis, ApiError> {
    if !file_name.to_lowercase().ends_with(".zip") {
        return Err(ApiError::BadRequest(
            "only zip archives are supported in the rust gateway".to_string(),
        ));
    }

    let reader = Cursor::new(file_bytes);
    let mut archive = ZipArchive::new(reader)
        .map_err(|error| ApiError::BadRequest(format!("invalid zip archive: {error}")))?;
    let mut languages = BTreeSet::new();
    let mut language_counts: BTreeMap<String, usize> = BTreeMap::new();
    let mut total_files = 0usize;

    for index in 0..archive.len() {
        let entry = archive.by_index(index).map_err(|error| {
            ApiError::BadRequest(format!("failed to inspect zip archive: {error}"))
        })?;
        if entry.is_dir() {
            continue;
        }
        total_files += 1;
        if let Some(language) = detect_language(entry.name()) {
            languages.insert(language.to_string());
            *language_counts.entry(language.to_string()).or_insert(0) += 1;
        }
    }

    let languages: Vec<String> = languages.into_iter().collect();
    let language_info = json!({
        "total": total_files,
        "total_files": total_files,
        "languages": language_counts.iter().map(|(language, count)| {
            (
                language.clone(),
                json!({
                    "files_count": count,
                    "file_count": count,
                    "proportion": if total_files == 0 { 0.0 } else { (*count as f64) / (total_files as f64) },
                    "loc_number": 0
                })
            )
        }).collect::<serde_json::Map<String, Value>>()
    });

    Ok(ParsedArchiveAnalysis {
        languages,
        language_info_string: language_info.to_string(),
    })
}

async fn delete_archive_files(storage_path: &str) -> Result<(), ApiError> {
    let path = PathBuf::from(storage_path);
    if fs::try_exists(&path)
        .await
        .map_err(|error| ApiError::Internal(error.to_string()))?
    {
        fs::remove_file(&path)
            .await
            .map_err(|error| ApiError::Internal(error.to_string()))?;
    }
    let meta_path = path.with_extension("meta");
    if fs::try_exists(&meta_path)
        .await
        .map_err(|error| ApiError::Internal(error.to_string()))?
    {
        fs::remove_file(meta_path)
            .await
            .map_err(|error| ApiError::Internal(error.to_string()))?;
    }
    Ok(())
}

fn to_project_response(project: &StoredProject, include_metrics: bool) -> ProjectResponse {
    ProjectResponse {
        id: project.id.clone(),
        name: project.name.clone(),
        description: project.description.clone(),
        source_type: project.source_type.clone(),
        repository_type: project.repository_type.clone(),
        default_branch: project.default_branch.clone(),
        programming_languages: project.programming_languages_json.clone(),
        is_active: project.is_active,
        created_at: project.created_at.clone(),
        updated_at: project.updated_at.clone(),
        management_metrics: include_metrics.then(|| build_metrics(project)),
    }
}

fn build_metrics(project: &StoredProject) -> ProjectManagementMetricsResponse {
    let archive = project.archive.as_ref();
    ProjectManagementMetricsResponse {
        archive_size_bytes: archive.map(|item| item.file_size),
        archive_original_filename: archive.map(|item| item.original_filename.clone()),
        archive_uploaded_at: archive.map(|item| item.uploaded_at.clone()),
        total_tasks: 0,
        completed_tasks: 0,
        running_tasks: 0,
        agent_tasks: 0,
        opengrep_tasks: 0,
        gitleaks_tasks: 0,
        bandit_tasks: 0,
        phpstan_tasks: 0,
        critical: 0,
        high: 0,
        medium: 0,
        low: 0,
        verified_critical: 0,
        verified_high: 0,
        verified_medium: 0,
        verified_low: 0,
        last_completed_task_at: None,
        status: if archive.is_some() {
            "ready"
        } else {
            "pending"
        }
        .to_string(),
        error_message: None,
        created_at: project.created_at.clone(),
        updated_at: project.updated_at.clone(),
    }
}

fn validate_project_payload(
    source_type: Option<&str>,
    repository_url: Option<&str>,
) -> Result<(), ApiError> {
    if source_type.unwrap_or("zip") != "zip" || repository_url.is_some() {
        return Err(ApiError::BadRequest(
            "only zip projects are supported".to_string(),
        ));
    }
    Ok(())
}

fn detect_language(path: &str) -> Option<&'static str> {
    match Path::new(path)
        .extension()
        .and_then(|ext| ext.to_str())
        .unwrap_or_default()
        .to_ascii_lowercase()
        .as_str()
    {
        "rs" => Some("Rust"),
        "py" => Some("Python"),
        "ts" | "tsx" => Some("TypeScript"),
        "js" | "jsx" => Some("JavaScript"),
        "java" => Some("Java"),
        "go" => Some("Go"),
        "php" => Some("PHP"),
        "rb" => Some("Ruby"),
        "c" | "h" => Some("C"),
        "cpp" | "cc" | "cxx" | "hpp" => Some("C++"),
        "cs" => Some("C#"),
        _ => None,
    }
}

fn build_description(project_name: &str, languages: &[String]) -> String {
    if languages.is_empty() {
        return format!("{project_name} imported via Rust gateway ZIP flow.");
    }
    format!(
        "{project_name} imported via Rust gateway ZIP flow. Detected languages: {}.",
        languages.join(", ")
    )
}

fn empty_language_info_string() -> String {
    json!({
        "total": 0,
        "total_files": 0,
        "languages": {}
    })
    .to_string()
}

fn now_rfc3339() -> String {
    OffsetDateTime::now_utc()
        .format(&Rfc3339)
        .unwrap_or_else(|_| OffsetDateTime::now_utc().unix_timestamp().to_string())
}

fn hex_digest(bytes: &[u8]) -> String {
    let mut hasher = Sha256::new();
    hasher.update(bytes);
    format!("{:x}", hasher.finalize())
}

async fn sync_python_project_mirror(
    state: &AppState,
    project: &StoredProject,
) -> Result<(), ApiError> {
    let Some(pool) = &state.db_pool else {
        return Ok(());
    };

    let bootstrap_user_id: Option<String> =
        sqlx::query_scalar("select id from users order by created_at asc limit 1")
            .fetch_optional(pool)
            .await
            .map_err(|error| ApiError::Internal(error.to_string()))?;

    let Some(bootstrap_user_id) = bootstrap_user_id else {
        return Ok(());
    };

    sqlx::query(
        r#"
        insert into projects (
            id, name, description, source_type, repository_url, repository_type,
            default_branch, programming_languages, zip_file_hash, owner_id, is_active
        )
        values ($1, $2, $3, 'zip', null, $4, $5, $6, $7, $8, $9)
        on conflict (id) do update
        set name = excluded.name,
            description = excluded.description,
            repository_type = excluded.repository_type,
            default_branch = excluded.default_branch,
            programming_languages = excluded.programming_languages,
            zip_file_hash = excluded.zip_file_hash,
            owner_id = excluded.owner_id,
            is_active = excluded.is_active,
            updated_at = now()
        "#,
    )
    .bind(&project.id)
    .bind(&project.name)
    .bind(&project.description)
    .bind(&project.repository_type)
    .bind(&project.default_branch)
    .bind(&project.programming_languages_json)
    .bind(
        project
            .archive
            .as_ref()
            .map(|archive| archive.sha256.clone()),
    )
    .bind(bootstrap_user_id)
    .bind(project.is_active)
    .execute(pool)
    .await
    .map_err(|error| ApiError::Internal(error.to_string()))?;

    sqlx::query(
        r#"
        insert into project_info (id, project_id, language_info, description, status)
        values ($1, $2, $3::jsonb, $4, $5)
        on conflict (project_id) do update
        set language_info = excluded.language_info,
            description = excluded.description,
            status = excluded.status
        "#,
    )
    .bind(Uuid::new_v4().to_string())
    .bind(&project.id)
    .bind(&project.language_info)
    .bind(&project.description)
    .bind(&project.info_status)
    .execute(pool)
    .await
    .map_err(|error| ApiError::Internal(error.to_string()))?;

    sqlx::query(
        r#"
        insert into project_management_metrics (
            project_id, archive_size_bytes, archive_original_filename, archive_uploaded_at,
            total_tasks, completed_tasks, running_tasks, agent_tasks, opengrep_tasks,
            gitleaks_tasks, bandit_tasks, phpstan_tasks, critical, high, medium, low,
            verified_critical, verified_high, verified_medium, verified_low,
            status, error_message
        )
        values (
            $1, $2, $3, $4::timestamptz,
            0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
            $5, null
        )
        on conflict (project_id) do update
        set archive_size_bytes = excluded.archive_size_bytes,
            archive_original_filename = excluded.archive_original_filename,
            archive_uploaded_at = excluded.archive_uploaded_at,
            status = excluded.status,
            updated_at = now()
        "#,
    )
    .bind(&project.id)
    .bind(
        project
            .archive
            .as_ref()
            .map(|archive| archive.file_size)
            .unwrap_or(0),
    )
    .bind(
        project
            .archive
            .as_ref()
            .map(|archive| archive.original_filename.clone()),
    )
    .bind(
        project
            .archive
            .as_ref()
            .map(|archive| archive.uploaded_at.clone()),
    )
    .bind(if project.archive.is_some() {
        "ready"
    } else {
        "pending"
    })
    .execute(pool)
    .await
    .map_err(|error| ApiError::Internal(error.to_string()))?;

    Ok(())
}

async fn delete_python_project_mirror(state: &AppState, project_id: &str) -> Result<(), ApiError> {
    let Some(pool) = &state.db_pool else {
        return Ok(());
    };

    sqlx::query("delete from project_management_metrics where project_id = $1")
        .bind(project_id)
        .execute(pool)
        .await
        .map_err(|error| ApiError::Internal(error.to_string()))?;
    sqlx::query("delete from project_info where project_id = $1")
        .bind(project_id)
        .execute(pool)
        .await
        .map_err(|error| ApiError::Internal(error.to_string()))?;
    sqlx::query("delete from projects where id = $1")
        .bind(project_id)
        .execute(pool)
        .await
        .map_err(|error| ApiError::Internal(error.to_string()))?;
    Ok(())
}

fn internal_error(error: anyhow::Error) -> ApiError {
    ApiError::Internal(error.to_string())
}
