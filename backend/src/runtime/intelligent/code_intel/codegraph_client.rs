//! `CodeGraphClient` — codegraph-backed `CodeIntelligence` impl.
//!
//! Transport: **per-query CLI** (GATE-0 G0.5 — `codegraph serve` is stdio MCP
//! only, so a sidecar would just add JSON-RPC plumbing). Each trait method
//! invokes `codegraph <sub> -j` inside the bound PodmanSession and parses the
//! JSON stdout via [`protocol`] types.
//!
//! Lifecycle: [`CodeGraphClient::init`] extracts host-side, optionally restores
//! from cache or runs `codegraph init -i .`, detects languages from
//! `codegraph files -j`; [`CodeGraphClient::shutdown`] destroys the session
//! (staging dir cleans on drop; cache survives, keyed by archive SHA256).
//!
//! Caps: `depth` and `max_hops` clamped to 5; result count clamped to 100.
//!
//! See `.omc/plans/ralplan-codegraph-integration-v2.md` §Phase 2.

use std::path::{Path, PathBuf};
use std::sync::Arc;

use anyhow::{anyhow, bail, Context, Result};
use async_trait::async_trait;
use tracing::{debug, warn};

use crate::runtime::intelligent::agent_runner::podman::PodmanSession;

use super::cache::CodeGraphCache;
use super::protocol::{
    CgCallEdge, CgCalleesResponse, CgCallersResponse, CgFileEntry, CgNode, CgQueryItem,
};
use super::staging::{self, StagingDir};
use super::{
    CallChain, CallNode, CodeContext, CodeIntelligence, SymbolMatch, TaintNode, TaintSearchResult,
};

/// BFS hard cap on `max_hops` for [`CodeGraphClient::find_taint_through`].
/// Beyond 5 the cross-product of caller/callee lookups makes Pass 2 unstable.
const MAX_HOPS_HARD_CAP: u32 = 5;

/// Hard cap on total CLI invocations during one taint search. At ~5s/query this
/// keeps worst-case wall time under ~2.5 minutes regardless of `max_hops`.
const CLI_INVOCATION_HARD_CAP: usize = 30;

/// Max caller/callee depth and call-chain hop count exposed to callers.
const MAX_DEPTH: u32 = 5;
/// Max nodes returned by any single query.
const MAX_RESULTS: usize = 100;
/// Default timeout for a query CLI invocation.
const QUERY_TIMEOUT_MS: u64 = 5_000;
/// Default timeout for `codegraph init`.
const INIT_TIMEOUT_MS: u64 = 60_000;
/// Path inside the container where the indexed source is bind-mounted.
const CONTAINER_SRC: &str = "/codegraph/src";
/// Path inside the container where the writable index dir is bind-mounted.
const CONTAINER_INDEX: &str = "/codegraph/index";
/// Codegraph data root override for deployments with an explicit host-visible path.
const ARGUS_CODEGRAPH_DATA_DIR_ENV: &str = "ARGUS_CODEGRAPH_DATA_DIR";
/// Shared workspace root used by scanner runners and visible to host Podman.
const SCAN_WORKSPACE_ROOT_ENV: &str = "SCAN_WORKSPACE_ROOT";

/// CodeIntelligence backed by `@colbymchenry/codegraph` inside a PodmanSession.
pub struct CodeGraphClient {
    /// Long-lived session bound to the bind-mounted source + writable index dir.
    pub(crate) session: Arc<PodmanSession>,
    /// SHA256 of the source archive — used as the cache key.
    #[allow(dead_code)]
    pub(crate) archive_sha256: String,
    /// Languages detected by codegraph during init.
    pub(crate) languages: Vec<String>,
    /// Whether `init()` succeeded and the client is ready to serve queries.
    pub(crate) ready: bool,
    /// Staging dir RAII guard — removed when last Arc clone drops.
    #[allow(dead_code)]
    pub(crate) staging_dir: Arc<StagingDir>,
    /// Cache handle (kept so commit can be retried if needed by future work).
    #[allow(dead_code)]
    pub(crate) cache: Arc<CodeGraphCache>,
    /// Host-side path of the index dir bind-mounted at `/codegraph/index`.
    #[allow(dead_code)]
    pub(crate) index_host_path: PathBuf,
}

impl CodeGraphClient {
    /// Full bring-up: extract, cache-check or index, detect languages.
    ///
    /// Steps follow plan §Step 2.4. Errors during any step abort init and the
    /// caller is responsible for marking `partial_analysis`.
    pub async fn init(
        archive_path: &Path,
        archive_name: &str,
        archive_sha256: String,
        image: &str,
        cache: Arc<CodeGraphCache>,
    ) -> Result<Self> {
        // 1. Host-side extraction.
        let staging = staging::prepare(archive_path, archive_name, &archive_sha256)
            .await
            .context("staging::prepare failed")?;
        let staging_dir = Arc::new(staging);

        // 2. Host-side index dir (writable bind mount target).
        let index_host_path = build_index_dir(&archive_sha256);
        tokio::fs::create_dir_all(&index_host_path)
            .await
            .with_context(|| format!("create index dir {}", index_host_path.display()))?;
        // Bind-mounted writable target: the codegraph container runs as a
        // non-root UID and the in-container UID often does not map to the host
        // UID owning this dir (backend-in-container + Podman-on-host). Widen
        // perms on the directory so the `cp` step inside the container can
        // write `codegraph.db` regardless of UID mapping.
        #[cfg(unix)]
        {
            use std::os::unix::fs::PermissionsExt;
            let perms = std::fs::Permissions::from_mode(0o777);
            if let Err(e) = tokio::fs::set_permissions(&index_host_path, perms).await {
                warn!(path = %index_host_path.display(), error = %e, "chmod codegraph index dir failed");
            }
        }

        // 3. Try cache.
        let cache_hit = cache
            .try_load(&archive_sha256, &index_host_path)
            .await
            .context("cache.try_load failed")?
            .is_some();
        debug!(sha = %archive_sha256, cache_hit, "codegraph cache check");

        // 4. Create the session (needed whether we ran init or not — queries need it).
        let cache_root = cache_root_path();
        let session = PodmanSession::create_for_codegraph(
            staging_path_str(&staging_dir)?,
            path_str(&index_host_path)?,
            path_str(&cache_root)?,
            image,
        )
        .await
        .context("PodmanSession::create_for_codegraph failed")?;
        let session = Arc::new(session);

        // 5. Cold path: run `codegraph init -i .` inside the container.
        if !cache_hit {
            let cmd = format!("cd {CONTAINER_SRC} && codegraph init -i .");
            let (stdout, stderr, code) = session
                .exec_command(&cmd, INIT_TIMEOUT_MS)
                .await
                .context("codegraph init exec failed")?;
            if code != 0 {
                bail!(
                    "codegraph init exit {code}: stdout={} stderr={}",
                    truncate_for_err(&stdout),
                    truncate_for_err(&stderr),
                );
            }

            // codegraph init writes to `.codegraph/codegraph.db` inside the
            // source tree. Copy to the writable index mount so the cache picks
            // it up (and so subsequent queries can find it).
            let cp = format!(
                "cp {CONTAINER_SRC}/.codegraph/codegraph.db {CONTAINER_INDEX}/codegraph.db",
            );
            let (_, cp_stderr, cp_code) = session
                .exec_command(&cp, 10_000)
                .await
                .context("codegraph index copy exec failed")?;
            if cp_code != 0 {
                bail!(
                    "codegraph index copy exit {cp_code}: {}",
                    truncate_for_err(&cp_stderr)
                );
            }

            // codegraph init wrote `.codegraph/` into the staging tree.
            // Those files are owned by the container's UID — the host
            // side cannot delete them. Remove them here while the
            // container is still running (its UID owns the files).
            let cleanup = format!("rm -rf {CONTAINER_SRC}/.codegraph");
            match session.exec_command(&cleanup, 5_000).await {
                Ok((_, _, 0)) => {}
                Ok((_, stderr, code)) => {
                    debug!(code, stderr = %truncate_for_err(&stderr), "rm .codegraph/ non-zero exit");
                }
                Err(e) => {
                    debug!(error = %e, "rm .codegraph/ exec failed");
                }
            }

            // Commit to the host-side cache (best-effort — log on failure).
            let host_db = index_host_path.join("codegraph.db");
            if let Err(e) = cache.commit(&archive_sha256, &host_db).await {
                warn!(error = %e, sha = %archive_sha256, "codegraph cache commit failed");
            }
        }

        // 6. Language detection — parse `codegraph files -j --path /codegraph/src`.
        let languages = detect_languages(&session).await.unwrap_or_else(|e| {
            warn!(error = %e, "language detection failed; proceeding with empty list");
            Vec::new()
        });

        Ok(Self {
            session,
            archive_sha256,
            languages,
            ready: true,
            staging_dir,
            cache,
            index_host_path,
        })
    }

    /// Build or refresh the archive's persistent codegraph cache and then stop
    /// the temporary query container. Project import uses this to pre-warm the
    /// index so later intelligent scans avoid the cold `codegraph init` path.
    pub async fn ensure_index_cached(
        archive_path: &Path,
        archive_name: &str,
        archive_sha256: String,
        image: &str,
        cache: Arc<CodeGraphCache>,
    ) -> Result<Vec<String>> {
        let client = Self::init(archive_path, archive_name, archive_sha256, image, cache).await?;
        let languages = client.languages_indexed();
        client.shutdown().await?;
        Ok(languages)
    }
}

#[async_trait]
impl CodeIntelligence for CodeGraphClient {
    async fn get_callers(&self, symbol: &str, depth: u32) -> Result<Vec<CallNode>> {
        self.ready_check()?;
        let depth = depth.min(MAX_DEPTH).max(1);
        let cmd = format!(
            "codegraph callers {} --path {CONTAINER_SRC} -j -l {}",
            sh_quote(symbol),
            MAX_RESULTS,
        );
        let resp: CgCallersResponse = run_json(&self.session, &cmd).await?;
        // codegraph `callers` returns direct callers only; deeper hops require
        // iterative invocation. MVP returns depth=1 only and tags the depth on
        // each node so callers can decide whether to traverse further.
        if depth > 1 {
            debug!(
                requested_depth = depth,
                "codegraph callers returns direct edges only; deeper depth ignored at MVP",
            );
        }
        Ok(resp
            .callers
            .into_iter()
            .take(MAX_RESULTS)
            .map(|e| call_edge_to_node(e, 1))
            .collect())
    }

    async fn get_callees(&self, symbol: &str, depth: u32) -> Result<Vec<CallNode>> {
        self.ready_check()?;
        let depth = depth.min(MAX_DEPTH).max(1);
        let cmd = format!(
            "codegraph callees {} --path {CONTAINER_SRC} -j -l {}",
            sh_quote(symbol),
            MAX_RESULTS,
        );
        let resp: CgCalleesResponse = run_json(&self.session, &cmd).await?;
        if depth > 1 {
            debug!(
                requested_depth = depth,
                "codegraph callees returns direct edges only; deeper depth ignored at MVP",
            );
        }
        Ok(resp
            .callees
            .into_iter()
            .take(MAX_RESULTS)
            .map(|e| call_edge_to_node(e, 1))
            .collect())
    }

    async fn get_context(&self, file: &str, line: u32) -> Result<CodeContext> {
        self.ready_check()?;
        // No direct codegraph subcommand for file:line context; query everything
        // and locally filter by file_path + line range.
        let cmd = format!(
            "codegraph query '*' --path {CONTAINER_SRC} -j -l {}",
            MAX_RESULTS * 2,
        );
        let items: Vec<CgQueryItem> = run_json(&self.session, &cmd).await?;
        let best = items
            .iter()
            .find(|it| it.node.file_path == file && range_contains(&it.node, line))
            .cloned();

        let related: Vec<SymbolMatch> = items
            .into_iter()
            .filter(|it| it.node.file_path == file)
            .take(MAX_RESULTS)
            .map(|it| node_to_symbol(it.node))
            .collect();

        Ok(CodeContext {
            file: file.to_string(),
            line,
            function_body: best.and_then(|it| it.node.signature),
            imports: Vec::new(),
            related_symbols: related,
        })
    }

    async fn search_symbol(&self, name: &str) -> Result<Vec<SymbolMatch>> {
        self.ready_check()?;
        let cmd = format!(
            "codegraph query {} --path {CONTAINER_SRC} -j -l 50",
            sh_quote(name),
        );
        let items: Vec<CgQueryItem> = run_json(&self.session, &cmd).await?;
        Ok(items
            .into_iter()
            .take(MAX_RESULTS)
            .map(|it| node_to_symbol(it.node))
            .collect())
    }

    async fn resolve_symbol_at(&self, file: &str, line: u32) -> Result<Option<SymbolMatch>> {
        self.ready_check()?;
        let cmd = format!("codegraph query '*' --path {CONTAINER_SRC} -j -l 200",);
        let items: Vec<CgQueryItem> = run_json(&self.session, &cmd).await?;
        Ok(items
            .into_iter()
            .find(|it| it.node.file_path == file && range_contains(&it.node, line))
            .map(|it| node_to_symbol(it.node)))
    }

    async fn get_call_chain(
        &self,
        from_file: &str,
        from_line: u32,
        max_hops: u32,
    ) -> Result<Vec<CallChain>> {
        self.ready_check()?;
        let max_hops = max_hops.clamp(1, MAX_DEPTH);

        let Some(start) = self.resolve_symbol_at(from_file, from_line).await? else {
            return Ok(Vec::new());
        };

        let mut nodes = vec![CallNode {
            symbol: start.symbol.clone(),
            file: start.file.clone(),
            line: start.line,
            language: start.language.clone(),
            depth: 0,
        }];
        let mut current = start.symbol.clone();
        let mut truncated = false;
        for hop in 1..=max_hops {
            let callees = match self.get_callees(&current, 1).await {
                Ok(v) => v,
                Err(e) => {
                    warn!(symbol = %current, hop, error = %e, "callees lookup failed mid-chain");
                    truncated = true;
                    break;
                }
            };
            let Some(next) = callees.into_iter().next() else {
                break;
            };
            current = next.symbol.clone();
            nodes.push(CallNode { depth: hop, ..next });
            if hop == max_hops {
                truncated = true;
            }
        }
        Ok(vec![CallChain { nodes, truncated }])
    }

    async fn find_taint_through(
        &self,
        source: &str,
        sink: &str,
        max_hops: u32,
    ) -> Result<TaintSearchResult> {
        self.ready_check()?;
        // Adapt &self.get_callees into the closure the pure BFS expects.
        bfs_taint_search(source, sink, max_hops, |sym| async move {
            self.get_callees(&sym, 1).await
        })
        .await
    }

    fn languages_indexed(&self) -> Vec<String> {
        self.languages.clone()
    }

    fn is_available(&self) -> bool {
        self.ready
    }

    async fn shutdown(&self) -> Result<()> {
        // Per-query CLI transport — no persistent server to stop (GATE-0 G0.5).
        // Destroy the container; staging dir cleans itself when the last Arc<StagingDir>
        // drops (Drop on TempCleanupGuard).
        self.session
            .destroy()
            .await
            .context("PodmanSession::destroy failed")?;
        Ok(())
    }
}

impl CodeGraphClient {
    fn ready_check(&self) -> Result<()> {
        if !self.ready {
            bail!("CodeGraphClient not ready — init() has not completed");
        }
        Ok(())
    }
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

fn codegraph_data_root() -> PathBuf {
    std::env::var(ARGUS_CODEGRAPH_DATA_DIR_ENV)
        .ok()
        .map(|value| PathBuf::from(value.trim()))
        .filter(|value| !value.as_os_str().is_empty())
        .unwrap_or_else(|| {
            std::env::var(SCAN_WORKSPACE_ROOT_ENV)
                .ok()
                .map(|value| PathBuf::from(value.trim()))
                .filter(|value| !value.as_os_str().is_empty())
                .unwrap_or_else(|| PathBuf::from("/tmp/argus-codegraph"))
                .join("codegraph")
        })
}

fn build_index_dir(sha: &str) -> PathBuf {
    codegraph_data_root().join("indexes").join(sha)
}

fn cache_root_path() -> PathBuf {
    codegraph_data_root().join("cache")
}

fn staging_path_str(staging: &StagingDir) -> Result<&str> {
    staging
        .root
        .to_str()
        .ok_or_else(|| anyhow!("staging path is not valid UTF-8"))
}

fn path_str(p: &Path) -> Result<&str> {
    p.to_str()
        .ok_or_else(|| anyhow!("path is not valid UTF-8: {}", p.display()))
}

/// Single-quote escape for shell-passed arguments.
fn sh_quote(s: &str) -> String {
    format!("'{}'", s.replace('\'', "'\\''"))
}

/// Execute a codegraph CLI command inside the container and parse stdout as JSON.
async fn run_json<T: serde::de::DeserializeOwned>(session: &PodmanSession, cmd: &str) -> Result<T> {
    let (stdout, stderr, code) = session
        .exec_command(cmd, QUERY_TIMEOUT_MS)
        .await
        .with_context(|| format!("exec_command failed for: {cmd}"))?;
    if code != 0 {
        bail!(
            "codegraph CLI exit {code} for `{cmd}`: stderr={}",
            truncate_for_err(&stderr),
        );
    }
    serde_json::from_str::<T>(stdout.trim()).with_context(|| {
        format!(
            "JSON parse failed for `{cmd}` — first 200 bytes of stdout: {}",
            stdout.chars().take(200).collect::<String>(),
        )
    })
}

async fn detect_languages(session: &PodmanSession) -> Result<Vec<String>> {
    let cmd = format!("codegraph files -j --path {CONTAINER_SRC}");
    let files: Vec<CgFileEntry> = run_json(session, &cmd).await?;
    let mut langs: Vec<String> = files
        .into_iter()
        .map(|f| f.language)
        .filter(|l| !l.is_empty())
        .collect();
    langs.sort();
    langs.dedup();
    Ok(langs)
}

fn call_edge_to_node(edge: CgCallEdge, depth: u32) -> CallNode {
    CallNode {
        symbol: edge.name,
        file: edge.file_path,
        line: edge.start_line,
        // codegraph callers/callees compact shape doesn't include language;
        // leave empty so stages can fall back via file extension if needed.
        language: String::new(),
        depth,
    }
}

fn node_to_symbol(node: CgNode) -> SymbolMatch {
    SymbolMatch {
        symbol: if node.qualified_name.is_empty() {
            node.name
        } else {
            node.qualified_name
        },
        file: node.file_path,
        line: node.start_line,
        language: node.language,
        kind: node.kind,
    }
}

fn range_contains(node: &CgNode, line: u32) -> bool {
    let end = if node.end_line == 0 {
        node.start_line
    } else {
        node.end_line
    };
    node.start_line <= line && line <= end
}

fn truncate_for_err(s: &str) -> String {
    s.chars().take(400).collect()
}

// ---------------------------------------------------------------------------
// BFS taint search — pure (testable) core
// ---------------------------------------------------------------------------

/// Pure BFS taint search core, parameterised over an async `get_callees` provider.
///
/// Same contract as [`CodeGraphClient::find_taint_through`] but the get_callees
/// step is supplied by the caller (so unit tests can inject a fixed graph
/// without spinning up codegraph). Live impl threads `client.get_callees` here.
async fn bfs_taint_search<F, Fut>(
    source: &str,
    sink: &str,
    max_hops: u32,
    mut get_callees_fn: F,
) -> Result<TaintSearchResult>
where
    F: FnMut(String) -> Fut,
    Fut: std::future::Future<Output = Result<Vec<CallNode>>>,
{
    use std::collections::{HashMap, HashSet, VecDeque};

    let max_hops = max_hops.clamp(1, MAX_HOPS_HARD_CAP);
    if source.is_empty() || sink.is_empty() {
        return Ok(TaintSearchResult {
            nodes: Vec::new(),
            truncated: true,
            sink_reached: false,
        });
    }
    if source == sink {
        return Ok(TaintSearchResult {
            nodes: vec![TaintNode {
                symbol: source.to_string(),
                file: String::new(),
                line: 0,
                hop_index: 0,
            }],
            truncated: false,
            sink_reached: true,
        });
    }

    let mut frontier: VecDeque<(CallNode, u32)> = VecDeque::new();
    let mut visited: HashSet<String> = HashSet::new();
    let mut parent: HashMap<String, CallNode> = HashMap::new();
    let mut cli_invocations: usize = 0;
    let mut truncated = false;

    let source_seed = CallNode {
        symbol: source.to_string(),
        file: String::new(),
        line: 0,
        language: String::new(),
        depth: 0,
    };
    frontier.push_back((source_seed, 0));
    visited.insert(source.to_string());

    let mut sink_node: Option<CallNode> = None;
    'bfs: while let Some((current, depth)) = frontier.pop_front() {
        if depth >= max_hops {
            truncated = true;
            continue;
        }
        if cli_invocations >= CLI_INVOCATION_HARD_CAP {
            truncated = true;
            break 'bfs;
        }
        cli_invocations += 1;
        let callees = match get_callees_fn(current.symbol.clone()).await {
            Ok(v) => v,
            Err(err) => {
                warn!(
                    symbol = %current.symbol,
                    depth,
                    error = %err,
                    "get_callees failed mid taint search; truncating"
                );
                truncated = true;
                continue;
            }
        };
        for next in callees {
            if visited.contains(&next.symbol) {
                continue;
            }
            visited.insert(next.symbol.clone());
            parent.insert(next.symbol.clone(), current.clone());

            if next.symbol == sink {
                sink_node = Some(next);
                break 'bfs;
            }
            frontier.push_back((next, depth + 1));
        }
    }

    if let Some(end) = sink_node {
        let mut path: Vec<CallNode> = vec![end.clone()];
        let mut cursor = end.symbol.clone();
        while let Some(prev) = parent.get(&cursor) {
            path.push(prev.clone());
            if prev.symbol == source {
                break;
            }
            cursor = prev.symbol.clone();
        }
        path.reverse();
        let nodes: Vec<TaintNode> = path
            .into_iter()
            .enumerate()
            .map(|(i, n)| TaintNode {
                symbol: n.symbol,
                file: n.file,
                line: n.line,
                hop_index: i as u32,
            })
            .collect();
        return Ok(TaintSearchResult {
            nodes,
            truncated: false,
            sink_reached: true,
        });
    }

    if truncated {
        warn!(
            target: "argus::code_intel",
            source = %source,
            sink = %sink,
            max_hops,
            cli_invocations,
            "taint_search_truncated"
        );
    }
    Ok(TaintSearchResult {
        nodes: Vec::new(),
        truncated,
        sink_reached: false,
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::sync::{LazyLock, Mutex};

    static TEST_ENV_LOCK: LazyLock<Mutex<()>> = LazyLock::new(|| Mutex::new(()));

    struct EnvVarGuard {
        key: &'static str,
        previous: Option<String>,
    }

    impl EnvVarGuard {
        fn set(key: &'static str, value: &str) -> Self {
            let previous = std::env::var(key).ok();
            std::env::set_var(key, value);
            Self { key, previous }
        }

        fn remove(key: &'static str) -> Self {
            let previous = std::env::var(key).ok();
            std::env::remove_var(key);
            Self { key, previous }
        }
    }

    impl Drop for EnvVarGuard {
        fn drop(&mut self) {
            if let Some(value) = &self.previous {
                std::env::set_var(self.key, value);
            } else {
                std::env::remove_var(self.key);
            }
        }
    }

    fn make_node(file: &str, sl: u32, el: u32) -> CgNode {
        CgNode {
            id: "id".into(),
            kind: "function".into(),
            name: "f".into(),
            qualified_name: "mod::f".into(),
            file_path: file.into(),
            language: "rust".into(),
            start_line: sl,
            end_line: el,
            start_column: 0,
            end_column: 0,
            signature: Some("fn f()".into()),
            visibility: None,
            is_exported: false,
            is_async: false,
        }
    }

    #[test]
    fn sh_quote_escapes_single_quotes() {
        assert_eq!(sh_quote("foo"), "'foo'");
        assert_eq!(sh_quote("a'b"), "'a'\\''b'");
    }

    #[test]
    fn range_contains_inclusive_bounds() {
        let n = make_node("x.rs", 10, 20);
        assert!(range_contains(&n, 10));
        assert!(range_contains(&n, 15));
        assert!(range_contains(&n, 20));
        assert!(!range_contains(&n, 9));
        assert!(!range_contains(&n, 21));
    }

    #[test]
    fn range_contains_handles_missing_end_line() {
        let n = make_node("x.rs", 7, 0);
        assert!(range_contains(&n, 7));
        assert!(!range_contains(&n, 8));
    }

    #[test]
    fn call_edge_to_node_passes_through_fields() {
        let edge = CgCallEdge {
            name: "render".into(),
            kind: "method".into(),
            file_path: "src/render.ts".into(),
            start_line: 42,
        };
        let n = call_edge_to_node(edge, 3);
        assert_eq!(n.symbol, "render");
        assert_eq!(n.file, "src/render.ts");
        assert_eq!(n.line, 42);
        assert_eq!(n.depth, 3);
        // language intentionally left empty — codegraph edge schema omits it.
        assert_eq!(n.language, "");
    }

    #[test]
    fn node_to_symbol_prefers_qualified_name() {
        let n = make_node("x.rs", 1, 5);
        let s = node_to_symbol(n);
        assert_eq!(s.symbol, "mod::f");
        assert_eq!(s.file, "x.rs");
        assert_eq!(s.line, 1);
        assert_eq!(s.language, "rust");
        assert_eq!(s.kind, "function");
    }

    #[test]
    fn node_to_symbol_falls_back_to_name_when_qualified_empty() {
        let mut n = make_node("x.rs", 1, 5);
        n.qualified_name = String::new();
        n.name = "bare".into();
        let s = node_to_symbol(n);
        assert_eq!(s.symbol, "bare");
    }

    #[test]
    fn codegraph_data_root_defaults_to_shared_scan_workspace() {
        let _lock = TEST_ENV_LOCK.lock().expect("env lock");
        let scan_root = tempfile::tempdir().expect("scan root");
        let _override_guard = EnvVarGuard::remove(ARGUS_CODEGRAPH_DATA_DIR_ENV);
        let _scan_guard =
            EnvVarGuard::set(SCAN_WORKSPACE_ROOT_ENV, scan_root.path().to_str().unwrap());

        assert_eq!(codegraph_data_root(), scan_root.path().join("codegraph"));
        assert_eq!(
            build_index_dir("abc"),
            scan_root.path().join("codegraph/indexes/abc")
        );
        assert_eq!(cache_root_path(), scan_root.path().join("codegraph/cache"));
    }

    #[test]
    fn codegraph_data_root_allows_explicit_host_visible_override() {
        let _lock = TEST_ENV_LOCK.lock().expect("env lock");
        let override_root = tempfile::tempdir().expect("override root");
        let scan_root = tempfile::tempdir().expect("scan root");
        let _override_guard = EnvVarGuard::set(
            ARGUS_CODEGRAPH_DATA_DIR_ENV,
            override_root.path().to_str().unwrap(),
        );
        let _scan_guard =
            EnvVarGuard::set(SCAN_WORKSPACE_ROOT_ENV, scan_root.path().to_str().unwrap());

        assert_eq!(codegraph_data_root(), override_root.path());
        assert_eq!(
            build_index_dir("abc"),
            override_root.path().join("indexes/abc")
        );
        assert_eq!(cache_root_path(), override_root.path().join("cache"));
    }

    // -----------------------------------------------------------------------
    // BFS taint search tests (`find_taint_through` core).
    // -----------------------------------------------------------------------

    fn cn(sym: &str, file: &str, line: u32) -> CallNode {
        CallNode {
            symbol: sym.to_string(),
            file: file.to_string(),
            line,
            language: "test".to_string(),
            depth: 0,
        }
    }

    /// Build a closure that returns canned callees from a static map.
    fn graph_provider(
        graph: std::collections::HashMap<&'static str, Vec<CallNode>>,
    ) -> impl FnMut(
        String,
    ) -> std::pin::Pin<
        Box<dyn std::future::Future<Output = Result<Vec<CallNode>>> + Send>,
    > {
        move |sym: String| {
            let v = graph.get(sym.as_str()).cloned().unwrap_or_default();
            Box::pin(async move { Ok(v) })
        }
    }

    #[tokio::test]
    async fn bfs_finds_sink_with_monotonic_hop_index() {
        // src → mid → sink
        let mut g = std::collections::HashMap::new();
        g.insert("src", vec![cn("mid", "a.rs", 10)]);
        g.insert("mid", vec![cn("sink", "b.rs", 20)]);
        g.insert("sink", vec![]);
        let result = bfs_taint_search("src", "sink", 3, graph_provider(g))
            .await
            .expect("bfs");
        assert!(result.sink_reached, "should reach sink: {result:?}");
        assert!(!result.truncated);
        let symbols: Vec<&str> = result.nodes.iter().map(|n| n.symbol.as_str()).collect();
        assert_eq!(symbols, vec!["src", "mid", "sink"]);
        let hop_indices: Vec<u32> = result.nodes.iter().map(|n| n.hop_index).collect();
        assert_eq!(hop_indices, vec![0, 1, 2], "hop_index must be monotonic");
    }

    #[tokio::test]
    async fn bfs_max_hops_one_with_no_direct_edge_truncates() {
        // src → mid → sink; max_hops = 1 cannot reach sink (needs 2 hops).
        let mut g = std::collections::HashMap::new();
        g.insert("src", vec![cn("mid", "a.rs", 1)]);
        g.insert("mid", vec![cn("sink", "b.rs", 2)]);
        let result = bfs_taint_search("src", "sink", 1, graph_provider(g))
            .await
            .expect("bfs");
        assert!(
            !result.sink_reached,
            "max_hops=1 cannot reach sink: {result:?}"
        );
        assert!(
            result.truncated,
            "truncated must be set when hop cap blocks search"
        );
        assert!(result.nodes.is_empty(), "no path returned on truncation");
    }

    #[tokio::test]
    async fn bfs_cycle_does_not_infinite_loop() {
        // src → a → b → a (cycle), sink is reachable only via straight path → not reached.
        let mut g = std::collections::HashMap::new();
        g.insert("src", vec![cn("a", "x.rs", 1)]);
        g.insert("a", vec![cn("b", "x.rs", 2)]);
        g.insert("b", vec![cn("a", "x.rs", 1)]); // cycle back to a
        let result = bfs_taint_search("src", "sink", 5, graph_provider(g))
            .await
            .expect("bfs");
        assert!(!result.sink_reached, "sink unreachable in this graph");
        // Sink not reached; visited set prevented infinite loop. Either
        // truncated (hop cap reached against cycle) or simply finished —
        // both acceptable: the load-bearing assertion is that we returned.
    }

    #[tokio::test]
    async fn bfs_source_equals_sink_short_circuits() {
        let g = std::collections::HashMap::new();
        let result = bfs_taint_search("same", "same", 5, graph_provider(g))
            .await
            .expect("bfs");
        assert!(result.sink_reached);
        assert!(!result.truncated);
        assert_eq!(result.nodes.len(), 1);
        assert_eq!(result.nodes[0].symbol, "same");
        assert_eq!(result.nodes[0].hop_index, 0);
    }

    #[tokio::test]
    async fn bfs_empty_source_or_sink_returns_truncated_unreachable() {
        let g = std::collections::HashMap::new();
        let result = bfs_taint_search("", "sink", 3, graph_provider(g))
            .await
            .expect("bfs");
        assert!(!result.sink_reached);
        assert!(result.truncated);
    }
}
