use std::time::Duration;

use anyhow::{anyhow, bail, Context, Result};
use base64::{engine::general_purpose::STANDARD as BASE64_STANDARD, Engine as _};
use reqwest::{
    header::HOST,
    multipart::{Form, Part},
    Client, StatusCode, Url,
};
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use uuid::Uuid;

use super::config::parse_url;

const ENVD_PORT: u16 = 49_983;
const ENVD_USERNAME: &str = "root";
const ENVD_PROCESS_START_PATH: &str = "process.Process/Start";
const ENVD_FILES_PATH: &str = "files";
const SCRIPT_INLINE_LIMIT: usize = 32 * 1024;

#[derive(Clone, Debug)]
pub struct CubeSandboxClientConfig {
    pub api_base_url: String,
    pub data_plane_base_url: String,
    pub template_id: String,
    pub execution_timeout_seconds: u64,
    pub cleanup_timeout_seconds: u64,
    pub stdout_limit_bytes: usize,
    pub stderr_limit_bytes: usize,
}

#[derive(Clone)]
pub struct CubeSandboxClient {
    http_client: Client,
    api_base_url: Url,
    data_plane_base_url: Url,
    config: CubeSandboxClientConfig,
}

#[derive(Clone, Debug, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct CubeSandboxSandbox {
    #[serde(rename = "sandboxID")]
    pub sandbox_id: String,
    #[serde(rename = "templateID")]
    pub template_id: String,
    #[serde(rename = "clientID")]
    pub client_id: String,
    #[serde(rename = "envdVersion")]
    pub envd_version: String,
    pub domain: Option<String>,
}

#[derive(Clone, Debug, Serialize)]
pub struct EnvdProcessRequest {
    pub cmd: String,
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct EnvdProcessOutput {
    pub stdout: String,
    pub stderr: String,
    pub stdout_truncated: bool,
    pub stderr_truncated: bool,
    pub exit_code: Option<i32>,
}

impl CubeSandboxClient {
    pub fn new(config: CubeSandboxClientConfig) -> Result<Self> {
        let api_base_url = parse_url(&config.api_base_url, "apiBaseUrl")?;
        let data_plane_base_url = parse_url(&config.data_plane_base_url, "dataPlaneBaseUrl")?;
        let http_client = Client::builder()
            .timeout(Duration::from_secs(config.execution_timeout_seconds.max(1)))
            .danger_accept_invalid_certs(true)
            .no_proxy()
            .build()?;
        Ok(Self {
            http_client,
            api_base_url,
            data_plane_base_url,
            config,
        })
    }

    pub async fn health(&self) -> Result<()> {
        let response = self
            .http_client
            .get(self.join_api("health")?)
            .send()
            .await?;
        if response.status().is_success() {
            Ok(())
        } else {
            bail!("CubeSandbox API health failed: {}", response.status())
        }
    }

    pub async fn create_sandbox(&self) -> Result<CubeSandboxSandbox> {
        let response = self
            .http_client
            .post(self.join_api("sandboxes")?)
            .json(&json!({
                "templateID": self.config.template_id,
                "timeout": self.config.execution_timeout_seconds
            }))
            .send()
            .await?;
        if !response.status().is_success() {
            bail!("CubeSandbox create failed: {}", response.status());
        }
        Ok(response.json().await?)
    }

    pub async fn connect_sandbox(&self, sandbox_id: &str) -> Result<()> {
        let response = self
            .http_client
            .post(self.join_api(&format!("sandboxes/{sandbox_id}/connect"))?)
            .json(&json!({
                "timeout": self.config.execution_timeout_seconds
            }))
            .send()
            .await?;
        if response.status().is_success() {
            Ok(())
        } else {
            bail!("CubeSandbox connect failed: {}", response.status())
        }
    }

    pub async fn get_sandbox(&self, sandbox_id: &str) -> Result<CubeSandboxSandbox> {
        let response = self
            .http_client
            .get(self.join_api(&format!("sandboxes/{sandbox_id}"))?)
            .send()
            .await?;
        if !response.status().is_success() {
            bail!("CubeSandbox diagnostics failed: {}", response.status());
        }
        Ok(response.json().await?)
    }

    pub async fn delete_sandbox(&self, sandbox_id: &str) -> Result<()> {
        let response = self
            .http_client
            .delete(self.join_api(&format!("sandboxes/{sandbox_id}"))?)
            .timeout(Duration::from_secs(
                self.config.cleanup_timeout_seconds.max(1),
            ))
            .send()
            .await?;
        if response.status().is_success() || response.status() == StatusCode::NOT_FOUND {
            Ok(())
        } else {
            bail!("CubeSandbox cleanup failed: {}", response.status())
        }
    }

    pub async fn run_python(
        &self,
        sandbox: &CubeSandboxSandbox,
        code: &str,
    ) -> Result<EnvdProcessOutput> {
        self.run_command(sandbox, &format!("python3 -c {}", shell_quote(code)))
            .await
    }

    /// Upload a file to the sandbox via envd `/files` multipart endpoint.
    pub async fn write_file(
        &self,
        sandbox: &CubeSandboxSandbox,
        path: &str,
        content: Vec<u8>,
    ) -> Result<()> {
        let host = self.envd_host(&sandbox.sandbox_id, sandbox.domain.as_deref())?;
        let auth = format!(
            "Basic {}",
            BASE64_STANDARD.encode(format!("{ENVD_USERNAME}:").as_bytes())
        );
        let mut url = self.envd_url(ENVD_FILES_PATH)?;
        url.query_pairs_mut()
            .append_pair("path", path)
            .append_pair("username", ENVD_USERNAME);
        let form = Form::new().part(
            "file",
            Part::bytes(content).file_name(path.to_string()),
        );
        let response = self
            .http_client
            .post(url)
            .header(HOST, host)
            .header("Authorization", &auth)
            .multipart(form)
            .send()
            .await?;
        if !response.status().is_success() {
            let status = response.status();
            let body = response.text().await.unwrap_or_default();
            bail!(
                "CubeSandbox envd write_file failed: {} body={}",
                status,
                truncate_utf8(body, 512).0
            );
        }
        Ok(())
    }

    /// Run a shell script inside the sandbox via envd Connect-RPC `process.Process/Start`.
    ///
    /// Short scripts are executed inline as `/bin/sh -c <script>`. Larger scripts are
    /// uploaded to `/tmp/argus-<uuid>.sh` first to bypass argv size limits.
    pub async fn run_command(
        &self,
        sandbox: &CubeSandboxSandbox,
        command: &str,
    ) -> Result<EnvdProcessOutput> {
        let request_json = if command.len() <= SCRIPT_INLINE_LIMIT {
            json!({
                "process": {
                    "cmd": "/bin/sh",
                    "args": ["-c", command],
                }
            })
        } else {
            let script_path = format!("/tmp/argus-{}.sh", Uuid::new_v4());
            self.write_file(sandbox, &script_path, command.as_bytes().to_vec())
                .await?;
            json!({
                "process": {
                    "cmd": "/bin/sh",
                    "args": [&script_path],
                }
            })
        };
        let body = serde_json::to_vec(&request_json)?;
        let mut framed = Vec::with_capacity(5 + body.len());
        framed.push(0u8);
        framed.extend_from_slice(&(body.len() as u32).to_be_bytes());
        framed.extend_from_slice(&body);

        let auth = format!(
            "Basic {}",
            BASE64_STANDARD.encode(format!("{ENVD_USERNAME}:").as_bytes())
        );
        let response = self
            .http_client
            .post(self.envd_url(ENVD_PROCESS_START_PATH)?)
            .header(
                HOST,
                self.envd_host(&sandbox.sandbox_id, sandbox.domain.as_deref())?,
            )
            .header("Content-Type", "application/connect+json")
            .header("Connect-Protocol-Version", "1")
            .header("Authorization", &auth)
            .body(framed)
            .send()
            .await?;
        if !response.status().is_success() {
            let status = response.status();
            let body = response.text().await.unwrap_or_default();
            bail!(
                "CubeSandbox envd process failed: {} body={}",
                status,
                truncate_utf8(body, 512).0
            );
        }
        let bytes = response.bytes().await?;
        let aggregated = parse_connect_process_stream(&bytes)?;

        let (stdout, stdout_truncated) =
            truncate_utf8(aggregated.stdout, self.config.stdout_limit_bytes);
        let (stderr, stderr_truncated) =
            truncate_utf8(aggregated.stderr, self.config.stderr_limit_bytes);
        Ok(EnvdProcessOutput {
            stdout,
            stderr,
            stdout_truncated,
            stderr_truncated,
            exit_code: aggregated.exit_code,
        })
    }

    fn join_api(&self, path: &str) -> Result<Url> {
        Ok(self.api_base_url.join(path)?)
    }

    fn envd_url(&self, tail: &str) -> Result<Url> {
        let tail = tail.trim_start_matches('/');
        Ok(self.data_plane_base_url.join(tail)?)
    }

    fn envd_host(&self, sandbox_id: &str, domain: Option<&str>) -> Result<String> {
        let Some(domain) = domain.filter(|value| !value.trim().is_empty()) else {
            bail!("CubeSandbox response missing sandbox domain");
        };
        Ok(format!("{ENVD_PORT}-{sandbox_id}.{domain}"))
    }
}

fn truncate_utf8(value: String, limit: usize) -> (String, bool) {
    if value.len() <= limit {
        return (value, false);
    }
    let mut end = limit;
    while !value.is_char_boundary(end) {
        end = end.saturating_sub(1);
    }
    (value[..end].to_string(), true)
}

fn shell_quote(value: &str) -> String {
    format!("'{}'", value.replace('\'', "'\"'\"'"))
}

#[derive(Debug, Default)]
struct ProcessStreamAggregate {
    stdout: String,
    stderr: String,
    exit_code: Option<i32>,
    error: Option<String>,
}

/// Parse a Connect-RPC server-streaming response body for envd `process.Process/Start`.
///
/// The body is a sequence of envelopes: `[1 byte flags][4 byte BE length][payload]`.
/// Regular frames have flags=0; the trailer frame has flags & 0x02 = end-stream.
/// Each regular frame's JSON payload is a `StartResponse` with an `event` field:
/// - `event.start.pid` - process started
/// - `event.data.stdout` / `event.data.stderr` - base64 chunks
/// - `event.end.{exited, status, error, exit_code}` - terminal state
fn parse_connect_process_stream(bytes: &[u8]) -> Result<ProcessStreamAggregate> {
    let mut agg = ProcessStreamAggregate::default();
    let mut idx = 0usize;
    while idx + 5 <= bytes.len() {
        let flags = bytes[idx];
        let length = u32::from_be_bytes([
            bytes[idx + 1],
            bytes[idx + 2],
            bytes[idx + 3],
            bytes[idx + 4],
        ]) as usize;
        idx += 5;
        if idx + length > bytes.len() {
            bail!(
                "envd process stream truncated: expected {} bytes payload, got {}",
                length,
                bytes.len() - idx
            );
        }
        let payload = &bytes[idx..idx + length];
        idx += length;
        let value: Value = serde_json::from_slice(payload).with_context(|| {
            format!(
                "envd process frame is not JSON (flags={}, len={})",
                flags, length
            )
        })?;
        if flags & 0x02 != 0 {
            // Trailer frame: may contain an error code/message.
            if let Some(err) = value.get("error") {
                let code = err
                    .get("code")
                    .and_then(Value::as_str)
                    .unwrap_or("unknown");
                let message = err
                    .get("message")
                    .and_then(Value::as_str)
                    .unwrap_or_default();
                agg.error = Some(format!("{code}: {message}"));
            }
            continue;
        }
        let Some(event) = value.get("event") else {
            continue;
        };
        if let Some(start) = event.get("start") {
            tracing::debug!(?start, "envd process started");
        }
        if let Some(data) = event.get("data") {
            if let Some(b64) = data.get("stdout").and_then(Value::as_str) {
                agg.stdout
                    .push_str(&decode_base64_to_string(b64).unwrap_or_default());
            }
            if let Some(b64) = data.get("stderr").and_then(Value::as_str) {
                agg.stderr
                    .push_str(&decode_base64_to_string(b64).unwrap_or_default());
            }
        }
        if let Some(end) = event.get("end") {
            if let Some(code) = end.get("exit_code").and_then(Value::as_i64) {
                agg.exit_code = Some(code as i32);
            } else if let Some(status) = end.get("status").and_then(Value::as_str) {
                agg.exit_code = parse_exit_status(status);
            }
            if let Some(error) = end.get("error").and_then(Value::as_str) {
                if !error.is_empty() {
                    agg.error.get_or_insert_with(|| error.to_string());
                }
            }
        }
    }
    if agg.exit_code.is_none() {
        if let Some(error) = agg.error.as_ref() {
            return Err(anyhow!("envd process error: {error}"));
        }
    }
    Ok(agg)
}

fn decode_base64_to_string(value: &str) -> Option<String> {
    let bytes = BASE64_STANDARD.decode(value).ok()?;
    Some(String::from_utf8_lossy(&bytes).into_owned())
}

fn parse_exit_status(value: &str) -> Option<i32> {
    if let Some(rest) = value.strip_prefix("exit status ") {
        return rest.trim().parse().ok();
    }
    if value.is_empty() {
        return Some(0);
    }
    None
}

#[cfg(test)]
mod tests {
    use super::*;

    fn frame(flags: u8, payload: &[u8]) -> Vec<u8> {
        let mut out = Vec::new();
        out.push(flags);
        out.extend_from_slice(&(payload.len() as u32).to_be_bytes());
        out.extend_from_slice(payload);
        out
    }

    #[test]
    fn parses_envd_process_stream_with_stdout_and_exit() {
        let mut buf = Vec::new();
        buf.extend(frame(0, br#"{"event":{"start":{"pid":42}}}"#));
        buf.extend(frame(
            0,
            br#"{"event":{"data":{"stdout":"aGVsbG8K"}}}"#,
        ));
        buf.extend(frame(
            0,
            br#"{"event":{"data":{"stderr":"d2Fybgo="}}}"#,
        ));
        buf.extend(frame(
            0,
            br#"{"event":{"end":{"exited":true,"status":"exit status 0"}}}"#,
        ));
        buf.extend(frame(2, b"{}"));
        let agg = parse_connect_process_stream(&buf).unwrap();
        assert_eq!(agg.stdout, "hello\n");
        assert!(agg.stderr.starts_with("warn"));
        assert_eq!(agg.exit_code, Some(0));
    }

    #[test]
    fn surfaces_envd_trailer_error_when_no_exit() {
        let mut buf = Vec::new();
        buf.extend(frame(
            2,
            br#"{"error":{"code":"unauthenticated","message":"no user specified"}}"#,
        ));
        let err = parse_connect_process_stream(&buf).unwrap_err();
        assert!(err.to_string().contains("unauthenticated"));
    }

    #[test]
    fn parse_exit_status_handles_known_formats() {
        assert_eq!(parse_exit_status("exit status 0"), Some(0));
        assert_eq!(parse_exit_status("exit status 1"), Some(1));
        assert_eq!(parse_exit_status("exit status 127"), Some(127));
        assert_eq!(parse_exit_status(""), Some(0));
        assert_eq!(parse_exit_status("signal: terminated"), None);
    }
}
