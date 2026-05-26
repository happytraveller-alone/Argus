//! Dead-code detection — v0.3.b deterministic 5th dismissal channel.
//!
//! Engineers waste triage time on findings that live in unreachable code paths
//! (`if False:` blocks, `#[cfg(test)]` regions, branches after an unconditional
//! return). This module is a pure-Rust, source-only scanner that classifies
//! whether a given `(file_content, line)` pair lives inside such a region.
//!
//! Contract:
//!
//! * Returns `Some(pattern_name)` when `line` is inside a known dead region;
//!   `None` otherwise. `pattern_name` is a stable string identifier — e.g.
//!   `"if_false_branch"`, `"cfg_test_region"`, `"after_unconditional_return"` —
//!   suitable for storage in `DismissalEvidence::sanitizer_symbols[0]`.
//! * Pure source-text scan: no parser dependency, no codegraph CLI. Hard-coded
//!   substring + indentation/block tracking only.
//! * Conservative: when a region cannot be definitively identified as dead,
//!   return `None`. False negatives are preferred over false positives because
//!   this channel writes a deterministic dismissal — a wrong hit silences a
//!   real bug.
//!
//! Supported language → pattern matrix (v0.3.b):
//!
//! | Language   | Patterns covered                                              |
//! |------------|---------------------------------------------------------------|
//! | python     | `if False:`, `if 0:`, code after an unconditional `return`    |
//! |            | inside the enclosing function, code after `raise SystemExit`  |
//! | rust       | `#[cfg(test)]` module gate, `if false {` branch, `unreachable!()` |
//! | go         | `if false {` branch, `//go:build never` file-level tag        |
//! | typescript | `if (false) {` / `if (0) {` branch                            |
//! | javascript | same as typescript                                            |
//! | java       | `if (false) {` branch                                         |
//!
//! Pattern names exposed (stable):
//!
//! * `"if_false_branch"` — Python `if False:` / `if 0:`, Rust `if false {`,
//!   Go `if false {`, TS/JS/Java `if (false) {` / `if (0) {`.
//! * `"after_unconditional_return"` — Python only: code after a `return` or
//!   `raise SystemExit` at the same indentation level inside the enclosing
//!   function.
//! * `"cfg_test_region"` — Rust `#[cfg(test)]` immediately preceding the
//!   enclosing item (mod/fn).
//! * `"unreachable_call"` — Rust `unreachable!()` earlier in the enclosing
//!   block; subsequent siblings are dead.
//! * `"build_tag_never"` — Go `//go:build never` (or `// +build never`) at
//!   file head. Whole file is dead.

/// Identify whether the `line` (1-indexed) inside `source` of the given
/// `language` lives inside a deterministically dead region.
///
/// `language` is a lowercase canonical identifier matching the Hunt stage's
/// `map_extension_to_language` outputs: `python`, `rust`, `go`, `typescript`,
/// `tsx`, `javascript`, `jsx`, `java`. Unknown languages return `None`.
///
/// Returns the pattern name on hit; `None` when no dead-code shape encloses
/// the line, or the inputs are invalid (empty source, line out of bounds).
#[must_use]
pub fn detect_dead_code(source: &str, line: u32, language: &str) -> Option<&'static str> {
    if source.is_empty() || line == 0 {
        return None;
    }
    let lines: Vec<&str> = source.lines().collect();
    let idx = (line as usize).checked_sub(1)?;
    if idx >= lines.len() {
        return None;
    }
    let lang = language.to_ascii_lowercase();
    match lang.as_str() {
        "python" => detect_python(&lines, idx),
        "rust" => detect_rust(&lines, idx),
        "go" => detect_go(&lines, idx),
        "typescript" | "tsx" | "javascript" | "jsx" => detect_c_brace(&lines, idx),
        "java" => detect_c_brace(&lines, idx),
        _ => None,
    }
}

// ---------------------------------------------------------------------------
// Python
// ---------------------------------------------------------------------------

/// Python detection covers three shapes:
///   1. The target line is inside an `if False:` / `if 0:` block (indentation
///      strictly greater than the `if` line).
///   2. The target line comes after an unconditional `return` / `raise
///      SystemExit` at the SAME indentation inside the enclosing function.
fn detect_python(lines: &[&str], target_idx: usize) -> Option<&'static str> {
    let target_indent = leading_spaces(lines[target_idx]);
    // Skip blank / comment-only target lines — they don't carry semantics.
    let trimmed = lines[target_idx].trim_start();
    if trimmed.is_empty() || trimmed.starts_with('#') {
        return None;
    }

    // Walk backwards looking for an enclosing `if False:` or `if 0:`.
    for i in (0..target_idx).rev() {
        let raw = lines[i];
        let stripped = raw.trim_start();
        if stripped.is_empty() || stripped.starts_with('#') {
            continue;
        }
        let indent = leading_spaces(raw);
        // Only outer-scope lines (indent < target_indent) can enclose us.
        if indent >= target_indent {
            continue;
        }
        // Found an outer-scope statement. It's an enclosing block ONLY if it
        // ends with `:` (Python compound statement).
        if is_python_if_false_header(stripped) {
            return Some("if_false_branch");
        }
        // First non-matching enclosing line wins — don't keep climbing past
        // it (an `if False:` further out doesn't span our scope if a non-dead
        // block opens in between).
        if stripped.ends_with(':') {
            break;
        }
    }

    // Walk backwards looking for a prior `return`/`raise SystemExit` at the
    // SAME indentation as the target line. Stop the moment we cross OUT of
    // the enclosing function (a `def`/`async def` at lower indent).
    for i in (0..target_idx).rev() {
        let raw = lines[i];
        let stripped = raw.trim_start();
        if stripped.is_empty() || stripped.starts_with('#') {
            continue;
        }
        let indent = leading_spaces(raw);
        if indent < target_indent {
            // Crossed enclosing-scope boundary. If it's a function header,
            // we're still in the same function — but a `return` at a higher
            // level wouldn't apply. Stop the search.
            if stripped.starts_with("def ")
                || stripped.starts_with("async def ")
                || stripped.starts_with("class ")
            {
                break;
            }
            // Other outer statements: continue search (we may still be in
            // a nested block whose parent contains the return).
            continue;
        }
        if indent == target_indent && is_python_unconditional_exit(stripped) {
            return Some("after_unconditional_return");
        }
    }

    None
}

fn is_python_if_false_header(stripped: &str) -> bool {
    // Accept "if False:" / "if 0:" optionally followed by whitespace + comment.
    // Trailing colon required.
    let without_comment = stripped
        .split('#')
        .next()
        .unwrap_or("")
        .trim_end();
    without_comment == "if False:" || without_comment == "if 0:"
}

fn is_python_unconditional_exit(stripped: &str) -> bool {
    // "return", "return <expr>", "raise SystemExit", "raise SystemExit(...)".
    if stripped == "return" || stripped.starts_with("return ") || stripped.starts_with("return\t") {
        return true;
    }
    stripped.starts_with("raise SystemExit")
}

// ---------------------------------------------------------------------------
// Rust
// ---------------------------------------------------------------------------

/// Rust detection covers three shapes:
///   1. `if false { ... }` enclosing block.
///   2. `#[cfg(test)]` attribute immediately preceding an enclosing
///      `mod`/`fn` whose body contains the target line.
///   3. `unreachable!()` earlier in the enclosing block at any prior sibling
///      line at the SAME indent as the target.
fn detect_rust(lines: &[&str], target_idx: usize) -> Option<&'static str> {
    if let Some(pat) = detect_brace_if_false(lines, target_idx, &["if false"]) {
        return Some(pat);
    }
    if let Some(pat) = detect_rust_cfg_test(lines, target_idx) {
        return Some(pat);
    }
    if let Some(pat) = detect_unreachable_call(lines, target_idx) {
        return Some(pat);
    }
    None
}

/// Detect `#[cfg(test)]` regions: walk backwards looking for ANY enclosing
/// `mod`/`fn` item (at strictly lower indent). For each candidate, check
/// whether the line immediately preceding it (skipping blanks) carries
/// `#[cfg(test)]`. Hit anywhere up the ancestor chain wins.
fn detect_rust_cfg_test(lines: &[&str], target_idx: usize) -> Option<&'static str> {
    let mut current_indent = leading_spaces(lines[target_idx]);
    if current_indent == 0 {
        return None;
    }
    let mut i = target_idx;
    while i > 0 {
        i -= 1;
        let raw = lines[i];
        let stripped = raw.trim_start();
        if stripped.is_empty() {
            continue;
        }
        let indent = leading_spaces(raw);
        if indent >= current_indent {
            continue;
        }
        // Strict lower-indent candidate. We only care about items that open
        // a block (mod / fn).
        let opens_block = stripped.contains("mod ") || stripped.contains("fn ");
        // Tighten the search scope to the candidate's indent so the next
        // iteration looks for a still-outer enclosing item.
        current_indent = indent;
        if !opens_block {
            continue;
        }
        // Check the immediately preceding non-blank line.
        for j in (0..i).rev() {
            let prior = lines[j].trim();
            if prior.is_empty() {
                continue;
            }
            if prior.starts_with("#[cfg(test)]") {
                return Some("cfg_test_region");
            }
            break;
        }
        if current_indent == 0 {
            return None;
        }
    }
    None
}

/// Detect `unreachable!()` at a prior sibling line (same indent, between the
/// target and the enclosing block opener).
fn detect_unreachable_call(lines: &[&str], target_idx: usize) -> Option<&'static str> {
    let target_indent = leading_spaces(lines[target_idx]);
    for i in (0..target_idx).rev() {
        let raw = lines[i];
        let stripped = raw.trim_start();
        if stripped.is_empty() {
            continue;
        }
        let indent = leading_spaces(raw);
        // If we drop below target_indent, we've left the enclosing block.
        if indent < target_indent {
            return None;
        }
        if indent == target_indent && stripped.starts_with("unreachable!(") {
            return Some("unreachable_call");
        }
    }
    None
}

// ---------------------------------------------------------------------------
// Go
// ---------------------------------------------------------------------------

/// Go detection covers:
///   1. `if false {` enclosing block.
///   2. File-level `//go:build never` (or legacy `// +build never`) build
///      tag — kills the whole file.
fn detect_go(lines: &[&str], target_idx: usize) -> Option<&'static str> {
    // Build tag scan: look at the first ~5 non-blank lines for the tag. Go
    // requires the build directive in the first block of comments.
    let mut seen = 0usize;
    for raw in lines.iter() {
        let stripped = raw.trim();
        if stripped.is_empty() {
            continue;
        }
        if stripped.starts_with("//go:build never") || stripped.starts_with("// +build never") {
            return Some("build_tag_never");
        }
        // Stop scanning once we hit a non-comment line.
        if !stripped.starts_with("//") {
            break;
        }
        seen += 1;
        if seen >= 10 {
            break;
        }
    }
    detect_brace_if_false(lines, target_idx, &["if false"])
}

// ---------------------------------------------------------------------------
// C-brace languages: TS / JS / Java
// ---------------------------------------------------------------------------

/// C-brace languages share an `if (false) {` / `if (0) {` shape.
fn detect_c_brace(lines: &[&str], target_idx: usize) -> Option<&'static str> {
    detect_brace_if_false(lines, target_idx, &["if (false)", "if (0)"])
}

// ---------------------------------------------------------------------------
// Brace block detection (Rust / Go / TS / JS / Java)
// ---------------------------------------------------------------------------

/// Walk backwards counting `{` and `}` braces relative to the target line.
/// When we cross a line whose trimmed start matches ANY of `headers`, the
/// target sits inside that header's block IFF the brace depth between header
/// and target is positive (header `{` not yet matched by a `}`).
fn detect_brace_if_false(
    lines: &[&str],
    target_idx: usize,
    headers: &[&str],
) -> Option<&'static str> {
    // We accumulate net `}` minus `{` going BACKWARDS from target_idx-1.
    // When `pending_close > 0` we're "above" a `{`-opened block that already
    // closed; the only way to be INSIDE a target block is when pending_close
    // becomes negative.
    let mut closes_pending: i32 = 0;
    for i in (0..target_idx).rev() {
        let raw = lines[i];
        let stripped = raw.trim_start();
        // Skip line/block comments only loosely — comments inside strings or
        // multi-line literals are out of scope; this is a heuristic.
        let trimmed_full = stripped.split("//").next().unwrap_or("").trim_end();
        let (opens, closes) = count_braces(trimmed_full);
        // Backwards: a closing brace below us (already counted) represents a
        // block ending BEFORE our target. Going up, an opening brace cancels
        // one such close.
        closes_pending += closes as i32;
        closes_pending -= opens as i32;
        if closes_pending < 0 {
            // We're inside this line's open brace's block. Check if the line
            // is one of the dead-code headers.
            for header in headers {
                if stripped.starts_with(header) {
                    return Some("if_false_branch");
                }
            }
            // Inside a non-dead block — bring pending back to 0 so we continue
            // searching for an even more-enclosing block.
            closes_pending = 0;
        }
    }
    None
}

fn count_braces(s: &str) -> (usize, usize) {
    let mut opens = 0usize;
    let mut closes = 0usize;
    let mut in_str: Option<char> = None;
    let mut escape = false;
    for c in s.chars() {
        if escape {
            escape = false;
            continue;
        }
        match (in_str, c) {
            (Some(q), c) if c == q => in_str = None,
            (Some(_), '\\') => escape = true,
            (Some(_), _) => {}
            (None, '"') | (None, '\'') | (None, '`') => in_str = Some(c),
            (None, '{') => opens += 1,
            (None, '}') => closes += 1,
            _ => {}
        }
    }
    (opens, closes)
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

fn leading_spaces(line: &str) -> usize {
    line.chars().take_while(|c| c.is_whitespace()).count()
}

// ---------------------------------------------------------------------------
// Tests — at least one per supported language, plus negative cases.
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn python_if_false_branch_detected() {
        let src = "\
def handler():
    if False:
        dangerous_sql = f\"SELECT * FROM x WHERE id = {user_input}\"
        return dangerous_sql
    return None
";
        // Line 3 is inside `if False:`.
        assert_eq!(detect_dead_code(src, 3, "python"), Some("if_false_branch"));
        // Line 5 (return None) is OUTSIDE the if False — must NOT flag.
        assert_eq!(detect_dead_code(src, 5, "python"), None);
    }

    #[test]
    fn python_after_unconditional_return_detected() {
        let src = "\
def handler(input):
    return safe_value(input)
    dangerous = run_query(input)
    return dangerous
";
        // Line 3 lives after an unconditional `return` at the same indent.
        assert_eq!(
            detect_dead_code(src, 3, "python"),
            Some("after_unconditional_return")
        );
    }

    #[test]
    fn python_reachable_code_not_flagged() {
        let src = "\
def handler(input):
    if input:
        return safe_value(input)
    return dangerous(input)
";
        // Line 4 is inside the function body but reachable.
        assert_eq!(detect_dead_code(src, 4, "python"), None);
    }

    #[test]
    fn python_if_zero_branch_detected() {
        let src = "\
def handler():
    if 0:
        bad = inject(input)
        return bad
    return ok()
";
        assert_eq!(detect_dead_code(src, 3, "python"), Some("if_false_branch"));
    }

    #[test]
    fn rust_if_false_branch_detected() {
        let src = "\
fn handler() {
    if false {
        let q = format!(\"SELECT * FROM x WHERE id = {input}\");
        execute(&q);
    }
}
";
        assert_eq!(detect_dead_code(src, 3, "rust"), Some("if_false_branch"));
    }

    #[test]
    fn rust_cfg_test_region_detected() {
        let src = "\
#[cfg(test)]
mod tests {
    fn helper() {
        let q = format!(\"DROP TABLE users\");
    }
}
";
        assert_eq!(detect_dead_code(src, 4, "rust"), Some("cfg_test_region"));
    }

    #[test]
    fn rust_unreachable_call_detected() {
        let src = "\
fn handler() {
    unreachable!(\"never\");
    let q = build_query(input);
    execute(q);
}
";
        assert_eq!(
            detect_dead_code(src, 3, "rust"),
            Some("unreachable_call")
        );
    }

    #[test]
    fn go_if_false_branch_detected() {
        let src = "\
package main

func handler() {
    if false {
        q := fmt.Sprintf(\"SELECT * FROM x WHERE id = %s\", input)
        db.Exec(q)
    }
}
";
        assert_eq!(detect_dead_code(src, 5, "go"), Some("if_false_branch"));
    }

    #[test]
    fn go_build_tag_never_detected() {
        let src = "\
//go:build never

package main

func handler() {
    q := buildQuery(input)
}
";
        assert_eq!(detect_dead_code(src, 6, "go"), Some("build_tag_never"));
    }

    #[test]
    fn typescript_if_false_branch_detected() {
        let src = "\
function handler(input: string) {
    if (false) {
        const q = `SELECT * FROM x WHERE id = ${input}`;
        db.exec(q);
    }
}
";
        assert_eq!(detect_dead_code(src, 3, "typescript"), Some("if_false_branch"));
    }

    #[test]
    fn typescript_if_zero_branch_detected() {
        let src = "\
function handler(input: string) {
    if (0) {
        const q = `SELECT * FROM x WHERE id = ${input}`;
        db.exec(q);
    }
}
";
        assert_eq!(detect_dead_code(src, 3, "typescript"), Some("if_false_branch"));
    }

    #[test]
    fn java_if_false_branch_detected() {
        let src = "\
class Handler {
    void handle(String input) {
        if (false) {
            String q = \"SELECT * FROM x WHERE id = \" + input;
            db.execute(q);
        }
    }
}
";
        assert_eq!(detect_dead_code(src, 4, "java"), Some("if_false_branch"));
    }

    #[test]
    fn unknown_language_returns_none() {
        let src = "if False:\n    dead = 1\n";
        assert_eq!(detect_dead_code(src, 2, "haskell"), None);
    }

    #[test]
    fn out_of_bounds_line_returns_none() {
        let src = "fn x() {}\n";
        assert_eq!(detect_dead_code(src, 99, "rust"), None);
        assert_eq!(detect_dead_code(src, 0, "rust"), None);
    }

    #[test]
    fn empty_source_returns_none() {
        assert_eq!(detect_dead_code("", 1, "python"), None);
    }

    #[test]
    fn rust_outside_cfg_test_not_flagged() {
        let src = "\
mod prod {
    fn helper() {
        let q = format!(\"SELECT 1\");
    }
}
";
        assert_eq!(detect_dead_code(src, 3, "rust"), None);
    }
}
