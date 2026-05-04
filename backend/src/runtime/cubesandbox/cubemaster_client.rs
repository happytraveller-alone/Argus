use std::time::Duration;

use anyhow::{bail, Context, Result};
use reqwest::Client;
use serde::{Deserialize, Serialize};
use uuid::Uuid;

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
}

#[derive(Debug, Serialize)]
struct DeleteTemplateBody {
    #[serde(rename = "RequestID")]
    request_id: String,
    template_id: String,
    instance_type: String,
    sync: bool,
}

#[derive(Debug, Deserialize)]
struct RetEnvelope {
    ret: Ret,
}

#[derive(Debug, Deserialize)]
struct Ret {
    ret_code: i32,
    ret_msg: String,
}

impl CubemasterClient {
    pub fn new(config: CubemasterClientConfig) -> Result<Self> {
        let http_client = Client::builder()
            .timeout(Duration::from_secs(config.cleanup_timeout_seconds.max(1)))
            .build()
            .context("failed to build reqwest client for CubemasterClient")?;
        Ok(Self {
            http_client,
            config,
        })
    }

    /// DELETE /cube/template — delete a template by id.
    ///
    /// Idempotent: `ret_code=130404` (NotFound) is treated as success so that
    /// retries after a partial failure do not surface spurious errors.
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
}
