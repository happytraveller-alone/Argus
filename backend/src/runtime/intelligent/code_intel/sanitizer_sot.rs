//! Source of Truth for sanitizer/validator/encoder symbols used by Hunt Pass 2
//! dismissal classification.
//!
//! Each symbol must trace to an authoritative reference (OWASP Cheat Sheet link
//! OR language stdlib documentation section). This file is the audit-grade
//! `rule_matched` evidence source; LLM-only judgment is allowed only when SoT
//! lookup misses.
//!
//! Plan Phase 1 / v0.1 scope: Python + Java + TypeScript, each ≥15 high-confidence
//! sanitizer/encoder/validator symbols. Go + Rust extend in Phase 2 / v0.2.
//!
//! References:
//! - OWASP Cheat Sheet Series: https://cheatsheetseries.owasp.org/
//! - OWASP Java Security Cheat Sheet (parameterized queries, encoding)
//! - OWASP Python Security: https://owasp.org/www-project-python-security/
//! - OWASP XSS Prevention Cheat Sheet (HTML/JS encoders)
//! - Python stdlib `html`, `urllib.parse`, `shlex`, `sqlite3` docs
//! - Java stdlib `java.sql.PreparedStatement`, OWASP ESAPI
//! - TypeScript/Node: `DOMPurify`, `validator.js`, OWASP HTML sanitizer

/// Python sanitizers / encoders / parameterized-query helpers.
///
/// Matching semantics in [`lookup_sanitizer`]:
///   - Bare identifiers (e.g. `escape`) match by qualified-tail suffix
///   - Dotted paths (e.g. `psycopg2.sql.SQL`) match by prefix (covers
///     `psycopg2.sql.SQL("...")` and `psycopg2.sql.SQL.format`).
pub const PYTHON_SANITIZERS: &[&str] = &[
    "psycopg2.sql.SQL",            // OWASP SQLi Cheat Sheet: psycopg2 parameterized composition
    "psycopg2.sql.Identifier",     // OWASP SQLi Cheat Sheet: safe identifier quoting
    "psycopg2.sql.Literal",        // OWASP SQLi Cheat Sheet: safe literal binding
    "sqlalchemy.text",             // SQLAlchemy: parameterized text() with :bindparams
    "sqlalchemy.bindparam",        // SQLAlchemy: explicit bind parameter
    "sqlite3.Cursor.execute",      // Python stdlib sqlite3: ? placeholder binding
    "django.db.models.QuerySet.raw", // Django ORM: params= safe form (sanitizer at call site)
    "html.escape",                 // Python stdlib html: HTML entity escaping
    "markupsafe.escape",           // Jinja/Flask: HTML escape via Markup
    "urllib.parse.quote",          // Python stdlib: URL encoding
    "urllib.parse.quote_plus",     // Python stdlib: URL form encoding
    "shlex.quote",                 // Python stdlib: shell-safe quoting (CWE-78 sanitizer)
    "bleach.clean",                // OWASP HTML sanitizer (Mozilla bleach)
    "secrets.compare_digest",      // Python stdlib: constant-time comparison
    "werkzeug.utils.secure_filename", // OWASP Path-Traversal Cheat Sheet
    "os.path.realpath",            // Python stdlib: canonicalization for path traversal defense
    "pathlib.Path.resolve",        // Python stdlib pathlib: canonical path resolution
    "json.dumps",                  // Python stdlib: structured JSON output (escapes quotes)
];

/// Java sanitizers / encoders / parameterized-query helpers.
///
/// Java entries typically reference type names; matching is suffix-aware so a
/// fully-qualified `java.sql.PreparedStatement` and a bare `PreparedStatement`
/// both hit.
pub const JAVA_SANITIZERS: &[&str] = &[
    "PreparedStatement",                       // OWASP Java SQLi Cheat Sheet: java.sql.PreparedStatement bind params
    "NamedParameterJdbcTemplate",              // Spring JdbcTemplate: named-parameter binding
    "JdbcTemplate.queryForObject",             // Spring JdbcTemplate: parameterized variant
    "CriteriaBuilder",                         // JPA Criteria API: type-safe parameterization
    "TypedQuery.setParameter",                 // JPA setParameter — bound parameter binding
    "EntityManager.createNamedQuery",          // JPA named query (compile-time bound)
    "OWASP.ESAPI.encoder",                     // OWASP ESAPI Encoder facade
    "ESAPI.encoder",                           // OWASP ESAPI Encoder facade (short form)
    "Encode.forHtml",                          // OWASP Java Encoder forHtml (HTML context)
    "Encode.forJavaScript",                    // OWASP Java Encoder forJavaScript
    "Encode.forUriComponent",                  // OWASP Java Encoder forUriComponent
    "HtmlUtils.htmlEscape",                    // Spring web HtmlUtils HTML escape
    "StringEscapeUtils.escapeHtml4",           // Apache Commons Text HTML entity escape
    "StringEscapeUtils.escapeXml11",           // Apache Commons Text XML escape
    "URLEncoder.encode",                       // Java stdlib java.net.URLEncoder
    "Files.createTempFile",                    // java.nio.file: safe temp file creation (no symlink racing)
    "MessageDigest.isEqual",                   // java.security: constant-time digest comparison
    "Path.normalize",                          // java.nio.file: canonicalization for path-traversal defense
    "Paths.get",                               // java.nio.file paths constructor (precondition for normalize)
];

/// TypeScript / JavaScript sanitizers / encoders / parameterized-query helpers.
///
/// Dotted paths cover library-style entries (`mysql.escape`); bare identifiers
/// match by suffix (e.g. `escape`).
pub const TYPESCRIPT_SANITIZERS: &[&str] = &[
    "DOMPurify.sanitize",          // OWASP XSS Cheat Sheet: DOMPurify HTML sanitizer
    "sanitize-html",               // OWASP HTML sanitizer (sanitize-html npm)
    "validator.escape",            // validator.js HTML entity escape
    "validator.isURL",              // validator.js URL whitelist validation
    "validator.isEmail",            // validator.js email whitelist validation
    "lodash.escape",               // Lodash _.escape (HTML entity escape)
    "he.encode",                   // he library: HTML entity encoder
    "encodeURIComponent",          // ECMAScript stdlib: URI component encoding
    "encodeURI",                   // ECMAScript stdlib: URI encoding
    "mysql.escape",                // mysql/mysql2 npm: parameterized escape helper
    "mysql.escapeId",              // mysql/mysql2 npm: identifier escape
    "pg.Pool.query",               // node-postgres parameterized query ($1, $2 placeholders)
    "knex.raw",                    // Knex.js: parameterized raw with bindings
    "sequelize.literal",           // Sequelize literal helper (used with bind params)
    "express-validator.body",      // express-validator: middleware-level validation
    "express-validator.check",     // express-validator: middleware-level validation
    "path.resolve",                // Node.js stdlib path: canonicalization
    "path.normalize",              // Node.js stdlib path: canonicalization
    "crypto.timingSafeEqual",      // Node.js stdlib crypto: constant-time comparison
];

/// Look up a symbol against the SoT array for the given language. Returns the
/// matched canonical entry (suitable for `dismissal_evidence.sanitizer_symbols`)
/// when there is a hit, `None` otherwise.
///
/// Matching rules:
///   - For dotted SoT entries (e.g. `psycopg2.sql.SQL`): prefix match on the
///     symbol. A call site `psycopg2.sql.SQL("SELECT ...")` resolves the
///     symbol to a string containing `psycopg2.sql.SQL`, which matches.
///   - For bare entries (e.g. `PreparedStatement`): suffix-match on the
///     last dotted/colon component of the symbol. So
///     `java.sql.PreparedStatement` matches `PreparedStatement`.
///   - Language is matched case-insensitively against `"python"`, `"java"`,
///     `"typescript"`, `"tsx"`, `"javascript"`. Unknown languages return None.
#[must_use]
pub fn lookup_sanitizer(language: &str, symbol: &str) -> Option<&'static str> {
    let lang = language.to_ascii_lowercase();
    let table: &[&str] = match lang.as_str() {
        "python" | "py" => PYTHON_SANITIZERS,
        "java" => JAVA_SANITIZERS,
        "typescript" | "ts" | "tsx" | "javascript" | "js" => TYPESCRIPT_SANITIZERS,
        _ => return None,
    };

    let trimmed = symbol.trim();
    if trimmed.is_empty() {
        return None;
    }
    // Extract trailing component (last segment after `.`/`:`/`/`/`\\`) — used for
    // bare-entry matching (e.g. `PreparedStatement` matches `java.sql.PreparedStatement`).
    let tail = trimmed
        .rsplit(['.', ':', '/', '\\'])
        .next()
        .unwrap_or(trimmed);

    for entry in table {
        if entry.contains('.') {
            // Dotted SoT entry: match only on (a) exact equality, (b) entry followed by
            // `(` (call site like `psycopg2.sql.SQL(...)`), or (c) entry followed by `.`
            // (further member access). This avoids cross-entry collisions where two
            // entries share a trailing component (e.g. `shlex.quote` vs `urllib.parse.quote`).
            if trimmed == *entry
                || trimmed.starts_with(&format!("{entry}("))
                || trimmed.starts_with(&format!("{entry}."))
            {
                return Some(entry);
            }
        } else if *entry == tail {
            return Some(entry);
        }
    }
    None
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn python_hit_psycopg2_sql_dotted_prefix() {
        let m = lookup_sanitizer("python", "psycopg2.sql.SQL");
        assert_eq!(m, Some("psycopg2.sql.SQL"));
    }

    #[test]
    fn python_hit_shlex_quote_bare() {
        // Even when called as `shlex.quote(arg)` the call-site symbol contains
        // the dotted form; ensure both forms hit.
        assert_eq!(
            lookup_sanitizer("python", "shlex.quote"),
            Some("shlex.quote")
        );
    }

    #[test]
    fn python_miss_random_symbol() {
        assert_eq!(lookup_sanitizer("python", "my_helper"), None);
    }

    #[test]
    fn java_hit_qualified_prepared_statement() {
        // Fully-qualified call-site symbol must match bare SoT entry.
        let m = lookup_sanitizer("java", "java.sql.PreparedStatement");
        assert_eq!(m, Some("PreparedStatement"));
    }

    #[test]
    fn java_hit_bare_prepared_statement() {
        assert_eq!(
            lookup_sanitizer("java", "PreparedStatement"),
            Some("PreparedStatement")
        );
    }

    #[test]
    fn java_miss_random_class() {
        assert_eq!(lookup_sanitizer("java", "MyCustomQueryBuilder"), None);
    }

    #[test]
    fn typescript_hit_dompurify_sanitize() {
        assert_eq!(
            lookup_sanitizer("typescript", "DOMPurify.sanitize"),
            Some("DOMPurify.sanitize")
        );
    }

    #[test]
    fn typescript_hit_encode_uri_component_bare() {
        assert_eq!(
            lookup_sanitizer("typescript", "encodeURIComponent"),
            Some("encodeURIComponent")
        );
    }

    #[test]
    fn typescript_miss_random_helper() {
        assert_eq!(lookup_sanitizer("typescript", "myHelper"), None);
    }

    #[test]
    fn unknown_language_returns_none() {
        // Plan: language-unknown returns None.
        assert_eq!(
            lookup_sanitizer("haskell", "PreparedStatement"),
            None
        );
        assert_eq!(lookup_sanitizer("", "anything"), None);
    }

    #[test]
    fn empty_symbol_returns_none() {
        assert_eq!(lookup_sanitizer("python", ""), None);
        assert_eq!(lookup_sanitizer("java", "   "), None);
    }

    #[test]
    fn language_case_is_normalized() {
        // language is case-insensitive
        assert_eq!(
            lookup_sanitizer("Python", "psycopg2.sql.SQL"),
            Some("psycopg2.sql.SQL")
        );
        assert_eq!(
            lookup_sanitizer("JAVA", "PreparedStatement"),
            Some("PreparedStatement")
        );
        assert_eq!(
            lookup_sanitizer("TypeScript", "DOMPurify.sanitize"),
            Some("DOMPurify.sanitize")
        );
    }

    #[test]
    fn each_language_array_has_at_least_15_entries() {
        assert!(
            PYTHON_SANITIZERS.len() >= 15,
            "PYTHON_SANITIZERS must contain ≥15 entries (AC1.A); got {}",
            PYTHON_SANITIZERS.len()
        );
        assert!(
            JAVA_SANITIZERS.len() >= 15,
            "JAVA_SANITIZERS must contain ≥15 entries (AC1.A); got {}",
            JAVA_SANITIZERS.len()
        );
        assert!(
            TYPESCRIPT_SANITIZERS.len() >= 15,
            "TYPESCRIPT_SANITIZERS must contain ≥15 entries (AC1.A); got {}",
            TYPESCRIPT_SANITIZERS.len()
        );
    }
}
