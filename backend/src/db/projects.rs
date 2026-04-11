use std::collections::BTreeMap;

use anyhow::Result;

use crate::state::{AppState, StoredProject, StoredProjectArchive};

pub async fn create_project(state: &AppState, project: StoredProject) -> Result<StoredProject> {
    let mut projects = state.memory_store.projects.write().await;
    projects.insert(project.id.clone(), project.clone());
    Ok(project)
}

pub async fn list_projects(state: &AppState) -> Result<Vec<StoredProject>> {
    let projects = state.memory_store.projects.read().await;
    Ok(projects.values().cloned().collect())
}

pub async fn get_project(state: &AppState, project_id: &str) -> Result<Option<StoredProject>> {
    let projects = state.memory_store.projects.read().await;
    Ok(projects.get(project_id).cloned())
}

pub async fn update_project(state: &AppState, project: StoredProject) -> Result<StoredProject> {
    let mut projects = state.memory_store.projects.write().await;
    projects.insert(project.id.clone(), project.clone());
    Ok(project)
}

pub async fn delete_project(state: &AppState, project_id: &str) -> Result<Option<StoredProject>> {
    let mut projects = state.memory_store.projects.write().await;
    Ok(projects.remove(project_id))
}

pub async fn save_archive(
    state: &AppState,
    project_id: &str,
    archive: StoredProjectArchive,
) -> Result<Option<StoredProject>> {
    let mut projects = state.memory_store.projects.write().await;
    if let Some(project) = projects.get_mut(project_id) {
        project.archive = Some(archive);
        return Ok(Some(project.clone()));
    }
    Ok(None)
}

pub async fn clear_archive(state: &AppState, project_id: &str) -> Result<Option<StoredProject>> {
    let mut projects = state.memory_store.projects.write().await;
    if let Some(project) = projects.get_mut(project_id) {
        project.archive = None;
        return Ok(Some(project.clone()));
    }
    Ok(None)
}

pub async fn replace_all(
    state: &AppState,
    projects: BTreeMap<String, StoredProject>,
) -> Result<()> {
    *state.memory_store.projects.write().await = projects;
    Ok(())
}
