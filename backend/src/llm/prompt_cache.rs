use serde::{Deserialize, Serialize};
use serde_json::{json, Value};

#[derive(Debug, Clone, Copy, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum CacheStrategy {
    None,
    SystemOnly,
    SystemAndEarly,
    MultiPoint,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "camelCase")]
pub struct CacheConfig {
    pub enabled: bool,
    pub strategy: CacheStrategy,
    pub min_system_prompt_tokens: usize,
    pub early_messages_count: usize,
    pub multi_point_interval: usize,
    pub max_cache_points: usize,
}

impl Default for CacheConfig {
    fn default() -> Self {
        Self {
            enabled: true,
            strategy: CacheStrategy::SystemAndEarly,
            min_system_prompt_tokens: 1_000,
            early_messages_count: 5,
            multi_point_interval: 10,
            max_cache_points: 4,
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq, Default)]
#[serde(rename_all = "camelCase")]
pub struct CacheStats {
    pub cache_hits: usize,
    pub cache_misses: usize,
    pub cached_tokens: usize,
    pub total_tokens: usize,
}

impl CacheStats {
    pub fn hit_rate(&self) -> f64 {
        let total = self.cache_hits + self.cache_misses;
        if total == 0 {
            0.0
        } else {
            self.cache_hits as f64 / total as f64
        }
    }

    pub fn token_savings(&self) -> f64 {
        if self.total_tokens == 0 {
            0.0
        } else {
            self.cached_tokens as f64 / self.total_tokens as f64
        }
    }
}

#[derive(Debug, Clone)]
pub struct PromptCacheManager {
    pub config: CacheConfig,
    pub stats: CacheStats,
    cache_enabled_for_session: bool,
}

impl Default for PromptCacheManager {
    fn default() -> Self {
        Self::new(None)
    }
}

impl PromptCacheManager {
    pub fn new(config: Option<CacheConfig>) -> Self {
        Self {
            config: config.unwrap_or_default(),
            stats: CacheStats::default(),
            cache_enabled_for_session: true,
        }
    }

    pub fn supports_caching(&self, model: &str, provider: &str) -> bool {
        if !self.config.enabled || !self.cache_enabled_for_session {
            return false;
        }
        if !matches!(provider.to_ascii_lowercase().as_str(), "anthropic" | "claude") {
            return false;
        }

        let model = model.to_ascii_lowercase();
        [
            "claude-3-5-sonnet",
            "claude-3-opus",
            "claude-3-haiku",
            "claude-3-sonnet",
        ]
        .iter()
        .any(|prefix| model.contains(prefix))
    }

    pub fn determine_strategy(
        &self,
        messages: &[Value],
        system_prompt_tokens: usize,
    ) -> CacheStrategy {
        if !self.config.enabled || system_prompt_tokens < self.config.min_system_prompt_tokens {
            return CacheStrategy::None;
        }

        let message_count = messages.len();
        if message_count < 10 {
            CacheStrategy::SystemOnly
        } else if message_count < 30 {
            CacheStrategy::SystemAndEarly
        } else {
            CacheStrategy::MultiPoint
        }
    }

    pub fn process_messages(
        &self,
        messages: &[Value],
        model: &str,
        provider: &str,
        system_prompt_tokens: usize,
    ) -> (Vec<Value>, bool) {
        if !self.supports_caching(model, provider) {
            return (messages.to_vec(), false);
        }

        let strategy = self.determine_strategy(messages, system_prompt_tokens);
        if strategy == CacheStrategy::None {
            return (messages.to_vec(), false);
        }

        (self.add_cache_markers_anthropic(messages, strategy), true)
    }

    pub fn update_stats(&mut self, cache_hit: bool, cached_tokens: usize, total_tokens: usize) {
        if cache_hit {
            self.stats.cache_hits += 1;
        } else {
            self.stats.cache_misses += 1;
        }
        self.stats.cached_tokens += cached_tokens;
        self.stats.total_tokens += total_tokens;
    }

    fn add_cache_markers_anthropic(
        &self,
        messages: &[Value],
        strategy: CacheStrategy,
    ) -> Vec<Value> {
        let mut cached_messages = Vec::with_capacity(messages.len());

        for (index, message) in messages.iter().enumerate() {
            let should_cache = is_cache_target(message, index, strategy, &self.config);
            cached_messages.push(if should_cache {
                add_cache_marker(message)
            } else {
                message.clone()
            });
        }

        cached_messages
    }
}

fn is_cache_target(
    message: &Value,
    index: usize,
    strategy: CacheStrategy,
    config: &CacheConfig,
) -> bool {
    if message.get("role").and_then(Value::as_str) == Some("system") {
        return true;
    }

    match strategy {
        CacheStrategy::None | CacheStrategy::SystemOnly => false,
        CacheStrategy::SystemAndEarly => index <= config.early_messages_count,
        CacheStrategy::MultiPoint => {
            index <= config.early_messages_count
                || (index > 0
                    && index % config.multi_point_interval == 0
                    && index / config.multi_point_interval <= config.max_cache_points)
        }
    }
}

fn add_cache_marker(message: &Value) -> Value {
    let mut message = message.clone();
    let Some(content) = message.get_mut("content") else {
        return message;
    };

    match content {
        Value::String(text) => {
            *content = json!([
                {
                    "type": "text",
                    "text": text,
                    "cache_control": {"type": "ephemeral"}
                }
            ]);
        }
        Value::Array(items) => {
            if let Some(Value::Object(last_item)) = items.last_mut() {
                last_item.insert("cache_control".to_string(), json!({"type": "ephemeral"}));
            }
        }
        _ => {}
    }

    message
}

#[cfg(test)]
mod tests {
    use serde_json::json;

    use super::{CacheStrategy, PromptCacheManager};

    #[test]
    fn supports_caching_only_for_cacheable_claude_models() {
        let manager = PromptCacheManager::default();
        assert!(manager.supports_caching("claude-3-5-sonnet-20241022", "anthropic"));
        assert!(manager.supports_caching("claude-3-haiku-20240307", "claude"));
        assert!(!manager.supports_caching("gpt-4o-mini", "openai"));
    }

    #[test]
    fn determine_strategy_matches_retired_thresholds() {
        let manager = PromptCacheManager::default();
        let short_messages = vec![json!({"role":"system","content":"s"}); 2];
        let medium_messages = vec![json!({"role":"user","content":"u"}); 12];
        let long_messages = vec![json!({"role":"user","content":"u"}); 35];

        assert_eq!(
            manager.determine_strategy(&short_messages, 1_500),
            CacheStrategy::SystemOnly
        );
        assert_eq!(
            manager.determine_strategy(&medium_messages, 1_500),
            CacheStrategy::SystemAndEarly
        );
        assert_eq!(
            manager.determine_strategy(&long_messages, 1_500),
            CacheStrategy::MultiPoint
        );
    }

    #[test]
    fn process_messages_adds_cache_markers_to_target_messages() {
        let manager = PromptCacheManager::default();
        let messages = std::iter::once(json!({"role":"system","content":"system prompt"}))
            .chain((0..11).map(|idx| {
                if idx % 2 == 0 {
                    json!({"role":"user","content":format!("hello-{idx}")})
                } else {
                    json!({"role":"assistant","content":format!("world-{idx}")})
                }
            }))
            .collect::<Vec<_>>();

        let (processed, enabled) =
            manager.process_messages(&messages, "claude-3-5-sonnet-20241022", "anthropic", 1_500);
        assert!(enabled);
        assert!(processed[0]["content"].is_array());
        assert!(processed[1]["content"].is_array());
        assert!(!processed.last().expect("message should exist")["content"].is_array());
    }
}
