use std::env;

/// Resolve the container runtime binary path.
/// Checks env vars in order: Argus_PODMAN_BIN, BACKEND_PODMAN_BIN, Argus_CONTAINER_BIN, BACKEND_CONTAINER_BIN.
/// Falls back to "podman" if none are set.
pub fn container_runtime_bin() -> String {
    [
        "Argus_PODMAN_BIN",
        "BACKEND_PODMAN_BIN",
        "Argus_CONTAINER_BIN",
        "BACKEND_CONTAINER_BIN",
    ]
    .iter()
    .find_map(|key| {
        env::var(key)
            .ok()
            .map(|value| value.trim().to_string())
            .filter(|value| !value.is_empty())
    })
    .unwrap_or_else(|| "podman".to_string())
}
