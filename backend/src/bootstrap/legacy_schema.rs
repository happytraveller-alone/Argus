use std::{
    collections::BTreeSet,
    fs,
    path::{Path, PathBuf},
};

use anyhow::{anyhow, Context, Result};

#[derive(Clone, Debug)]
pub(crate) struct LegacySchemaExpectation {
    pub versions_dir: String,
    pub expected_heads: Vec<String>,
    pub error: Option<String>,
}

impl LegacySchemaExpectation {
    pub(crate) fn load_from_repo() -> Self {
        let versions_dir = default_versions_dir();
        let versions_dir_text = versions_dir.display().to_string();
        match resolve_expected_heads_from_versions_dir(&versions_dir) {
            Ok(expected_heads) => Self {
                versions_dir: versions_dir_text,
                expected_heads,
                error: None,
            },
            Err(error) => Self {
                versions_dir: versions_dir_text,
                expected_heads: Vec::new(),
                error: Some(error.to_string()),
            },
        }
    }
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub(crate) struct MigrationIdentity {
    pub revision: String,
    pub down_revisions: Vec<String>,
}

pub(crate) fn default_versions_dir() -> PathBuf {
    Path::new(env!("CARGO_MANIFEST_DIR")).join("../backend_old/alembic/versions")
}

pub(crate) fn resolve_expected_heads_from_versions_dir(versions_dir: &Path) -> Result<Vec<String>> {
    let mut revisions = BTreeSet::new();
    let mut referenced_down_revisions = BTreeSet::new();
    let entries = fs::read_dir(versions_dir).with_context(|| {
        format!(
            "failed to read legacy alembic versions directory: {}",
            versions_dir.display()
        )
    })?;

    for entry in entries {
        let entry = entry.with_context(|| {
            format!(
                "failed to enumerate legacy alembic versions directory: {}",
                versions_dir.display()
            )
        })?;
        let path = entry.path();
        if path.extension().and_then(|ext| ext.to_str()) != Some("py") {
            continue;
        }

        let content = fs::read_to_string(&path).with_context(|| {
            format!(
                "failed to read legacy migration file while resolving heads: {}",
                path.display()
            )
        })?;
        let migration = parse_migration_identity(&content).with_context(|| {
            format!(
                "failed to parse revision/down_revision in migration file: {}",
                path.display()
            )
        })?;
        revisions.insert(migration.revision);
        for down_revision in migration.down_revisions {
            referenced_down_revisions.insert(down_revision);
        }
    }

    if revisions.is_empty() {
        return Err(anyhow!(
            "no legacy migration files found under {}",
            versions_dir.display()
        ));
    }

    let heads: Vec<String> = revisions
        .difference(&referenced_down_revisions)
        .cloned()
        .collect();
    if heads.is_empty() {
        return Err(anyhow!(
            "legacy migration graph has no head revisions under {}",
            versions_dir.display()
        ));
    }
    Ok(heads)
}

pub(crate) fn parse_migration_identity(content: &str) -> Result<MigrationIdentity> {
    let revision_rhs = find_assignment_rhs(content, "revision")
        .ok_or_else(|| anyhow!("missing revision assignment"))?;
    let down_revision_rhs = find_assignment_rhs(content, "down_revision")
        .ok_or_else(|| anyhow!("missing down_revision assignment"))?;

    let revisions = parse_python_string_literals(&revision_rhs);
    if revisions.len() != 1 {
        return Err(anyhow!(
            "revision assignment must contain exactly one string literal"
        ));
    }
    let revision = revisions.into_iter().next().unwrap_or_default();

    let down_revisions = if expression_is_none_literal(&down_revision_rhs) {
        Vec::new()
    } else {
        let parsed = parse_python_string_literals(&down_revision_rhs);
        if parsed.is_empty() {
            return Err(anyhow!(
                "down_revision assignment must contain at least one string literal or None"
            ));
        }
        parsed
    };

    Ok(MigrationIdentity {
        revision,
        down_revisions,
    })
}

fn find_assignment_rhs(content: &str, field: &str) -> Option<String> {
    let lines: Vec<&str> = content.lines().collect();
    for (line_index, raw_line) in lines.iter().enumerate() {
        let Some(rhs_start) = assignment_rhs_start_index(raw_line, field) else {
            continue;
        };

        let mut expression = String::new();
        let mut current_line_index = line_index;
        let mut current_start = rhs_start;
        let mut bracket_depth: i32 = 0;
        let mut in_single_quote = false;
        let mut in_double_quote = false;
        let mut escaped = false;

        loop {
            let current_line = lines[current_line_index];
            let rhs_fragment = &current_line[current_start..];
            if !expression.is_empty() {
                expression.push('\n');
            }
            expression.push_str(rhs_fragment.trim_end());

            let mut trailing_backslash = false;
            for ch in rhs_fragment.chars() {
                if escaped {
                    escaped = false;
                    continue;
                }
                if (in_single_quote || in_double_quote) && ch == '\\' {
                    escaped = true;
                    continue;
                }
                if ch == '\'' && !in_double_quote {
                    in_single_quote = !in_single_quote;
                    continue;
                }
                if ch == '"' && !in_single_quote {
                    in_double_quote = !in_double_quote;
                    continue;
                }
                if in_single_quote || in_double_quote {
                    continue;
                }
                if ch == '#' {
                    break;
                }
                match ch {
                    '(' | '[' | '{' => bracket_depth += 1,
                    ')' | ']' | '}' => bracket_depth -= 1,
                    _ => {}
                }
            }
            if !in_single_quote && !in_double_quote {
                trailing_backslash = rhs_fragment.trim_end().ends_with('\\');
            }

            let should_continue = current_line_index + 1 < lines.len()
                && (in_single_quote || in_double_quote || bracket_depth > 0 || trailing_backslash);
            if !should_continue {
                break;
            }
            current_line_index += 1;
            current_start = 0;
        }

        if !expression.trim().is_empty() {
            return Some(expression.trim().to_string());
        }
    }
    None
}

fn assignment_rhs_start_index(raw_line: &str, field: &str) -> Option<usize> {
    let trimmed = raw_line.trim_start();
    if trimmed.is_empty() || trimmed.starts_with('#') {
        return None;
    }
    if !trimmed.starts_with(field) {
        return None;
    }
    let tail = &trimmed[field.len()..];
    if !(tail.starts_with(':') || tail.starts_with(' ') || tail.starts_with('=')) {
        return None;
    }
    let eq_index = trimmed.find('=')?;
    let leading_ws = raw_line.len() - trimmed.len();
    Some(leading_ws + eq_index + 1)
}

fn expression_is_none_literal(value: &str) -> bool {
    let mut in_single_quote = false;
    let mut in_double_quote = false;
    let mut escaped = false;
    let mut compact = String::new();

    for ch in value.chars() {
        if escaped {
            escaped = false;
            compact.push(ch);
            continue;
        }
        if (in_single_quote || in_double_quote) && ch == '\\' {
            escaped = true;
            compact.push(ch);
            continue;
        }
        if ch == '\'' && !in_double_quote {
            in_single_quote = !in_single_quote;
            compact.push(ch);
            continue;
        }
        if ch == '"' && !in_single_quote {
            in_double_quote = !in_double_quote;
            compact.push(ch);
            continue;
        }
        if !in_single_quote && !in_double_quote && ch == '#' {
            break;
        }
        if !ch.is_whitespace() {
            compact.push(ch);
        }
    }

    let compact = compact.trim_end_matches(',');
    compact == "None"
}

fn parse_python_string_literals(value: &str) -> Vec<String> {
    let mut results = Vec::new();
    let mut chars = value.chars().peekable();
    while let Some(ch) = chars.next() {
        if ch != '"' && ch != '\'' {
            continue;
        }

        let quote = ch;
        let mut parsed = String::new();
        let mut escaped = false;
        while let Some(current) = chars.next() {
            if escaped {
                parsed.push(current);
                escaped = false;
                continue;
            }
            if current == '\\' {
                escaped = true;
                continue;
            }
            if current == quote {
                results.push(parsed);
                break;
            }
            parsed.push(current);
        }
    }
    results
}
