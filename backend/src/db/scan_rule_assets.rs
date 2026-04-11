use std::{
    collections::{BTreeMap, BTreeSet},
    path::{Path, PathBuf},
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
}

pub async fn ensure_initialized(state: &AppState) -> Result<ScanRuleAssetImportSummary> {
    let Some(pool) = &state.db_pool else {
        return Ok(ScanRuleAssetImportSummary::default());
    };

    let assets = discover_rule_assets()?;
    let existing_rows = sqlx::query_as::<_, (String, String)>(
        "select asset_path, sha256 from rust_scan_rule_assets",
    )
    .fetch_all(pool)
    .await?;
    let existing = existing_rows.into_iter().collect::<BTreeMap<_, _>>();

    let mut inserted = 0;
    let mut updated = 0;
    let mut skipped = 0;

    for asset in &assets {
        match existing.get(&asset.asset_path) {
            Some(existing_sha) if existing_sha == &asset.sha256 => skipped += 1,
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

    Ok(ScanRuleAssetImportSummary {
        discovered: assets.len(),
        inserted,
        updated,
        skipped,
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

pub fn discover_rule_assets() -> Result<Vec<ScanRuleAsset>> {
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
        if matches!(
            top,
            Some(
                "rules_opengrep"
                    | "rules_from_patches"
                    | "patches"
                    | "gitleaks_builtin"
                    | "bandit_builtin"
                    | "rules_phpstan"
                    | "rules_pmd"
            )
        ) && seen.insert(relative.clone())
        {
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
        "rules_from_patches" => Ok(("opengrep", "patch_rule")),
        "patches" => Ok(("opengrep", "patch_artifact")),
        "gitleaks_builtin" => Ok(("gitleaks", "builtin")),
        "bandit_builtin" => Ok(("bandit", "builtin")),
        "rules_phpstan" => Ok(("phpstan", "builtin")),
        "rules_pmd" => Ok(("pmd", "builtin")),
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

    #[test]
    fn discovers_all_supported_rule_asset_families() {
        let assets = discover_rule_assets().expect("rule assets should load");
        assert!(assets.len() > 7000);

        let paths = assets
            .iter()
            .map(|asset| asset.asset_path.as_str())
            .collect::<Vec<_>>();
        assert!(paths
            .iter()
            .any(|path| path == &"rules_opengrep/X509-subject-name-validation.yaml"));
        assert!(paths
            .iter()
            .any(|path| path == &"gitleaks_builtin/gitleaks-default.toml"));
        assert!(paths
            .iter()
            .any(|path| path == &"bandit_builtin/bandit_builtin_rules.json"));
        assert!(paths
            .iter()
            .any(|path| path == &"rules_phpstan/phpstan_rules_combined.json"));
        assert!(!paths.iter().any(|path| path.starts_with("yasa_builtin/")));
    }

    #[test]
    fn classifies_patch_and_builtin_assets_by_engine() {
        let assets = discover_rule_assets().expect("rule assets should load");

        let patch_rule = assets
            .iter()
            .find(|asset| asset.asset_path.starts_with("rules_from_patches/"))
            .expect("patch rule asset should exist");
        assert_eq!(patch_rule.engine, "opengrep");
        assert_eq!(patch_rule.source_kind, "patch_rule");

        let patch_artifact = assets
            .iter()
            .find(|asset| asset.asset_path.starts_with("patches/"))
            .expect("patch artifact should exist");
        assert_eq!(patch_artifact.engine, "opengrep");
        assert_eq!(patch_artifact.source_kind, "patch_artifact");

        let pmd = assets
            .iter()
            .find(|asset| asset.asset_path.starts_with("rules_pmd/"))
            .expect("pmd asset should exist");
        assert_eq!(pmd.engine, "pmd");
        assert_eq!(pmd.source_kind, "builtin");
    }
}
