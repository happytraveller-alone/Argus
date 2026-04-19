pub mod git;
pub mod patch;

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct RuleSummary {
    pub id: String,
    pub message: String,
    pub severity: String,
    pub languages: Vec<String>,
    pub has_pattern: bool,
}

impl RuleSummary {
    pub fn primary_language(&self) -> &str {
        self.languages
            .first()
            .map(String::as_str)
            .unwrap_or("generic")
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct NormalizedRule {
    pub pattern_yaml: String,
    pub summary: RuleSummary,
}

pub fn normalize_and_validate_rule_yaml(raw: &str) -> Result<NormalizedRule, String> {
    let normalized = normalize_rule_yaml(raw)?;
    validate_yaml_subset(&normalized)?;
    let summary = extract_first_rule_summary(&normalized)?;
    validate_rule_summary(&summary)?;
    Ok(NormalizedRule {
        pattern_yaml: normalized,
        summary,
    })
}

fn normalize_rule_yaml(raw: &str) -> Result<String, String> {
    let stripped = strip_code_fences_and_markers(raw);
    if stripped.trim().is_empty() {
        return Err("规则YAML不能为空".to_string());
    }

    let first_non_empty = stripped
        .lines()
        .find(|line| !line.trim().is_empty())
        .map(|line| strip_inline_comment(line.trim()))
        .unwrap_or_default();

    let normalized = if first_non_empty == "rules:" || first_non_empty.starts_with("rules: ") {
        stripped
    } else if first_non_empty.starts_with("- ") {
        format!("rules:\n{}", indent_block(&stripped, "  "))
    } else {
        wrap_single_rule_mapping(&stripped)
    };

    Ok(normalized.trim().to_string())
}

fn strip_code_fences_and_markers(raw: &str) -> String {
    let mut lines = raw
        .lines()
        .map(|line| line.trim_end().to_string())
        .collect::<Vec<_>>();

    while lines.first().is_some_and(|line| line.trim().is_empty()) {
        lines.remove(0);
    }
    while lines.last().is_some_and(|line| line.trim().is_empty()) {
        lines.pop();
    }

    if lines
        .first()
        .is_some_and(|line| line.trim_start().starts_with("```"))
    {
        lines.remove(0);
        while lines.last().is_some_and(|line| line.trim().is_empty()) {
            lines.pop();
        }
        if lines
            .last()
            .is_some_and(|line| line.trim_start().starts_with("```"))
        {
            lines.pop();
        }
    }

    lines
        .into_iter()
        .filter(|line| {
            let trimmed = line.trim();
            trimmed != "---" && trimmed != "..."
        })
        .collect::<Vec<_>>()
        .join("\n")
}

fn indent_block(block: &str, prefix: &str) -> String {
    block
        .lines()
        .map(|line| {
            if line.trim().is_empty() {
                String::new()
            } else {
                format!("{prefix}{line}")
            }
        })
        .collect::<Vec<_>>()
        .join("\n")
}

fn wrap_single_rule_mapping(block: &str) -> String {
    let lines = block.lines().collect::<Vec<_>>();
    let min_indent = lines
        .iter()
        .filter(|line| !line.trim().is_empty())
        .map(|line| leading_spaces(line))
        .min()
        .unwrap_or(0);

    let mut wrapped = vec!["rules:".to_string()];
    let mut wrote_first = false;
    for line in lines {
        if line.trim().is_empty() {
            continue;
        }
        let trimmed = &line[min_indent.min(line.len())..];
        if !wrote_first {
            wrapped.push(format!("  - {}", trimmed.trim_start()));
            wrote_first = true;
        } else {
            wrapped.push(format!("    {trimmed}"));
        }
    }

    wrapped.join("\n")
}

fn extract_first_rule_summary(normalized: &str) -> Result<RuleSummary, String> {
    let mut in_rules = false;
    let mut saw_rule = false;
    let mut rule_indent = 0usize;
    let mut direct_key_indent = 0usize;
    let mut languages_indent = None::<usize>;
    let mut block_scalar_indent = None::<usize>;
    let mut summary = RuleSummary {
        id: String::new(),
        message: String::new(),
        severity: String::new(),
        languages: Vec::new(),
        has_pattern: false,
    };

    for line in normalized.lines() {
        let trimmed = strip_inline_comment(line.trim());
        if trimmed.is_empty() {
            continue;
        }

        let indent = leading_spaces(line);
        if !in_rules {
            if trimmed == "rules:" || trimmed.starts_with("rules: ") {
                in_rules = true;
            }
            continue;
        }

        if !saw_rule {
            if trimmed.starts_with("- ") {
                saw_rule = true;
                rule_indent = indent;
                direct_key_indent = rule_indent + 2;
                block_scalar_indent = parse_rule_line(
                    trimmed.trim_start_matches("- ").trim_start(),
                    indent,
                    &mut languages_indent,
                    &mut summary,
                );
            }
            continue;
        }

        if indent <= rule_indent && trimmed.starts_with("- ") {
            break;
        }

        if let Some(base_indent) = block_scalar_indent {
            if indent > base_indent {
                continue;
            }
            block_scalar_indent = None;
        }

        if let Some(list_indent) = languages_indent {
            if indent > list_indent && trimmed.starts_with("- ") {
                let language = clean_scalar(strip_inline_comment(
                    trimmed.trim_start_matches("- ").trim(),
                ));
                if !language.is_empty() {
                    summary.languages.push(language);
                }
                continue;
            }
            if indent <= list_indent {
                languages_indent = None;
            }
        }

        if indent > direct_key_indent {
            continue;
        }

        block_scalar_indent = parse_rule_line(trimmed, indent, &mut languages_indent, &mut summary);
    }

    if !saw_rule {
        return Err("规则中未找到有效的 rules 列表".to_string());
    }

    Ok(summary)
}

fn validate_yaml_subset(normalized: &str) -> Result<(), String> {
    let mut saw_rules = false;
    let mut saw_rule_item = false;
    let mut block_scalar_indent = None::<usize>;

    for line in normalized.lines() {
        let trimmed = strip_inline_comment(line.trim());
        if trimmed.is_empty() || trimmed.starts_with('#') {
            continue;
        }

        let indent = leading_spaces(line);
        if let Some(base_indent) = block_scalar_indent {
            if indent > base_indent {
                continue;
            }
            block_scalar_indent = None;
        }

        if !saw_rules {
            if trimmed == "rules:" || trimmed == "rules: []" {
                saw_rules = true;
                continue;
            }
            return Err("规则YAML解析失败".to_string());
        }

        if trimmed.starts_with("- ") {
            saw_rule_item = true;
            let item = trimmed.trim_start_matches("- ").trim();
            if item.is_empty() {
                return Err("规则YAML解析失败".to_string());
            }
            if let Some((key, value)) = item.split_once(':') {
                validate_mapping_line(key, value)?;
                if is_block_scalar(value) {
                    block_scalar_indent = Some(indent);
                }
            }
            continue;
        }

        let Some((key, value)) = trimmed.split_once(':') else {
            return Err("规则YAML解析失败".to_string());
        };
        validate_mapping_line(key, value)?;
        if is_block_scalar(value) {
            block_scalar_indent = Some(indent);
        }
    }

    if !saw_rule_item {
        return Err("规则中未找到有效的 rules 列表".to_string());
    }

    Ok(())
}

fn validate_mapping_line(key: &str, value: &str) -> Result<(), String> {
    if key.trim().is_empty() {
        return Err("规则YAML解析失败".to_string());
    }

    let trimmed_value = strip_inline_comment(value.trim());
    if trimmed_value.starts_with('[') != trimmed_value.ends_with(']') {
        return Err("规则YAML解析失败".to_string());
    }

    Ok(())
}

fn is_block_scalar(value: &str) -> bool {
    matches!(value.trim(), "|" | "|-" | "|+" | ">" | ">-" | ">+")
}

fn strip_inline_comment(value: &str) -> &str {
    let mut in_single_quote = false;
    let mut in_double_quote = false;
    let mut previous = '\0';

    for (idx, ch) in value.char_indices() {
        match ch {
            '\'' if !in_double_quote && previous != '\\' => in_single_quote = !in_single_quote,
            '"' if !in_single_quote && previous != '\\' => in_double_quote = !in_double_quote,
            '#' if !in_single_quote && !in_double_quote => {
                let prefix = &value[..idx];
                if prefix.ends_with(char::is_whitespace) || prefix.is_empty() {
                    return prefix.trim_end();
                }
            }
            _ => {}
        }
        previous = ch;
    }

    value
}

fn parse_rule_line(
    line: &str,
    indent: usize,
    languages_indent: &mut Option<usize>,
    summary: &mut RuleSummary,
) -> Option<usize> {
    let Some((key, raw_value)) = line.split_once(':') else {
        return None;
    };

    let key = key.trim();
    let value = strip_inline_comment(raw_value.trim());
    match key {
        "id" => summary.id = clean_scalar(value),
        "message" => summary.message = clean_scalar(value),
        "severity" => summary.severity = clean_scalar(value).to_uppercase(),
        "languages" => {
            if value.starts_with('[') && value.ends_with(']') {
                summary.languages = parse_inline_list(value);
                *languages_indent = None;
            } else if value.is_empty() {
                *languages_indent = Some(indent);
            } else {
                let language = clean_scalar(value);
                if !language.is_empty() {
                    summary.languages = vec![language];
                }
                *languages_indent = None;
            }
        }
        "pattern" | "patterns" | "pattern-either" | "pattern-regex" => {
            summary.has_pattern = true;
        }
        _ => {}
    }

    if is_block_scalar(value) {
        return Some(indent);
    }

    None
}

fn parse_inline_list(value: &str) -> Vec<String> {
    value
        .trim()
        .trim_start_matches('[')
        .trim_end_matches(']')
        .split(',')
        .map(clean_scalar)
        .filter(|item| !item.is_empty())
        .collect()
}

fn clean_scalar(value: &str) -> String {
    value
        .trim()
        .trim_matches('"')
        .trim_matches('\'')
        .trim()
        .to_string()
}

fn validate_rule_summary(summary: &RuleSummary) -> Result<(), String> {
    let mut missing = Vec::new();
    if summary.id.is_empty() {
        missing.push("id");
    }
    if summary.message.is_empty() {
        missing.push("message");
    }
    if summary.severity.is_empty() {
        missing.push("severity");
    }
    if summary.languages.is_empty() {
        missing.push("languages");
    }
    if !missing.is_empty() {
        return Err(format!("缺少必填字段: {}", missing.join(", ")));
    }

    if !summary.has_pattern {
        return Err("缺少模式字段: pattern/patterns/pattern-either/pattern-regex".to_string());
    }

    if !matches!(summary.severity.as_str(), "ERROR" | "WARNING" | "INFO") {
        return Err("严重程度必须为: ERROR, WARNING, INFO".to_string());
    }

    if !is_valid_rule_id(&summary.id) {
        return Err("规则ID只能包含小写字母、数字、-、_、.".to_string());
    }

    if summary
        .languages
        .iter()
        .any(|language| language.trim().is_empty())
    {
        return Err("languages 必须为非空列表".to_string());
    }

    Ok(())
}

fn is_valid_rule_id(rule_id: &str) -> bool {
    !rule_id.is_empty()
        && rule_id.chars().all(|ch| {
            ch.is_ascii_lowercase() || ch.is_ascii_digit() || matches!(ch, '-' | '_' | '.')
        })
}

fn leading_spaces(line: &str) -> usize {
    line.chars().take_while(|ch| *ch == ' ').count()
}

#[cfg(test)]
mod tests {
    use super::normalize_and_validate_rule_yaml;

    const TOP_LEVEL_LIST_RULE_YAML: &str = r#"
- id: demo-rule-with-dash
  message: Detect demo usage
  severity: ERROR
  languages:
    - generic
  pattern: demo($X)
"#;

    const WRAPPED_RULE_YAML: &str = r#"
rules:
  - id: function-use-after-free
    message: Detect use-after-free
    severity: WARNING
    languages:
      - c
    pattern: free($X)
"#;

    #[test]
    fn accepts_top_level_list_rules() {
        let result = normalize_and_validate_rule_yaml(TOP_LEVEL_LIST_RULE_YAML)
            .expect("top-level list should normalize");

        assert_eq!(result.summary.id, "demo-rule-with-dash");
        assert_eq!(result.summary.severity, "ERROR");
        assert_eq!(result.summary.languages, vec!["generic".to_string()]);
        assert!(result.pattern_yaml.starts_with("rules:\n  - id:"));
    }

    #[test]
    fn accepts_wrapped_rule_with_hyphenated_identifier() {
        let result =
            normalize_and_validate_rule_yaml(WRAPPED_RULE_YAML).expect("wrapped rule is valid");

        assert_eq!(result.summary.id, "function-use-after-free");
        assert_eq!(result.summary.severity, "WARNING");
        assert_eq!(result.summary.languages, vec!["c".to_string()]);
    }

    #[test]
    fn rejects_rule_without_pattern_field() {
        let error = normalize_and_validate_rule_yaml(
            r#"
rules:
  - id: demo-rule
    message: Missing pattern
    severity: ERROR
    languages: [python]
"#,
        )
        .expect_err("missing pattern should fail");

        assert_eq!(
            error,
            "缺少模式字段: pattern/patterns/pattern-either/pattern-regex"
        );
    }

    #[test]
    fn rejects_malformed_yaml_before_schema_validation() {
        let error = normalize_and_validate_rule_yaml(
            r#"
rules:
  - id: malformed-rule
    message: malformed
    severity: ERROR
    languages: [python
    : bad
    pattern: dangerous_call($X)
"#,
        )
        .expect_err("malformed yaml should fail");

        assert_eq!(error, "规则YAML解析失败");
    }

    #[test]
    fn ignores_nested_metadata_pattern_keys_when_validating_schema() {
        let error = normalize_and_validate_rule_yaml(
            r#"
rules:
  - id: nested-pattern-only
    message: Missing top-level pattern
    severity: ERROR
    languages: [python]
    metadata:
      pattern: should-not-count
"#,
        )
        .expect_err("nested metadata pattern should not satisfy schema");

        assert_eq!(
            error,
            "缺少模式字段: pattern/patterns/pattern-either/pattern-regex"
        );
    }
}
