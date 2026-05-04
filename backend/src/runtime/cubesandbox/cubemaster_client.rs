use anyhow::{bail, Context, Result};
use reqwest::Client;
use serde::{Deserialize, Serialize};
use time::{format_description::well_known::Rfc3339, OffsetDateTime};
use uuid::Uuid;

use super::{
    config::CubeSandboxConfig,
    helper::{run_helper_command, CubeSandboxHelperCommand},
};

/// Observed `ret_code` returned by `DELETE /cube/sandbox` when the sandbox
/// does not exist (`ret_msg = "no such sandbox"`).  Treat as idempotent success
/// so that retries after partial failure do not surface spurious errors.
///
/// Observed via: `curl -X DELETE http://127.0.0.1:8089/cube/sandbox -d '{"sandbox_id":"sb-nonexistent-000"}'`
/// Response: `{"ret":{"ret_code":200,"ret_msg":"no such sandbox"},"sandbox_id":"sb-nonexistent-000"}`
pub const SANDBOX_NOT_FOUND_RET_CODE: i64 = 200;

/// Configuration for the CubeMaster HTTP client.
/// CubeMaster is the control-plane service that manages cube templates.
/// Its base URL is distinct from the CubeSandbox data-plane (`data_plane_base_url`)
/// and the CubeAPI (`api_base_url`); by default it listens on the same host as
/// `api_base_url` (default http://127.0.0.1:23000).
#[derive(Clone, Debug)]
pub struct CubemasterClientConfig {
    /// Base URL of the CubeMaster service, e.g. "http://127.0.0.1:23000".
    pub base_url: String,
    /// Timeout in seconds for each HTTP request to CubeMaster.
    pub cleanup_timeout_seconds: u64,
    /// Instance type string sent in the request body (default: "cubebox").
    pub instance_type: String,
}

/// HTTP client for the CubeMaster control-plane API.
#[derive(Clone)]
pub struct CubemasterClient {
    http_client: Client,
    config: CubemasterClientConfig,
    cube_config: CubeSandboxConfig,
}

/// A template record as returned by `cubemastercli tpl list`.
///
/// The cubemaster HTTP API has no `/cube/templates` list endpoint (returns 404);
/// list data is obtained via `cubemastercli --address 127.0.0.1 tpl list` shell-out
/// and the tabular stdout is parsed here.
#[derive(Debug, Clone)]
pub struct CubemasterTemplate {
    pub template_id: String,
    pub kind: String,
    pub status: String,
    pub created_at: OffsetDateTime,
    pub image_fingerprint: Option<String>,
}

/// A sandbox record as returned by the cubemaster sandbox list endpoint.
///
/// NOTE: as of the current cubemaster build, neither `GET /cube/sandboxes` nor
/// any `cubemastercli sandbox` subcommand exists.  `list_sandboxes` is therefore
/// best-effort: it always returns `Ok(Vec::new())` with a one-time warning log
/// until the cubemaster API surface grows.
#[derive(Debug, Clone)]
pub struct CubemasterSandbox {
    pub sandbox_id: String,
    pub template_id: Option<String>,
    pub status: String,
    pub created_at: OffsetDateTime,
}

// ── wire types ────────────────────────────────────────────────────────────────

#[derive(Debug, Serialize)]
struct DeleteTemplateBody {
    #[serde(rename = "RequestID")]
    request_id: String,
    template_id: String,
    instance_type: String,
    sync: bool,
}

#[derive(Debug, Serialize)]
struct DeleteSandboxBody {
    #[serde(rename = "RequestID")]
    request_id: String,
    sandbox_id: String,
}

#[derive(Debug, Deserialize)]
struct RetEnvelope {
    ret: Ret,
}

#[derive(Debug, Deserialize)]
struct Ret {
    ret_code: i64,
    ret_msg: String,
}

// ── impl ──────────────────────────────────────────────────────────────────────

impl CubemasterClient {
    pub fn new(config: CubemasterClientConfig, cube_config: CubeSandboxConfig) -> Result<Self> {
        let http_client = Client::builder()
            .timeout(std::time::Duration::from_secs(
                config.cleanup_timeout_seconds.max(1),
            ))
            .build()
            .context("failed to build reqwest client for CubemasterClient")?;
        Ok(Self {
            http_client,
            config,
            cube_config,
        })
    }

    /// DELETE /cube/template — delete a template by id.
    ///
    /// This method implements the spec's `delete_template_idempotent` contract:
    /// `ret_code=130404` (NotFound) is treated as success so that retries after
    /// a partial failure do not surface spurious errors.
    /// Both `ret_code=0` and `ret_code=200` are considered success.
    pub async fn delete_template(&self, template_id: &str) -> Result<()> {
        let body = DeleteTemplateBody {
            request_id: Uuid::new_v4().to_string(),
            template_id: template_id.to_string(),
            instance_type: self.config.instance_type.clone(),
            sync: true,
        };
        let url = format!(
            "{}/cube/template",
            self.config.base_url.trim_end_matches('/')
        );
        let resp = self
            .http_client
            .delete(&url)
            .json(&body)
            .send()
            .await
            .with_context(|| format!("cubemaster DELETE {url} failed"))?;

        if resp.status() == reqwest::StatusCode::NOT_FOUND {
            tracing::info!(
                template_id,
                "cubemaster template delete returned HTTP 404 (idempotent ok)"
            );
            return Ok(());
        }

        let envelope: RetEnvelope = resp
            .json()
            .await
            .context("cubemaster response parse failed")?;

        match envelope.ret.ret_code {
            0 | 200 => {
                tracing::info!(template_id, "cubemaster template deleted successfully");
                Ok(())
            }
            130404 => {
                tracing::info!(
                    template_id,
                    "cubemaster template already gone (idempotent ok)"
                );
                Ok(())
            }
            code if is_template_not_found_message(&envelope.ret.ret_msg) => {
                tracing::info!(
                    template_id,
                    ret_code = code,
                    "cubemaster template already gone by message (idempotent ok)"
                );
                Ok(())
            }
            code => {
                bail!(
                    "cubemaster delete_template {} failed: ret_code={} ret_msg={}",
                    template_id,
                    code,
                    envelope.ret.ret_msg
                )
            }
        }
    }

    /// List all templates known to cubemaster.
    ///
    /// Implementation: the cubemaster HTTP API has no list-templates endpoint
    /// (`GET /cube/templates` returns 404).  This method invokes the
    /// `tpl-list` helper subcommand which SSHes into the guest VM and runs
    /// `cubemastercli --address 127.0.0.1 tpl list` there.  The tabular
    /// stdout is parsed here.  The CLI output format is:
    ///
    /// ```text
    /// TEMPLATE_ID                     STATUS     CREATED_AT              IMAGE_INFO
    /// tpl-1fae012a7bcc45af9bd6cf0d    READY      2026-05-04T10:11:23Z    <image@digest>
    /// ```
    ///
    /// Columns: `TEMPLATE_ID` (col 0), `STATUS` (col 1), `CREATED_AT` (col 2),
    /// `IMAGE_INFO` (col 3, used as `image_fingerprint`).  `kind` is not exposed
    /// by the CLI; it is set to an empty string for now.
    pub async fn list_templates(&self) -> Result<Vec<CubemasterTemplate>> {
        let output =
            run_helper_command(&self.cube_config, CubeSandboxHelperCommand::TplList).await?;
        if !output.success {
            bail!(
                "tpl-list helper failed (exit {:?}): {}",
                output.exit_code,
                output.stderr_tail.trim()
            );
        }
        parse_tpl_list_output(&output.stdout_tail)
    }

    /// List all sandboxes known to cubemaster (best-effort).
    ///
    /// As of the current cubemaster build, neither `GET /cube/sandboxes` nor any
    /// `cubemastercli sandbox` subcommand exists.  This method always returns
    /// `Ok(Vec::new())` and emits a single `tracing::warn!` so callers can detect
    /// that the sandbox list is unavailable without treating it as a fatal error.
    /// When the cubemaster API surface grows, replace this body with an HTTP call.
    pub async fn list_sandboxes(&self) -> Result<Vec<CubemasterSandbox>> {
        tracing::warn!(
            "list_sandboxes: cubemaster has no sandbox-list endpoint and no cubemastercli \
             sandbox subcommand in current build — returning empty list (orphan_sandbox_check_skipped=true)"
        );
        Ok(Vec::new())
    }

    /// DELETE /cube/sandbox — delete a sandbox by id.
    ///
    /// Idempotent: `ret_code=SANDBOX_NOT_FOUND_RET_CODE` (200, `"no such sandbox"`)
    /// is treated as success so that retries after a partial failure do not surface
    /// spurious errors.  `ret_code=0` is the nominal success code.
    ///
    /// Observed behaviour (cubemaster live probe):
    /// - existing sandbox deleted → `ret_code=0`
    /// - non-existent sandbox → `ret_code=200, ret_msg="no such sandbox"`
    pub async fn delete_sandbox(&self, sandbox_id: &str) -> Result<()> {
        let body = DeleteSandboxBody {
            request_id: Uuid::new_v4().to_string(),
            sandbox_id: sandbox_id.to_string(),
        };
        let url = format!(
            "{}/cube/sandbox",
            self.config.base_url.trim_end_matches('/')
        );
        let resp = self
            .http_client
            .delete(&url)
            .json(&body)
            .send()
            .await
            .with_context(|| format!("cubemaster DELETE {url} failed"))?;

        let envelope: RetEnvelope = resp
            .json()
            .await
            .context("cubemaster delete_sandbox response parse failed")?;

        match envelope.ret.ret_code {
            0 => {
                tracing::info!(sandbox_id, "cubemaster sandbox deleted successfully");
                Ok(())
            }
            code if code == SANDBOX_NOT_FOUND_RET_CODE => {
                tracing::info!(
                    sandbox_id,
                    ret_code = code,
                    "cubemaster sandbox already gone (idempotent ok)"
                );
                Ok(())
            }
            code => {
                bail!(
                    "cubemaster delete_sandbox {} failed: ret_code={} ret_msg={}",
                    sandbox_id,
                    code,
                    envelope.ret.ret_msg
                )
            }
        }
    }
}

// ── helpers ───────────────────────────────────────────────────────────────────

fn is_template_not_found_message(value: &str) -> bool {
    let normalized = value.to_ascii_lowercase();
    normalized.contains("template not found")
        || normalized.contains("no such template")
        || normalized.contains("not found template")
}

/// Parse the tabular output of `cubemastercli tpl list`.
///
/// Expected header: `TEMPLATE_ID  STATUS  CREATED_AT  IMAGE_INFO`
/// Non-header lines with fewer than 3 whitespace-separated tokens are skipped.
/// `CREATED_AT` is expected in RFC 3339 / ISO 8601 UTC format (e.g. `2026-05-04T10:11:23Z`).
/// Lines that fail timestamp parsing are skipped with a warning log.
fn parse_tpl_list_output(stdout: &str) -> Result<Vec<CubemasterTemplate>> {
    let mut templates = Vec::new();
    for line in stdout.lines() {
        let parts: Vec<&str> = line.split_whitespace().collect();
        // Skip header and short/empty lines
        if parts.len() < 3 || parts[0] == "TEMPLATE_ID" {
            continue;
        }
        let template_id = parts[0].to_string();
        let status = parts[1].to_string();
        let created_at_str = parts[2];
        let image_fingerprint = if parts.len() >= 4 {
            Some(parts[3].to_string())
        } else {
            None
        };

        let created_at = match OffsetDateTime::parse(created_at_str, &Rfc3339) {
            Ok(dt) => dt,
            Err(e) => {
                tracing::warn!(
                    template_id,
                    created_at_str,
                    error = %e,
                    "cubemastercli tpl list: failed to parse CREATED_AT; skipping row"
                );
                continue;
            }
        };

        templates.push(CubemasterTemplate {
            template_id,
            kind: String::new(), // not exposed by cubemastercli tpl list
            status,
            created_at,
            image_fingerprint,
        });
    }
    Ok(templates)
}

// ── tests ─────────────────────────────────────────────────────────────────────

#[cfg(test)]
mod tests {
    use super::*;
    use httpmock::prelude::*;

    fn make_client(base_url: &str) -> CubemasterClient {
        CubemasterClient::new(
            CubemasterClientConfig {
                base_url: base_url.to_string(),
                cleanup_timeout_seconds: 5,
                instance_type: "cubebox".to_string(),
            },
            test_cube_config(),
        )
        .unwrap()
    }

    fn test_cube_config() -> CubeSandboxConfig {
        CubeSandboxConfig {
            enabled: true,
            api_base_url: "http://127.0.0.1:23000".to_string(),
            data_plane_base_url: "https://127.0.0.1:21443".to_string(),
            template_id: "tpl-test".to_string(),
            helper_path: "/app/scripts/cubesandbox-quickstart.sh".to_string(),
            work_dir: ".cubesandbox".to_string(),
            auto_start: true,
            auto_install: true,
            helper_timeout_seconds: 600,
            execution_timeout_seconds: 120,
            sandbox_cleanup_timeout_seconds: 30,
            stdout_limit_bytes: 65_536,
            stderr_limit_bytes: 65_536,
            cubemaster_base_url: "http://127.0.0.1:23000".to_string(),
            cubemaster_cleanup_timeout_seconds: 30,
        }
    }

    // ── delete_template tests ─────────────────────────────────────────────────

    #[tokio::test]
    async fn delete_template_success_ret0() {
        let server = MockServer::start();
        let mock = server.mock(|when, then| {
            when.method(DELETE).path("/cube/template");
            then.status(200)
                .json_body(serde_json::json!({"ret": {"ret_code": 0, "ret_msg": "ok"}}));
        });

        let client = make_client(&server.base_url());
        let result = client.delete_template("tpl-abc123").await;
        assert!(result.is_ok(), "expected Ok, got {:?}", result);
        mock.assert();
    }

    #[tokio::test]
    async fn delete_template_idempotent_130404() {
        let server = MockServer::start();
        let mock = server.mock(|when, then| {
            when.method(DELETE).path("/cube/template");
            then.status(200).json_body(serde_json::json!({
                "ret": {"ret_code": 130404, "ret_msg": "template not found"}
            }));
        });

        let client = make_client(&server.base_url());
        let result = client.delete_template("tpl-gone").await;
        assert!(result.is_ok(), "expected idempotent Ok, got {:?}", result);
        mock.assert();
    }

    #[tokio::test]
    async fn delete_template_idempotent_http_404() {
        let server = MockServer::start();
        let mock = server.mock(|when, then| {
            when.method(DELETE).path("/cube/template");
            then.status(404);
        });

        let client = make_client(&server.base_url());
        let result = client.delete_template("tpl-gone").await;
        assert!(
            result.is_ok(),
            "expected HTTP 404 idempotent Ok, got {:?}",
            result
        );
        mock.assert();
    }

    #[tokio::test]
    async fn delete_template_idempotent_no_such_template_message() {
        let server = MockServer::start();
        let mock = server.mock(|when, then| {
            when.method(DELETE).path("/cube/template");
            then.status(200).json_body(serde_json::json!({
                "ret": {"ret_code": 200, "ret_msg": "no such template"}
            }));
        });

        let client = make_client(&server.base_url());
        let result = client.delete_template("tpl-gone").await;
        assert!(
            result.is_ok(),
            "expected no-such-template idempotent Ok, got {:?}",
            result
        );
        mock.assert();
    }

    #[tokio::test]
    async fn delete_template_error_500001() {
        let server = MockServer::start();
        let mock = server.mock(|when, then| {
            when.method(DELETE).path("/cube/template");
            then.status(200).json_body(serde_json::json!({
                "ret": {"ret_code": 500001, "ret_msg": "internal error"}
            }));
        });

        let client = make_client(&server.base_url());
        let result = client.delete_template("tpl-bad").await;
        assert!(result.is_err(), "expected Err for ret_code=500001");
        mock.assert();
    }

    #[tokio::test]
    async fn delete_template_transport_error() {
        // Point at a port nothing listens on
        let client = make_client("http://127.0.0.1:19999");
        let result = client.delete_template("tpl-x").await;
        assert!(result.is_err(), "expected Err on transport failure");
    }

    // ── delete_sandbox tests ──────────────────────────────────────────────────

    #[tokio::test]
    async fn delete_sandbox_success_ret0() {
        let server = MockServer::start();
        let mock = server.mock(|when, then| {
            when.method(DELETE).path("/cube/sandbox");
            then.status(200)
                .json_body(serde_json::json!({"ret": {"ret_code": 0, "ret_msg": "ok"}}));
        });

        let client = make_client(&server.base_url());
        let result = client.delete_sandbox("sb-abc123").await;
        assert!(result.is_ok(), "expected Ok, got {:?}", result);
        mock.assert();
    }

    #[tokio::test]
    async fn delete_sandbox_idempotent_not_found() {
        // SANDBOX_NOT_FOUND_RET_CODE = 200 with "no such sandbox"
        let server = MockServer::start();
        let mock = server.mock(|when, then| {
            when.method(DELETE).path("/cube/sandbox");
            then.status(200).json_body(serde_json::json!({
                "ret": {"ret_code": SANDBOX_NOT_FOUND_RET_CODE, "ret_msg": "no such sandbox"}
            }));
        });

        let client = make_client(&server.base_url());
        let result = client.delete_sandbox("sb-gone").await;
        assert!(
            result.is_ok(),
            "expected idempotent Ok for SANDBOX_NOT_FOUND_RET_CODE, got {:?}",
            result
        );
        mock.assert();
    }

    #[tokio::test]
    async fn delete_sandbox_error_500001() {
        let server = MockServer::start();
        let mock = server.mock(|when, then| {
            when.method(DELETE).path("/cube/sandbox");
            then.status(200).json_body(serde_json::json!({
                "ret": {"ret_code": 500001, "ret_msg": "internal error"}
            }));
        });

        let client = make_client(&server.base_url());
        let result = client.delete_sandbox("sb-bad").await;
        assert!(result.is_err(), "expected Err for ret_code=500001");
        mock.assert();
    }

    #[tokio::test]
    async fn delete_sandbox_transport_error() {
        let client = make_client("http://127.0.0.1:19999");
        let result = client.delete_sandbox("sb-x").await;
        assert!(result.is_err(), "expected Err on transport failure");
    }

    // ── parse_tpl_list_output unit tests ─────────────────────────────────────

    #[test]
    fn parse_tpl_list_header_skipped() {
        let input = "TEMPLATE_ID  STATUS  CREATED_AT  IMAGE_INFO\n";
        let result = parse_tpl_list_output(input).unwrap();
        assert!(result.is_empty());
    }

    #[test]
    fn parse_tpl_list_single_row() {
        let input = "TEMPLATE_ID                     STATUS     CREATED_AT              IMAGE_INFO\n\
                     tpl-1fae012a7bcc45af9bd6cf0d    READY      2026-05-04T10:11:23Z    img@sha256:abc\n";
        let result = parse_tpl_list_output(input).unwrap();
        assert_eq!(result.len(), 1);
        let t = &result[0];
        assert_eq!(t.template_id, "tpl-1fae012a7bcc45af9bd6cf0d");
        assert_eq!(t.status, "READY");
        assert_eq!(t.image_fingerprint.as_deref(), Some("img@sha256:abc"));
    }

    #[test]
    fn parse_tpl_list_bad_timestamp_skipped() {
        let input = "tpl-bad  READY  not-a-date  img\n";
        let result = parse_tpl_list_output(input).unwrap();
        assert!(result.is_empty(), "bad timestamp row should be skipped");
    }

    #[test]
    fn parse_tpl_list_no_image_col() {
        let input = "tpl-abc  FAILED  2026-05-04T08:00:00Z\n";
        let result = parse_tpl_list_output(input).unwrap();
        assert_eq!(result.len(), 1);
        assert!(result[0].image_fingerprint.is_none());
    }
}
