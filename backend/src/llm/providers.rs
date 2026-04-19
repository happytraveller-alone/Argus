use serde::Serialize;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum RuntimeProvider {
    Gemini,
    OpenAi,
    Claude,
    Qwen,
    Deepseek,
    Zhipu,
    Moonshot,
    Baidu,
    Minimax,
    Doubao,
    Ollama,
}

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

const PREFERRED_ORDER: &[&str] = &[
    "custom",
    "openai",
    "openrouter",
    "anthropic",
    "azure_openai",
    "moonshot",
    "ollama",
];

const CATALOG_PROVIDER_IDS: &[&str] = &[
    "gemini",
    "openai",
    "anthropic",
    "qwen",
    "deepseek",
    "zhipu",
    "moonshot",
    "baidu",
    "minimax",
    "doubao",
    "ollama",
    "custom",
    "openrouter",
    "azure_openai",
];

pub fn normalize_provider_id(provider: &str) -> String {
    let normalized = provider.trim().to_ascii_lowercase();
    if normalized.is_empty() {
        return String::new();
    }

    match normalized.as_str() {
        "claude" => "anthropic".to_string(),
        "openai_compatible" => "custom".to_string(),
        _ => normalized,
    }
}

pub fn provider_catalog() -> Vec<ProviderCatalogItem> {
    let mut providers = CATALOG_PROVIDER_IDS
        .iter()
        .map(|provider_id| build_provider_item(provider_id))
        .collect::<Vec<_>>();
    providers.sort_by_key(|item| {
        (
            PREFERRED_ORDER
                .iter()
                .position(|preferred| preferred == &item.id)
                .unwrap_or(usize::MAX),
            item.id.clone(),
        )
    });
    providers
}

pub fn provider_api_key_field(provider: &str) -> Option<&'static str> {
    match provider {
        "custom" | "openai" | "openrouter" | "azure_openai" => Some("openaiApiKey"),
        "anthropic" | "claude" => Some("claudeApiKey"),
        "gemini" => Some("geminiApiKey"),
        "qwen" => Some("qwenApiKey"),
        "deepseek" => Some("deepseekApiKey"),
        "zhipu" => Some("zhipuApiKey"),
        "moonshot" => Some("moonshotApiKey"),
        "baidu" => Some("baiduApiKey"),
        "minimax" => Some("minimaxApiKey"),
        "doubao" => Some("doubaoApiKey"),
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
    let provider_id = if normalized.is_empty() {
        "openai".to_string()
    } else {
        normalized
    };

    provider_catalog()
        .into_iter()
        .find(|item| item.id == provider_id)
        .unwrap_or_else(|| ProviderCatalogItem {
            id: provider_id.clone(),
            name: provider_id.clone(),
            description: "自定义模型提供商".to_string(),
            default_model: String::new(),
            models: Vec::new(),
            default_base_url: String::new(),
            requires_api_key: provider_id != "ollama",
            supports_model_fetch: true,
            fetch_style: "openai_compatible".to_string(),
            example_base_urls: Vec::new(),
            supports_custom_headers: true,
        })
}

fn build_provider_item(provider_id: &str) -> ProviderCatalogItem {
    let runtime_provider = runtime_provider_for(provider_id);
    let default_model = provider_default_model(provider_id, runtime_provider);
    let models = provider_models(provider_id, runtime_provider);
    let default_base_url = provider_default_base_url(provider_id, runtime_provider);
    let (
        name,
        description,
        requires_api_key,
        supports_model_fetch,
        fetch_style,
        example_base_urls,
        supports_custom_headers,
    ) = provider_meta(provider_id, runtime_provider);

    ProviderCatalogItem {
        id: provider_id.to_string(),
        name,
        description,
        default_model,
        models,
        default_base_url,
        requires_api_key,
        supports_model_fetch,
        fetch_style,
        example_base_urls,
        supports_custom_headers,
    }
}

fn runtime_provider_for(provider_id: &str) -> Option<RuntimeProvider> {
    match normalize_provider_id(provider_id).as_str() {
        "gemini" => Some(RuntimeProvider::Gemini),
        "openai" => Some(RuntimeProvider::OpenAi),
        "anthropic" => Some(RuntimeProvider::Claude),
        "qwen" => Some(RuntimeProvider::Qwen),
        "deepseek" => Some(RuntimeProvider::Deepseek),
        "zhipu" => Some(RuntimeProvider::Zhipu),
        "moonshot" => Some(RuntimeProvider::Moonshot),
        "baidu" => Some(RuntimeProvider::Baidu),
        "minimax" => Some(RuntimeProvider::Minimax),
        "doubao" => Some(RuntimeProvider::Doubao),
        "ollama" => Some(RuntimeProvider::Ollama),
        "openrouter" | "azure_openai" | "custom" => Some(RuntimeProvider::OpenAi),
        _ => None,
    }
}

fn provider_default_model(provider_id: &str, runtime_provider: Option<RuntimeProvider>) -> String {
    match provider_id {
        "custom" | "openrouter" | "azure_openai" => "gpt-5".to_string(),
        _ => runtime_provider
            .map(default_model_for_runtime)
            .unwrap_or_default()
            .to_string(),
    }
}

fn provider_models(_provider_id: &str, runtime_provider: Option<RuntimeProvider>) -> Vec<String> {
    runtime_provider
        .map(models_for_runtime)
        .unwrap_or(&[])
        .iter()
        .map(|model| (*model).to_string())
        .collect::<Vec<_>>()
}

fn provider_default_base_url(
    provider_id: &str,
    runtime_provider: Option<RuntimeProvider>,
) -> String {
    match provider_id {
        "custom" => String::new(),
        "openrouter" => "https://openrouter.ai/api/v1".to_string(),
        "azure_openai" => "https://{resource}.openai.azure.com/openai/v1".to_string(),
        _ => runtime_provider
            .map(default_base_url_for_runtime)
            .unwrap_or_default()
            .to_string(),
    }
}

#[allow(clippy::type_complexity)]
fn provider_meta(
    provider_id: &str,
    runtime_provider: Option<RuntimeProvider>,
) -> (String, String, bool, bool, String, Vec<String>, bool) {
    match provider_id {
        "custom" => (
            "OpenAI Compatible".to_string(),
            "适用于 OpenAI 兼容站点、中转服务和自建网关。".to_string(),
            true,
            true,
            "openai_compatible".to_string(),
            vec![
                "https://api.openai.com/v1".to_string(),
                "https://api.moonshot.cn/v1".to_string(),
                "http://localhost:11434/v1".to_string(),
            ],
            true,
        ),
        "openai" => (
            "OpenAI".to_string(),
            "OpenAI 官方接口。".to_string(),
            true,
            true,
            "openai_compatible".to_string(),
            vec!["https://api.openai.com/v1".to_string()],
            true,
        ),
        "openrouter" => (
            "OpenRouter".to_string(),
            "OpenRouter 聚合网关（OpenAI 兼容）。".to_string(),
            true,
            true,
            "openai_compatible".to_string(),
            vec!["https://openrouter.ai/api/v1".to_string()],
            true,
        ),
        "anthropic" => (
            "Anthropic".to_string(),
            "Anthropic Claude 官方接口。".to_string(),
            true,
            true,
            "anthropic".to_string(),
            vec!["https://api.anthropic.com/v1".to_string()],
            true,
        ),
        "azure_openai" => (
            "Azure OpenAI".to_string(),
            "Azure 托管 OpenAI 接口。".to_string(),
            true,
            true,
            "azure_openai".to_string(),
            vec!["https://{resource}.openai.azure.com/openai/v1".to_string()],
            true,
        ),
        "moonshot" => (
            "Moonshot / Kimi".to_string(),
            "Moonshot Kimi 官方接口（OpenAI 兼容）。".to_string(),
            true,
            true,
            "openai_compatible".to_string(),
            vec!["https://api.moonshot.cn/v1".to_string()],
            true,
        ),
        "ollama" => (
            "Ollama".to_string(),
            "本地部署 LLM（OpenAI 兼容，无需 API Key）。".to_string(),
            false,
            true,
            "openai_compatible".to_string(),
            vec!["http://localhost:11434/v1".to_string()],
            true,
        ),
        "baidu" | "minimax" | "doubao" => (
            provider_id.to_ascii_uppercase(),
            format!("{provider_id} 模型服务"),
            true,
            false,
            "native_static".to_string(),
            Vec::new(),
            true,
        ),
        _ => (
            provider_id.to_ascii_uppercase(),
            format!("{provider_id} 模型服务"),
            runtime_provider != Some(RuntimeProvider::Ollama),
            true,
            "openai_compatible".to_string(),
            Vec::new(),
            true,
        ),
    }
}

fn default_model_for_runtime(provider: RuntimeProvider) -> &'static str {
    match provider {
        RuntimeProvider::Gemini => "gemini-3-pro",
        RuntimeProvider::OpenAi => "gpt-5",
        RuntimeProvider::Claude => "claude-sonnet-4.5",
        RuntimeProvider::Qwen => "qwen3-max-instruct",
        RuntimeProvider::Deepseek => "deepseek-v3.1-terminus",
        RuntimeProvider::Zhipu => "glm-4.6",
        RuntimeProvider::Moonshot => "kimi-k2",
        RuntimeProvider::Baidu => "ernie-4.5",
        RuntimeProvider::Minimax => "minimax-m2",
        RuntimeProvider::Doubao => "doubao-1.6-pro",
        RuntimeProvider::Ollama => "llama3.3-70b",
    }
}

fn default_base_url_for_runtime(provider: RuntimeProvider) -> &'static str {
    match provider {
        RuntimeProvider::Gemini => "https://generativelanguage.googleapis.com/v1beta",
        RuntimeProvider::OpenAi => "https://api.openai.com/v1",
        RuntimeProvider::Claude => "https://api.anthropic.com/v1",
        RuntimeProvider::Qwen => "https://dashscope.aliyuncs.com/compatible-mode/v1",
        RuntimeProvider::Deepseek => "https://api.deepseek.com",
        RuntimeProvider::Zhipu => "https://open.bigmodel.cn/api/paas/v4",
        RuntimeProvider::Moonshot => "https://api.moonshot.cn/v1",
        RuntimeProvider::Baidu => "https://aip.baidubce.com/rpc/2.0/ai_custom/v1",
        RuntimeProvider::Minimax => "https://api.minimax.chat/v1",
        RuntimeProvider::Doubao => "https://ark.cn-beijing.volces.com/api/v3",
        RuntimeProvider::Ollama => "http://localhost:11434/v1",
    }
}

fn models_for_runtime(provider: RuntimeProvider) -> &'static [&'static str] {
    match provider {
        RuntimeProvider::Gemini => &[
            "gemini-3-pro",
            "gemini-3.0-deep-think",
            "gemini-2.5-flash",
            "gemini-2.5-pro",
            "gemini-2.5-flash-lite",
            "gemini-2.5-flash-live-api",
            "veo-3.1",
            "veo-3.1-fast",
        ],
        RuntimeProvider::OpenAi => &[
            "gpt-5",
            "gpt-5.1",
            "gpt-5.1-instant",
            "gpt-5.1-codex-max",
            "gpt-4o",
            "gpt-4o-mini",
            "gpt-4.5",
            "o4-mini",
            "o3",
            "o3-mini",
            "gpt-oss-120b",
            "gpt-oss-20b",
        ],
        RuntimeProvider::Claude => &[
            "claude-opus-4.5",
            "claude-sonnet-4.5",
            "claude-haiku-4.5",
            "claude-sonnet-4",
            "claude-opus-4",
            "claude-3.7-sonnet",
            "claude-3.5-sonnet",
            "claude-3.5-haiku",
            "claude-3-opus",
        ],
        RuntimeProvider::Qwen => &[
            "qwen3-max-instruct",
            "qwen3-235b-a22b",
            "qwen3-turbo",
            "qwen3-32b",
            "qwen3-4b",
            "qwen3-embedding-8b",
            "qwen-image",
            "qwen-vl",
            "qwen-audio",
        ],
        RuntimeProvider::Deepseek => &[
            "deepseek-v3.1-terminus",
            "deepseek-r1-70b",
            "deepseek-r1-zero",
            "deepseek-v3.2-exp",
            "deepseek-chat",
            "deepseek-reasoner",
            "deepseek-ocr",
        ],
        RuntimeProvider::Zhipu => &[
            "glm-4.6",
            "glm-4.6-reap-218b",
            "glm-4.5",
            "glm-4.5v",
            "glm-4.5-air-106b",
            "glm-4-flash",
            "glm-4v-flash",
            "glm-4.1v-thinking",
        ],
        RuntimeProvider::Moonshot => &[
            "kimi-k2",
            "kimi-k2-thinking",
            "kimi-k2-instruct-0905",
            "kimi-k1.5",
            "kimi-vl",
            "kimi-dev-72b",
            "kimi-researcher",
            "kimi-linear",
        ],
        RuntimeProvider::Baidu => &[
            "ernie-4.5",
            "ernie-4.5-21b-a3b-thinking",
            "ernie-4.0-8k",
            "ernie-3.5-8k",
            "ernie-vl",
        ],
        RuntimeProvider::Minimax => &[
            "minimax-m2",
            "minimax-01-text",
            "minimax-01-vl",
            "minimax-m1",
            "speech-2.6",
            "hailuo-02",
            "music-1.5",
        ],
        RuntimeProvider::Doubao => &[
            "doubao-1.6-pro",
            "doubao-1.5-pro",
            "doubao-seed-code",
            "doubao-seed-1.6",
            "doubao-vision-language",
        ],
        RuntimeProvider::Ollama => &[
            "llama3.3-70b",
            "qwen3-8b",
            "gemma3-27b",
            "dolphin-3.0-llama3.1-8b",
            "cogito-v1",
            "deepseek-r1",
            "gpt-oss-120b",
            "llama3.1-405b",
            "mistral-nemo",
            "phi-3",
        ],
    }
}

#[cfg(test)]
mod tests {
    use super::{
        normalize_provider_id, provider_api_key_field, provider_catalog,
        provider_catalog_entry_or_fallback, recommend_tokens,
    };

    #[test]
    fn provider_catalog_uses_preferred_order_and_richer_models() {
        let catalog = provider_catalog();
        let ids: Vec<&str> = catalog.iter().map(|item| item.id.as_str()).collect();
        assert_eq!(
            &ids[..7],
            &[
                "custom",
                "openai",
                "openrouter",
                "anthropic",
                "azure_openai",
                "moonshot",
                "ollama",
            ]
        );

        let gemini = catalog
            .iter()
            .find(|item| item.id == "gemini")
            .expect("gemini provider should exist");
        assert!(gemini.models.iter().any(|model| model == "veo-3.1"));
    }

    #[test]
    fn provider_helpers_cover_runtime_metadata() {
        let baidu = provider_catalog()
            .into_iter()
            .find(|item| item.id == "baidu")
            .expect("baidu provider should exist");
        assert_eq!(baidu.fetch_style, "native_static");
        assert!(!baidu.supports_model_fetch);
        assert_eq!(provider_api_key_field("anthropic"), Some("claudeApiKey"));
        assert_eq!(recommend_tokens("gpt-5.1-codex-max"), 16_384);
        assert_eq!(recommend_tokens("llama3.3-70b"), 8_192);
    }

    #[test]
    fn provider_aliases_and_fallback_match_python_contract() {
        assert_eq!(normalize_provider_id("claude"), "anthropic");
        assert_eq!(normalize_provider_id("openai_compatible"), "custom");
        assert_eq!(normalize_provider_id(" openrouter "), "openrouter");

        let fallback = provider_catalog_entry_or_fallback("my-gateway");
        assert_eq!(fallback.id, "my-gateway");
        assert_eq!(fallback.fetch_style, "openai_compatible");
        assert!(fallback.models.is_empty());
    }
}
