use serde::de::DeserializeOwned;

use crate::runtime::intelligent::{
    config::IntelligentLlmConfig,
    llm::{IntelligentLlmInvocation, IntelligentLlmInvocationError, IntelligentLlmInvoker},
};

use super::context::AuditStage;

#[derive(Debug)]
pub enum StageInvokeError {
    Llm(IntelligentLlmInvocationError),
    Json(String),
}

impl std::fmt::Display for StageInvokeError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            Self::Llm(error) => write!(f, "{error}"),
            Self::Json(error) => write!(f, "{error}"),
        }
    }
}

impl std::error::Error for StageInvokeError {}

#[derive(Debug, Clone)]
pub struct StageInvokeResult<T> {
    pub payload: T,
    pub invocation: IntelligentLlmInvocation,
    pub repair_used: bool,
}

pub async fn invoke_json<T>(
    invoker: &(dyn IntelligentLlmInvoker + Send + Sync),
    stage: AuditStage,
    prompt: &str,
    config: &IntelligentLlmConfig,
) -> Result<StageInvokeResult<T>, StageInvokeError>
where
    T: DeserializeOwned,
{
    let invocation = invoker
        .invoke(prompt, config)
        .await
        .map_err(StageInvokeError::Llm)?;
    match parse_json::<T>(&invocation.content) {
        Ok(payload) => Ok(StageInvokeResult {
            payload,
            invocation,
            repair_used: false,
        }),
        Err(first_error) => {
            let repair_prompt = format!(
                "The previous {stage} output did not parse as the required JSON object: {first_error}. Re-emit only the corrected JSON object, no prose. Previous output:\n{}",
                invocation.content
            );
            let repair_invocation = invoker
                .invoke(&repair_prompt, config)
                .await
                .map_err(StageInvokeError::Llm)?;
            let payload =
                parse_json::<T>(&repair_invocation.content).map_err(StageInvokeError::Json)?;
            Ok(StageInvokeResult {
                payload,
                invocation: repair_invocation,
                repair_used: true,
            })
        }
    }
}

pub fn parse_json<T>(text: &str) -> Result<T, String>
where
    T: DeserializeOwned,
{
    let value = extract_json_value(text)?;
    serde_json::from_value(value).map_err(|error| error.to_string())
}

pub fn extract_json_value(text: &str) -> Result<serde_json::Value, String> {
    let trimmed = text.trim();
    if trimmed.is_empty() {
        return Err("empty output".to_string());
    }
    if let Ok(value) = serde_json::from_str::<serde_json::Value>(trimmed) {
        return Ok(value);
    }
    if let Some(fenced) = extract_fenced_json(trimmed) {
        if let Ok(value) = serde_json::from_str::<serde_json::Value>(&fenced) {
            return Ok(value);
        }
    }
    if let Some(candidate) = extract_balanced_json_object(trimmed) {
        if let Ok(value) = serde_json::from_str::<serde_json::Value>(&candidate) {
            return Ok(value);
        }
    }
    Err("no parseable JSON object found".to_string())
}

fn extract_fenced_json(text: &str) -> Option<String> {
    let start = text.find("```")?;
    let after_start = &text[start + 3..];
    let content_start = after_start.find('\n').map(|idx| idx + 1).unwrap_or(0);
    let after_lang = &after_start[content_start..];
    let end = after_lang.find("```")?;
    Some(after_lang[..end].trim().to_string())
}

fn extract_balanced_json_object(text: &str) -> Option<String> {
    let start = text.find('{')?;
    let mut depth = 0i32;
    let mut in_string = false;
    let mut escaped = false;
    for (offset, ch) in text[start..].char_indices() {
        if in_string {
            if escaped {
                escaped = false;
            } else if ch == '\\' {
                escaped = true;
            } else if ch == '"' {
                in_string = false;
            }
            continue;
        }
        match ch {
            '"' => in_string = true,
            '{' => depth += 1,
            '}' => {
                depth -= 1;
                if depth == 0 {
                    let end = start + offset + ch.len_utf8();
                    return Some(text[start..end].to_string());
                }
            }
            _ => {}
        }
    }
    None
}

#[cfg(test)]
mod tests {
    use super::*;

    #[derive(serde::Deserialize)]
    struct Tiny {
        ok: bool,
    }

    #[test]
    fn parse_json_accepts_plain_fenced_and_embedded_objects() {
        assert!(parse_json::<Tiny>("{\"ok\":true}").unwrap().ok);
        assert!(
            parse_json::<Tiny>("```json\n{\"ok\":true}\n```")
                .unwrap()
                .ok
        );
        assert!(parse_json::<Tiny>("text {\"ok\":true} tail").unwrap().ok);
    }
}
