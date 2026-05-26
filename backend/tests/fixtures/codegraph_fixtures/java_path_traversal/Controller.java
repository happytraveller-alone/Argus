/*
 * Cross-file path traversal test fixture (CWE-22).
 *
 * Spring controller reads `name` query param, passes it directly to
 * FileService.readFile which constructs an absolute path by concatenation.
 * A codegraph-aware Trace MUST identify the chain
 *   serveFile -> FileService.readFile
 * as reachable across 2 files.
 */
package fixture.path_traversal;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class Controller {
    @GetMapping("/file")
    public String serveFile(@RequestParam("name") String name) {
        return FileService.readFile(name);
    }
}
