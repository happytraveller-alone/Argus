use std::{collections::BTreeMap, io::ErrorKind, path::PathBuf};

use anyhow::{Context, Result};
use serde::{Deserialize, Serialize};
use tokio::fs;

use crate::{runtime::intelligent::types::IntelligentTaskRecord, state::AppState};

const INTELLIGENT_TASK_STATE_FILE_NAME: &str = "rust-intelligent-task-state.json";

#[derive(Clone, Debug, Default, Serialize, Deserialize)]
pub struct IntelligentTaskStateSnapshot {
    #[serde(default)]
    pub tasks: BTreeMap<String, IntelligentTaskRecord>,
}

pub async fn load_snapshot(state: &AppState) -> Result<IntelligentTaskStateSnapshot> {
    let _guard = state.file_store_lock.lock().await;
    load_snapshot_unlocked(state).await
}

pub async fn save_record(state: &AppState, record: IntelligentTaskRecord) -> Result<()> {
    let _guard = state.file_store_lock.lock().await;
    let mut snapshot = load_snapshot_unlocked(state).await?;
    snapshot.tasks.insert(record.task_id.clone(), record);
    save_snapshot_unlocked(state, &snapshot).await
}

pub async fn get_record(state: &AppState, task_id: &str) -> Result<Option<IntelligentTaskRecord>> {
    Ok(load_snapshot(state).await?.tasks.remove(task_id))
}

pub async fn list_records(state: &AppState, limit: usize) -> Result<Vec<IntelligentTaskRecord>> {
    let mut records: Vec<_> = load_snapshot(state).await?.tasks.into_values().collect();
    records.sort_by(|left, right| right.created_at.cmp(&left.created_at));
    records.truncate(limit);
    Ok(records)
}

pub async fn update_record<F>(
    state: &AppState,
    task_id: &str,
    update: F,
) -> Result<Option<IntelligentTaskRecord>>
where
    F: FnOnce(&mut IntelligentTaskRecord),
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
) -> Result<Option<IntelligentTaskRecord>> {
    let _guard = state.file_store_lock.lock().await;
    let mut snapshot = load_snapshot_unlocked(state).await?;
    let removed = snapshot.tasks.remove(task_id);
    if removed.is_some() {
        save_snapshot_unlocked(state, &snapshot).await?;
    }
    Ok(removed)
}

/// Remove all intelligent task records belonging to `project_id` from an
/// already-loaded snapshot. Returns the count of removed records.
/// Caller holds the file_store_lock.
pub(crate) fn remove_project_records_from_snapshot(
    snapshot: &mut IntelligentTaskStateSnapshot,
    project_id: &str,
) -> usize {
    let before = snapshot.tasks.len();
    snapshot
        .tasks
        .retain(|_, record| record.project_id != project_id);
    before.saturating_sub(snapshot.tasks.len())
}

pub(crate) async fn load_snapshot_unlocked(
    state: &AppState,
) -> Result<IntelligentTaskStateSnapshot> {
    let path = task_state_file_path(state);
    match fs::read_to_string(&path).await {
        Ok(raw) => serde_json::from_str(&raw).with_context(|| {
            format!(
                "failed to parse intelligent task state snapshot: {}",
                path.display()
            )
        }),
        Err(error) if error.kind() == ErrorKind::NotFound => {
            Ok(IntelligentTaskStateSnapshot::default())
        }
        Err(error) => Err(error.into()),
    }
}

pub(crate) async fn save_snapshot_unlocked(
    state: &AppState,
    snapshot: &IntelligentTaskStateSnapshot,
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
        .join(INTELLIGENT_TASK_STATE_FILE_NAME)
}

async fn ensure_file_storage_root(state: &AppState) -> Result<()> {
    fs::create_dir_all(&state.config.zip_storage_path).await?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::{config::AppConfig, runtime::intelligent::types::IntelligentTaskRecord};
    use uuid::Uuid;

    fn isolated_config(scope: &str) -> AppConfig {
        let mut config = AppConfig::for_tests();
        config.zip_storage_path =
            std::env::temp_dir().join(format!("argus-intelligent-{scope}-{}", Uuid::new_v4()));
        config
    }

    async fn build_state(scope: &str) -> crate::state::AppState {
        crate::state::AppState::from_config(isolated_config(scope))
            .await
            .expect("state should build")
    }

    #[tokio::test]
    async fn missing_file_returns_empty_snapshot() {
        let state = build_state("missing-file").await;
        let snapshot = load_snapshot(&state).await.expect("load should succeed");
        assert!(snapshot.tasks.is_empty());
    }

    #[tokio::test]
    async fn save_and_get_record_roundtrip() {
        let state = build_state("roundtrip").await;
        let record = IntelligentTaskRecord::new_pending(
            "task-1".to_string(),
            "proj-1".to_string(),
            "model".to_string(),
            "fp".to_string(),
        );
        save_record(&state, record.clone()).await.unwrap();
        let loaded = get_record(&state, "task-1").await.unwrap();
        assert!(loaded.is_some());
        assert_eq!(loaded.unwrap().task_id, "task-1");
    }

    #[tokio::test]
    async fn list_records_sorted_desc_by_created_at() {
        let state = build_state("list-sort").await;
        for i in 0..3u8 {
            let mut r = IntelligentTaskRecord::new_pending(
                format!("t{i}"),
                "p".to_string(),
                "m".to_string(),
                "f".to_string(),
            );
            // force distinct timestamps via slight sleep simulation by manipulating created_at
            r.created_at = format!("2026-05-02T00:00:0{i}Z");
            save_record(&state, r).await.unwrap();
        }
        let records = list_records(&state, 10).await.unwrap();
        assert_eq!(records.len(), 3);
        // should be descending
        assert!(records[0].created_at >= records[1].created_at);
        assert!(records[1].created_at >= records[2].created_at);
    }

    #[tokio::test]
    async fn update_record_mutates_in_place() {
        let state = build_state("update").await;
        let record = IntelligentTaskRecord::new_pending(
            "task-u".to_string(),
            "p".to_string(),
            "m".to_string(),
            "f".to_string(),
        );
        save_record(&state, record).await.unwrap();
        let updated = update_record(&state, "task-u", |r| {
            r.mark_running();
        })
        .await
        .unwrap();
        assert!(updated.is_some());
        assert_eq!(
            updated.unwrap().status,
            crate::runtime::intelligent::types::IntelligentTaskStatus::Running
        );
    }

    #[tokio::test]
    async fn delete_record_removes_it() {
        let state = build_state("delete").await;
        let record = IntelligentTaskRecord::new_pending(
            "task-d".to_string(),
            "p".to_string(),
            "m".to_string(),
            "f".to_string(),
        );
        save_record(&state, record).await.unwrap();
        let removed = delete_record(&state, "task-d").await.unwrap();
        assert!(removed.is_some());
        let after = get_record(&state, "task-d").await.unwrap();
        assert!(after.is_none());
    }

    #[tokio::test]
    async fn remove_project_records_from_snapshot_returns_count() {
        let mut snapshot = IntelligentTaskStateSnapshot::default();
        for i in 0..3u8 {
            let r = IntelligentTaskRecord::new_pending(
                format!("t{i}"),
                "proj-a".to_string(),
                "m".to_string(),
                "f".to_string(),
            );
            snapshot.tasks.insert(r.task_id.clone(), r);
        }
        let other = IntelligentTaskRecord::new_pending(
            "other".to_string(),
            "proj-b".to_string(),
            "m".to_string(),
            "f".to_string(),
        );
        snapshot.tasks.insert(other.task_id.clone(), other);

        let removed = remove_project_records_from_snapshot(&mut snapshot, "proj-a");
        assert_eq!(removed, 3);
        assert_eq!(snapshot.tasks.len(), 1);
    }
}
