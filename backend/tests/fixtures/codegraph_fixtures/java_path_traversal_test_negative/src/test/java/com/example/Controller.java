/*
 * Test-code path traversal fixture.
 *
 * This Controller lives under src/test/java/com/example/ — Maven/Gradle's
 * canonical test-source root. A codegraph-aware Hunt MUST classify findings
 * here as `category=test` with `confidence_source=path_pattern` regardless
 * of the inner code shape: test code is non-production and not actionable
 * to internal code review.
 *
 * Mirrors the shape of java_path_traversal/Controller.java but under the
 * test-source tree.
 */
package com.example;

public class Controller {
    public String serveFile(String name) {
        // Sink-equivalent call: the SAME vulnerable shape as the production
        // fixture. The audit pipeline must dismiss it because of the path,
        // not because of the inner logic.
        return FileService.readFile(name);
    }
}
