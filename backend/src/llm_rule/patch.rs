#[derive(Debug, Clone, PartialEq, Eq)]
pub struct FileChange {
    pub file_path: String,
    pub changes: String,
    pub language: String,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct PatchInfo {
    pub repo_owner: String,
    pub repo_name: String,
    pub commit_id: String,
    pub file_changes: Vec<FileChange>,
}

pub fn get_language_from_file(file_path: &str) -> Option<&'static str> {
    let extension = file_path
        .rsplit_once('.')
        .map(|(_, ext)| ext.to_ascii_lowercase())?;
    match extension.as_str() {
        "py" | "pyi" | "pyx" | "pyw" => Some("python"),
        "js" | "jsx" | "mjs" | "cjs" => Some("javascript"),
        "ts" | "tsx" => Some("typescript"),
        "java" | "jav" => Some("java"),
        "cpp" | "hpp" | "cc" | "cxx" | "c++" | "h" | "hh" | "hxx" | "h++" => Some("cpp"),
        "c" => Some("c"),
        "cs" => Some("csharp"),
        "rb" | "rbw" | "rake" | "gemspec" => Some("ruby"),
        "php" | "phtml" | "php3" | "php4" | "php5" => Some("php"),
        "go" => Some("go"),
        "rs" => Some("rust"),
        "swift" => Some("swift"),
        "kt" | "kts" => Some("kotlin"),
        "scala" | "sc" => Some("scala"),
        "html" | "htm" | "xhtml" => Some("html"),
        "css" => Some("css"),
        "scss" => Some("scss"),
        "sass" => Some("sass"),
        "less" => Some("less"),
        "sh" | "bash" | "zsh" | "fish" => Some("shell"),
        "ps1" | "psm1" | "psd1" => Some("powershell"),
        "pl" | "pm" | "t" => Some("perl"),
        "r" | "rmd" => Some("r"),
        "lua" => Some("lua"),
        "hs" | "lhs" => Some("haskell"),
        "jl" => Some("julia"),
        "dart" => Some("dart"),
        "vb" | "bas" | "vbs" => Some("vb"),
        "m" | "mm" => Some("objectivec"),
        "asm" | "s" => Some("assembly"),
        "sql" => Some("sql"),
        "md" | "markdown" => Some("markdown"),
        "xml" | "xsl" | "xsd" => Some("xml"),
        "json" => Some("json"),
        "yml" | "yaml" => Some("yaml"),
        "proto" => Some("protobuf"),
        "groovy" | "gvy" => Some("groovy"),
        "fs" | "fsi" | "fsx" => Some("fsharp"),
        "clj" | "cljs" | "cljc" => Some("clojure"),
        "ex" | "exs" => Some("elixir"),
        "erl" | "hrl" => Some("erlang"),
        _ => None,
    }
}

pub fn parse_patch_filename(filename: &str) -> Result<(String, String, String), String> {
    let Some(stem) = filename.strip_suffix(".patch") else {
        return Err(format!("Invalid patch filename format: {filename}"));
    };
    let Some(rest) = stem.strip_prefix("github.com_") else {
        return Err(format!("Invalid patch filename format: {filename}"));
    };
    let mut segments = rest.split('_').collect::<Vec<_>>();
    if segments.len() < 3 {
        return Err(format!("Invalid patch filename format: {filename}"));
    }
    let commit = segments.pop().unwrap_or_default().to_string();
    let repo_name = segments.pop().unwrap_or_default().to_string();
    let repo_owner = segments.join("/");
    if repo_owner.is_empty() || repo_name.is_empty() || commit.is_empty() {
        return Err(format!("Invalid patch filename format: {filename}"));
    }
    Ok((repo_owner, repo_name, commit))
}

pub fn process_patch_text(filename: &str, content: &str) -> Option<PatchInfo> {
    let (repo_owner, repo_name, commit_id) = parse_patch_filename(filename).ok()?;
    if content.trim().is_empty() {
        return None;
    }

    let mut file_changes = Vec::new();
    let mut current_file = None::<String>;
    let mut current_changes = Vec::new();
    let mut first_language = None::<String>;

    for line in content.lines() {
        if line.starts_with("diff --git ") {
            flush_file_change(
                &mut file_changes,
                &mut current_file,
                &mut current_changes,
                &mut first_language,
            );
            current_file = line.split_whitespace().nth(3).map(|path| {
                path.trim_start_matches("a/")
                    .trim_start_matches("b/")
                    .to_string()
            });
            current_changes.clear();
            continue;
        }

        if current_file.is_some() && (line.starts_with('+') || line.starts_with('-')) {
            current_changes.push(line.to_string());
        }
    }

    flush_file_change(
        &mut file_changes,
        &mut current_file,
        &mut current_changes,
        &mut first_language,
    );

    if file_changes.is_empty() {
        return None;
    }

    Some(PatchInfo {
        repo_owner,
        repo_name,
        commit_id,
        file_changes,
    })
}

fn flush_file_change(
    file_changes: &mut Vec<FileChange>,
    current_file: &mut Option<String>,
    current_changes: &mut Vec<String>,
    first_language: &mut Option<String>,
) {
    let Some(file_path) = current_file.take() else {
        return;
    };
    let Some(language) = get_language_from_file(&file_path).map(ToString::to_string) else {
        current_changes.clear();
        return;
    };

    if let Some(expected) = first_language.as_deref() {
        if expected != language {
            current_changes.clear();
            return;
        }
    } else {
        *first_language = Some(language.clone());
    }

    file_changes.push(FileChange {
        file_path,
        changes: current_changes.join("\n"),
        language,
    });
    current_changes.clear();
}

#[cfg(test)]
mod tests {
    use super::{get_language_from_file, parse_patch_filename, process_patch_text};

    #[test]
    fn parses_patch_filename_components() {
        let (owner, repo, commit) =
            parse_patch_filename("github.com_org_team_demo_deadbeef.patch").expect("filename");

        assert_eq!(owner, "org/team");
        assert_eq!(repo, "demo");
        assert_eq!(commit, "deadbeef");
    }

    #[test]
    fn detects_languages_from_extensions() {
        assert_eq!(get_language_from_file("src/app.py"), Some("python"));
        assert_eq!(get_language_from_file("src/app.ts"), Some("typescript"));
        assert_eq!(get_language_from_file("README"), None);
    }

    #[test]
    fn processes_first_language_group_from_patch_text() {
        let patch = r#"
diff --git a/src/app.py b/src/app.py
--- a/src/app.py
+++ b/src/app.py
@@
-dangerous_call(user_input)
+safe_call(user_input)
diff --git a/frontend/index.ts b/frontend/index.ts
--- a/frontend/index.ts
+++ b/frontend/index.ts
@@
-legacy()
+modern()
"#;

        let patch_info =
            process_patch_text("github.com_octo_demo_deadbeef.patch", patch).expect("patch info");

        assert_eq!(patch_info.repo_owner, "octo");
        assert_eq!(patch_info.repo_name, "demo");
        assert_eq!(patch_info.commit_id, "deadbeef");
        assert_eq!(patch_info.file_changes.len(), 1);
        assert_eq!(patch_info.file_changes[0].file_path, "src/app.py");
        assert_eq!(patch_info.file_changes[0].language, "python");
        assert!(patch_info.file_changes[0]
            .changes
            .contains("-dangerous_call(user_input)"));
    }
}
