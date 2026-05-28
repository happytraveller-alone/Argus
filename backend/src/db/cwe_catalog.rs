use std::collections::{BTreeMap, BTreeSet};

use anyhow::{anyhow, bail, Context, Result};
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use sqlx::{postgres::PgRow, PgPool, Row};
use time::{format_description::well_known::Rfc3339, OffsetDateTime};

use crate::{core::hex, state::AppState};

const BUNDLED_CWE_CATALOG_JSON: &str =
    include_str!("../../assets/cwe_catalog/cwe_catalog_v4_20_zh.json");
const BUNDLED_CWE_CATALOG_REVIEW: &str =
    include_str!("../../assets/cwe_catalog/cwe_catalog_v4_20_zh.review.md");
const EXPECTED_CONTENT_VERSION: &str = "4.20";
const EXPECTED_CONTENT_DATE: &str = "2026-04-30";
const EXPECTED_WEAKNESS_COUNT: usize = 969;
const TRANSLATION_SOURCE: &str = "agent_curated_self_reviewed";
const MAX_LIST_LIMIT: usize = 1000;
const DEFAULT_LIST_LIMIT: usize = 100;

#[derive(Clone, Debug, Default, PartialEq, Eq)]
pub struct CweCatalogSyncSummary {
    pub discovered: usize,
    pub inserted: usize,
    pub updated: usize,
    pub skipped: usize,
    pub deactivated: usize,
    pub active_total: usize,
}

#[derive(Clone, Debug, Default, PartialEq, Eq)]
pub struct CweCatalogListParams {
    pub keyword: Option<String>,
    pub limit: Option<usize>,
    pub offset: Option<usize>,
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct CweCatalogListResult {
    pub entries: Vec<CweCatalogEntry>,
    pub total: usize,
    pub limit: usize,
    pub offset: usize,
    pub source_version: Option<String>,
    pub source_date: Option<String>,
    pub source_sha256: Option<String>,
    pub translation_source: Option<String>,
    pub translation_reviewed_at: Option<String>,
}

#[derive(Clone, Debug, PartialEq, Eq, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct CweCatalogEntry {
    pub id: String,
    pub numeric_id: i32,
    pub name_en_official: String,
    pub name_en_short: String,
    pub name_zh: String,
    pub source_version: String,
    pub source_date: String,
    pub source_sha256: String,
    pub translation_source: String,
    pub translation_reviewed_at: String,
}

#[derive(Clone, Debug, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct CweCatalogSeed {
    pub content_version: String,
    pub content_date: String,
    pub generated_at: String,
    pub reviewed_at: String,
    pub source: String,
    pub translation_source: String,
    pub entry_count: usize,
    pub entries: Vec<CweCatalogSeedEntry>,
}

#[derive(Clone, Debug, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct CweCatalogSeedEntry {
    pub id: String,
    pub numeric_id: i32,
    pub name_en_official: String,
    pub name_en_short: String,
    pub name_zh: String,
}

#[derive(Debug)]
struct ExistingCatalogRow {
    numeric_id: i32,
    name_en_official: String,
    name_en_short: String,
    name_zh: String,
    source_version: String,
    source_date: String,
    source_sha256: String,
    translation_source: String,
    translation_reviewed_at: OffsetDateTime,
    is_active: bool,
}

pub async fn ensure_initialized(state: &AppState) -> Result<CweCatalogSyncSummary> {
    let Some(pool) = &state.db_pool else {
        return Ok(CweCatalogSyncSummary::default());
    };
    ensure_initialized_with_pool(pool).await
}

pub async fn ensure_initialized_with_pool(pool: &PgPool) -> Result<CweCatalogSyncSummary> {
    let seed = load_bundled_seed()?;
    let seed_sha256 = bundled_seed_sha256();
    let reviewed_at = parse_timestamp(&seed.reviewed_at)?;
    let existing = load_existing_rows(pool).await?;

    let mut inserted = 0;
    let mut updated = 0;
    let mut skipped = 0;
    let mut active_ids = Vec::with_capacity(seed.entries.len());

    for entry in &seed.entries {
        let current = existing.get(&entry.id);
        if should_skip_existing_row(current, entry, &seed, &seed_sha256, reviewed_at) {
            skipped += 1;
        } else {
            upsert_seed_entry(pool, entry, &seed, &seed_sha256, reviewed_at).await?;
            if current.is_some() {
                updated += 1;
            } else {
                inserted += 1;
            }
        }
        active_ids.push(entry.id.clone());
    }

    let deactivated = deactivate_missing_rows(pool, &active_ids).await?;
    let active_total = active_row_count(pool).await?;

    Ok(CweCatalogSyncSummary {
        discovered: seed.entries.len(),
        inserted,
        updated,
        skipped,
        deactivated,
        active_total,
    })
}

pub async fn list_active_entries(
    pool: &PgPool,
    params: CweCatalogListParams,
) -> Result<CweCatalogListResult> {
    let limit = params
        .limit
        .unwrap_or(DEFAULT_LIST_LIMIT)
        .min(MAX_LIST_LIMIT);
    let offset = params.offset.unwrap_or(0);
    let keyword = params.keyword.unwrap_or_default().trim().to_string();

    let (total, rows) = if keyword.is_empty() {
        let total = sqlx::query_scalar::<_, i64>(
            "select count(*) from rust_cwe_catalog where is_active = true",
        )
        .fetch_one(pool)
        .await?;
        let rows = sqlx::query(
            r#"
            select cwe_id, numeric_id, name_en_official, name_en_short, name_zh,
                   source_version, source_date, source_sha256, translation_source,
                   translation_reviewed_at
            from rust_cwe_catalog
            where is_active = true
            order by numeric_id asc
            limit $1 offset $2
            "#,
        )
        .bind(limit as i64)
        .bind(offset as i64)
        .fetch_all(pool)
        .await?;
        (total as usize, rows)
    } else {
        let pattern = format!("%{keyword}%");
        let total = sqlx::query_scalar::<_, i64>(
            r#"
            select count(*)
            from rust_cwe_catalog
            where is_active = true
              and (
                cwe_id ilike $1
                or numeric_id::text ilike $1
                or name_en_official ilike $1
                or name_en_short ilike $1
                or name_zh ilike $1
              )
            "#,
        )
        .bind(&pattern)
        .fetch_one(pool)
        .await?;
        let rows = sqlx::query(
            r#"
            select cwe_id, numeric_id, name_en_official, name_en_short, name_zh,
                   source_version, source_date, source_sha256, translation_source,
                   translation_reviewed_at
            from rust_cwe_catalog
            where is_active = true
              and (
                cwe_id ilike $1
                or numeric_id::text ilike $1
                or name_en_official ilike $1
                or name_en_short ilike $1
                or name_zh ilike $1
              )
            order by numeric_id asc
            limit $2 offset $3
            "#,
        )
        .bind(&pattern)
        .bind(limit as i64)
        .bind(offset as i64)
        .fetch_all(pool)
        .await?;
        (total as usize, rows)
    };

    let entries = rows
        .into_iter()
        .map(map_catalog_row)
        .collect::<Result<Vec<_>>>()?;
    let metadata_entry = if entries.is_empty() {
        load_first_active_entry(pool).await?
    } else {
        entries.first().cloned()
    };

    Ok(CweCatalogListResult {
        entries,
        total,
        limit,
        offset,
        source_version: metadata_entry
            .as_ref()
            .map(|entry| entry.source_version.clone()),
        source_date: metadata_entry
            .as_ref()
            .map(|entry| entry.source_date.clone()),
        source_sha256: metadata_entry
            .as_ref()
            .map(|entry| entry.source_sha256.clone()),
        translation_source: metadata_entry
            .as_ref()
            .map(|entry| entry.translation_source.clone()),
        translation_reviewed_at: metadata_entry
            .as_ref()
            .map(|entry| entry.translation_reviewed_at.clone()),
    })
}

pub async fn lookup_active_entry(pool: &PgPool, cwe_id: &str) -> Result<Option<CweCatalogEntry>> {
    let Some(canonical) = normalize_cwe_id(cwe_id) else {
        return Ok(None);
    };
    let row = sqlx::query(
        r#"
        select cwe_id, numeric_id, name_en_official, name_en_short, name_zh,
               source_version, source_date, source_sha256, translation_source,
               translation_reviewed_at
        from rust_cwe_catalog
        where cwe_id = $1 and is_active = true
        "#,
    )
    .bind(canonical)
    .fetch_optional(pool)
    .await?;
    row.map(map_catalog_row).transpose()
}

pub fn normalize_cwe_id(value: &str) -> Option<String> {
    let trimmed = value.trim();
    if trimmed.is_empty() {
        return None;
    }
    let upper = trimmed.to_ascii_uppercase().replace(['_', ':', ' '], "-");
    let numeric = upper.strip_prefix("CWE-").unwrap_or(upper.as_str());
    if numeric.is_empty() || !numeric.chars().all(|ch| ch.is_ascii_digit()) {
        return None;
    }
    let id = numeric.parse::<i32>().ok()?;
    if id <= 0 {
        return None;
    }
    Some(format!("CWE-{id}"))
}

pub fn load_bundled_seed() -> Result<CweCatalogSeed> {
    let seed: CweCatalogSeed = serde_json::from_str(BUNDLED_CWE_CATALOG_JSON)
        .context("failed to parse bundled CWE catalog seed")?;
    validate_seed(&seed)?;
    validate_review_artifact(&seed, &bundled_seed_sha256())?;
    Ok(seed)
}

pub fn bundled_seed_sha256() -> String {
    sha256_hex(BUNDLED_CWE_CATALOG_JSON.as_bytes())
}

fn validate_seed(seed: &CweCatalogSeed) -> Result<()> {
    validate_seed_with_expected_count(seed, EXPECTED_WEAKNESS_COUNT)
}

fn validate_seed_with_expected_count(seed: &CweCatalogSeed, expected_count: usize) -> Result<()> {
    if seed.content_version != EXPECTED_CONTENT_VERSION {
        bail!("unexpected CWE contentVersion: {}", seed.content_version);
    }
    if seed.content_date != EXPECTED_CONTENT_DATE {
        bail!("unexpected CWE contentDate: {}", seed.content_date);
    }
    if seed.translation_source != TRANSLATION_SOURCE {
        bail!(
            "unexpected CWE translationSource: {}",
            seed.translation_source
        );
    }
    if seed.entry_count != expected_count || seed.entries.len() != expected_count {
        bail!(
            "CWE seed count mismatch: entryCount={} entries={} expected={expected_count}",
            seed.entry_count,
            seed.entries.len()
        );
    }
    parse_timestamp(&seed.reviewed_at)
        .with_context(|| format!("invalid CWE reviewedAt: {}", seed.reviewed_at))?;

    let mut ids = BTreeSet::new();
    let mut numeric_ids = BTreeSet::new();
    for entry in &seed.entries {
        let canonical =
            normalize_cwe_id(&entry.id).ok_or_else(|| anyhow!("malformed CWE id: {}", entry.id))?;
        if canonical != entry.id {
            bail!("non-canonical CWE id: {}", entry.id);
        }
        let expected_numeric = entry
            .id
            .trim_start_matches("CWE-")
            .parse::<i32>()
            .with_context(|| format!("invalid numeric suffix for {}", entry.id))?;
        if entry.numeric_id != expected_numeric {
            bail!(
                "numericId mismatch for {}: {} != {}",
                entry.id,
                entry.numeric_id,
                expected_numeric
            );
        }
        if !ids.insert(entry.id.clone()) {
            bail!("duplicate CWE id: {}", entry.id);
        }
        if !numeric_ids.insert(entry.numeric_id) {
            bail!("duplicate CWE numericId: {}", entry.numeric_id);
        }
        if entry.name_en_official.trim().is_empty() {
            bail!("{} blank nameEnOfficial", entry.id);
        }
        if entry.name_en_short.trim().is_empty() {
            bail!("{} blank nameEnShort", entry.id);
        }
        if entry.name_zh.trim().is_empty() {
            bail!("{} blank nameZh", entry.id);
        }
        if !contains_cjk(&entry.name_zh) {
            bail!(
                "{} nameZh lacks Chinese characters: {}",
                entry.id,
                entry.name_zh
            );
        }
        let suspicious = suspicious_untranslated_tokens(&entry.name_zh);
        if !suspicious.is_empty() {
            bail!(
                "{} suspicious untranslated tokens {:?} in {}",
                entry.id,
                suspicious,
                entry.name_zh
            );
        }
    }

    let by_id = seed
        .entries
        .iter()
        .map(|entry| (entry.id.as_str(), entry.name_zh.as_str()))
        .collect::<BTreeMap<_, _>>();
    for (cwe_id, expected_zh) in [
        ("CWE-89", "SQL注入"),
        ("CWE-79", "跨站脚本"),
        ("CWE-22", "路径遍历"),
    ] {
        if by_id.get(cwe_id).copied() != Some(expected_zh) {
            bail!("{cwe_id} nameZh must be {expected_zh}");
        }
    }

    Ok(())
}

fn validate_review_artifact(seed: &CweCatalogSeed, seed_sha256: &str) -> Result<()> {
    if !BUNDLED_CWE_CATALOG_REVIEW.contains(seed_sha256) {
        bail!("CWE review artifact does not contain current seed SHA-256");
    }
    if !BUNDLED_CWE_CATALOG_REVIEW.contains(&format!("Reviewed at: {}", seed.reviewed_at)) {
        bail!("CWE review artifact does not contain seed reviewedAt");
    }
    if !BUNDLED_CWE_CATALOG_REVIEW.contains("Retained English-token allowlist") {
        bail!("CWE review artifact missing retained English-token allowlist");
    }
    Ok(())
}

fn should_skip_existing_row(
    current: Option<&ExistingCatalogRow>,
    entry: &CweCatalogSeedEntry,
    seed: &CweCatalogSeed,
    seed_sha256: &str,
    reviewed_at: OffsetDateTime,
) -> bool {
    let Some(current) = current else {
        return false;
    };
    current.is_active
        && current.numeric_id == entry.numeric_id
        && current.name_en_official == entry.name_en_official
        && current.name_en_short == entry.name_en_short
        && !current.name_zh.trim().is_empty()
        && current.source_version == seed.content_version
        && current.source_date == seed.content_date
        && current.source_sha256 == seed_sha256
        && current.translation_source == seed.translation_source
        && current.translation_reviewed_at == reviewed_at
}

async fn load_existing_rows(pool: &PgPool) -> Result<BTreeMap<String, ExistingCatalogRow>> {
    let rows = sqlx::query(
        r#"
        select cwe_id, numeric_id, name_en_official, name_en_short, name_zh, source_version, source_date,
               source_sha256, translation_source, translation_reviewed_at, is_active
        from rust_cwe_catalog
        "#,
    )
    .fetch_all(pool)
    .await?;

    rows.into_iter()
        .map(|row| {
            let cwe_id: String = row.try_get("cwe_id")?;
            Ok((
                cwe_id,
                ExistingCatalogRow {
                    numeric_id: row.try_get("numeric_id")?,
                    name_en_official: row.try_get("name_en_official")?,
                    name_en_short: row.try_get("name_en_short")?,
                    name_zh: row.try_get("name_zh")?,
                    source_version: row.try_get("source_version")?,
                    source_date: row.try_get("source_date")?,
                    source_sha256: row.try_get("source_sha256")?,
                    translation_source: row.try_get("translation_source")?,
                    translation_reviewed_at: row.try_get("translation_reviewed_at")?,
                    is_active: row.try_get("is_active")?,
                },
            ))
        })
        .collect()
}

async fn upsert_seed_entry(
    pool: &PgPool,
    entry: &CweCatalogSeedEntry,
    seed: &CweCatalogSeed,
    seed_sha256: &str,
    reviewed_at: OffsetDateTime,
) -> Result<()> {
    sqlx::query(
        r#"
        insert into rust_cwe_catalog (
            cwe_id, numeric_id, name_en_official, name_en_short, name_zh,
            source_version, source_date, source_sha256, translation_source,
            translation_reviewed_at, is_active
        )
        values ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, true)
        on conflict (cwe_id) do update
        set
            numeric_id = excluded.numeric_id,
            name_en_official = excluded.name_en_official,
            name_en_short = excluded.name_en_short,
            -- Preserve any existing nonblank Chinese name per v1 product policy.
            -- v1 has no write/admin provenance yet, so DB-held nonblank names are treated as curated overrides.
            name_zh = case
                when length(trim(rust_cwe_catalog.name_zh)) > 0 then rust_cwe_catalog.name_zh
                else excluded.name_zh
            end,
            source_version = excluded.source_version,
            source_date = excluded.source_date,
            source_sha256 = excluded.source_sha256,
            translation_source = excluded.translation_source,
            translation_reviewed_at = excluded.translation_reviewed_at,
            is_active = true,
            updated_at = now()
        "#,
    )
    .bind(&entry.id)
    .bind(entry.numeric_id)
    .bind(&entry.name_en_official)
    .bind(&entry.name_en_short)
    .bind(&entry.name_zh)
    .bind(&seed.content_version)
    .bind(&seed.content_date)
    .bind(seed_sha256)
    .bind(&seed.translation_source)
    .bind(reviewed_at)
    .execute(pool)
    .await?;
    Ok(())
}

async fn deactivate_missing_rows(pool: &PgPool, active_ids: &[String]) -> Result<usize> {
    let result = sqlx::query(
        r#"
        update rust_cwe_catalog
        set is_active = false, updated_at = now()
        where is_active = true
          and not (cwe_id = any($1))
        "#,
    )
    .bind(active_ids)
    .execute(pool)
    .await?;
    Ok(result.rows_affected() as usize)
}

async fn active_row_count(pool: &PgPool) -> Result<usize> {
    let count = sqlx::query_scalar::<_, i64>(
        "select count(*) from rust_cwe_catalog where is_active = true",
    )
    .fetch_one(pool)
    .await?;
    Ok(count as usize)
}

async fn load_first_active_entry(pool: &PgPool) -> Result<Option<CweCatalogEntry>> {
    let row = sqlx::query(
        r#"
        select cwe_id, numeric_id, name_en_official, name_en_short, name_zh,
               source_version, source_date, source_sha256, translation_source,
               translation_reviewed_at
        from rust_cwe_catalog
        where is_active = true
        order by numeric_id asc
        limit 1
        "#,
    )
    .fetch_optional(pool)
    .await?;
    row.map(map_catalog_row).transpose()
}

fn map_catalog_row(row: PgRow) -> Result<CweCatalogEntry> {
    let reviewed_at: OffsetDateTime = row.try_get("translation_reviewed_at")?;
    Ok(CweCatalogEntry {
        id: row.try_get("cwe_id")?,
        numeric_id: row.try_get("numeric_id")?,
        name_en_official: row.try_get("name_en_official")?,
        name_en_short: row.try_get("name_en_short")?,
        name_zh: row.try_get("name_zh")?,
        source_version: row.try_get("source_version")?,
        source_date: row.try_get("source_date")?,
        source_sha256: row.try_get("source_sha256")?,
        translation_source: row.try_get("translation_source")?,
        translation_reviewed_at: format_timestamp(reviewed_at),
    })
}

fn parse_timestamp(value: &str) -> Result<OffsetDateTime> {
    OffsetDateTime::parse(value, &Rfc3339).with_context(|| format!("invalid timestamp: {value}"))
}

fn format_timestamp(value: OffsetDateTime) -> String {
    value
        .format(&Rfc3339)
        .unwrap_or_else(|_| value.unix_timestamp().to_string())
}

fn sha256_hex(bytes: &[u8]) -> String {
    let mut hasher = Sha256::new();
    hasher.update(bytes);
    hex::encode_lower(hasher.finalize())
}

fn contains_cjk(value: &str) -> bool {
    value
        .chars()
        .any(|ch| ('\u{4e00}'..='\u{9fff}').contains(&ch))
}

fn suspicious_untranslated_tokens(value: &str) -> Vec<String> {
    const SUSPICIOUS: &[&str] = &[
        "Improper",
        "Neutralization",
        "Special",
        "Elements",
        "Missing",
        "Insufficient",
        "Incorrect",
        "Incorrectly",
        "Uncontrolled",
        "Unchecked",
        "Untrusted",
        "Unauthorized",
        "Exposure",
        "Observable",
        "Generation",
        "Validation",
        "Restriction",
        "Privilege",
        "Privileges",
        "Authentication",
        "Authorization",
    ];
    let suspicious = SUSPICIOUS.iter().copied().collect::<BTreeSet<_>>();
    ascii_word_tokens(value)
        .into_iter()
        .filter(|token| suspicious.contains(token.as_str()))
        .collect()
}

fn ascii_word_tokens(value: &str) -> Vec<String> {
    let mut tokens = Vec::new();
    let mut current = String::new();
    for ch in value.chars() {
        if ch.is_ascii_alphabetic() {
            current.push(ch);
        } else if !current.is_empty() {
            tokens.push(std::mem::take(&mut current));
        }
    }
    if !current.is_empty() {
        tokens.push(current);
    }
    tokens
}

#[cfg(test)]
mod tests {
    use super::{
        bundled_seed_sha256, load_bundled_seed, normalize_cwe_id, suspicious_untranslated_tokens,
        validate_seed_with_expected_count, CweCatalogSeed, CweCatalogSeedEntry,
        BUNDLED_CWE_CATALOG_REVIEW, EXPECTED_CONTENT_DATE, EXPECTED_CONTENT_VERSION,
        EXPECTED_WEAKNESS_COUNT, TRANSLATION_SOURCE,
    };

    fn seed_with_entries(entries: Vec<CweCatalogSeedEntry>) -> CweCatalogSeed {
        CweCatalogSeed {
            content_version: EXPECTED_CONTENT_VERSION.to_string(),
            content_date: EXPECTED_CONTENT_DATE.to_string(),
            generated_at: "2026-05-28T10:58:05Z".to_string(),
            reviewed_at: "2026-05-28T10:58:05Z".to_string(),
            source: "test".to_string(),
            translation_source: TRANSLATION_SOURCE.to_string(),
            entry_count: entries.len(),
            entries,
        }
    }

    fn entry(id: &str, numeric_id: i32, name_zh: &str) -> CweCatalogSeedEntry {
        CweCatalogSeedEntry {
            id: id.to_string(),
            numeric_id,
            name_en_official: format!("Official name for {id}"),
            name_en_short: format!("Short name for {id}"),
            name_zh: name_zh.to_string(),
        }
    }

    #[test]
    fn bundled_seed_contains_expected_v4_20_weakness_entries() {
        let seed = load_bundled_seed().expect("bundled seed should validate");
        assert_eq!(seed.content_version, EXPECTED_CONTENT_VERSION);
        assert_eq!(seed.content_date, EXPECTED_CONTENT_DATE);
        assert_eq!(seed.entry_count, EXPECTED_WEAKNESS_COUNT);
        assert_eq!(seed.entries.len(), EXPECTED_WEAKNESS_COUNT);

        let entry = |id: &str| {
            seed.entries
                .iter()
                .find(|entry| entry.id == id)
                .expect("expected CWE entry")
        };
        assert_eq!(entry("CWE-89").name_zh, "SQL注入");
        assert_eq!(entry("CWE-79").name_zh, "跨站脚本");
        assert_eq!(entry("CWE-22").name_zh, "路径遍历");
    }

    #[test]
    fn bundled_seed_hash_matches_review_artifact() {
        let seed_hash = bundled_seed_sha256();
        assert_eq!(
            seed_hash,
            "59a8abcb37809b3ac6a1b169df149467d322a49f619cddf483b084aefbf23f2b"
        );
        assert!(BUNDLED_CWE_CATALOG_REVIEW.contains(&seed_hash));
        assert!(BUNDLED_CWE_CATALOG_REVIEW.contains("Reviewed at: 2026-05-28T10:58:05Z"));
    }

    #[test]
    fn normalize_cwe_id_accepts_common_forms() {
        assert_eq!(normalize_cwe_id("CWE-89").as_deref(), Some("CWE-89"));
        assert_eq!(normalize_cwe_id("89").as_deref(), Some("CWE-89"));
        assert_eq!(normalize_cwe_id("cwe_89").as_deref(), Some("CWE-89"));
        assert_eq!(normalize_cwe_id("cwe:089").as_deref(), Some("CWE-89"));
        assert_eq!(normalize_cwe_id("CWE-0"), None);
        assert_eq!(normalize_cwe_id("CWE-abc"), None);
    }

    #[test]
    fn seed_validation_rejects_duplicate_ids() {
        let seed = seed_with_entries(vec![
            entry("CWE-89", 89, "SQL注入"),
            entry("CWE-89", 89, "SQL注入"),
        ]);
        let error = validate_seed_with_expected_count(&seed, 2)
            .unwrap_err()
            .to_string();
        assert!(error.contains("duplicate CWE id") || error.contains("duplicate CWE numericId"));
    }

    #[test]
    fn seed_validation_rejects_malformed_id() {
        let seed = seed_with_entries(vec![entry("CWE-abc", 89, "SQL注入")]);
        let error = validate_seed_with_expected_count(&seed, 1)
            .unwrap_err()
            .to_string();
        assert!(error.contains("malformed CWE id"));
    }

    #[test]
    fn seed_validation_rejects_mismatched_numeric_id() {
        let seed = seed_with_entries(vec![entry("CWE-89", 90, "SQL注入")]);
        let error = validate_seed_with_expected_count(&seed, 1)
            .unwrap_err()
            .to_string();
        assert!(error.contains("numericId mismatch"));
    }

    #[test]
    fn seed_validation_rejects_blank_chinese_name() {
        let seed = seed_with_entries(vec![entry("CWE-89", 89, "")]);
        let error = validate_seed_with_expected_count(&seed, 1)
            .unwrap_err()
            .to_string();
        assert!(error.contains("blank nameZh"));
    }

    #[test]
    fn seed_validation_rejects_suspicious_untranslated_fragments() {
        let seed = seed_with_entries(vec![entry(
            "CWE-89",
            89,
            "Improper Neutralization 的 Special Elements",
        )]);
        let error = validate_seed_with_expected_count(&seed, 1)
            .unwrap_err()
            .to_string();
        assert!(error.contains("suspicious untranslated tokens"));
        assert!(suspicious_untranslated_tokens("Missing 加密").contains(&"Missing".to_string()));
    }
}
