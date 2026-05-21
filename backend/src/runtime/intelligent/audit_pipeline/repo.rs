use std::path::PathBuf;

use anyhow::Result;
use serde::{Deserialize, Serialize};

use crate::archive;

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "camelCase")]
pub struct ArchiveEntry {
    pub path: String,
    pub size: u64,
}

#[derive(Debug, Clone)]
pub struct ProjectArchive {
    storage_path: PathBuf,
    original_filename: String,
}

impl ProjectArchive {
    pub fn new(storage_path: impl Into<PathBuf>, original_filename: impl Into<String>) -> Self {
        Self {
            storage_path: storage_path.into(),
            original_filename: original_filename.into(),
        }
    }

    pub fn list_entries(&self) -> Result<Vec<ArchiveEntry>> {
        Ok(
            archive::list_archive_files_from_path(&self.storage_path, &self.original_filename)?
                .into_iter()
                .map(|entry| ArchiveEntry {
                    path: entry.path,
                    size: entry.size,
                })
                .collect(),
        )
    }

    pub fn read_text_file(&self, path: &str, max_bytes: usize) -> Result<Option<String>> {
        let (content, _size, _encoding, is_text) = archive::read_archive_file_from_path(
            &self.storage_path,
            &self.original_filename,
            path,
        )?;
        if !is_text {
            return Ok(None);
        }
        Ok(Some(content.chars().take(max_bytes).collect()))
    }
}

#[must_use]
pub fn build_inventory_summary(entries: &[ArchiveEntry]) -> String {
    const MAX_ENTRIES: usize = 200;
    let mut lines = vec![format!(
        "Project file inventory ({}/{}) files:",
        entries.len().min(MAX_ENTRIES),
        entries.len()
    )];
    lines.extend(
        entries
            .iter()
            .take(MAX_ENTRIES)
            .map(|entry| format!("{} ({}B)", entry.path, entry.size)),
    );
    if entries.len() > MAX_ENTRIES {
        lines.push(format!(
            "... and {} more files",
            entries.len() - MAX_ENTRIES
        ));
    }
    lines.join("\n")
}

#[must_use]
pub fn select_representative_files(entries: &[ArchiveEntry], max_files: usize) -> Vec<String> {
    let mut paths: Vec<String> = entries
        .iter()
        .filter(|entry| is_source_like(&entry.path))
        .map(|entry| entry.path.clone())
        .collect();
    if paths.is_empty() {
        paths = entries.iter().map(|entry| entry.path.clone()).collect();
    }
    paths.sort();
    paths.truncate(max_files);
    paths
}

#[must_use]
pub fn source_snippets(
    archive: &ProjectArchive,
    paths: &[String],
    max_bytes: usize,
) -> Vec<String> {
    paths
        .iter()
        .filter_map(|path| match archive.read_text_file(path, max_bytes) {
            Ok(Some(content)) => Some(format!("--- {path} ---\n{content}")),
            _ => None,
        })
        .collect()
}

fn is_source_like(path: &str) -> bool {
    let lower = path.to_ascii_lowercase();
    [
        ".rs", ".py", ".ts", ".tsx", ".js", ".jsx", ".go", ".java", ".kt", ".c", ".cpp", ".h",
        ".hpp", ".cs", ".rb", ".php", ".md", ".toml", ".yaml", ".yml", ".json",
    ]
    .iter()
    .any(|suffix| lower.ends_with(suffix))
}
