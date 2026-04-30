pub const HTTPS_ONLY_REPOSITORY_ERROR: &str = "仅支持 HTTPS 仓库地址，不再支持 SSH 地址";

pub fn is_ssh_git_url(url: &str) -> bool {
    let text = url.trim();
    !text.is_empty() && (text.starts_with("git@") || text.starts_with("ssh://"))
}

pub fn ensure_supported_repository_url(url: &str) -> Result<(), &'static str> {
    if is_ssh_git_url(url) {
        return Err(HTTPS_ONLY_REPOSITORY_ERROR);
    }
    Ok(())
}

pub fn has_url_auth(url: &str) -> bool {
    let Some(host_start) = url.find("://").map(|idx| idx + 3) else {
        return false;
    };
    let remainder = &url[host_start..];
    let authority = remainder.split('/').next().unwrap_or_default();
    authority.contains('@')
}

pub fn build_mirror_url(original_url: &str, mirror_prefix: &str) -> String {
    let raw_url = original_url.trim();
    let raw_prefix = mirror_prefix.trim();
    if raw_url.is_empty() || raw_prefix.is_empty() {
        return raw_url.to_string();
    }
    if raw_prefix.contains("{url}") {
        return raw_prefix.replace("{url}", raw_url);
    }
    format!("{}/{}", raw_prefix.trim_end_matches('/'), raw_url)
}

pub fn should_use_mirror(
    url: &str,
    enabled: bool,
    allow_auth_url: bool,
    allow_hosts: &[String],
) -> bool {
    let text = url.trim();
    if text.is_empty() || !enabled || is_ssh_git_url(text) {
        return false;
    }

    let Some((scheme, authority)) = split_url_components(text) else {
        return false;
    };
    if !scheme.eq_ignore_ascii_case("http") && !scheme.eq_ignore_ascii_case("https") {
        return false;
    }

    if !host_in_allow_list(host_from_authority(authority), allow_hosts) {
        return false;
    }
    if !allow_auth_url && has_url_auth(text) {
        return false;
    }
    true
}

pub fn get_mirror_candidates(
    original_url: &str,
    enabled: bool,
    mirror_prefix: Option<&str>,
    mirror_prefixes: Option<&str>,
    allow_hosts: Option<&str>,
    allow_auth_url: bool,
    fallback_to_origin: bool,
) -> Vec<String> {
    let raw_url = original_url.trim();
    if raw_url.is_empty() {
        return Vec::new();
    }

    let hosts = split_csv(allow_hosts.unwrap_or("github.com"))
        .into_iter()
        .map(|value| value.to_lowercase())
        .collect::<Vec<_>>();
    if !should_use_mirror(raw_url, enabled, allow_auth_url, &hosts) {
        return vec![raw_url.to_string()];
    }

    let mut prefixes = split_csv(mirror_prefixes.unwrap_or_default());
    if prefixes.is_empty() {
        if let Some(prefix) = mirror_prefix
            .map(str::trim)
            .filter(|prefix| !prefix.is_empty())
        {
            prefixes.push(prefix.to_string());
        }
    }

    let mut candidates = Vec::new();
    for prefix in prefixes {
        let candidate = build_mirror_url(raw_url, &prefix);
        if !candidate.is_empty() && !candidates.iter().any(|existing| existing == &candidate) {
            candidates.push(candidate);
        }
    }

    if fallback_to_origin && !candidates.iter().any(|existing| existing == raw_url) {
        candidates.push(raw_url.to_string());
    }

    if candidates.is_empty() {
        vec![raw_url.to_string()]
    } else {
        candidates
    }
}

fn split_csv(raw: &str) -> Vec<String> {
    raw.split(',')
        .map(str::trim)
        .filter(|value| !value.is_empty())
        .map(ToString::to_string)
        .collect()
}

fn split_url_components(url: &str) -> Option<(&str, &str)> {
    let (scheme, remainder) = url.split_once("://")?;
    let authority = remainder.split('/').next().unwrap_or_default();
    Some((scheme.trim(), authority))
}

fn host_from_authority(authority: &str) -> String {
    let without_auth = authority
        .rsplit_once('@')
        .map(|(_, value)| value)
        .unwrap_or(authority);
    let host = without_auth.split(':').next().unwrap_or_default().trim();
    host.to_ascii_lowercase()
}

fn host_in_allow_list(host: String, allow_hosts: &[String]) -> bool {
    if host.is_empty() || allow_hosts.is_empty() {
        return false;
    }
    allow_hosts.iter().any(|candidate| {
        let normalized = candidate.trim().to_ascii_lowercase();
        !normalized.is_empty() && (host == normalized || host.ends_with(&format!(".{normalized}")))
    })
}

#[cfg(test)]
mod tests {
    use super::{
        ensure_supported_repository_url, get_mirror_candidates, HTTPS_ONLY_REPOSITORY_ERROR,
    };

    #[test]
    fn mirror_candidates_keep_order_and_dedup() {
        let candidates = get_mirror_candidates(
            "https://github.com/example/repo.git",
            true,
            None,
            Some("https://a.example, https://a.example,https://b.example"),
            Some("github.com"),
            false,
            false,
        );

        assert_eq!(
            candidates,
            vec![
                "https://a.example/https://github.com/example/repo.git".to_string(),
                "https://b.example/https://github.com/example/repo.git".to_string(),
            ]
        );
    }

    #[test]
    fn mirror_candidates_skip_origin_without_fallback() {
        let candidates = get_mirror_candidates(
            "https://github.com/example/repo.git",
            true,
            None,
            Some("https://a.example,https://b.example"),
            Some("github.com"),
            false,
            false,
        );

        assert!(!candidates
            .iter()
            .any(|candidate| candidate == "https://github.com/example/repo.git"));
    }

    #[test]
    fn mirror_candidates_append_origin_when_fallback_enabled() {
        let candidates = get_mirror_candidates(
            "https://github.com/example/repo.git",
            true,
            None,
            Some("https://a.example,https://b.example"),
            Some("github.com"),
            false,
            true,
        );

        assert_eq!(
            candidates,
            vec![
                "https://a.example/https://github.com/example/repo.git".to_string(),
                "https://b.example/https://github.com/example/repo.git".to_string(),
                "https://github.com/example/repo.git".to_string(),
            ]
        );
    }

    #[test]
    fn mirror_candidates_fall_back_to_single_prefix() {
        let candidates = get_mirror_candidates(
            "https://github.com/example/repo.git",
            true,
            Some("https://single.example"),
            Some(""),
            Some("github.com"),
            false,
            false,
        );

        assert_eq!(
            candidates,
            vec!["https://single.example/https://github.com/example/repo.git".to_string()]
        );
    }

    #[test]
    fn mirror_candidates_respect_allow_auth_url_false() {
        let candidates = get_mirror_candidates(
            "https://token@github.com/example/repo.git",
            true,
            None,
            Some("https://a.example,https://b.example"),
            Some("github.com"),
            false,
            true,
        );

        assert_eq!(
            candidates,
            vec!["https://token@github.com/example/repo.git".to_string()]
        );
    }

    #[test]
    fn mirror_candidates_respect_allow_host_list() {
        let candidates = get_mirror_candidates(
            "https://gitlab.com/example/repo.git",
            true,
            None,
            Some("https://a.example,https://b.example"),
            Some("github.com"),
            false,
            true,
        );

        assert_eq!(
            candidates,
            vec!["https://gitlab.com/example/repo.git".to_string()]
        );
    }

    #[test]
    fn ssh_urls_are_rejected() {
        let error = ensure_supported_repository_url("git@github.com:octo/repo.git")
            .expect_err("ssh url should be rejected");

        assert_eq!(error, HTTPS_ONLY_REPOSITORY_ERROR);
    }
}
