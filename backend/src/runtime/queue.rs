use std::collections::{HashSet, VecDeque};

use serde_json::{json, Map, Value};

#[derive(Clone, Debug, Default, Eq, PartialEq)]
pub struct QueueStats {
    pub current_size: usize,
    pub total_enqueued: usize,
    pub total_dequeued: usize,
    pub total_deduplicated: usize,
}

#[derive(Debug, Default)]
pub struct ReconQueue {
    items: VecDeque<Value>,
    seen: HashSet<String>,
    stats: QueueStats,
}

impl ReconQueue {
    pub fn enqueue(&mut self, risk_point: Value) -> bool {
        let fingerprint = recon_fingerprint(&risk_point);
        if !self.seen.insert(fingerprint) {
            self.stats.total_deduplicated += 1;
            return false;
        }

        self.items.push_back(risk_point);
        self.stats.total_enqueued += 1;
        self.stats.current_size = self.items.len();
        true
    }

    pub fn dequeue(&mut self) -> Option<Value> {
        let item = self.items.pop_front();
        if item.is_some() {
            self.stats.total_dequeued += 1;
            self.stats.current_size = self.items.len();
        }
        item
    }

    pub fn peek(&self, limit: usize) -> Vec<Value> {
        self.items.iter().take(limit).cloned().collect()
    }

    pub fn size(&self) -> usize {
        self.items.len()
    }

    pub fn stats(&self) -> QueueStats {
        QueueStats {
            current_size: self.items.len(),
            ..self.stats.clone()
        }
    }

    pub fn contains(&self, risk_point: &Value) -> bool {
        self.seen.contains(&recon_fingerprint(risk_point))
    }

    pub fn clear(&mut self) {
        self.items.clear();
        self.seen.clear();
        self.stats = QueueStats::default();
    }

    pub fn snapshot(&self, key: &str, label: &str, limit: usize) -> Value {
        build_snapshot(key, label, self.size(), self.peek(limit))
    }
}

#[derive(Debug, Default)]
pub struct VulnerabilityQueue {
    items: VecDeque<Value>,
    seen: HashSet<String>,
    stats: QueueStats,
}

impl VulnerabilityQueue {
    pub fn enqueue(&mut self, finding: Value) -> bool {
        let fingerprint = vulnerability_fingerprint(&finding);
        if !self.seen.insert(fingerprint) {
            self.stats.total_deduplicated += 1;
            return false;
        }

        self.items.push_back(finding);
        self.stats.total_enqueued += 1;
        self.stats.current_size = self.items.len();
        true
    }

    pub fn peek(&self, limit: usize) -> Vec<Value> {
        self.items.iter().take(limit).cloned().collect()
    }

    pub fn size(&self) -> usize {
        self.items.len()
    }

    pub fn stats(&self) -> QueueStats {
        QueueStats {
            current_size: self.items.len(),
            ..self.stats.clone()
        }
    }

    pub fn contains(&self, finding: &Value) -> bool {
        self.seen.contains(&vulnerability_fingerprint(finding))
    }

    pub fn clear(&mut self) {
        self.items.clear();
        self.seen.clear();
        self.stats = QueueStats::default();
    }

    pub fn snapshot(&self, key: &str, label: &str, limit: usize) -> Value {
        build_snapshot(key, label, self.size(), self.peek(limit))
    }
}

pub fn queue_snapshot(kind: &str, payload: &Value) -> Value {
    match kind {
        "verification" => build_vulnerability_queue_snapshot(payload),
        "business_logic_analysis" => build_recon_queue_snapshot(
            "bl_recon",
            "业务逻辑风险点队列",
            payload
                .get("risk_point")
                .cloned()
                .unwrap_or_else(|| sample_risk_point(kind)),
        ),
        "business_logic_recon" | "business_logic" => {
            build_recon_queue_snapshot("bl_recon", "业务逻辑风险点队列", sample_risk_point(kind))
        }
        "report" => build_recon_queue_snapshot("report", "报告生成队列", sample_risk_point(kind)),
        _ => build_recon_queue_snapshot("recon", "风险点队列", sample_risk_point(kind)),
    }
}

pub fn recon_fingerprint(risk_point: &Value) -> String {
    let components = [
        normalized_string_component(risk_point, "file_path"),
        normalized_line_start_component(risk_point),
        normalized_string_component(risk_point, "vulnerability_type"),
        normalized_string_component(risk_point, "entry_function"),
        normalized_string_component(risk_point, "source"),
        normalized_string_component(risk_point, "sink"),
        normalized_string_component(risk_point, "input_surface"),
        normalized_string_component(risk_point, "trust_boundary"),
        normalized_description_component(risk_point.get("description")),
    ];
    fingerprint_with_fallback(&components, risk_point)
}

pub fn vulnerability_fingerprint(finding: &Value) -> String {
    let components = [
        normalized_string_component(finding, "file_path"),
        normalized_line_start_component(finding),
        normalized_string_component(finding, "vulnerability_type"),
        normalized_string_component(finding, "title"),
    ];
    fingerprint_with_fallback(&components, finding)
}

pub fn build_snapshot(key: &str, label: &str, size: usize, peek: Vec<Value>) -> Value {
    let mut queue = Map::new();
    queue.insert("label".to_string(), Value::String(label.to_string()));
    queue.insert("size".to_string(), json!(size));
    queue.insert("peek".to_string(), Value::Array(peek));

    let mut root = Map::new();
    root.insert(key.to_string(), Value::Object(queue));
    Value::Object(root)
}

fn build_vulnerability_queue_snapshot(payload: &Value) -> Value {
    let findings = payload
        .get("findings")
        .and_then(Value::as_array)
        .cloned()
        .unwrap_or_default();
    build_snapshot("vuln", "漏洞队列", findings.len(), findings)
}

fn build_recon_queue_snapshot(key: &str, label: &str, risk_point: Value) -> Value {
    let mut queue = ReconQueue::default();
    queue.enqueue(risk_point);
    queue.snapshot(key, label, 10)
}

fn fingerprint_with_fallback(components: &[(String, bool)], value: &Value) -> String {
    let mut fingerprint = components
        .iter()
        .map(|(component, _)| component.as_str())
        .collect::<Vec<_>>()
        .join("|");
    if components.iter().any(|(_, missing)| *missing) {
        fingerprint.push_str("|raw=");
        fingerprint.push_str(&compact_payload(value));
    }
    fingerprint
}

fn normalized_string_component(value: &Value, key: &str) -> (String, bool) {
    let normalized = value
        .get(key)
        .and_then(Value::as_str)
        .map(str::trim)
        .unwrap_or_default()
        .to_ascii_lowercase();
    let missing = normalized.is_empty();
    (normalized, missing)
}

fn normalized_description_component(value: Option<&Value>) -> (String, bool) {
    let normalized = value
        .and_then(Value::as_str)
        .unwrap_or_default()
        .split_whitespace()
        .collect::<Vec<_>>()
        .join(" ")
        .trim()
        .to_ascii_lowercase();
    let missing = normalized.is_empty();
    (normalized, missing)
}

fn normalized_line_start_component(value: &Value) -> (String, bool) {
    let parsed = value.get("line_start").and_then(|line| match line {
        Value::Number(number) => number.as_i64(),
        Value::String(text) => text.trim().parse::<i64>().ok(),
        _ => None,
    });
    let missing = parsed.is_none();
    (parsed.unwrap_or_default().to_string(), missing)
}

fn compact_payload(value: &Value) -> String {
    serde_json::to_string(value).unwrap_or_else(|_| "<unserializable>".to_string())
}

fn sample_risk_point(kind: &str) -> Value {
    json!({
        "title": format!("{kind}-candidate"),
        "severity": "medium",
        "description": format!("{kind} queue snapshot from rust backend"),
        "file_path": format!("/agent-test/{kind}.rs"),
        "line_start": 1,
        "vulnerability_type": kind,
        "entry_function": format!("{kind}_entry"),
        "source": "request.payload",
        "sink": "result.stream",
        "input_surface": "http body",
        "trust_boundary": "external input",
    })
}
