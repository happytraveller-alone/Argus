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
        queue_snapshot(key, label, self.size(), self.peek(limit))
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
        queue_snapshot(key, label, self.size(), self.peek(limit))
    }
}

pub fn recon_fingerprint(risk_point: &Value) -> String {
    [
        normalized_string_field(risk_point, "file_path"),
        normalized_line_start(risk_point).to_string(),
        normalized_string_field(risk_point, "vulnerability_type"),
        normalized_string_field(risk_point, "entry_function"),
        normalized_string_field(risk_point, "source"),
        normalized_string_field(risk_point, "sink"),
        normalized_string_field(risk_point, "input_surface"),
        normalized_string_field(risk_point, "trust_boundary"),
        normalized_description(risk_point.get("description")),
    ]
    .join("|")
}

pub fn vulnerability_fingerprint(finding: &Value) -> String {
    [
        normalized_string_field(finding, "file_path"),
        normalized_line_start(finding).to_string(),
        normalized_string_field(finding, "vulnerability_type"),
        normalized_string_field(finding, "title"),
    ]
    .join("|")
}

fn queue_snapshot(key: &str, label: &str, size: usize, peek: Vec<Value>) -> Value {
    let mut queue = Map::new();
    queue.insert("label".to_string(), Value::String(label.to_string()));
    queue.insert("size".to_string(), json!(size));
    queue.insert("peek".to_string(), Value::Array(peek));

    let mut root = Map::new();
    root.insert(key.to_string(), Value::Object(queue));
    Value::Object(root)
}

fn normalized_string_field(value: &Value, key: &str) -> String {
    value
        .get(key)
        .and_then(Value::as_str)
        .unwrap_or_default()
        .trim()
        .to_ascii_lowercase()
}

fn normalized_description(value: Option<&Value>) -> String {
    value
        .and_then(Value::as_str)
        .unwrap_or_default()
        .split_whitespace()
        .collect::<Vec<_>>()
        .join(" ")
        .trim()
        .to_ascii_lowercase()
}

fn normalized_line_start(value: &Value) -> i64 {
    value
        .get("line_start")
        .and_then(|line| match line {
            Value::Number(number) => number.as_i64(),
            Value::String(text) => text.trim().parse::<i64>().ok(),
            _ => None,
        })
        .unwrap_or(0)
}
