use std::{
    collections::{BTreeSet, HashSet},
    fs::File,
    path::Path,
};

use anyhow::Result;
use serde_json::Value;
use zip::ZipArchive;

const LIKELY_PROJECT_ROOT_SEGMENTS: &[&str] = &[
    "src", "include", "lib", "app", "apps", "test", "tests", "config", "configs",
];

pub fn normalize_scan_file_path(path_value: &str, project_root: Option<&str>) -> String {
    let normalized = normalize_path_text(path_value);
    if normalized.is_empty() {
        return String::new();
    }

    let normalized_root = normalize_path_text(project_root.unwrap_or_default());
    if !normalized_root.is_empty() {
        if let Some(relative) = relative_posix_path(&normalized, &normalized_root) {
            let relative = normalize_relative_path(&relative);
            if !relative.is_empty() && !relative.starts_with("../") {
                return relative;
            }
        }
    }

    if normalized.starts_with('/') {
        return normalize_relative_path(posix_basename(&normalized));
    }

    normalize_relative_path(&normalized)
}

pub fn normalize_scan_line_start(line_value: &Value) -> Option<u64> {
    match line_value {
        Value::Null | Value::Bool(_) => None,
        Value::Number(number) => {
            if let Some(value) = number.as_u64() {
                return (value > 0).then_some(value);
            }
            if let Some(value) = number.as_i64() {
                return (value > 0).then_some(value as u64);
            }
            if let Some(value) = number.as_f64() {
                let normalized = value as i64;
                return (normalized > 0).then_some(normalized as u64);
            }
            None
        }
        Value::String(raw) => {
            let stripped = raw.trim();
            if !stripped.is_empty() && stripped.chars().all(|ch| ch.is_ascii_digit()) {
                stripped.parse::<u64>().ok().filter(|value| *value > 0)
            } else {
                None
            }
        }
        _ => None,
    }
}

pub fn resolve_scan_finding_location(
    file_path: Option<&str>,
    line_start: Option<&Value>,
    project_root: Option<&str>,
    known_relative_paths: Option<&BTreeSet<String>>,
) -> (Option<String>, Option<u64>) {
    let normalized_line = line_start.and_then(normalize_scan_line_start);
    let raw_file_path = file_path.unwrap_or_default().trim();
    if raw_file_path.is_empty() {
        return (None, normalized_line);
    }

    let normalized_root = normalize_path_text(project_root.unwrap_or_default());
    let normalized_path = normalize_path_text(raw_file_path);
    if !normalized_root.is_empty() && !normalized_path.is_empty() {
        if let Some(relative) = relative_posix_path(&normalized_path, &normalized_root) {
            let normalized_relative = normalize_relative_path(&relative);
            if !normalized_relative.is_empty() && !normalized_relative.starts_with("../") {
                return (Some(normalized_relative), normalized_line);
            }
        }
    }

    if let Some(known_relative_paths) = known_relative_paths {
        if let Some(resolved) =
            resolve_scan_zip_member_path(raw_file_path, known_relative_paths.iter())
        {
            return (Some(resolved), normalized_line);
        }
    }

    for candidate in build_scan_zip_member_path_candidates(raw_file_path) {
        if candidate.starts_with("tmp/") {
            continue;
        }
        if let Some(known_relative_paths) = known_relative_paths {
            if let Some(resolved) =
                resolve_scan_zip_member_path(&candidate, known_relative_paths.iter())
            {
                return (Some(resolved), normalized_line);
            }
        }
        return (Some(candidate), normalized_line);
    }

    let normalized_file_path = normalize_scan_file_path(raw_file_path, project_root);
    if normalized_file_path.is_empty() {
        return (None, normalized_line);
    }

    if let Some(known_relative_paths) = known_relative_paths {
        if let Some(resolved) =
            resolve_scan_zip_member_path(&normalized_file_path, known_relative_paths.iter())
        {
            return (Some(resolved), normalized_line);
        }
    }

    (Some(normalized_file_path), normalized_line)
}

pub fn build_legacy_scan_path_candidates(file_path: &str) -> Vec<String> {
    let normalized = normalize_path_text(file_path);
    if normalized.is_empty() {
        return Vec::new();
    }

    let mut candidates = Vec::new();
    let leading_trimmed = normalize_relative_path(&normalized);
    if !leading_trimmed.is_empty() {
        candidates.push(leading_trimmed.clone());
    }

    let parts = split_relative_parts(&leading_trimmed);
    if parts.len() >= 3 && parts.first() == Some(&"tmp") {
        candidates.push(parts[2..].join("/"));
    }
    if parts.len() >= 4 && parts.first() == Some(&"tmp") {
        candidates.push(parts[3..].join("/"));
    }

    let basename = posix_basename(&leading_trimmed);
    if !basename.is_empty() {
        candidates.push(basename.to_string());
    }

    dedupe_relative_candidates(candidates)
}

pub fn build_scan_zip_member_path_candidates(file_path: &str) -> Vec<String> {
    let normalized = normalize_relative_path(file_path);
    if normalized.is_empty() {
        return Vec::new();
    }

    let mut candidates = Vec::new();
    let mut seen = HashSet::new();
    append_candidate(&mut candidates, &mut seen, &normalized);

    let parts = split_relative_parts(&normalized);
    if parts.len() >= 2 {
        let first_segment = parts[0].to_ascii_lowercase();
        let second_segment = parts[1].to_ascii_lowercase();
        let should_strip_archive_root = first_segment != "tmp"
            && !LIKELY_PROJECT_ROOT_SEGMENTS.contains(&first_segment.as_str())
            && (LIKELY_PROJECT_ROOT_SEGMENTS.contains(&second_segment.as_str())
                || parts[1].contains('.'));
        if should_strip_archive_root {
            append_candidate(&mut candidates, &mut seen, &parts[1..].join("/"));
        }
    }

    for candidate in build_legacy_scan_path_candidates(file_path) {
        append_candidate(&mut candidates, &mut seen, &candidate);
    }

    candidates
}

pub fn resolve_scan_zip_member_path<I, S>(
    file_path: &str,
    known_relative_paths: I,
) -> Option<String>
where
    I: IntoIterator<Item = S>,
    S: AsRef<str>,
{
    let normalized_known: HashSet<String> = known_relative_paths
        .into_iter()
        .map(|item| normalize_relative_path(item.as_ref()))
        .filter(|item| !item.is_empty())
        .collect();

    build_scan_zip_member_path_candidates(file_path)
        .into_iter()
        .find(|candidate| normalized_known.contains(candidate))
}

pub fn resolve_legacy_scan_path<I, S>(file_path: &str, known_relative_paths: I) -> Option<String>
where
    I: IntoIterator<Item = S>,
    S: AsRef<str>,
{
    resolve_scan_zip_member_path(file_path, known_relative_paths)
}

pub fn collect_zip_relative_paths(zip_path: impl AsRef<Path>) -> Result<BTreeSet<String>> {
    let reader = File::open(zip_path.as_ref())?;
    let mut archive = ZipArchive::new(reader)?;
    let mut normalized_paths = BTreeSet::new();

    for index in 0..archive.len() {
        let entry = archive.by_index(index)?;
        if entry.is_dir() {
            continue;
        }
        let normalized = normalize_relative_path(entry.name());
        if !normalized.is_empty() {
            normalized_paths.insert(normalized);
        }
    }

    Ok(normalized_paths)
}

fn normalize_path_text(path_value: &str) -> String {
    let raw = path_value.trim().replace('\\', "/");
    if raw.is_empty() {
        return String::new();
    }

    let has_leading_slash = raw.starts_with('/');
    let collapsed = collapse_path_separators(&raw);
    let normalized = posix_normpath(&collapsed);

    if normalized == "." {
        return String::new();
    }
    if has_leading_slash && !normalized.starts_with('/') {
        return format!("/{normalized}");
    }
    normalized
}

fn normalize_relative_path(path_value: &str) -> String {
    let mut normalized = normalize_path_text(path_value)
        .trim_start_matches('/')
        .to_string();
    while normalized.starts_with("./") {
        normalized = normalized[2..].to_string();
    }
    normalized
}

fn collapse_path_separators(raw: &str) -> String {
    let mut collapsed = String::with_capacity(raw.len());
    let mut previous_was_slash = false;
    for ch in raw.chars() {
        if ch == '/' {
            if !previous_was_slash {
                collapsed.push(ch);
            }
            previous_was_slash = true;
        } else {
            collapsed.push(ch);
            previous_was_slash = false;
        }
    }
    collapsed
}

fn posix_normpath(path: &str) -> String {
    let is_absolute = path.starts_with('/');
    let mut stack: Vec<&str> = Vec::new();

    for part in path.split('/') {
        if part.is_empty() || part == "." {
            continue;
        }
        if part == ".." {
            if let Some(last) = stack.last() {
                if *last != ".." {
                    stack.pop();
                    continue;
                }
            }
            if !is_absolute {
                stack.push(part);
            }
            continue;
        }
        stack.push(part);
    }

    if is_absolute {
        if stack.is_empty() {
            "/".to_string()
        } else {
            format!("/{}", stack.join("/"))
        }
    } else if stack.is_empty() {
        ".".to_string()
    } else {
        stack.join("/")
    }
}

fn relative_posix_path(path: &str, root: &str) -> Option<String> {
    let path_is_absolute = path.starts_with('/');
    let root_is_absolute = root.starts_with('/');
    if path_is_absolute != root_is_absolute {
        return None;
    }

    let path_parts = split_path_parts(path);
    let root_parts = split_path_parts(root);
    let mut common = 0usize;
    while common < path_parts.len()
        && common < root_parts.len()
        && path_parts[common] == root_parts[common]
    {
        common += 1;
    }

    let mut relative_parts = Vec::new();
    relative_parts.extend(std::iter::repeat_n(
        "..",
        root_parts.len().saturating_sub(common),
    ));
    relative_parts.extend_from_slice(&path_parts[common..]);
    Some(relative_parts.join("/"))
}

fn split_path_parts(path: &str) -> Vec<&str> {
    path.split('/')
        .filter(|part| !part.is_empty())
        .collect::<Vec<_>>()
}

fn split_relative_parts(path: &str) -> Vec<&str> {
    path.split('/').filter(|part| !part.is_empty()).collect()
}

fn posix_basename(path: &str) -> &str {
    path.trim_end_matches('/')
        .rsplit('/')
        .next()
        .unwrap_or_default()
}

fn dedupe_relative_candidates(candidates: Vec<String>) -> Vec<String> {
    let mut deduplicated = Vec::new();
    let mut seen = HashSet::new();
    for item in candidates {
        append_candidate(&mut deduplicated, &mut seen, &item);
    }
    deduplicated
}

fn append_candidate(candidates: &mut Vec<String>, seen: &mut HashSet<String>, value: &str) {
    let normalized = normalize_relative_path(value);
    if normalized.is_empty() || !seen.insert(normalized.clone()) {
        return;
    }
    candidates.push(normalized);
}

#[cfg(test)]
mod tests {
    use std::{collections::BTreeSet, fs::File, io::Write};

    use serde_json::Value;
    use tempfile::TempDir;
    use zip::write::SimpleFileOptions;

    use super::{
        build_legacy_scan_path_candidates, build_scan_zip_member_path_candidates,
        collect_zip_relative_paths, normalize_scan_file_path, normalize_scan_line_start,
        resolve_legacy_scan_path, resolve_scan_finding_location, resolve_scan_zip_member_path,
    };

    #[test]
    fn normalize_scan_file_path_converts_absolute_path_under_project_root() {
        assert_eq!(
            normalize_scan_file_path("/tmp/project-root/src/main.py", Some("/tmp/project-root")),
            "src/main.py"
        );
    }

    #[test]
    fn normalize_scan_file_path_cleans_relative_path() {
        assert_eq!(
            normalize_scan_file_path("./src//pkg/../main.py", Some("/tmp/project-root")),
            "src/main.py"
        );
    }

    #[test]
    fn normalize_scan_line_start_accepts_positive_int_like_values() {
        assert_eq!(normalize_scan_line_start(&Value::from(7)), Some(7));
        assert_eq!(normalize_scan_line_start(&Value::from(7.9)), Some(7));
        assert_eq!(normalize_scan_line_start(&Value::from("9")), Some(9));
    }

    #[test]
    fn normalize_scan_line_start_rejects_null_bool_non_positive_and_non_digits() {
        assert_eq!(normalize_scan_line_start(&Value::Null), None);
        assert_eq!(normalize_scan_line_start(&Value::Bool(false)), None);
        assert_eq!(normalize_scan_line_start(&Value::from(0)), None);
        assert_eq!(normalize_scan_line_start(&Value::from(-3)), None);
        assert_eq!(normalize_scan_line_start(&Value::from(" 12a ")), None);
    }

    #[test]
    fn build_legacy_scan_path_candidates_strips_temp_prefix_and_archive_root() {
        assert_eq!(
            build_legacy_scan_path_candidates(
                "/tmp/Argus_proj_123/archive-root/./src/app/main.py"
            ),
            vec![
                "tmp/Argus_proj_123/archive-root/src/app/main.py",
                "archive-root/src/app/main.py",
                "src/app/main.py",
                "main.py",
            ]
        );
    }

    #[test]
    fn build_scan_zip_member_path_candidates_supports_archive_root_prefix() {
        assert_eq!(
            build_scan_zip_member_path_candidates("openclaw-2026.3.7/src/discord/voice-message.ts"),
            vec![
                "openclaw-2026.3.7/src/discord/voice-message.ts",
                "src/discord/voice-message.ts",
                "voice-message.ts",
            ]
        );
    }

    #[test]
    fn resolve_scan_zip_member_path_prefers_exact_match_before_archive_root_fallback() {
        assert_eq!(
            resolve_scan_zip_member_path(
                "openclaw-2026.3.7/src/discord/voice-message.ts",
                [
                    "openclaw-2026.3.7/src/discord/voice-message.ts",
                    "src/discord/voice-message.ts",
                ],
            ),
            Some("openclaw-2026.3.7/src/discord/voice-message.ts".to_string())
        );
    }

    #[test]
    fn resolve_scan_zip_member_path_falls_back_to_archive_stripped_relative_path() {
        assert_eq!(
            resolve_scan_zip_member_path(
                "openclaw-2026.3.7/src/discord/voice-message.ts",
                ["src/discord/voice-message.ts"],
            ),
            Some("src/discord/voice-message.ts".to_string())
        );
    }

    #[test]
    fn resolve_legacy_scan_path_uses_first_known_zip_match() {
        assert_eq!(
            resolve_legacy_scan_path(
                "/tmp/Argus_proj_123/archive-root/./src/app/main.py",
                ["archive-root/src/app/main.py", "src/app/main.py"],
            ),
            Some("archive-root/src/app/main.py".to_string())
        );
    }

    #[test]
    fn resolve_legacy_scan_path_returns_none_when_zip_has_no_match() {
        assert_eq!(
            resolve_legacy_scan_path(
                "/tmp/Argus_proj_123/archive-root/./src/app/missing.py",
                ["src/app/main.py"],
            ),
            None
        );
    }

    #[test]
    fn resolve_scan_finding_location_uses_archive_candidates_and_normalizes_line_start() {
        let known = BTreeSet::from([
            "archive-root/src/app/main.py".to_string(),
            "src/app/main.py".to_string(),
        ]);

        assert_eq!(
            resolve_scan_finding_location(
                Some("/tmp/Argus_proj_123/archive-root/./src/app/main.py"),
                Some(&Value::from("14")),
                Some("/tmp/project-root"),
                Some(&known),
            ),
            (Some("archive-root/src/app/main.py".to_string()), Some(14),)
        );
    }

    #[test]
    fn resolve_scan_finding_location_prefers_project_relative_path_before_archive_lookup() {
        let known = BTreeSet::from(["src/app/main.py".to_string()]);

        assert_eq!(
            resolve_scan_finding_location(
                Some("/tmp/project-root/src/app/main.py"),
                Some(&Value::from(3)),
                Some("/tmp/project-root"),
                Some(&known),
            ),
            (Some("src/app/main.py".to_string()), Some(3))
        );
    }

    #[test]
    fn resolve_scan_finding_location_skips_tmp_candidates_without_known_paths() {
        assert_eq!(
            resolve_scan_finding_location(
                Some("/tmp/Argus_proj_123/archive-root/src/app/main.py"),
                Some(&Value::Null),
                None,
                None,
            ),
            (Some("archive-root/src/app/main.py".to_string()), None)
        );
    }

    #[test]
    fn collect_zip_relative_paths_normalizes_members_and_skips_directories() {
        let temp_dir = TempDir::new().expect("temp dir");
        let archive_path = temp_dir.path().join("sample.zip");
        let file = File::create(&archive_path).expect("archive file");
        let mut writer = zip::ZipWriter::new(file);
        let options = SimpleFileOptions::default();

        writer
            .add_directory("./archive-root/src/", options)
            .expect("directory entry");
        writer
            .start_file("./archive-root/src/app/main.py", options)
            .expect("start main file");
        writer
            .write_all(b"print('main')\n")
            .expect("write main file");
        writer
            .start_file("archive-root//README.md", options)
            .expect("start readme file");
        writer.write_all(b"# readme\n").expect("write readme file");
        writer.finish().expect("finish archive");

        assert_eq!(
            collect_zip_relative_paths(&archive_path).expect("collect zip paths"),
            BTreeSet::from([
                "archive-root/README.md".to_string(),
                "archive-root/src/app/main.py".to_string(),
            ])
        );
    }
}
