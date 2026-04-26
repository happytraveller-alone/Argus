use std::{
    collections::BTreeSet,
    fs,
    io::{Cursor, Read},
    path::{Component, Path, PathBuf},
};

use anyhow::{anyhow, Context, Result};
use bzip2::read::BzDecoder;
use flate2::read::GzDecoder;
use uuid::Uuid;
use xz2::read::XzDecoder;
use zip::ZipArchive;
use zstd::stream::read::Decoder as ZstdDecoder;

pub const SUPPORTED_PROJECT_ARCHIVE_SUFFIXES: &[&str] = &[
    ".tar.zstd",
    ".tar.zst",
    ".tar.xz",
    ".tar.bz2",
    ".tar.gz",
    ".tzst",
    ".txz",
    ".tbz2",
    ".tbz",
    ".tgz",
    ".zip",
    ".tar",
    ".zst",
];

#[derive(Debug, Clone, PartialEq, Eq)]
enum ArchiveKind {
    Zip,
    Tar,
    TarGz,
    TarBz2,
    TarXz,
    TarZst,
    Zst,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ArchiveFileEntry {
    pub path: String,
    pub size: u64,
}

pub fn supported_archive_suffixes() -> &'static [&'static str] {
    SUPPORTED_PROJECT_ARCHIVE_SUFFIXES
}

pub fn archive_content_type(file_name: &str) -> &'static str {
    match detect_archive_kind(file_name) {
        Some(ArchiveKind::Zip) => "application/zip",
        Some(ArchiveKind::Tar) => "application/x-tar",
        Some(ArchiveKind::TarGz) => "application/gzip",
        Some(ArchiveKind::TarBz2) => "application/x-bzip2",
        Some(ArchiveKind::TarXz) => "application/x-xz",
        Some(ArchiveKind::TarZst | ArchiveKind::Zst) => "application/zstd",
        None => "application/octet-stream",
    }
}

pub fn list_archive_files_from_bytes(
    file_name: &str,
    file_bytes: &[u8],
) -> Result<Vec<ArchiveFileEntry>> {
    with_extracted_archive_bytes(file_name, file_bytes, collect_files_from_directory)
}

pub fn list_archive_files_from_path(
    storage_path: impl AsRef<Path>,
    original_filename: &str,
) -> Result<Vec<ArchiveFileEntry>> {
    let bytes = fs::read(storage_path.as_ref()).with_context(|| {
        format!(
            "failed to read archive: {}",
            storage_path.as_ref().display()
        )
    })?;
    list_archive_files_from_bytes(original_filename, &bytes)
}

pub fn collect_relative_paths_from_directory(root: &Path) -> Result<BTreeSet<String>> {
    Ok(collect_files_from_directory(root)?
        .into_iter()
        .map(|entry| entry.path)
        .collect())
}

pub fn extract_archive_path_to_directory(
    storage_path: impl AsRef<Path>,
    original_filename: &str,
    destination: &Path,
) -> Result<usize> {
    let bytes = fs::read(storage_path.as_ref()).with_context(|| {
        format!(
            "failed to read archive: {}",
            storage_path.as_ref().display()
        )
    })?;
    extract_archive_bytes_to_directory(original_filename, &bytes, destination)
}

pub fn read_archive_file_from_path(
    storage_path: impl AsRef<Path>,
    original_filename: &str,
    file_path: &str,
) -> Result<(String, u64, String, bool)> {
    let bytes = fs::read(storage_path.as_ref()).with_context(|| {
        format!(
            "failed to read archive: {}",
            storage_path.as_ref().display()
        )
    })?;
    with_extracted_archive_bytes(original_filename, &bytes, |root| {
        let target = resolve_extracted_file_path(root, file_path)
            .ok_or_else(|| anyhow!("file not found in extracted archive: {}", file_path))?;
        let file_bytes =
            fs::read(&target).with_context(|| format!("failed to read {}", target.display()))?;
        let size = file_bytes.len() as u64;
        let is_text = is_probably_text(file_path, &file_bytes);
        let encoding = "utf-8".to_string();
        let content = if is_text {
            String::from_utf8_lossy(&file_bytes).to_string()
        } else {
            String::new()
        };
        Ok((content, size, encoding, is_text))
    })
}

pub fn read_file_lines_from_archive_path(
    storage_path: impl AsRef<Path>,
    original_filename: &str,
    file_path: &str,
    range_start: usize,
    range_end: usize,
) -> (Vec<(usize, String)>, usize) {
    let Ok(bytes) = fs::read(storage_path.as_ref()) else {
        return (Vec::new(), 0);
    };
    let Ok(result) = with_extracted_archive_bytes(original_filename, &bytes, |root| {
        let Some(target) = resolve_extracted_file_path(root, file_path) else {
            return Ok((Vec::new(), 0));
        };
        let Ok(content) = fs::read_to_string(&target) else {
            return Ok((Vec::new(), 0));
        };
        let all_lines: Vec<&str> = content.lines().collect();
        let total_lines = all_lines.len();
        let clamped_end = range_end.min(total_lines);
        let lines = all_lines
            .iter()
            .enumerate()
            .filter_map(|(index, line)| {
                let line_number = index + 1;
                (line_number >= range_start && line_number <= clamped_end)
                    .then(|| (line_number, (*line).to_string()))
            })
            .collect();
        Ok((lines, total_lines))
    }) else {
        return (Vec::new(), 0);
    };
    result
}

pub fn extract_archive_bytes_to_directory(
    file_name: &str,
    file_bytes: &[u8],
    destination: &Path,
) -> Result<usize> {
    fs::create_dir_all(destination)
        .with_context(|| format!("failed to create {}", destination.display()))?;

    match detect_archive_kind(file_name) {
        Some(ArchiveKind::Zip) => extract_zip_bytes(file_bytes, destination),
        Some(ArchiveKind::Tar) => extract_tar_reader(Cursor::new(file_bytes), destination),
        Some(ArchiveKind::TarGz) => {
            extract_tar_reader(GzDecoder::new(Cursor::new(file_bytes)), destination)
        }
        Some(ArchiveKind::TarBz2) => {
            extract_tar_reader(BzDecoder::new(Cursor::new(file_bytes)), destination)
        }
        Some(ArchiveKind::TarXz) => {
            extract_tar_reader(XzDecoder::new(Cursor::new(file_bytes)), destination)
        }
        Some(ArchiveKind::TarZst) => {
            let decoder =
                ZstdDecoder::new(Cursor::new(file_bytes)).context("failed to open zstd archive")?;
            extract_tar_reader(decoder, destination)
        }
        Some(ArchiveKind::Zst) => extract_plain_zst_bytes(file_name, file_bytes, destination),
        None => Err(anyhow!(
            "unsupported archive format: {}",
            supported_archive_suffixes().join(", ")
        )),
    }
}

fn with_extracted_archive_bytes<T, F>(file_name: &str, file_bytes: &[u8], f: F) -> Result<T>
where
    F: FnOnce(&Path) -> Result<T>,
{
    let extraction_root =
        std::env::temp_dir().join(format!("argus-archive-{}", Uuid::new_v4()));
    fs::create_dir_all(&extraction_root)
        .with_context(|| format!("failed to create {}", extraction_root.display()))?;

    let extract_result =
        extract_archive_bytes_to_directory(file_name, file_bytes, &extraction_root);
    if let Err(error) = extract_result {
        let _ = fs::remove_dir_all(&extraction_root);
        return Err(error);
    }

    let result = f(&extraction_root);
    let _ = fs::remove_dir_all(&extraction_root);
    result
}

fn detect_archive_kind(file_name: &str) -> Option<ArchiveKind> {
    let lower = file_name.to_ascii_lowercase();
    if lower.ends_with(".tar.zstd") || lower.ends_with(".tar.zst") || lower.ends_with(".tzst") {
        return Some(ArchiveKind::TarZst);
    }
    if lower.ends_with(".tar.xz") || lower.ends_with(".txz") {
        return Some(ArchiveKind::TarXz);
    }
    if lower.ends_with(".tar.bz2") || lower.ends_with(".tbz2") || lower.ends_with(".tbz") {
        return Some(ArchiveKind::TarBz2);
    }
    if lower.ends_with(".tar.gz") || lower.ends_with(".tgz") {
        return Some(ArchiveKind::TarGz);
    }
    if lower.ends_with(".zip") {
        return Some(ArchiveKind::Zip);
    }
    if lower.ends_with(".tar") {
        return Some(ArchiveKind::Tar);
    }
    if lower.ends_with(".zst") {
        return Some(ArchiveKind::Zst);
    }
    None
}

fn extract_zip_bytes(file_bytes: &[u8], destination: &Path) -> Result<usize> {
    let reader = Cursor::new(file_bytes);
    let mut archive = ZipArchive::new(reader).context("invalid zip archive")?;
    let mut count = 0usize;

    for index in 0..archive.len() {
        let mut entry = archive
            .by_index(index)
            .with_context(|| format!("failed to inspect zip entry #{index}"))?;
        let Some(enclosed_name) = entry.enclosed_name() else {
            continue;
        };
        let Some(relative_path) = sanitize_relative_path(&enclosed_name) else {
            continue;
        };
        let target = destination.join(&relative_path);

        if entry.is_dir() {
            fs::create_dir_all(&target)
                .with_context(|| format!("failed to create {}", target.display()))?;
            continue;
        }

        if let Some(parent) = target.parent() {
            fs::create_dir_all(parent)
                .with_context(|| format!("failed to create {}", parent.display()))?;
        }

        let mut bytes = Vec::new();
        entry
            .read_to_end(&mut bytes)
            .with_context(|| format!("failed to read {}", entry.name()))?;
        fs::write(&target, bytes)
            .with_context(|| format!("failed to write {}", target.display()))?;
        count += 1;
    }

    Ok(count)
}

fn extract_tar_reader<R: Read>(reader: R, destination: &Path) -> Result<usize> {
    let mut archive = tar::Archive::new(reader);
    let mut count = 0usize;

    for entry in archive
        .entries()
        .context("failed to read tar archive entries")?
    {
        let mut entry = entry.context("failed to read tar entry")?;
        let path = entry.path().context("failed to read tar entry path")?;
        let Some(relative_path) = sanitize_relative_path(&path) else {
            continue;
        };
        let target = destination.join(&relative_path);
        let entry_type = entry.header().entry_type();

        if entry_type.is_dir() {
            fs::create_dir_all(&target)
                .with_context(|| format!("failed to create {}", target.display()))?;
            continue;
        }
        if !entry_type.is_file() {
            continue;
        }
        if let Some(parent) = target.parent() {
            fs::create_dir_all(parent)
                .with_context(|| format!("failed to create {}", parent.display()))?;
        }

        let mut bytes = Vec::new();
        entry
            .read_to_end(&mut bytes)
            .with_context(|| format!("failed to read {}", target.display()))?;
        fs::write(&target, bytes)
            .with_context(|| format!("failed to write {}", target.display()))?;
        count += 1;
    }

    Ok(count)
}

fn extract_plain_zst_bytes(
    file_name: &str,
    file_bytes: &[u8],
    destination: &Path,
) -> Result<usize> {
    let mut decoder =
        ZstdDecoder::new(Cursor::new(file_bytes)).context("failed to open zstd archive")?;
    let mut decoded = Vec::new();
    decoder
        .read_to_end(&mut decoded)
        .context("failed to decode zstd archive")?;

    if looks_like_tar(&decoded) {
        return extract_tar_reader(Cursor::new(decoded), destination);
    }

    let fallback_name = strip_supported_suffix(file_name).unwrap_or("archive".to_string());
    let Some(relative_path) = sanitize_relative_path(Path::new(&fallback_name)) else {
        return Err(anyhow!(
            "failed to derive extracted filename from {file_name}"
        ));
    };
    let target = destination.join(&relative_path);
    if let Some(parent) = target.parent() {
        fs::create_dir_all(parent)
            .with_context(|| format!("failed to create {}", parent.display()))?;
    }
    fs::write(&target, decoded).with_context(|| format!("failed to write {}", target.display()))?;
    Ok(1)
}

fn collect_files_from_directory(root: &Path) -> Result<Vec<ArchiveFileEntry>> {
    let mut pending = vec![root.to_path_buf()];
    let mut files = Vec::new();

    while let Some(current) = pending.pop() {
        for entry in fs::read_dir(&current)
            .with_context(|| format!("failed to read {}", current.display()))?
        {
            let entry = entry?;
            let path = entry.path();
            let file_type = entry.file_type()?;
            if file_type.is_dir() {
                pending.push(path);
                continue;
            }
            if !file_type.is_file() {
                continue;
            }

            let relative = path
                .strip_prefix(root)
                .with_context(|| format!("failed to strip root {}", root.display()))?;
            files.push(ArchiveFileEntry {
                path: normalize_relative_path_string(relative),
                size: entry.metadata()?.len(),
            });
        }
    }

    files.sort_by(|left, right| left.path.cmp(&right.path));
    Ok(files)
}

fn resolve_extracted_file_path(root: &Path, requested: &str) -> Option<PathBuf> {
    let normalized_target = requested.trim_start_matches('/').replace('\\', "/");
    let direct = sanitize_relative_path(Path::new(&normalized_target))
        .map(|relative| root.join(relative))
        .filter(|candidate| candidate.is_file());
    if direct.is_some() {
        return direct;
    }

    collect_files_from_directory(root)
        .ok()?
        .into_iter()
        .find(|entry| {
            entry.path == normalized_target
                || entry.path.ends_with(&format!("/{normalized_target}"))
        })
        .map(|entry| root.join(Path::new(&entry.path)))
}

fn sanitize_relative_path(path: &Path) -> Option<PathBuf> {
    let mut relative = PathBuf::new();
    for component in path.components() {
        match component {
            Component::Normal(segment) => relative.push(segment),
            Component::CurDir => {}
            Component::ParentDir | Component::RootDir | Component::Prefix(_) => return None,
        }
    }
    (!relative.as_os_str().is_empty()).then_some(relative)
}

fn normalize_relative_path_string(path: &Path) -> String {
    path.components()
        .filter_map(|component| match component {
            Component::Normal(segment) => Some(segment.to_string_lossy().into_owned()),
            _ => None,
        })
        .collect::<Vec<_>>()
        .join("/")
}

fn strip_supported_suffix(file_name: &str) -> Option<String> {
    let lower = file_name.to_ascii_lowercase();
    for suffix in supported_archive_suffixes() {
        if lower.ends_with(suffix) {
            let stripped = file_name[..file_name.len() - suffix.len()].trim_end_matches('.');
            return (!stripped.is_empty()).then(|| stripped.to_string());
        }
    }
    None
}

fn looks_like_tar(bytes: &[u8]) -> bool {
    bytes.len() > 262 && &bytes[257..262] == b"ustar"
}

fn is_probably_text(path: &str, bytes: &[u8]) -> bool {
    if bytes.contains(&0) {
        return false;
    }
    detect_language(path).is_some() || path.ends_with(".md") || path.ends_with(".txt")
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
