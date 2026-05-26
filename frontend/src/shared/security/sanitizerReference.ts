/**
 * Mapping from canonical sanitizer / parameterized-query symbol names (as
 * emitted by the backend `audit_pipeline` SoT layer in `DismissalEvidence
 * .sanitizerSymbols`) to authoritative reference URLs.
 *
 * Coverage is intentionally small — only well-known OWASP / stdlib mappings.
 * Unknown symbols return `null` and should render as a plain non-clickable chip.
 */

const SANITIZER_REFERENCE_URLS: Record<string, string> = {
  // Python parameterized SQL
  "psycopg2.sql.SQL": "https://www.psycopg.org/docs/sql.html",
  "sqlite3.Cursor.execute":
    "https://docs.python.org/3/library/sqlite3.html#sqlite3.Cursor.execute",
  // Python output escaping
  "html.escape":
    "https://docs.python.org/3/library/html.html#html.escape",
  "shlex.quote":
    "https://docs.python.org/3/library/shlex.html#shlex.quote",
  // Java / JDBC parameterized queries
  "java.sql.PreparedStatement":
    "https://docs.oracle.com/javase/8/docs/api/java/sql/PreparedStatement.html",
  "org.owasp.encoder.Encode":
    "https://owasp.org/www-project-java-encoder/",
  // JavaScript / browser sanitizers
  "DOMPurify.sanitize": "https://github.com/cure53/DOMPurify",
  "encodeURIComponent":
    "https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/encodeURIComponent",
  // Generic OWASP guidance
  "OWASP.SQLInjection":
    "https://owasp.org/www-community/attacks/SQL_Injection",
  "OWASP.PathTraversal":
    "https://owasp.org/www-community/attacks/Path_Traversal",
};

/**
 * Returns an authoritative reference URL for a sanitizer / canonical symbol,
 * or `null` when the symbol is not in the lookup table.
 */
export function sanitizerReferenceUrl(symbol: string): string | null {
  const trimmed = String(symbol || "").trim();
  if (!trimmed) return null;
  return SANITIZER_REFERENCE_URLS[trimmed] ?? null;
}
