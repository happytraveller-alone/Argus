use backend_rust::runtime::queue::{
    recon_fingerprint, vulnerability_fingerprint, QueueStats, ReconQueue, VulnerabilityQueue,
};
use serde_json::json;

#[test]
fn recon_fingerprint_uses_expected_dedupe_fields() {
    let risk_point = json!({
        "file_path": " SRC/Auth/Login.rs ",
        "line_start": "42",
        "vulnerability_type": " SQL_Injection ",
        "entry_function": " Login_Handler ",
        "source": " query.user ",
        "sink": " db.execute ",
        "input_surface": " HTTP Body ",
        "trust_boundary": " DB Boundary ",
        "description": "  Unsanitized   SQL\nflows   into sink  ",
        "title": "ignored title",
        "severity": "high",
    });

    assert_eq!(
        recon_fingerprint(&risk_point),
        "src/auth/login.rs|42|sql_injection|login_handler|query.user|db.execute|http body|db boundary|unsanitized sql flows into sink"
    );

    let same_fingerprint = json!({
        "file_path": "src/auth/login.rs",
        "line_start": 42,
        "vulnerability_type": "sql_injection",
        "entry_function": "login_handler",
        "source": "query.user",
        "sink": "db.execute",
        "input_surface": "http body",
        "trust_boundary": "db boundary",
        "description": "unsanitized sql flows into sink",
        "title": "different title",
        "severity": "low",
    });
    assert_eq!(
        recon_fingerprint(&risk_point),
        recon_fingerprint(&same_fingerprint)
    );

    let changed_sink = json!({
        "file_path": "src/auth/login.rs",
        "line_start": 42,
        "vulnerability_type": "sql_injection",
        "entry_function": "login_handler",
        "source": "query.user",
        "sink": "cache.write",
        "input_surface": "http body",
        "trust_boundary": "db boundary",
        "description": "unsanitized sql flows into sink",
    });
    assert_ne!(recon_fingerprint(&risk_point), recon_fingerprint(&changed_sink));
}

#[test]
fn recon_queue_is_fifo_and_tracks_stats_clear_and_contains() {
    let first = json!({
        "title": "first-candidate",
        "severity": "medium",
        "description": "reflects query input into html response",
        "file_path": "src/handlers/search.rs",
        "line_start": 12,
        "vulnerability_type": "xss",
        "entry_function": "search",
        "source": "query.q",
        "sink": "response.write",
        "input_surface": "query string",
        "trust_boundary": "public request",
    });
    let first_duplicate = json!({
        "title": "same-fingerprint-different-title",
        "severity": "low",
        "description": "  reflects   query input into html response ",
        "file_path": " SRC/Handlers/Search.rs ",
        "line_start": "12",
        "vulnerability_type": " XSS ",
        "entry_function": " Search ",
        "source": " query.q ",
        "sink": " response.write ",
        "input_surface": " Query String ",
        "trust_boundary": " Public Request ",
    });
    let second = json!({
        "title": "second-candidate",
        "severity": "high",
        "description": "flows tainted body into shell execution",
        "file_path": "src/jobs/import.rs",
        "line_start": 34,
        "vulnerability_type": "command_injection",
        "entry_function": "run_import",
        "source": "request.body",
        "sink": "command.exec",
        "input_surface": "http body",
        "trust_boundary": "worker shell",
    });

    let mut queue = ReconQueue::default();
    assert!(queue.enqueue(first.clone()));
    assert!(!queue.enqueue(first_duplicate.clone()));
    assert!(queue.enqueue(second.clone()));
    assert!(queue.contains(&first));
    assert!(queue.contains(&first_duplicate));
    assert_eq!(queue.size(), 2);
    assert_eq!(queue.peek(10), vec![first.clone(), second.clone()]);
    assert_eq!(
        queue.stats(),
        QueueStats {
            current_size: 2,
            total_enqueued: 2,
            total_dequeued: 0,
            total_deduplicated: 1,
        }
    );

    assert_eq!(queue.dequeue(), Some(first.clone()));
    assert_eq!(queue.dequeue(), Some(second.clone()));
    assert_eq!(queue.dequeue(), None);
    assert!(queue.contains(&first));
    assert_eq!(
        queue.stats(),
        QueueStats {
            current_size: 0,
            total_enqueued: 2,
            total_dequeued: 2,
            total_deduplicated: 1,
        }
    );

    queue.clear();
    assert_eq!(queue.size(), 0);
    assert!(!queue.contains(&first));
    assert!(queue.peek(10).is_empty());
    assert_eq!(queue.stats(), QueueStats::default());
}

#[test]
fn vulnerability_fingerprint_uses_expected_dedupe_fields() {
    let finding = json!({
        "file_path": " SRC/Auth/Login.rs ",
        "line_start": "42",
        "vulnerability_type": " SQL_Injection ",
        "title": " Login bypass ",
        "description": "ignored description",
        "severity": "critical",
    });

    assert_eq!(
        vulnerability_fingerprint(&finding),
        "src/auth/login.rs|42|sql_injection|login bypass"
    );

    let same_fingerprint = json!({
        "file_path": "src/auth/login.rs",
        "line_start": 42,
        "vulnerability_type": "sql_injection",
        "title": "login bypass",
        "description": "different description",
    });
    assert_eq!(
        vulnerability_fingerprint(&finding),
        vulnerability_fingerprint(&same_fingerprint)
    );

    let changed_title = json!({
        "file_path": "src/auth/login.rs",
        "line_start": 42,
        "vulnerability_type": "sql_injection",
        "title": "admin bypass",
    });
    assert_ne!(
        vulnerability_fingerprint(&finding),
        vulnerability_fingerprint(&changed_title)
    );

    let mut queue = VulnerabilityQueue::default();
    assert!(queue.enqueue(finding.clone()));
    assert!(!queue.enqueue(same_fingerprint));
}
