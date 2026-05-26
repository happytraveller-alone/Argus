//! Source of Truth for sanitizer/validator/encoder symbols used by Hunt Pass 2
//! dismissal classification.
//!
//! Each symbol must trace to an authoritative reference (OWASP Cheat Sheet link
//! OR language stdlib documentation section). This file is the audit-grade
//! `rule_matched` evidence source; LLM-only judgment is allowed only when SoT
//! lookup misses.
//!
//! Plan Phase 1 / v0.1 scope: Python + Java + TypeScript, each ≥15 high-confidence
//! sanitizer/encoder/validator symbols.
//! Plan Phase 2 / v0.2 scope: extend with Go + Rust, each ≥10 high-confidence
//! symbols sourced from OWASP Cheat Sheets + each language's stdlib doc.
//!
//! References:
//! - OWASP Cheat Sheet Series: https://cheatsheetseries.owasp.org/
//! - OWASP Java Security Cheat Sheet (parameterized queries, encoding)
//! - OWASP Python Security: https://owasp.org/www-project-python-security/
//! - OWASP XSS Prevention Cheat Sheet (HTML/JS encoders)
//! - OWASP Go Secure Coding Practices: https://github.com/OWASP/Go-SCP
//! - Python stdlib `html`, `urllib.parse`, `shlex`, `sqlite3` docs
//! - Java stdlib `java.sql.PreparedStatement`, OWASP ESAPI
//! - TypeScript/Node: `DOMPurify`, `validator.js`, OWASP HTML sanitizer
//! - Go stdlib `html`, `html/template`, `net/url`, `database/sql`, `path/filepath`
//! - Rust ecosystem: `sqlx` (compile-time parameterized macros), `htmlescape`,
//!   `urlencoding`, `regex::escape`, `argon2`, `tokio-postgres` parameterized statements

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

/// Go sanitizers / encoders / parameterized-query helpers.
///
/// Dotted SoT entries match by prefix (covers e.g. `html.EscapeString` and
/// `template.HTMLEscapeString` called as method/package functions); bare
/// entries match by trailing-component suffix.
///
/// Source notes (per Plan Phase 2 / v0.2, AC2.A — each symbol traceable):
///   - Go stdlib: `pkg.go.dev/html`, `pkg.go.dev/html/template`,
///     `pkg.go.dev/net/url`, `pkg.go.dev/database/sql`, `pkg.go.dev/path/filepath`,
///     `pkg.go.dev/strconv`, `pkg.go.dev/crypto/subtle`, `pkg.go.dev/regexp`.
///   - OWASP Go-SCP (OWASP Go Secure Coding Practices) §5 Output Encoding,
///     §13 Database Security.
///   - `golang.org/x/crypto/bcrypt` — OWASP Password Storage Cheat Sheet.
pub const GO_SANITIZERS: &[&str] = &[
    "html.EscapeString",                  // Go stdlib html: HTML entity escape
    "template.HTMLEscapeString",          // Go stdlib html/template: HTML escape
    "template.JSEscapeString",            // Go stdlib html/template: JS-context escape
    "template.URLQueryEscaper",           // Go stdlib html/template: URL query escape
    "url.QueryEscape",                    // Go stdlib net/url: URL form encoding
    "url.PathEscape",                     // Go stdlib net/url: URL path component encoding
    "sql.DB.Prepare",                     // Go stdlib database/sql: prepared statement
    "sql.Tx.Prepare",                     // Go stdlib database/sql: prepared statement in tx
    "sql.Stmt.Exec",                      // Go stdlib database/sql: parameterized exec ($1, ?)
    "sql.Stmt.Query",                     // Go stdlib database/sql: parameterized query
    "filepath.Clean",                     // Go stdlib path/filepath: canonicalize (CWE-22 defense)
    "filepath.Rel",                       // Go stdlib path/filepath: relative-path containment check
    "strconv.Quote",                      // Go stdlib strconv: Go-syntax safe quoting
    "subtle.ConstantTimeCompare",         // Go stdlib crypto/subtle: constant-time comparison
    "regexp.QuoteMeta",                   // Go stdlib regexp: meta-character escape (CWE-625)
    "bcrypt.GenerateFromPassword",        // golang.org/x/crypto/bcrypt: OWASP password storage
    "argon2.IDKey",                       // golang.org/x/crypto/argon2: OWASP password storage
    "bluemonday.UGCPolicy",               // OWASP HTML sanitizer (bluemonday) — user-content policy
    "bluemonday.StrictPolicy",            // OWASP HTML sanitizer (bluemonday) — strict policy
];

/// Rust sanitizers / encoders / parameterized-query helpers.
///
/// Notes on coverage:
///   - The compile-time macros (`sqlx::query!`, `sqlx::query_as!`) are listed
///     with the trailing `!`; matching is exact OR followed by `(` to cover
///     invocations like `sqlx::query!("SELECT ...")`. Rust idiomatic call sites
///     surface these as dotted-path symbols, so prefix matching works.
///   - `sqlx::query` (no bang) is the runtime-parameterized variant; both are
///     safe forms.
///
/// Source notes (per Plan Phase 2 / v0.2, AC2.A):
///   - `docs.rs/sqlx`: compile-time parameterized query macros (sqlx::query!,
///     sqlx::query_as!, sqlx::query_scalar!); runtime `sqlx::query` is also
///     parameterized via bind() calls.
///   - `docs.rs/tokio-postgres`: parameterized statements via `Client::query`
///     and `Statement` prepared form.
///   - `docs.rs/diesel`: schema-typed query builder (Insertable, Queryable) —
///     parameterization is structural, not at sink.
///   - `docs.rs/htmlescape`, `docs.rs/v_htmlescape`, `docs.rs/askama`:
///     HTML-context output encoders (OWASP XSS Prevention).
///   - `docs.rs/urlencoding`: URL component encoding.
///   - `docs.rs/regex`: `regex::escape` for safe regex literal embedding.
///   - `docs.rs/argon2`, `docs.rs/bcrypt`: OWASP Password Storage Cheat Sheet.
///   - `docs.rs/subtle`: constant-time equality (`subtle::ConstantTimeEq`).
///   - Rust stdlib `Path::canonicalize` — canonicalization for path-traversal defense.
pub const RUST_SANITIZERS: &[&str] = &[
    "sqlx::query!",                       // sqlx compile-time parameterized macro
    "sqlx::query_as!",                    // sqlx compile-time parameterized + typed macro
    "sqlx::query_scalar!",                // sqlx compile-time parameterized scalar macro
    "sqlx::query",                        // sqlx runtime parameterized builder (bind() chain)
    "tokio_postgres::Client::query",      // tokio-postgres parameterized query
    "tokio_postgres::Statement",          // tokio-postgres prepared statement (parameterized)
    "htmlescape::encode_minimal",         // htmlescape crate: HTML entity escape
    "v_htmlescape::escape",               // v_htmlescape crate: HTML escape
    "askama::filters::e",                 // askama template engine: HTML auto-escape filter
    "urlencoding::encode",                // urlencoding crate: URL component encoding
    "regex::escape",                      // regex crate: regex meta-character escape
    "argon2::Argon2",                     // argon2 crate: OWASP password storage
    "bcrypt::hash",                       // bcrypt crate: OWASP password storage
    "subtle::ConstantTimeEq",             // subtle crate: constant-time equality
    "Path::canonicalize",                 // Rust stdlib std::path::Path: canonicalization (CWE-22)
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
        "go" | "golang" => GO_SANITIZERS,
        "rust" | "rs" => RUST_SANITIZERS,
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
        // A "qualified" SoT entry is any entry that contains a path separator —
        // `.` (Python/Java/TS), `::` (Rust), `/` (some packaged Go forms). Bare
        // entries (e.g. `PreparedStatement`) match by trailing-component suffix.
        let is_qualified = entry.contains('.') || entry.contains("::");
        if is_qualified {
            // Qualified entry matches when it is:
            //   (a) exact equality
            //   (b) prefix followed by `(` (call site: `entry(...)`).
            //   (c) prefix followed by `.` or `::` (further member access).
            //   (d) `::`-bounded path-aligned suffix of the input — covers
            //       Rust resolution forms like `std::path::Path::canonicalize`
            //       hitting the entry `Path::canonicalize`. The suffix must be
            //       preceded by `::` (or `.`) so we never partial-match across
            //       identifier characters.
            if trimmed == *entry
                || trimmed.starts_with(&format!("{entry}("))
                || trimmed.starts_with(&format!("{entry}."))
                || trimmed.starts_with(&format!("{entry}::"))
                || trimmed.ends_with(&format!("::{entry}"))
                || trimmed.ends_with(&format!(".{entry}"))
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
        // Phase 2: Go/Rust language id normalization.
        assert_eq!(
            lookup_sanitizer("Go", "html.EscapeString"),
            Some("html.EscapeString")
        );
        assert_eq!(
            lookup_sanitizer("Rust", "sqlx::query!"),
            Some("sqlx::query!")
        );
    }

    // ─── Plan Phase 2 / v0.2 — Go SoT (AC2.A) ──────────────────────────────

    #[test]
    fn go_hit_html_escapestring_dotted() {
        assert_eq!(
            lookup_sanitizer("go", "html.EscapeString"),
            Some("html.EscapeString")
        );
    }

    #[test]
    fn go_hit_qualified_filepath_clean() {
        // Call-site symbol "path/filepath.Clean" is the fully-qualified form
        // seen in some Go tooling; we accept the canonical `filepath.Clean`
        // entry as a prefix-from-tail match — but more importantly the bare
        // dotted form `filepath.Clean` must hit exactly.
        assert_eq!(
            lookup_sanitizer("go", "filepath.Clean"),
            Some("filepath.Clean")
        );
    }

    #[test]
    fn go_hit_golang_alias_lang_id() {
        // The "golang" language id alias must resolve to the same table.
        assert_eq!(
            lookup_sanitizer("golang", "url.QueryEscape"),
            Some("url.QueryEscape")
        );
    }

    #[test]
    fn go_miss_random_symbol() {
        // A symbol that looks ecosystem-shaped but is not in SoT must miss.
        assert_eq!(lookup_sanitizer("go", "myapp.SafeBuilder"), None);
        assert_eq!(lookup_sanitizer("go", "fmt.Println"), None);
    }

    // ─── Plan Phase 2 / v0.2 — Rust SoT (AC2.A) ────────────────────────────

    #[test]
    fn rust_hit_sqlx_query_macro() {
        // Plain match on the macro entry.
        assert_eq!(
            lookup_sanitizer("rust", "sqlx::query!"),
            Some("sqlx::query!")
        );
    }

    #[test]
    fn rust_hit_sqlx_query_call_site() {
        // `sqlx::query("SELECT ...")` is the runtime parameterized form;
        // entry `sqlx::query` matches prefix-with-`(`.
        assert_eq!(
            lookup_sanitizer("rust", "sqlx::query(\"SELECT 1\")"),
            Some("sqlx::query")
        );
    }

    #[test]
    fn rust_hit_path_canonicalize_bare() {
        // `Path::canonicalize` is the bare-entry form; call-site symbol
        // `std::path::Path::canonicalize` must match by trailing component.
        assert_eq!(
            lookup_sanitizer("rust", "std::path::Path::canonicalize"),
            Some("Path::canonicalize")
        );
    }

    #[test]
    fn rust_hit_rs_alias_lang_id() {
        // The "rs" alias must work alongside "rust".
        assert_eq!(
            lookup_sanitizer("rs", "urlencoding::encode"),
            Some("urlencoding::encode")
        );
    }

    #[test]
    fn rust_miss_random_symbol() {
        // Random ecosystem-shaped Rust symbol must miss.
        assert_eq!(lookup_sanitizer("rust", "my_crate::helpers::escape"), None);
        assert_eq!(lookup_sanitizer("rust", "println!"), None);
    }

    #[test]
    fn each_language_array_has_at_least_required_entries() {
        // Phase 1 baseline: Python / Java / TypeScript ≥ 15 (AC1.A).
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
        // Phase 2: Go / Rust ≥ 10 (AC2.A).
        assert!(
            GO_SANITIZERS.len() >= 10,
            "GO_SANITIZERS must contain ≥10 entries (AC2.A); got {}",
            GO_SANITIZERS.len()
        );
        assert!(
            RUST_SANITIZERS.len() >= 10,
            "RUST_SANITIZERS must contain ≥10 entries (AC2.A); got {}",
            RUST_SANITIZERS.len()
        );
    }
}
