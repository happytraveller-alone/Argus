use std::collections::HashMap;

use time::OffsetDateTime;

const DEFAULT_CACHE_TTL_SECONDS: i64 = 3600;
const DEFAULT_MAX_CACHE_SIZE_BYTES: usize = 100 * 1024 * 1024;
const MAX_CACHED_FILE_SIZE_BYTES: u64 = 5 * 1024 * 1024;
const ENTRY_OVERHEAD_BYTES: usize = 200;

#[derive(Clone, Debug)]
pub struct ProjectFileCacheEntry {
    pub project_id: String,
    pub file_path: String,
    pub zip_hash: String,
    pub content: String,
    pub size: u64,
    pub encoding: String,
    pub is_text: bool,
    created_at_unix: i64,
    last_accessed_unix: i64,
    access_count: u64,
}

impl ProjectFileCacheEntry {
    fn new(
        project_id: &str,
        file_path: &str,
        zip_hash: &str,
        content: &str,
        size: u64,
        encoding: &str,
        is_text: bool,
    ) -> Self {
        let now = OffsetDateTime::now_utc().unix_timestamp();
        Self {
            project_id: project_id.to_string(),
            file_path: file_path.to_string(),
            zip_hash: zip_hash.to_string(),
            content: content.to_string(),
            size,
            encoding: encoding.to_string(),
            is_text,
            created_at_unix: now,
            last_accessed_unix: now,
            access_count: 0,
        }
    }

    fn is_expired(&self, ttl_seconds: i64) -> bool {
        OffsetDateTime::now_utc().unix_timestamp() - self.created_at_unix > ttl_seconds
    }

    fn touch(&mut self) {
        self.last_accessed_unix = OffsetDateTime::now_utc().unix_timestamp();
        self.access_count += 1;
    }

    fn memory_size(&self) -> usize {
        self.content.len() + ENTRY_OVERHEAD_BYTES
    }

    pub fn created_at_unix(&self) -> i64 {
        self.created_at_unix
    }
}

#[derive(Clone, Debug, Default)]
pub struct ProjectFileCacheStats {
    pub total_entries: usize,
    pub hits: u64,
    pub misses: u64,
    pub hit_rate: f64,
    pub evictions: u64,
    pub memory_used_mb: f64,
    pub memory_limit_mb: f64,
}

pub struct ProjectFileCacheSet<'a> {
    pub project_id: &'a str,
    pub file_path: &'a str,
    pub zip_hash: &'a str,
    pub content: &'a str,
    pub size: u64,
    pub encoding: &'a str,
    pub is_text: bool,
}

#[derive(Debug)]
pub struct ProjectFileCache {
    ttl_seconds: i64,
    max_size_bytes: usize,
    total_memory_bytes: usize,
    hits: u64,
    misses: u64,
    evictions: u64,
    entries: HashMap<String, ProjectFileCacheEntry>,
}

impl Default for ProjectFileCache {
    fn default() -> Self {
        Self::new()
    }
}

impl ProjectFileCache {
    pub fn new() -> Self {
        Self::with_limits(DEFAULT_CACHE_TTL_SECONDS, DEFAULT_MAX_CACHE_SIZE_BYTES)
    }

    pub fn with_limits(ttl_seconds: i64, max_size_bytes: usize) -> Self {
        Self {
            ttl_seconds,
            max_size_bytes,
            total_memory_bytes: 0,
            hits: 0,
            misses: 0,
            evictions: 0,
            entries: HashMap::new(),
        }
    }

    pub fn get(
        &mut self,
        project_id: &str,
        file_path: &str,
        zip_hash: &str,
    ) -> Option<ProjectFileCacheEntry> {
        let key = cache_key(project_id, file_path, zip_hash);
        let expired = self
            .entries
            .get(&key)
            .map(|entry| entry.is_expired(self.ttl_seconds))
            .unwrap_or(false);
        if expired {
            self.remove_entry(&key);
            self.misses += 1;
            return None;
        }

        let Some(entry) = self.entries.get_mut(&key) else {
            self.misses += 1;
            return None;
        };

        entry.touch();
        self.hits += 1;
        Some(entry.clone())
    }

    pub fn set(&mut self, input: ProjectFileCacheSet<'_>) -> bool {
        if input.size > MAX_CACHED_FILE_SIZE_BYTES {
            return false;
        }

        self.prune_expired();

        let key = cache_key(input.project_id, input.file_path, input.zip_hash);
        self.remove_entry(&key);

        let entry = ProjectFileCacheEntry::new(
            input.project_id,
            input.file_path,
            input.zip_hash,
            input.content,
            input.size,
            input.encoding,
            input.is_text,
        );
        let entry_size = entry.memory_size();

        while self.total_memory_bytes + entry_size > self.max_size_bytes && !self.entries.is_empty()
        {
            let Some(evicted_key) = self.find_lru_key() else {
                break;
            };
            if self.remove_entry(&evicted_key) {
                self.evictions += 1;
            } else {
                break;
            }
        }

        if self.total_memory_bytes + entry_size > self.max_size_bytes {
            return false;
        }

        self.total_memory_bytes += entry_size;
        self.entries.insert(key, entry);
        true
    }

    pub fn invalidate_project(&mut self, project_id: &str) -> usize {
        let keys: Vec<String> = self
            .entries
            .iter()
            .filter_map(|(key, entry)| {
                if entry.project_id == project_id {
                    Some(key.clone())
                } else {
                    None
                }
            })
            .collect();

        let mut deleted = 0;
        for key in keys {
            if self.remove_entry(&key) {
                deleted += 1;
            }
        }
        deleted
    }

    pub fn clear_all(&mut self) -> usize {
        let deleted = self.entries.len();
        self.entries.clear();
        self.total_memory_bytes = 0;
        deleted
    }

    pub fn prune_expired(&mut self) -> usize {
        let keys: Vec<String> = self
            .entries
            .iter()
            .filter_map(|(key, entry)| {
                if entry.is_expired(self.ttl_seconds) {
                    Some(key.clone())
                } else {
                    None
                }
            })
            .collect();

        let mut removed = 0;
        for key in keys {
            if self.remove_entry(&key) {
                removed += 1;
            }
        }
        self.sync_total_memory();
        removed
    }

    pub fn stats(&mut self) -> ProjectFileCacheStats {
        self.sync_total_memory();
        let total_requests = self.hits + self.misses;
        ProjectFileCacheStats {
            total_entries: self.entries.len(),
            hits: self.hits,
            misses: self.misses,
            hit_rate: if total_requests == 0 {
                0.0
            } else {
                (self.hits as f64 / total_requests as f64) * 100.0
            },
            evictions: self.evictions,
            memory_used_mb: self.total_memory_bytes as f64 / (1024.0 * 1024.0),
            memory_limit_mb: self.max_size_bytes as f64 / (1024.0 * 1024.0),
        }
    }

    fn remove_entry(&mut self, key: &str) -> bool {
        let Some(entry) = self.entries.remove(key) else {
            return false;
        };
        self.total_memory_bytes = self.total_memory_bytes.saturating_sub(entry.memory_size());
        true
    }

    fn sync_total_memory(&mut self) {
        self.total_memory_bytes = self
            .entries
            .values()
            .map(ProjectFileCacheEntry::memory_size)
            .sum();
    }

    fn find_lru_key(&self) -> Option<String> {
        self.entries
            .iter()
            .min_by_key(|(_, entry)| (entry.access_count, entry.last_accessed_unix))
            .map(|(key, _)| key.clone())
    }

    #[cfg(test)]
    fn age_entry(&mut self, project_id: &str, file_path: &str, zip_hash: &str, seconds: i64) {
        let key = cache_key(project_id, file_path, zip_hash);
        if let Some(entry) = self.entries.get_mut(&key) {
            entry.created_at_unix -= seconds;
            entry.last_accessed_unix -= seconds;
        }
    }
}

fn cache_key(project_id: &str, file_path: &str, zip_hash: &str) -> String {
    format!("{project_id}:{file_path}:{zip_hash}")
}

#[cfg(test)]
mod tests {
    use super::{ProjectFileCache, ProjectFileCacheSet};

    #[test]
    fn prune_expired_removes_stale_entries_and_updates_stats() {
        let mut cache = ProjectFileCache::with_limits(60, 1024 * 1024);
        assert!(cache.set(ProjectFileCacheSet {
            project_id: "project-1",
            file_path: "src/app.py",
            zip_hash: "zip-hash",
            content: "print('ok')\n",
            size: 12,
            encoding: "utf-8",
            is_text: true,
        }));

        cache.age_entry("project-1", "src/app.py", "zip-hash", 120);

        let removed = cache.prune_expired();
        let stats = cache.stats();

        assert_eq!(removed, 1);
        assert_eq!(stats.total_entries, 0);
        assert_eq!(stats.memory_used_mb, 0.0);
    }

    #[test]
    fn get_drops_expired_entry_and_syncs_total_memory() {
        let mut cache = ProjectFileCache::with_limits(60, 1024 * 1024);
        assert!(cache.set(ProjectFileCacheSet {
            project_id: "project-1",
            file_path: "src/app.py",
            zip_hash: "zip-hash",
            content: "print('ok')\n",
            size: 12,
            encoding: "utf-8",
            is_text: true,
        }));

        cache.age_entry("project-1", "src/app.py", "zip-hash", 120);

        let cached = cache.get("project-1", "src/app.py", "zip-hash");
        let stats = cache.stats();

        assert!(cached.is_none());
        assert_eq!(stats.total_entries, 0);
        assert_eq!(stats.memory_used_mb, 0.0);
    }
}
