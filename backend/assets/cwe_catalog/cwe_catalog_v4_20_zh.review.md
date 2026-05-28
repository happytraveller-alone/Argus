# CWE Catalog Chinese Name Review

- Source: local `cwec_v4.20.xml` Weakness entries only
- Version: 4.20
- Date: 2026-04-30
- Entry count: 969
- Translation source: agent_curated_self_reviewed
- Reviewed at: 2026-05-28T10:58:05Z
- Curated seed JSON: `backend/assets/cwe_catalog/cwe_catalog_v4_20_zh.json`
- Curated seed SHA-256: `59a8abcb37809b3ac6a1b169df149467d322a49f619cddf483b084aefbf23f2b`

## Self-review evidence

- All 969 entries were generated from official CWE v4.20 Weakness names and passed deterministic validation.
- Common security display labels were pinned: CWE-89 SQL注入, CWE-79 跨站脚本, CWE-22 路径遍历.
- The validation pass rejects blank Chinese names, duplicate/malformed IDs, count mismatches, and unapproved English fragments.
- English tokens are retained only for conventional security/product/code terms or literal path/code fragments.

## Retained English-token allowlist

AI, API, ASP, ASP.NET, AWT, Action, ActionForm, ActiveX, Android, Apple, Bean, C, CAPTCHA, CBC, CPU, CRLF, CSRF, CSV, CVE, CWE, Cookie, Cplusplus, Cxx, DATA, DMA, DNS, DS_Store, EJB, Eval, FTP, GUI, HFS, HTML, HTTP, HTTPS, Hibernate, HttpOnly, ID, IMG, IOCTL, IV, J2EE, JNI, JSON, JTAG, JWT, Jail, LDAP, LLM, LNK, ML, NET, NUL, NULL, NoC, NoSQL, NullPointerException, OAEP, OAuth, OS, OpenSSL, PHP, PRNG, ROM, RSA, Referer, SOC, SQL, SSI, SSL, SSRF, SameSite, Servlet, Session, SoC, Struts, Swing, System.exit, TRNG, UI, UNC, UNIX, URI, URL, WSDL, WebSocket, WebSockets, Windows, XML, XPath, XQuery, XSS, chmod, chroot, clone, finalize, getlogin, opener, sizeof, umask, validate

## Suspicious-fragment validation

- Result: passed
