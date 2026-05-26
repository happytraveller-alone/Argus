package fixture.path_traversal;

import java.io.File;
import java.nio.file.Files;

public class FileService {
    public static String readFile(String name) {
        // Sink: concatenation lets `name` contain `../` to escape /data/.
        File f = new File("/data/" + name);
        try {
            return new String(Files.readAllBytes(f.toPath()));
        } catch (Exception e) {
            return "";
        }
    }
}
