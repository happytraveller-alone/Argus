use std::path::{Path, PathBuf};

pub const PIPELINE_RELATIVE_PATH: &str = "agentflow/pipelines/intelligent_audit.py";
pub const SOURCE_PIPELINE_PATH: &str = "backend/agentflow/pipelines/intelligent_audit.py";

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct PipelinePathResolution {
    pub path: PathBuf,
    pub exists: bool,
    pub candidates: Vec<PathBuf>,
}

pub fn resolve_agentflow_pipeline_path() -> PipelinePathResolution {
    resolve_agentflow_pipeline_path_with_roots(
        Path::new("."),
        Path::new("/app/backend"),
        Path::new("."),
    )
}

pub fn resolve_agentflow_pipeline_path_with_roots(
    source_root: &Path,
    packaged_backend_root: &Path,
    backend_cwd_root: &Path,
) -> PipelinePathResolution {
    let candidates = vec![
        source_root.join(SOURCE_PIPELINE_PATH),
        packaged_backend_root.join(PIPELINE_RELATIVE_PATH),
        backend_cwd_root.join(PIPELINE_RELATIVE_PATH),
    ];
    let selected = candidates
        .iter()
        .find(|path| path.exists())
        .cloned()
        .unwrap_or_else(|| candidates[0].clone());

    PipelinePathResolution {
        exists: selected.exists(),
        path: selected,
        candidates,
    }
}

pub fn display_candidates(candidates: &[PathBuf]) -> Vec<String> {
    candidates
        .iter()
        .map(|path| path.display().to_string())
        .collect()
}

#[cfg(test)]
mod tests {
    use super::*;

    fn touch(path: &Path) {
        std::fs::create_dir_all(path.parent().expect("parent")).expect("create parent");
        std::fs::write(path, "# pipeline").expect("write pipeline");
    }

    #[test]
    fn resolves_source_checkout_pipeline_first() {
        let temp_dir = tempfile::tempdir().expect("temp dir");
        let source_pipeline = temp_dir.path().join(SOURCE_PIPELINE_PATH);
        let packaged_root = temp_dir.path().join("app/backend");
        touch(&source_pipeline);
        touch(&packaged_root.join(PIPELINE_RELATIVE_PATH));

        let resolution = resolve_agentflow_pipeline_path_with_roots(
            temp_dir.path(),
            &packaged_root,
            temp_dir.path(),
        );

        assert_eq!(resolution.path, source_pipeline);
        assert!(resolution.exists);
    }

    #[test]
    fn resolves_packaged_runtime_pipeline_when_source_missing() {
        let temp_dir = tempfile::tempdir().expect("temp dir");
        let packaged_root = temp_dir.path().join("app/backend");
        let packaged_pipeline = packaged_root.join(PIPELINE_RELATIVE_PATH);
        touch(&packaged_pipeline);

        let resolution = resolve_agentflow_pipeline_path_with_roots(
            temp_dir.path(),
            &packaged_root,
            temp_dir.path(),
        );

        assert_eq!(resolution.path, packaged_pipeline);
        assert!(resolution.exists);
    }

    #[test]
    fn missing_resolution_preserves_all_checked_candidates() {
        let temp_dir = tempfile::tempdir().expect("temp dir");
        let packaged_root = temp_dir.path().join("app/backend");

        let resolution = resolve_agentflow_pipeline_path_with_roots(
            temp_dir.path(),
            &packaged_root,
            temp_dir.path(),
        );
        let displayed = display_candidates(&resolution.candidates);

        assert!(!resolution.exists);
        assert_eq!(resolution.path, temp_dir.path().join(SOURCE_PIPELINE_PATH));
        assert_eq!(resolution.candidates.len(), 3);
        assert!(displayed.contains(
            &temp_dir
                .path()
                .join(SOURCE_PIPELINE_PATH)
                .display()
                .to_string()
        ));
        assert!(displayed.contains(
            &packaged_root
                .join(PIPELINE_RELATIVE_PATH)
                .display()
                .to_string()
        ));
        assert!(displayed.contains(
            &temp_dir
                .path()
                .join(PIPELINE_RELATIVE_PATH)
                .display()
                .to_string()
        ));
    }
}
