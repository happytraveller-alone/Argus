//! Project-level CodeGraph pre-index status and warmup helpers.
//!
//! Project import/upload calls this module after the archive is persisted. The
//! generated cache is keyed by archive SHA256 and reused by intelligent scans.

use std::path::Path;
use std::sync::Arc;

use anyhow::{Context, Result};
use serde::{Deserialize, Serialize};
use serde_json::json;

use crate::{
    runtime::intelligent::code_intel::{cache::CodeGraphCache, codegraph_client::CodeGraphClient},
    state::StoredProjectArchive,
};

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum CodegraphIndexStatus {
    Empty,
    Pending,
    Indexing,
    Ready,
    Failed,
}

impl CodegraphIndexStatus {
    pub fn as_str(&self) -> &'static str {
        match self {
            Self::Empty => "empty",
            Self::Pending => "pending",
            Self::Indexing => "indexing",
            Self::Ready => "ready",
            Self::Failed => "failed",
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct CodegraphIndexState {
    pub status: CodegraphIndexStatus,
    pub progress: u8,
    pub message: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub archive_sha256: Option<String>,
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub languages_indexed: Vec<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub updated_at: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub error: Option<String>,
}

impl CodegraphIndexState {
    pub fn pending(archive_sha256: impl Into<String>, updated_at: impl Into<String>) -> Self {
        Self {
            status: CodegraphIndexStatus::Pending,
            progress: 20,
            message: "源码包已导入，等待建立 codegraph 索引".to_string(),
            archive_sha256: Some(archive_sha256.into()),
            languages_indexed: Vec::new(),
            updated_at: Some(updated_at.into()),
            error: None,
        }
    }

    pub fn indexing(archive_sha256: impl Into<String>, updated_at: impl Into<String>) -> Self {
        Self {
            status: CodegraphIndexStatus::Indexing,
            progress: 65,
            message: "正在建立 codegraph 索引".to_string(),
            archive_sha256: Some(archive_sha256.into()),
            languages_indexed: Vec::new(),
            updated_at: Some(updated_at.into()),
            error: None,
        }
    }

    pub fn ready(
        archive_sha256: impl Into<String>,
        languages_indexed: Vec<String>,
        updated_at: impl Into<String>,
    ) -> Self {
        Self {
            status: CodegraphIndexStatus::Ready,
            progress: 100,
            message: "codegraph 索引已建立".to_string(),
            archive_sha256: Some(archive_sha256.into()),
            languages_indexed,
            updated_at: Some(updated_at.into()),
            error: None,
        }
    }

    pub fn failed(
        archive_sha256: impl Into<String>,
        error: impl Into<String>,
        updated_at: impl Into<String>,
    ) -> Self {
        Self {
            status: CodegraphIndexStatus::Failed,
            progress: 100,
            message: "codegraph 索引建立失败，智能扫描会降级继续".to_string(),
            archive_sha256: Some(archive_sha256.into()),
            languages_indexed: Vec::new(),
            updated_at: Some(updated_at.into()),
            error: Some(error.into()),
        }
    }
}

pub fn empty_codegraph_state() -> CodegraphIndexState {
    CodegraphIndexState {
        status: CodegraphIndexStatus::Empty,
        progress: 0,
        message: "尚未导入源码包".to_string(),
        archive_sha256: None,
        languages_indexed: Vec::new(),
        updated_at: None,
        error: None,
    }
}

pub fn read_codegraph_state(language_info: &str) -> CodegraphIndexState {
    serde_json::from_str::<serde_json::Value>(language_info)
        .ok()
        .and_then(|value| value.get("codegraph_index").cloned())
        .and_then(|value| serde_json::from_value(value).ok())
        .unwrap_or_else(empty_codegraph_state)
}

pub fn write_codegraph_state(language_info: &mut String, state: CodegraphIndexState) -> Result<()> {
    let mut value =
        serde_json::from_str::<serde_json::Value>(language_info).unwrap_or_else(|_| json!({}));
    if !value.is_object() {
        value = json!({});
    }
    value["codegraph_index"] = serde_json::to_value(state)?;
    *language_info = value.to_string();
    Ok(())
}

pub async fn prebuild_project_index(
    archive: &StoredProjectArchive,
    sandbox_image: &str,
) -> Result<Vec<String>> {
    let cache = Arc::new(CodeGraphCache::new().context("CodeGraphCache::new failed")?);
    CodeGraphClient::ensure_index_cached(
        Path::new(&archive.storage_path),
        &archive.original_filename,
        archive.sha256.clone(),
        sandbox_image,
        cache,
    )
    .await
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn codegraph_state_round_trips_inside_language_info() {
        let mut language_info = json!({
            "total": 1,
            "languages": {"c": {"files_count": 1}}
        })
        .to_string();

        write_codegraph_state(
            &mut language_info,
            CodegraphIndexState::indexing("sha-1", "2026-05-26T00:00:00Z"),
        )
        .expect("write state");
        let state = read_codegraph_state(&language_info);
        assert_eq!(state.status, CodegraphIndexStatus::Indexing);
        assert_eq!(state.progress, 65);
        assert_eq!(state.archive_sha256.as_deref(), Some("sha-1"));
    }
}
