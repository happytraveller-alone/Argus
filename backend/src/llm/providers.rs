use serde::Serialize;

#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct ProviderCatalogItem {
    pub id: String,
    pub name: String,
    pub description: String,
    pub default_model: String,
    pub models: Vec<String>,
    pub default_base_url: String,
    pub requires_api_key: bool,
    pub supports_model_fetch: bool,
    pub fetch_style: String,
    pub example_base_urls: Vec<String>,
    pub supports_custom_headers: bool,
}

const SUPPORTED_PROVIDER_IDS: &[&str] = &[
    "openai_compatible",
    "anthropic_compatible",
    "kimi_compatible",
    "pi_compatible",
];

pub fn normalize_provider_id(provider: &str) -> String {
    provider.trim().to_ascii_lowercase()
}

pub fn is_supported_protocol_provider(provider: &str) -> bool {
    SUPPORTED_PROVIDER_IDS.contains(&normalize_provider_id(provider).as_str())
}

pub fn provider_catalog() -> Vec<ProviderCatalogItem> {
    vec![
        ProviderCatalogItem {
            id: "openai_compatible".to_string(),
            name: "OpenAI Compatible".to_string(),
            description: "适用于 OpenAI 兼容站点、中转服务和自建网关。".to_string(),
            default_model: "gpt-5".to_string(),
            models: vec![
                "gpt-5".to_string(),
                "gpt-5.1".to_string(),
                "gpt-4o".to_string(),
                "qwen-max".to_string(),
                "deepseek-chat".to_string(),
            ],
            default_base_url: "https://api.openai.com/v1".to_string(),
            requires_api_key: true,
            supports_model_fetch: true,
            fetch_style: "openai_compatible".to_string(),
            example_base_urls: vec![
                "https://api.openai.com/v1".to_string(),
                "http://localhost:11434/v1".to_string(),
            ],
            supports_custom_headers: true,
        },
        ProviderCatalogItem {
            id: "anthropic_compatible".to_string(),
            name: "Anthropic Compatible".to_string(),
            description: "适用于 Anthropic Messages 兼容接口。".to_string(),
            default_model: "claude-sonnet-4.5".to_string(),
            models: vec![
                "claude-sonnet-4.5".to_string(),
                "claude-opus-4.5".to_string(),
                "claude-haiku-4.5".to_string(),
            ],
            default_base_url: "https://api.anthropic.com/v1".to_string(),
            requires_api_key: true,
            supports_model_fetch: true,
            fetch_style: "anthropic_compatible".to_string(),
            example_base_urls: vec!["https://api.anthropic.com/v1".to_string()],
            supports_custom_headers: true,
        },
    ]
}

pub fn provider_api_key_field(provider: &str) -> Option<&'static str> {
    match normalize_provider_id(provider).as_str() {
        "openai_compatible" | "anthropic_compatible" => Some("llmApiKey"),
        "kimi_compatible" => Some("KIMI_API_KEY"),
        "pi_compatible" => Some("PI_API_KEY"),
        _ => None,
    }
}

pub fn recommend_tokens(model: &str) -> i64 {
    let normalized = model.to_ascii_lowercase();
    if [
        "gpt-5", "o3", "o4", "claude", "deepseek", "kimi", "glm", "gemini",
    ]
    .iter()
    .any(|hint| normalized.contains(hint))
    {
        16_384
    } else {
        8_192
    }
}

pub fn provider_catalog_entry_or_fallback(provider: &str) -> ProviderCatalogItem {
    let normalized = normalize_provider_id(provider);
    provider_catalog()
        .into_iter()
        .find(|item| item.id == normalized)
        .unwrap_or_else(|| ProviderCatalogItem {
            id: normalized,
            name: "Unsupported provider".to_string(),
            description: "不支持的旧版或未知模型协议。".to_string(),
            default_model: String::new(),
            models: Vec::new(),
            default_base_url: String::new(),
            requires_api_key: true,
            supports_model_fetch: false,
            fetch_style: "openai_compatible".to_string(),
            example_base_urls: Vec::new(),
            supports_custom_headers: false,
        })
}

#[cfg(test)]
mod tests {
    use super::{
        is_supported_protocol_provider, normalize_provider_id, provider_api_key_field,
        provider_catalog,
    };

    #[test]
    fn provider_catalog_exposes_only_protocol_providers() {
        let providers = provider_catalog();
        assert_eq!(providers.len(), 2);
        assert_eq!(providers[0].id, "openai_compatible");
        assert_eq!(providers[1].id, "anthropic_compatible");
    }

    #[test]
    fn provider_normalization_does_not_legacy_alias() {
        assert_eq!(
            normalize_provider_id(" OpenAI_Compatible "),
            "openai_compatible"
        );
        assert_eq!(normalize_provider_id("claude"), "claude");
        assert!(!is_supported_protocol_provider("openai"));
        assert!(!is_supported_protocol_provider("claude"));
    }

    #[test]
    fn protocol_providers_use_canonical_api_key_field() {
        assert_eq!(
            provider_api_key_field("openai_compatible"),
            Some("llmApiKey")
        );
        assert_eq!(
            provider_api_key_field("anthropic_compatible"),
            Some("llmApiKey")
        );
        assert_eq!(provider_api_key_field("openai"), None);
    }
}
