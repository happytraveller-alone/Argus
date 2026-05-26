# java_path_traversal_test_negative

This fixture demonstrates a non-actionable finding in test-code. The vulnerable
shape (concatenation of user-controlled input into a `new File("/data/" +
name)` call) is **identical** to `java_path_traversal/` but the entire
fixture lives under `src/test/java/com/example/` — Maven/Gradle's canonical
test source root.

The audit pipeline's path classifier (`path_classifier.rs`) MUST recognize
`src/test/java/` as a test-source tree and emit
`category=test`, `confidence_source=path_pattern`, and
`path_pattern="src/test/java/"`. No structural analysis is required to dismiss
this finding — the path alone is sufficient.

This is a static-analysis test fixture demonstrating non-production code
classification. It is NOT a real application and MUST NOT be deployed.
