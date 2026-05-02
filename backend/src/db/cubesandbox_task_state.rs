use std::{collections::BTreeMap, io::ErrorKind, path::PathBuf};

use anyhow::{Context, Result};
use serde::{Deserialize, Serialize};
use tokio::fs;

use crate::{runtime::cubesandbox::types::CubeSandboxTaskRecord, state::AppState};

const CUBESANDBOX_TASK_STATE_FILE_NAME: &str = "rust-cubesandbox-task-state.json";

#[derive(Clone, Debug, Default, Serialize, Deserialize)]
pub struct CubeSandboxTaskStateSnapshot {
    #[serde(default)]
    pub tasks: BTreeMap<String, CubeSandboxTaskRecord>,
}

pub async fn load_snapshot(state: &AppState) -> Result<CubeSandboxTaskStateSnapshot> {
    let _guard = state.file_store_lock.lock().await;
    load_snapshot_unlocked(state).await
}

pub async fn save_record(state: &AppState, record: CubeSandboxTaskRecord) -> Result<()> {
    let _guard = state.file_store_lock.lock().await;
    let mut snapshot = load_snapshot_unlocked(state).await?;
    snapshot.tasks.insert(record.task_id.clone(), record);
    save_snapshot_unlocked(state, &snapshot).await
}

pub async fn get_record(state: &AppState, task_id: &str) -> Result<Option<CubeSandboxTaskRecord>> {
    Ok(load_snapshot(state).await?.tasks.remove(task_id))
}

pub async fn list_records(state: &AppState, limit: usize) -> Result<Vec<CubeSandboxTaskRecord>> {
    let mut records: Vec<_> = load_snapshot(state).await?.tasks.into_values().collect();
    records.sort_by(|left, right| right.created_at.cmp(&left.created_at));
    records.truncate(limit);
    Ok(records)
}

pub async fn update_record<F>(
    state: &AppState,
    task_id: &str,
    update: F,
) -> Result<Option<CubeSandboxTaskRecord>>
where
    F: FnOnce(&mut CubeSandboxTaskRecord),
{
    let _guard = state.file_store_lock.lock().await;
    let mut snapshot = load_snapshot_unlocked(state).await?;
    let Some(record) = snapshot.tasks.get_mut(task_id) else {
        return Ok(None);
    };
    update(record);
    let next = record.clone();
    save_snapshot_unlocked(state, &snapshot).await?;
    Ok(Some(next))
}

pub async fn delete_record(
    state: &AppState,
    task_id: &str,
) -> Result<Option<CubeSandboxTaskRecord>> {
    let _guard = state.file_store_lock.lock().await;
    let mut snapshot = load_snapshot_unlocked(state).await?;
    let removed = snapshot.tasks.remove(task_id);
    if removed.is_some() {
        save_snapshot_unlocked(state, &snapshot).await?;
    }
    Ok(removed)
}

pub(crate) async fn load_snapshot_unlocked(
    state: &AppState,
) -> Result<CubeSandboxTaskStateSnapshot> {
    let path = task_state_file_path(state);
    match fs::read_to_string(&path).await {
        Ok(raw) => serde_json::from_str(&raw).with_context(|| {
            format!(
                "failed to parse CubeSandbox task state snapshot: {}",
                path.display()
            )
        }),
        Err(error) if error.kind() == ErrorKind::NotFound => {
            Ok(CubeSandboxTaskStateSnapshot::default())
        }
        Err(error) => Err(error.into()),
    }
}

pub(crate) async fn save_snapshot_unlocked(
    state: &AppState,
    snapshot: &CubeSandboxTaskStateSnapshot,
) -> Result<()> {
    ensure_file_storage_root(state).await?;
    let path = task_state_file_path(state);
    let tmp_path = path.with_extension("tmp");
    let bytes = serde_json::to_vec_pretty(snapshot)?;
    fs::write(&tmp_path, bytes).await?;
    fs::rename(tmp_path, path).await?;
    Ok(())
}

fn task_state_file_path(state: &AppState) -> PathBuf {
    state
        .config
        .zip_storage_path
        .join(CUBESANDBOX_TASK_STATE_FILE_NAME)
}

async fn ensure_file_storage_root(state: &AppState) -> Result<()> {
    fs::create_dir_all(&state.config.zip_storage_path).await?;
    Ok(())
}
