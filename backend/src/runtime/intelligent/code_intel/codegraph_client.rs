//! `CodeGraphClient` — codegraph-backed implementation of `CodeIntelligence`.
//!
//! Wraps a `PodmanSession` and invokes `codegraph` CLI commands inside the
//! container via per-query `exec_command`. Per the GATE-0 G0.5 decision,
//! codegraph's `serve` subcommand is stdio MCP only (no Unix socket), so we
//! use the per-query CLI transport — simpler and avoids new JSON-RPC plumbing.
//!
//! Lifecycle:
//!   1. `CodeGraphClient::init(...)` — extract host-side, bind-mount, run `codegraph init -i`
//!   2. Trait methods invoke `codegraph <subcommand> --json` per query
//!   3. `shutdown()` — destroy `PodmanSession`, remove staging dir
//!
//! See `.omc/plans/ralplan-codegraph-integration-v2.md` §Phase 2 for the full
//! implementation plan. This file currently provides the trait-conforming
//! skeleton; full method bodies land in subsequent commits.

use std::sync::Arc;

use anyhow::{anyhow, Result};
use async_trait::async_trait;

use crate::runtime::intelligent::agent_runner::podman::PodmanSession;

use super::{CallChain, CallNode, CodeContext, CodeIntelligence, SymbolMatch};

/// CodeIntelligence backed by `@colbymchenry/codegraph` inside a PodmanSession.
#[allow(dead_code)] // Phase 2 fields will be exercised once init/query wiring lands.
pub struct CodeGraphClient {
    /// Long-lived session bound to the bind-mounted source + writable index dir.
    pub(crate) session: Arc<PodmanSession>,
    /// SHA256 of the source archive — used as the cache key.
    pub(crate) archive_sha256: String,
    /// Languages detected by codegraph during init. Stages use this to decide
    /// whether to attempt two-pass or fall back per-finding.
    pub(crate) languages: Vec<String>,
    /// Whether `init()` succeeded and the client is ready to serve queries.
    pub(crate) ready: bool,
}

impl CodeGraphClient {
    /// Skeleton constructor — used by tests and by the pipeline runner until
    /// the full `init()` method (Phase 2 §Step 2.4) lands.
    pub(crate) fn new_skeleton(
        session: Arc<PodmanSession>,
        archive_sha256: String,
        languages: Vec<String>,
    ) -> Self {
        Self { session, archive_sha256, languages, ready: false }
    }
}

#[async_trait]
impl CodeIntelligence for CodeGraphClient {
    async fn get_callers(&self, _symbol: &str, _depth: u32) -> Result<Vec<CallNode>> {
        Err(anyhow!("CodeGraphClient::get_callers not yet implemented (Phase 2 §2.5)"))
    }

    async fn get_callees(&self, _symbol: &str, _depth: u32) -> Result<Vec<CallNode>> {
        Err(anyhow!("CodeGraphClient::get_callees not yet implemented (Phase 2 §2.5)"))
    }

    async fn get_context(&self, _file: &str, _line: u32) -> Result<CodeContext> {
        Err(anyhow!("CodeGraphClient::get_context not yet implemented (Phase 2 §2.5)"))
    }

    async fn search_symbol(&self, _name: &str) -> Result<Vec<SymbolMatch>> {
        Err(anyhow!("CodeGraphClient::search_symbol not yet implemented (Phase 2 §2.5)"))
    }

    async fn resolve_symbol_at(&self, _file: &str, _line: u32) -> Result<Option<SymbolMatch>> {
        Err(anyhow!("CodeGraphClient::resolve_symbol_at not yet implemented (Phase 2 §2.5)"))
    }

    async fn get_call_chain(
        &self,
        _from_file: &str,
        _from_line: u32,
        _max_hops: u32,
    ) -> Result<Vec<CallChain>> {
        Err(anyhow!("CodeGraphClient::get_call_chain not yet implemented (Phase 2 §2.5)"))
    }

    fn languages_indexed(&self) -> Vec<String> {
        self.languages.clone()
    }

    fn is_available(&self) -> bool {
        self.ready
    }

    async fn shutdown(&self) -> Result<()> {
        // Phase 2 §2.6 — explicit lifecycle: stop persistent processes (if any),
        // destroy PodmanSession, remove staging dir. Currently a no-op because
        // the full init+lifecycle wiring lands in §2.4–§2.7.
        Ok(())
    }
}
