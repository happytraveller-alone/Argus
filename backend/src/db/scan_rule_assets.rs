use std::{
    collections::{BTreeMap, BTreeSet},
    path::{Path, PathBuf},
    sync::OnceLock,
};

use anyhow::{anyhow, Context, Result};
use serde_json::{json, Value};
use sha2::{Digest, Sha256};

use crate::state::{AppState, ScanRuleAsset};

#[derive(Clone, Debug, Default)]
pub struct ScanRuleAssetImportSummary {
    pub discovered: usize,
    pub inserted: usize,
    pub updated: usize,
    pub skipped: usize,
    pub deactivated: usize,
}

pub async fn ensure_initialized(state: &AppState) -> Result<ScanRuleAssetImportSummary> {
    let Some(pool) = &state.db_pool else {
        return Ok(ScanRuleAssetImportSummary::default());
    };

    let assets = discover_rule_assets()?;
    let existing_rows = sqlx::query_as::<_, (String, String, String, String, bool)>(
        "select engine, source_kind, asset_path, sha256, is_active from rust_scan_rule_assets",
    )
    .fetch_all(pool)
    .await?;
    let existing = existing_rows
        .into_iter()
        .map(|(engine, source_kind, asset_path, sha256, is_active)| {
            ((engine, source_kind, asset_path), (sha256, is_active))
        })
        .collect::<BTreeMap<_, _>>();

    let mut discovered_by_scope = BTreeMap::<(String, String), Vec<String>>::new();
    for asset in &assets {
        discovered_by_scope
            .entry((asset.engine.clone(), asset.source_kind.clone()))
            .or_default()
            .push(asset.asset_path.clone());
    }

    let mut inserted = 0;
    let mut updated = 0;
    let mut skipped = 0;

    for asset in &assets {
        match existing.get(&(
            asset.engine.clone(),
            asset.source_kind.clone(),
            asset.asset_path.clone(),
        )) {
            Some((existing_sha, true)) if existing_sha == &asset.sha256 => skipped += 1,
            Some(_) => {
                sqlx::query(
                    r#"
                    insert into rust_scan_rule_assets (
                        engine, source_kind, asset_path, file_format, sha256, content, metadata_json, is_active
                    )
                    values ($1, $2, $3, $4, $5, $6, $7, true)
                    on conflict (engine, source_kind, asset_path) do update
                    set
                        file_format = excluded.file_format,
                        sha256 = excluded.sha256,
                        content = excluded.content,
                        metadata_json = excluded.metadata_json,
                        is_active = true,
                        updated_at = now()
                    "#,
                )
                .bind(&asset.engine)
                .bind(&asset.source_kind)
                .bind(&asset.asset_path)
                .bind(&asset.file_format)
                .bind(&asset.sha256)
                .bind(&asset.content)
                .bind(&asset.metadata_json)
                .execute(pool)
                .await?;
                updated += 1;
            }
            None => {
                sqlx::query(
                    r#"
                    insert into rust_scan_rule_assets (
                        engine, source_kind, asset_path, file_format, sha256, content, metadata_json, is_active
                    )
                    values ($1, $2, $3, $4, $5, $6, $7, true)
                    "#,
                )
                .bind(&asset.engine)
                .bind(&asset.source_kind)
                .bind(&asset.asset_path)
                .bind(&asset.file_format)
                .bind(&asset.sha256)
                .bind(&asset.content)
                .bind(&asset.metadata_json)
                .execute(pool)
                .await?;
                inserted += 1;
            }
        }
    }

    let mut deactivated = 0;
    for ((engine, source_kind), asset_paths) in discovered_by_scope {
        let result = sqlx::query(
            r#"
            update rust_scan_rule_assets
            set is_active = false, updated_at = now()
            where engine = $1
              and source_kind = $2
              and is_active = true
              and not (asset_path = any($3))
            "#,
        )
        .bind(&engine)
        .bind(&source_kind)
        .bind(&asset_paths)
        .execute(pool)
        .await?;
        deactivated += result.rows_affected() as usize;
    }

    Ok(ScanRuleAssetImportSummary {
        discovered: assets.len(),
        inserted,
        updated,
        skipped,
        deactivated,
    })
}

pub async fn load_asset_content(
    state: &AppState,
    engine: &str,
    source_kind: &str,
    asset_path: &str,
) -> Result<Option<String>> {
    if let Some(pool) = &state.db_pool {
        let row = sqlx::query_scalar::<_, String>(
            r#"
            select content
            from rust_scan_rule_assets
            where engine = $1 and source_kind = $2 and asset_path = $3 and is_active = true
            "#,
        )
        .bind(engine)
        .bind(source_kind)
        .bind(asset_path)
        .fetch_optional(pool)
        .await?;
        return Ok(row);
    }

    Ok(discover_rule_assets()?
        .into_iter()
        .find(|asset| {
            asset.engine == engine
                && asset.source_kind == source_kind
                && asset.asset_path == asset_path
        })
        .map(|asset| asset.content))
}

pub async fn load_assets_by_engine(
    state: &AppState,
    engine: &str,
    source_kinds: &[&str],
) -> Result<Vec<ScanRuleAsset>> {
    if let Some(pool) = &state.db_pool {
        let rows = sqlx::query_as::<_, (String, String, String, String, String, String, Value)>(
            r#"
            select engine, source_kind, asset_path, file_format, sha256, content, metadata_json
            from rust_scan_rule_assets
            where engine = $1
              and source_kind = any($2)
              and is_active = true
            order by asset_path asc
            "#,
        )
        .bind(engine)
        .bind(source_kinds)
        .fetch_all(pool)
        .await?;

        return Ok(rows
            .into_iter()
            .map(
                |(engine, source_kind, asset_path, file_format, sha256, content, metadata_json)| {
                    ScanRuleAsset {
                        engine,
                        source_kind,
                        asset_path,
                        file_format,
                        sha256,
                        content,
                        metadata_json,
                    }
                },
            )
            .collect());
    }

    let source_kinds = source_kinds.iter().copied().collect::<BTreeSet<_>>();
    Ok(discover_rule_assets()?
        .into_iter()
        .filter(|asset| asset.engine == engine && source_kinds.contains(asset.source_kind.as_str()))
        .collect())
}

static RULE_ASSET_CACHE: OnceLock<Vec<ScanRuleAsset>> = OnceLock::new();

pub fn discover_rule_assets() -> Result<Vec<ScanRuleAsset>> {
    if let Some(cached) = RULE_ASSET_CACHE.get() {
        return Ok(cached.clone());
    }
    let assets = discover_rule_assets_uncached()?;
    let _ = RULE_ASSET_CACHE.set(assets.clone());
    Ok(assets)
}

fn discover_rule_assets_uncached() -> Result<Vec<ScanRuleAsset>> {
    let root = rule_asset_root();
    let mut assets = Vec::new();
    for relative in collect_rule_asset_paths(&root)? {
        let absolute = root.join(&relative);
        let content = std::fs::read_to_string(&absolute)
            .with_context(|| format!("failed to read rule asset: {}", absolute.display()))?;
        let relative_text = relative.to_string_lossy().replace('\\', "/");
        let (engine, source_kind) = classify_rule_asset(&relative)?;
        assets.push(ScanRuleAsset {
            engine: engine.to_string(),
            source_kind: source_kind.to_string(),
            asset_path: relative_text.clone(),
            file_format: absolute
                .extension()
                .and_then(|ext| ext.to_str())
                .map(|ext| ext.to_ascii_lowercase())
                .unwrap_or_else(|| "unknown".to_string()),
            sha256: sha256_hex(content.as_bytes()),
            metadata_json: json!({
                "asset_path": relative_text,
                "size_bytes": content.len(),
            }),
            content,
        });
    }
    Ok(assets)
}

fn rule_asset_root() -> PathBuf {
    Path::new(env!("CARGO_MANIFEST_DIR")).join("assets/scan_rule_assets")
}

fn collect_rule_asset_paths(root: &Path) -> Result<Vec<PathBuf>> {
    let mut out = Vec::new();
    let mut seen = BTreeSet::new();
    for entry in walkdir(root)? {
        let relative = entry
            .strip_prefix(root)
            .with_context(|| format!("failed to strip rule asset prefix: {}", entry.display()))?
            .to_path_buf();
        let top = relative
            .components()
            .next()
            .and_then(|part| part.as_os_str().to_str());
        if matches!(top, Some("rules_opengrep")) && seen.insert(relative.clone()) {
            out.push(relative);
        }
    }
    Ok(out)
}

fn walkdir(root: &Path) -> Result<Vec<PathBuf>> {
    let mut stack = vec![root.to_path_buf()];
    let mut files = Vec::new();
    while let Some(path) = stack.pop() {
        for entry in std::fs::read_dir(&path)
            .with_context(|| format!("failed to read rule asset dir: {}", path.display()))?
        {
            let entry = entry?;
            let entry_path = entry.path();
            if entry_path.is_dir() {
                stack.push(entry_path);
            } else {
                files.push(entry_path);
            }
        }
    }
    files.sort();
    Ok(files)
}

fn classify_rule_asset(relative: &Path) -> Result<(&'static str, &'static str)> {
    let top = relative
        .components()
        .next()
        .and_then(|part| part.as_os_str().to_str())
        .ok_or_else(|| anyhow!("invalid rule asset path: {}", relative.display()))?;

    match top {
        "rules_opengrep" => Ok(("opengrep", "internal_rule")),
        _ => Err(anyhow!(
            "unsupported rule asset root: {}",
            relative.display()
        )),
    }
}

fn sha256_hex(bytes: &[u8]) -> String {
    let mut hasher = Sha256::new();
    hasher.update(bytes);
    format!("{:x}", hasher.finalize())
}

#[cfg(test)]
mod tests {
    use super::discover_rule_assets;
    use std::collections::BTreeSet;

    fn severity_tokens(content: &str) -> Vec<String> {
        content
            .lines()
            .filter_map(|line| {
                line.trim().strip_prefix("severity:").map(|value| {
                    value
                        .trim()
                        .trim_matches('"')
                        .trim_matches('\'')
                        .to_uppercase()
                })
            })
            .collect()
    }

    fn language_blocks(content: &str) -> Vec<Vec<String>> {
        let mut blocks = Vec::new();
        let mut current = Vec::new();
        let mut in_languages_block = false;
        let mut languages_indent = 0usize;
        for line in content.lines() {
            let indent = line.len().saturating_sub(line.trim_start().len());
            let trimmed = line.trim();
            if trimmed.starts_with("languages:") {
                if in_languages_block {
                    blocks.push(current);
                    current = Vec::new();
                }
                in_languages_block = true;
                languages_indent = indent;
                continue;
            }
            if in_languages_block {
                if indent < languages_indent {
                    blocks.push(current);
                    current = Vec::new();
                    in_languages_block = false;
                } else if let Some(lang) = trimmed.strip_prefix("- ") {
                    current.push(normalize_language_token(lang));
                } else {
                    blocks.push(current);
                    current = Vec::new();
                    in_languages_block = false;
                }
            }
        }
        if in_languages_block {
            blocks.push(current);
        }
        blocks
    }

    fn normalize_language_token(lang: &str) -> String {
        match lang
            .trim()
            .trim_matches('"')
            .trim_matches('\'')
            .to_lowercase()
            .as_str()
        {
            "c#" => "csharp".to_string(),
            "c++" => "cpp".to_string(),
            other => other.to_string(),
        }
    }

    #[test]
    fn discovers_only_retained_rule_asset_families() {
        let assets = discover_rule_assets().expect("rule assets should load");
        assert!(assets.len() > 500);

        let paths = assets
            .iter()
            .map(|asset| asset.asset_path.as_str())
            .collect::<Vec<_>>();
        assert!(paths
            .iter()
            .any(|path| path == &"rules_opengrep/java/aes_ecb_mode.yaml"));

        let roots = paths
            .iter()
            .filter_map(|path| path.split('/').next())
            .collect::<BTreeSet<_>>();
        assert_eq!(roots, BTreeSet::from(["rules_opengrep"]));
    }

    #[test]
    fn classifies_retained_assets_as_opengrep_sources() {
        let assets = discover_rule_assets().expect("rule assets should load");

        assert!(assets
            .iter()
            .all(|asset| asset.asset_path.starts_with("rules_opengrep/")));
        assert!(assets.iter().all(|asset| asset.engine == "opengrep"));
        assert!(assets
            .iter()
            .all(|asset| asset.source_kind == "internal_rule"));
    }

    #[test]
    fn retained_opengrep_assets_are_language_scoped() {
        let assets = discover_rule_assets().expect("rule assets should load");

        for asset in assets
            .iter()
            .filter(|asset| asset.asset_path.starts_with("rules_opengrep/"))
        {
            let parts = asset.asset_path.split('/').collect::<Vec<_>>();
            assert!(
                parts.len() >= 3,
                "expected rules_opengrep/<language>/<file> path, got {}",
                asset.asset_path
            );
            let directory_language = parts[1];
            let language_blocks = language_blocks(&asset.content);
            assert!(
                !language_blocks.is_empty(),
                "expected language metadata in {}",
                asset.asset_path
            );
            for languages in language_blocks {
                assert_eq!(
                    languages.len(),
                    1,
                    "expected exactly one language per rule in {}",
                    asset.asset_path
                );
                assert_eq!(
                    languages[0], directory_language,
                    "expected language directory to match rule language in {}",
                    asset.asset_path
                );
            }
        }
    }

    #[test]
    fn retained_assets_only_contain_error_rules() {
        let assets = discover_rule_assets().expect("rule assets should load");

        for asset in assets {
            let severities = severity_tokens(&asset.content);
            assert!(
                !severities.is_empty(),
                "expected severity markers in {}",
                asset.asset_path
            );
            assert!(
                severities.iter().all(|severity| severity == "ERROR"),
                "expected only ERROR severities in {}, got {:?}",
                asset.asset_path,
                severities
                    .into_iter()
                    .filter(|severity| severity != "ERROR")
                    .collect::<Vec<_>>()
            );
        }
    }

    #[test]
    fn retained_assets_exclude_nongeneric_patch_rules() {
        let assets = discover_rule_assets().expect("rule assets should load");

        for asset in assets {
            let filename = asset.asset_path.rsplit('/').next().unwrap_or_default();
            assert!(
                !filename.starts_with("vuln-"),
                "expected generated project/CVE-specific rule asset to stay pruned: {}",
                asset.asset_path
            );
            assert_ne!(
                asset.asset_path, "rules_opengrep/c/vim-double-free-b29f4abc.yml",
                "expected commit-specific Vim rule to stay pruned"
            );
        }
    }
}
