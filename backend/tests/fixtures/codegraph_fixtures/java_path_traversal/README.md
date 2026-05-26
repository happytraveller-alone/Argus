# Fixture: java_path_traversal

## Pattern
Cross-file path traversal (CWE-22) — Spring `@GetMapping("/file")` handler
passes the `name` query parameter through to `FileService.readFile`, which
concatenates it onto `/data/` and reads the resulting path.

## Ground truth
- **vuln_class**: `path_traversal`
- **Sink file:line**: `FileService.java:9` (the `new File("/data/" + name)` concatenation)
- **Source**: `Controller.java:18` via `@RequestParam("name")`
- **Reachable**: YES — taint flows `serveFile -> FileService.readFile` across 2 files
- **Expected codegraph evidence**: `get_callers("readFile")` returns `serveFile`

## Files
- `Controller.java` — Spring REST controller (entry point)
- `FileService.java` — file reading utility (sink)
