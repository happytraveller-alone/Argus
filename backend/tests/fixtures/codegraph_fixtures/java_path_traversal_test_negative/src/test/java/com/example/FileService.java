package com.example;

import java.io.File;
import java.nio.file.Files;

public class FileService {
    public static String readFile(String name) {
        // Same unsafe shape as production: `/data/` + name allows traversal.
        // But this lives in src/test/java/ — non-production, non-actionable.
        File f = new File("/data/" + name);
        try {
            return new String(Files.readAllBytes(f.toPath()));
        } catch (Exception e) {
            return "";
        }
    }
}
