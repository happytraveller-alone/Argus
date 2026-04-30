use serde::{Deserialize, Serialize};
use serde_json::{json, Map, Value};
use std::{collections::BTreeMap, fs, path::Path};

const PUSH_FINDING_ALIAS_MAP: &[(&str, &str)] = &[
    ("line", "line_start"),
    ("start_line", "line_start"),
    ("end_line", "line_end"),
    ("type", "vulnerability_type"),
    ("code", "code_snippet"),
    ("snippet", "code_snippet"),
    ("vulnerable_code", "code_snippet"),
    ("recommendation", "suggestion"),
    ("fix_suggestion", "suggestion"),
];

const PUSH_FINDING_LIST_FIELDS: &[&str] = &["evidence_chain", "missing_checks", "taint_flow"];
const PUSH_FINDING_ALLOWED_FIELDS: &[&str] = &[
    "file_path",
    "line_start",
    "line_end",
    "title",
    "description",
    "vulnerability_type",
    "severity",
    "confidence",
    "function_name",
    "code_snippet",
    "source",
    "sink",
    "suggestion",
    "evidence_chain",
    "attacker_flow",
    "missing_checks",
    "taint_flow",
    "finding_metadata",
];
const PUSH_FINDING_ENVELOPE_FIELDS: &[&str] = &["finding", "arguments"];
const PUSH_FINDING_MAX_EXTRA_KEYS: usize = 20;
const PUSH_FINDING_MAX_EXTRA_BYTES: usize = 8 * 1024;

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "kebab-case")]
pub enum FindingPayloadOperation {
    Normalize,
}

impl FindingPayloadOperation {
    pub fn from_cli(raw: &str) -> Result<Self, String> {
        match raw.trim() {
            "normalize" => Ok(Self::Normalize),
            other => Err(format!("unsupported_finding_payload_operation:{other}")),
        }
    }
}

#[derive(Debug, Clone, Deserialize)]
pub struct FindingPayloadRequest {
    #[serde(default)]
    pub payload: Value,
    #[serde(default)]
    pub ordering: BTreeMap<String, Vec<String>>,
}

pub fn execute_from_request_path(operation: FindingPayloadOperation, request_path: &Path) -> Value {
    let request = match fs::read_to_string(request_path) {
        Ok(raw) => match serde_json::from_str::<FindingPayloadRequest>(&raw) {
            Ok(value) => value,
            Err(error) => {
                return json!({
                    "ok": false,
                    "error": format!("invalid_finding_payload_request:{error}"),
                });
            }
        },
        Err(error) => {
            return json!({
                "ok": false,
                "error": format!("read_finding_payload_request_failed:{error}"),
            });
        }
    };

    execute(
        operation,
        json!({"payload": request.payload, "ordering": request.ordering}),
    )
}

pub fn execute(operation: FindingPayloadOperation, payload: Value) -> Value {
    match operation {
        FindingPayloadOperation::Normalize => {
            let payload_object = payload.as_object();
            let request_payload = payload_object
                .and_then(|items| items.get("payload"))
                .cloned()
                .unwrap_or(Value::Object(Map::new()));
            let ordering = payload_object
                .and_then(|items| items.get("ordering"))
                .and_then(parse_ordering_hints);
            let (normalized_payload, repair_map) =
                normalize_push_finding_payload_with_order(&request_payload, ordering.as_ref());
            json!({
                "ok": true,
                "normalized_payload": normalized_payload,
                "repair_map": repair_map,
            })
        }
    }
}

pub fn normalize_push_finding_payload(payload: &Value) -> (Value, BTreeMap<String, String>) {
    normalize_push_finding_payload_with_order(payload, None)
}

fn normalize_push_finding_payload_with_order(
    payload: &Value,
    ordering: Option<&BTreeMap<String, Vec<String>>>,
) -> (Value, BTreeMap<String, String>) {
    let mut normalized = payload.as_object().cloned().unwrap_or_default();
    let mut repair_map: BTreeMap<String, String> = BTreeMap::new();
    let mut normalized_order = ordered_keys_for_path("payload", &normalized, ordering);

    for source_name in ["arguments", "finding"] {
        let nested_payload = normalized
            .get(source_name)
            .and_then(Value::as_object)
            .cloned();
        if let Some(source_payload) = nested_payload.as_ref() {
            merge_payload_fields(
                &mut normalized,
                &mut normalized_order,
                &format!("__envelope.{source_name}"),
                &format!("payload.{source_name}"),
                source_payload,
                &mut repair_map,
                ordering,
            );
        }
    }

    let raw_input_payload = parse_object_payload(normalized.get("raw_input"));
    if let Some(source_payload) = raw_input_payload.as_ref() {
        merge_payload_fields(
            &mut normalized,
            &mut normalized_order,
            "__raw_input",
            "payload.raw_input",
            source_payload,
            &mut repair_map,
            ordering,
        );
        for nested_name in ["arguments", "finding"] {
            let nested_payload = source_payload.get(nested_name).and_then(Value::as_object);
            if let Some(items) = nested_payload {
                merge_payload_fields(
                    &mut normalized,
                    &mut normalized_order,
                    &format!("__raw_input.{nested_name}"),
                    &format!("payload.raw_input.{nested_name}"),
                    items,
                    &mut repair_map,
                    ordering,
                );
            }
        }
    }

    if is_placeholder_payload(&normalized) {
        normalized.retain(|key, _| key.starts_with("__"));
        repair_map.insert("__placeholder_payload".to_string(), "removed".to_string());
        normalized_order.retain(|key| normalized.contains_key(key));
    }

    for (alias_key, target_key) in PUSH_FINDING_ALIAS_MAP {
        let alias_value = normalized.get(*alias_key).cloned();
        let target_value = normalized.get(*target_key).cloned();
        if alias_value
            .as_ref()
            .is_some_and(|value| !is_empty_like(value))
            && target_value.as_ref().is_none_or(is_empty_like)
        {
            normalized.insert(
                (*target_key).to_string(),
                alias_value.unwrap_or(Value::Null),
            );
            repair_map.insert((*alias_key).to_string(), (*target_key).to_string());
            if !normalized_order.iter().any(|key| key == target_key) {
                normalized_order.push((*target_key).to_string());
            }
        }
        if alias_key != target_key {
            normalized.remove(*alias_key);
            normalized_order.retain(|key| key != alias_key);
        }
    }

    let mut metadata_payload =
        parse_object_payload(normalized.get("finding_metadata")).unwrap_or_default();
    let existing_extra = metadata_payload
        .get("extra_tool_input")
        .and_then(Value::as_object)
        .cloned()
        .unwrap_or_default();
    let mut extra_tool_input_entries = ordered_entries_for_path(
        "payload.finding_metadata.extra_tool_input",
        &existing_extra,
        ordering,
    );

    for key_text in normalized_order.clone() {
        if !normalized.contains_key(&key_text) {
            continue;
        }
        if PUSH_FINDING_ALLOWED_FIELDS.contains(&key_text.as_str()) || key_text.starts_with("__") {
            continue;
        }
        if PUSH_FINDING_ENVELOPE_FIELDS.contains(&key_text.as_str()) || key_text == "raw_input" {
            normalized.remove(&key_text);
            continue;
        }
        let Some(value) = normalized.remove(&key_text) else {
            continue;
        };
        if is_empty_like(&value) || is_placeholder_text(&value) {
            continue;
        }
        extra_tool_input_entries.push((key_text.clone(), normalize_extra_value(&value)));
        repair_map.insert(
            format!("__extra.{key_text}"),
            format!("finding_metadata.extra_tool_input.{key_text}"),
        );
    }

    if !extra_tool_input_entries.is_empty() {
        let (limited_extra, truncated) = limit_extra_tool_input(&extra_tool_input_entries);
        if !limited_extra.is_empty() {
            metadata_payload.insert("extra_tool_input".to_string(), Value::Object(limited_extra));
        }
        if truncated {
            metadata_payload.insert("extra_tool_input_truncated".to_string(), Value::Bool(true));
        }
    }

    if metadata_payload.is_empty() {
        normalized.remove("finding_metadata");
    } else {
        normalized.insert(
            "finding_metadata".to_string(),
            Value::Object(metadata_payload),
        );
    }

    for line_key in ["line_start", "line_end"] {
        if let Some(parsed) = coerce_positive_int(normalized.get(line_key)) {
            normalized.insert(line_key.to_string(), Value::from(parsed));
        }
    }

    for list_key in PUSH_FINDING_LIST_FIELDS {
        let normalized_list = normalize_text_list(normalized.get(*list_key));
        if normalized_list.is_empty() {
            normalized.remove(*list_key);
        } else {
            normalized.insert(
                (*list_key).to_string(),
                Value::Array(normalized_list.into_iter().map(Value::String).collect()),
            );
        }
    }

    for cleanup_key in ["finding", "arguments", "raw_input"] {
        normalized.remove(cleanup_key);
    }

    (Value::Object(normalized), repair_map)
}

fn parse_object_payload(raw_value: Option<&Value>) -> Option<Map<String, Value>> {
    match raw_value {
        Some(Value::Object(items)) => Some(items.clone()),
        Some(Value::String(text)) => {
            let trimmed = text.trim();
            if trimmed.is_empty() {
                return None;
            }
            let mut candidates = vec![trimmed.to_string()];
            if let (Some(start), Some(end)) = (trimmed.find('{'), trimmed.rfind('}')) {
                if end > start {
                    candidates.push(trimmed[start..=end].to_string());
                }
            }
            for candidate in candidates {
                if let Ok(Value::Object(items)) = serde_json::from_str::<Value>(&candidate) {
                    return Some(items);
                }
            }
            None
        }
        _ => None,
    }
}

fn normalize_extra_value(value: &Value) -> Value {
    value.clone()
}

fn is_placeholder_text(value: &Value) -> bool {
    let Value::String(text) = value else {
        return false;
    };
    let normalized = text.trim().to_lowercase();
    if normalized.is_empty() {
        return true;
    }
    matches!(
        normalized.as_str(),
        "<value>"
            | "<str>"
            | "<int>"
            | "<float>"
            | "value"
            | "string"
            | "placeholder"
            | "todo"
            | "none"
            | "null"
            | "参数值"
            | "参数名"
    ) || (normalized.starts_with('<') && normalized.ends_with('>'))
}

fn is_placeholder_payload(payload: &Map<String, Value>) -> bool {
    let public_items = payload
        .iter()
        .filter(|(key, _)| !key.starts_with("__"))
        .collect::<Vec<_>>();
    if public_items.is_empty() {
        return false;
    }
    public_items
        .iter()
        .all(|(key, value)| is_placeholder_key(key) || is_placeholder_text(value))
}

fn is_placeholder_key(key: &str) -> bool {
    is_placeholder_text(&Value::String(key.to_string()))
}

fn normalize_text_list(value: Option<&Value>) -> Vec<String> {
    match value {
        Some(Value::Array(items)) => items
            .iter()
            .filter_map(|item| match item {
                Value::String(text) => {
                    let trimmed = text.trim().to_string();
                    if trimmed.is_empty() {
                        None
                    } else {
                        Some(trimmed)
                    }
                }
                other => {
                    let trimmed = other.to_string().trim_matches('"').trim().to_string();
                    if trimmed.is_empty() {
                        None
                    } else {
                        Some(trimmed)
                    }
                }
            })
            .collect(),
        Some(Value::String(text)) => {
            let trimmed = text.trim().to_string();
            if trimmed.is_empty() {
                Vec::new()
            } else {
                vec![trimmed]
            }
        }
        _ => Vec::new(),
    }
}

fn coerce_positive_int(value: Option<&Value>) -> Option<i64> {
    match value {
        Some(Value::Number(number)) => {
            if let Some(parsed) = number.as_i64() {
                (parsed > 0).then_some(parsed)
            } else if let Some(parsed) = number.as_u64() {
                i64::try_from(parsed).ok().filter(|parsed| *parsed > 0)
            } else {
                number
                    .as_f64()
                    .map(|parsed| parsed as i64)
                    .filter(|parsed| *parsed > 0)
            }
        }
        Some(Value::String(text)) => text.trim().parse::<i64>().ok().filter(|parsed| *parsed > 0),
        _ => None,
    }
}

fn merge_payload_fields(
    target: &mut Map<String, Value>,
    target_order: &mut Vec<String>,
    source_name: &str,
    source_path: &str,
    source_payload: &Map<String, Value>,
    repair_map: &mut BTreeMap<String, String>,
    ordering: Option<&BTreeMap<String, Vec<String>>>,
) {
    for source_key in ordered_keys_for_path(source_path, source_payload, ordering) {
        let Some(source_value) = source_payload.get(&source_key) else {
            continue;
        };
        if source_key == "finding" || source_key == "arguments" {
            continue;
        }
        let existing = target.get(source_key.as_str());
        if existing.is_some_and(|value| !is_empty_like(value)) {
            continue;
        }
        target.insert(source_key.clone(), source_value.clone());
        if !target_order.iter().any(|key| key == &source_key) {
            target_order.push(source_key.clone());
        }
        repair_map.insert(format!("{source_name}.{source_key}"), source_key.clone());
    }
}

fn limit_extra_tool_input(extra_payload: &[(String, Value)]) -> (Map<String, Value>, bool) {
    let mut limited = Map::new();
    let mut truncated = false;

    for (index, (key, value)) in extra_payload.iter().enumerate() {
        if index >= PUSH_FINDING_MAX_EXTRA_KEYS {
            truncated = true;
            break;
        }
        let mut candidate = limited.clone();
        candidate.insert(key.clone(), value.clone());
        let encoded = serialize_sorted_map(&candidate);
        if encoded.len() > PUSH_FINDING_MAX_EXTRA_BYTES {
            truncated = true;
            break;
        }
        limited = candidate;
    }

    (limited, truncated)
}

fn serialize_sorted_map(items: &Map<String, Value>) -> Vec<u8> {
    let mut sorted = BTreeMap::new();
    for (key, value) in items {
        sorted.insert(key.clone(), value.clone());
    }
    serde_json::to_vec(&sorted).unwrap_or_default()
}

fn is_empty_like(value: &Value) -> bool {
    match value {
        Value::Null => true,
        Value::String(text) => text.is_empty(),
        Value::Array(items) => items.is_empty(),
        Value::Object(items) => items.is_empty(),
        _ => false,
    }
}

fn parse_ordering_hints(value: &Value) -> Option<BTreeMap<String, Vec<String>>> {
    let items = value.as_object()?;
    let mut ordering = BTreeMap::new();
    for (path, keys) in items {
        let Value::Array(raw_keys) = keys else {
            continue;
        };
        ordering.insert(
            path.clone(),
            raw_keys
                .iter()
                .filter_map(Value::as_str)
                .map(str::to_string)
                .collect(),
        );
    }
    Some(ordering)
}

fn ordered_keys_for_path(
    path: &str,
    items: &Map<String, Value>,
    ordering: Option<&BTreeMap<String, Vec<String>>>,
) -> Vec<String> {
    let mut ordered = Vec::new();
    if let Some(hints) = ordering.and_then(|items| items.get(path)) {
        for key in hints {
            if items.contains_key(key) && !ordered.iter().any(|existing| existing == key) {
                ordered.push(key.clone());
            }
        }
    }
    for key in items.keys() {
        if !ordered.iter().any(|existing| existing == key) {
            ordered.push(key.clone());
        }
    }
    ordered
}

fn ordered_entries_for_path(
    path: &str,
    items: &Map<String, Value>,
    ordering: Option<&BTreeMap<String, Vec<String>>>,
) -> Vec<(String, Value)> {
    ordered_keys_for_path(path, items, ordering)
        .into_iter()
        .filter_map(|key| items.get(&key).cloned().map(|value| (key, value)))
        .collect()
}
