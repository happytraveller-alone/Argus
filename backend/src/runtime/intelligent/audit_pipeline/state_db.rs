use std::path::Path;

use anyhow::{Context, Result};
use rusqlite::{params, Connection};
use serde_json::Value;

pub struct AuditStateDb {
    conn: Connection,
}

fn now_iso() -> String {
    format!(
        "{}",
        std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .unwrap()
            .as_secs()
    )
}

impl AuditStateDb {
    pub fn open(path: &Path) -> Result<Self> {
        let conn = Connection::open(path).context("open sqlite db")?;
        conn.execute_batch(
            "PRAGMA journal_mode=WAL;
             PRAGMA busy_timeout=5000;",
        )?;
        conn.execute_batch(
            "CREATE TABLE IF NOT EXISTS runs (
                run_id TEXT PRIMARY KEY,
                status TEXT,
                started_at TEXT,
                finished_at TEXT
            );
            CREATE TABLE IF NOT EXISTS tasks (
                run_id TEXT,
                task_id TEXT,
                attack_class TEXT,
                subsystem TEXT,
                status TEXT,
                priority INT,
                source TEXT,
                raw_json TEXT,
                PRIMARY KEY (run_id, task_id)
            );
            CREATE TABLE IF NOT EXISTS findings (
                run_id TEXT,
                finding_id TEXT,
                task_id TEXT,
                stage TEXT,
                raw_json TEXT,
                validation_status TEXT,
                group_id TEXT,
                PRIMARY KEY (run_id, finding_id)
            );",
        )?;
        conn.execute_batch(
            "CREATE TABLE IF NOT EXISTS traces (
                run_id TEXT,
                finding_id TEXT,
                reachable INT,
                confidence REAL,
                rationale TEXT,
                PRIMARY KEY (run_id, finding_id)
            );
            CREATE TABLE IF NOT EXISTS costs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT,
                stage TEXT,
                task_id TEXT,
                input_tokens INT,
                output_tokens INT
            );",
        )?;
        Ok(Self { conn })
    }

    pub fn start_run(&self, run_id: &str) -> Result<()> {
        self.conn.execute(
            "INSERT OR IGNORE INTO runs (run_id, status, started_at) VALUES (?1, 'running', ?2)",
            params![run_id, now_iso()],
        )?;
        Ok(())
    }

    pub fn finish_run(&self, run_id: &str, status: &str) -> Result<()> {
        self.conn.execute(
            "UPDATE runs SET status=?1, finished_at=?2 WHERE run_id=?3",
            params![status, now_iso(), run_id],
        )?;
        Ok(())
    }

    pub fn get_run_status(&self, run_id: &str) -> Option<String> {
        self.conn
            .query_row(
                "SELECT status FROM runs WHERE run_id=?1",
                params![run_id],
                |row| row.get(0),
            )
            .ok()
    }

    pub fn add_task(&self, run_id: &str, task_json: &Value) -> Result<()> {
        let task_id = task_json["task_id"].as_str().unwrap_or("").to_string();
        let attack_class = task_json["attack_class"].as_str().unwrap_or("").to_string();
        let subsystem = task_json["subsystem"].as_str().unwrap_or("").to_string();
        let priority = task_json["priority"].as_i64().unwrap_or(0) as i32;
        let source = task_json["source"].as_str().unwrap_or("").to_string();
        let raw = serde_json::to_string(task_json)?;
        self.conn.execute(
            "INSERT OR IGNORE INTO tasks (run_id, task_id, attack_class, subsystem, status, priority, source, raw_json)
             VALUES (?1, ?2, ?3, ?4, 'pending', ?5, ?6, ?7)",
            params![run_id, task_id, attack_class, subsystem, priority, source, raw],
        )?;
        Ok(())
    }

    pub fn get_pending_tasks(&self, run_id: &str) -> Vec<Value> {
        let mut stmt = match self
            .conn
            .prepare("SELECT raw_json FROM tasks WHERE run_id=?1 AND status='pending'")
        {
            Ok(s) => s,
            Err(_) => return vec![],
        };
        stmt.query_map(params![run_id], |row| row.get::<_, String>(0))
            .map(|rows| {
                rows.filter_map(|r| r.ok())
                    .filter_map(|s| serde_json::from_str(&s).ok())
                    .collect()
            })
            .unwrap_or_default()
    }

    pub fn mark_task_done(&self, run_id: &str, task_id: &str) -> Result<()> {
        self.conn.execute(
            "UPDATE tasks SET status='done' WHERE run_id=?1 AND task_id=?2",
            params![run_id, task_id],
        )?;
        Ok(())
    }

    pub fn mark_task_failed(&self, run_id: &str, task_id: &str) -> Result<()> {
        self.conn.execute(
            "UPDATE tasks SET status='failed' WHERE run_id=?1 AND task_id=?2",
            params![run_id, task_id],
        )?;
        Ok(())
    }

    pub fn add_finding(
        &self,
        run_id: &str,
        finding_json: &Value,
        stage: &str,
        task_id: &str,
    ) -> Result<()> {
        let finding_id = finding_json["finding_id"]
            .as_str()
            .unwrap_or("")
            .to_string();
        let raw = serde_json::to_string(finding_json)?;
        self.conn.execute(
            "INSERT OR IGNORE INTO findings (run_id, finding_id, task_id, stage, raw_json, validation_status)
             VALUES (?1, ?2, ?3, ?4, ?5, 'pending')",
            params![run_id, finding_id, task_id, stage, raw],
        )?;
        Ok(())
    }

    pub fn update_finding_validation(
        &self,
        run_id: &str,
        finding_id: &str,
        status: &str,
    ) -> Result<()> {
        self.conn.execute(
            "UPDATE findings SET validation_status=?1 WHERE run_id=?2 AND finding_id=?3",
            params![status, run_id, finding_id],
        )?;
        Ok(())
    }

    pub fn set_finding_group(&self, run_id: &str, finding_id: &str, group_id: &str) -> Result<()> {
        self.conn.execute(
            "UPDATE findings SET group_id=?1 WHERE run_id=?2 AND finding_id=?3",
            params![group_id, run_id, finding_id],
        )?;
        Ok(())
    }

    pub fn add_trace(
        &self,
        run_id: &str,
        finding_id: &str,
        reachable: bool,
        confidence: f64,
        rationale: &str,
    ) -> Result<()> {
        self.conn.execute(
            "INSERT OR REPLACE INTO traces (run_id, finding_id, reachable, confidence, rationale)
             VALUES (?1, ?2, ?3, ?4, ?5)",
            params![run_id, finding_id, reachable as i32, confidence, rationale],
        )?;
        Ok(())
    }

    pub fn record_cost(
        &self,
        run_id: &str,
        stage: &str,
        task_id: &str,
        input_tokens: i64,
        output_tokens: i64,
    ) -> Result<()> {
        self.conn.execute(
            "INSERT INTO costs (run_id, stage, task_id, input_tokens, output_tokens)
             VALUES (?1, ?2, ?3, ?4, ?5)",
            params![run_id, stage, task_id, input_tokens, output_tokens],
        )?;
        Ok(())
    }

    pub fn total_tokens(&self, run_id: &str) -> u64 {
        self.conn
            .query_row(
                "SELECT COALESCE(SUM(input_tokens + output_tokens), 0) FROM costs WHERE run_id=?1",
                params![run_id],
                |row| row.get::<_, i64>(0),
            )
            .unwrap_or(0) as u64
    }

    pub fn can_resume(&self, run_id: &str) -> bool {
        matches!(self.get_run_status(run_id).as_deref(), Some("running"))
    }

    pub fn resume_run(&self, run_id: &str) -> Result<()> {
        self.conn.execute(
            "UPDATE runs SET status='running', finished_at=NULL WHERE run_id=?1",
            params![run_id],
        )?;
        Ok(())
    }
}
