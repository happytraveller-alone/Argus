pub mod dedupe;
pub mod feedback;
pub mod gapfill;
pub mod hunt;
pub mod recon;
pub mod reflection;
pub mod report;
pub mod trace;
pub mod validate;

/// Security L1: strip ASCII/Unicode control chars and clamp length before
/// emitting a path into a `finding_blacklisted` event payload. The original
/// `&f.file` is still used for blacklist matching — only the event copy gets
/// sanitized to prevent log-injection / terminal escape abuse.
pub fn sanitize_path_for_event(p: &str) -> String {
    p.chars().filter(|c| !c.is_control()).take(512).collect()
}

#[cfg(test)]
mod sanitize_tests {
    use super::sanitize_path_for_event;

    #[test]
    fn strips_control_chars() {
        let s = "good\x1b[31mbad\x07/path\n";
        let out = sanitize_path_for_event(s);
        assert_eq!(out, "good[31mbad/path");
    }

    #[test]
    fn clamps_length() {
        let s = "a".repeat(2_000);
        let out = sanitize_path_for_event(&s);
        assert_eq!(out.chars().count(), 512);
    }

    #[test]
    fn preserves_normal_path() {
        let s = "src/handler.rs";
        assert_eq!(sanitize_path_for_event(s), s);
    }
}
