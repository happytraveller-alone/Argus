use serde::de::DeserializeOwned;
use serde_json::json;

use crate::runtime::intelligent::{
    config::IntelligentLlmConfig,
    llm::{IntelligentLlmInvocation, IntelligentLlmInvocationError, IntelligentLlmInvoker},
    types::IntelligentTaskEvent,
};

use super::context::{AuditStage, PipelineEventSink};

/// Tag an `llm_attempt` event with the pipeline stage that issued the call
/// (and an optional sub-phase such as `repair`). Without the tag the event
/// log shows the LLM exchange in isolation; with it, operators can trace
/// which stage failed when multiple stages run in close succession.
fn annotate_with_stage(event: &mut IntelligentTaskEvent, stage: AuditStage, phase: Option<&str>) {
    let data = event.data.get_or_insert_with(|| json!({}));
    if let Some(obj) = data.as_object_mut() {
        let stage_label = match phase {
            Some(p) => format!("{}:{}", stage.as_str(), p),
            None => stage.as_str().to_string(),
        };
        obj.insert("stage".to_string(), json!(stage_label));
    }
}

/// Emit a stage-tagged `llm_attempt` event from a successful invocation.
fn emit_success(
    events: &PipelineEventSink,
    stage: AuditStage,
    phase: Option<&str>,
    invocation: &IntelligentLlmInvocation,
) {
    let mut event = invocation.attempt_event.clone();
    annotate_with_stage(&mut event, stage, phase);
    events.emit(event);
}

/// Emit a stage-tagged `llm_attempt` event from a failed invocation. This is
/// the critical surface that, prior to this refactor, dropped the failure
/// attempt on the floor — leaving the audit time log with `audit_pipeline_failed`
/// but no preceding context for what the gateway actually returned.
fn emit_failure(
    events: &PipelineEventSink,
    stage: AuditStage,
    phase: Option<&str>,
    err: &IntelligentLlmInvocationError,
) {
    let mut event = err.attempt_event.clone();
    annotate_with_stage(&mut event, stage, phase);
    events.emit(event);
}

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

/// Invoke the LLM expecting a JSON payload, with one repair attempt on parse
/// failure. Emits a stage-tagged `llm_attempt` event for every invocation —
/// success, failure, primary, and repair — so the audit time log reflects the
/// complete LLM interaction trail.
pub async fn invoke_json<T>(
    invoker: &(dyn IntelligentLlmInvoker + Send + Sync),
    stage: AuditStage,
    prompt: &str,
    config: &IntelligentLlmConfig,
    events: &PipelineEventSink,
) -> Result<StageInvokeResult<T>, StageInvokeError>
where
    T: DeserializeOwned,
{
    let invocation = match invoker.invoke(prompt, config).await {
        Ok(inv) => {
            emit_success(events, stage, None, &inv);
            inv
        }
        Err(err) => {
            emit_failure(events, stage, None, &err);
            return Err(StageInvokeError::Llm(err));
        }
    };
    match parse_json::<T>(&invocation.content) {
        Ok(payload) => Ok(StageInvokeResult {
            payload,
            invocation,
            repair_used: false,
        }),
        Err(first_error) => {
            // First-shot terminal extract+deserialize failure. Emit before
            // attempting the repair shot so the timeline shows the parse fault
            // even when the repair shot subsequently succeeds.
            emit_parse_failure(events, "first_shot", &first_error);
            let repair_prompt = build_repair_prompt(stage, &first_error, &invocation.content);
            let repair_invocation = match invoker.invoke(&repair_prompt, config).await {
                Ok(inv) => {
                    emit_success(events, stage, Some("repair"), &inv);
                    inv
                }
                Err(err) => {
                    emit_failure(events, stage, Some("repair"), &err);
                    return Err(StageInvokeError::Llm(err));
                }
            };
            let payload = match parse_json::<T>(&repair_invocation.content) {
                Ok(p) => p,
                Err(repair_error) => {
                    // Repair-shot also failed — all extraction tiers exhausted.
                    emit_parse_failure(events, "repair_shot", &repair_error);
                    return Err(StageInvokeError::Json(repair_error));
                }
            };
            Ok(StageInvokeResult {
                payload,
                invocation: repair_invocation,
                repair_used: true,
            })
        }
    }
}

/// Emit a `parse_failure` event when `extract_json_value` exhausts every
/// fallback tier (plain, fenced, balanced) and the subsequent `from_value`
/// also fails. `stage` is `"first_shot"` or `"repair_shot"` to distinguish
/// which LLM invocation produced the unparseable content. The error message
/// is truncated to 256 chars to bound event size on long serde diagnostics.
fn emit_parse_failure(events: &PipelineEventSink, stage: &str, err_msg: &str) {
    let summary: String = err_msg.chars().take(256).collect();
    events.emit(IntelligentTaskEvent::new("parse_failure").with_data(json!({
        "stage": stage,
        "fallbackTier": "all_exhausted",
        "errorSummary": summary,
    })));
}

/// Build a repair prompt that names the parse error and the most common LLM
/// failure modes we have observed in production, so the second invocation
/// has concrete guidance instead of a generic "try again".
///
/// Observed failure modes (each one has dropped a whole audit stage):
///   - double-encoding: returning `"{\"new_tasks\":...}"` instead of the
///     object. Detected at 2026-05-26 on the feedback stage.
///   - schema drift: emitting `Vec<Object>` where the schema declared
///     `Vec<String>` (e.g. `patterns`).
///   - omitted required identifiers (e.g. `task_id` in feedback `new_tasks`).
///   - markdown fences around the JSON.
fn build_repair_prompt(stage: AuditStage, error: &str, previous: &str) -> String {
    format!(
        "The previous {stage} output did not parse as the required JSON object.\n\
Parse error: {error}\n\
\n\
Common failure modes — verify your next response avoids these:\n\
  1. Do NOT wrap the JSON object in a string literal (e.g. \"{{\\\"new_tasks\\\":...}}\"); emit the object directly.\n\
  2. Do NOT substitute object arrays for string arrays. If the schema says `\"patterns\": [\"string\"]`, emit string items, not objects.\n\
  3. Include every required field listed in the schema, including identifier fields (task_id, finding_id, etc.).\n\
  4. Do NOT wrap the output in markdown code fences (```json ... ```).\n\
\n\
Re-emit ONLY the corrected JSON object, with no prose, explanation, or markdown.\n\
\n\
Previous output:\n{previous}"
    )
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
        return Ok(unwrap_stringified_json(value));
    }
    if let Some(fenced) = extract_fenced_json(trimmed) {
        if let Ok(value) = serde_json::from_str::<serde_json::Value>(&fenced) {
            return Ok(unwrap_stringified_json(value));
        }
    }
    if let Some(candidate) = extract_balanced_json_object(trimmed) {
        if let Ok(value) = serde_json::from_str::<serde_json::Value>(&candidate) {
            return Ok(unwrap_stringified_json(value));
        }
    }
    Err("no parseable JSON object found".to_string())
}

/// LLMs occasionally double-encode their reply — returning a JSON *string
/// literal* that contains the actual JSON object as escaped text
/// (`"{\"new_tasks\":[...]}"`), rather than the object directly. Without
/// unwrapping, the downstream `from_value::<T>` rejects it as
/// `invalid type: string ..., expected struct ...` and the whole stage
/// dies (see feedback-stage incident at 2026-05-26).
///
/// Unwrap exactly one layer when the payload is a `Value::String` whose
/// trimmed contents start with `{` or `[`. Bounded depth (one) is enough —
/// triple-encoding has not been observed and unbounded recursion would risk
/// pathological input.
fn unwrap_stringified_json(value: serde_json::Value) -> serde_json::Value {
    if let serde_json::Value::String(inner) = &value {
        let trimmed = inner.trim();
        if trimmed.starts_with('{') || trimmed.starts_with('[') {
            if let Ok(parsed) = serde_json::from_str::<serde_json::Value>(trimmed) {
                return parsed;
            }
        }
    }
    value
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

    /// Regression: LLM returns the JSON object as a string literal containing
    /// escaped JSON (double-encoding). Without unwrap_stringified_json the
    /// feedback stage at 2026-05-26 failed with
    /// `invalid type: string "{...}", expected struct FeedbackOutput`.
    #[test]
    fn parse_json_unwraps_stringified_object() {
        let double_encoded = "\"{\\\"ok\\\":true}\"";
        let value = extract_json_value(double_encoded).expect("must unwrap");
        assert!(value.is_object(), "expected object, got: {value:?}");
        let tiny: Tiny = parse_json(double_encoded).expect("Tiny must deserialize");
        assert!(tiny.ok);
    }

    /// Triple-encoded payloads stay strings — we bound depth at one to avoid
    /// pathological inputs. The repair-prompt path will catch this case.
    #[test]
    fn parse_json_does_not_unwrap_beyond_one_layer() {
        let triple = "\"\\\"{\\\\\\\"ok\\\\\\\":true}\\\"\"";
        let value = extract_json_value(triple).expect("layer-1 unwrap succeeds");
        // After one unwrap we have a `Value::String` whose content is still a
        // quoted JSON literal — not an object. Deserialize fails, caller hits
        // the repair branch.
        assert!(
            value.is_string(),
            "expected unwrapped value to remain a string at depth 2, got {value:?}"
        );
    }

    /// Stringified array variant — LLMs occasionally double-encode an array
    /// payload too (e.g. when the top-level schema is `Vec<...>`).
    #[test]
    fn parse_json_unwraps_stringified_array() {
        let double_encoded = "\"[1,2,3]\"";
        let value = extract_json_value(double_encoded).expect("must unwrap");
        assert!(value.is_array(), "expected array, got: {value:?}");
    }
}
