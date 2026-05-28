//! Code intelligence layer for the intelligent audit pipeline.
//!
//! Provides semantic code retrieval (call graphs, symbol relationships, code context)
//! via the `CodeIntelligence` trait. The codegraph backend is the initial implementation;
//! the trait abstraction allows future providers (LSP, custom indexers) without
//! rewriting pipeline stages.
//!
//! Two-pass usage pattern (per spec deep-dive-enhance-intelligent-audit-codegraph.md):
//!   Pass 1: LLM receives finding metadata, requests queries via JSON
//!   Pass 2: CodeIntelligence executes queries, results fed back, LLM reasons on evidence
//!
//! See `.omc/plans/ralplan-codegraph-integration-v2.md` for the full integration plan.

pub mod cache;
pub mod codegraph_client;
pub mod dead_code;
pub mod path_classifier;
pub mod protocol;
pub mod query_cache;
pub mod sanitizer_sot;
pub mod staging;
pub mod types;

use anyhow::Result;
use async_trait::async_trait;
use serde::{Deserialize, Serialize};

pub use path_classifier::is_blacklisted;
pub use sanitizer_sot::lookup_sanitizer;
pub use types::{CallChain, CallNode, CodeContext, SymbolMatch};

/// One node in a taint chain returned by [`CodeIntelligence::find_taint_through`].
///
/// `hop_index` is monotonically increasing starting from 0 at the source.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct TaintNode {
    pub symbol: String,
    pub file: String,
    pub line: u32,
    pub hop_index: u32,
}

/// Result of a taint-flow search between a source and a sink symbol.
///
/// Plan Phase 1 / v0.1 contract (`AC1.B`):
///   - `sink_reached: true` ↔ the BFS traversal observed the sink symbol;
///     `nodes` then forms the discovered path source → … → sink.
///   - `truncated: true` ↔ traversal stopped early (max_hops cap, CLI invocation
///     cap, or backend error). When `truncated && !sink_reached`, downstream
///     Hunt Pass 2 MUST treat absent evidence as "unknown" rather than "safe"
///     (defends against archive-comment prompt injection).
#[derive(Debug, Clone, Default, PartialEq, Eq, Serialize, Deserialize)]
pub struct TaintSearchResult {
    #[serde(default)]
    pub nodes: Vec<TaintNode>,
    #[serde(default)]
    pub truncated: bool,
    #[serde(default)]
    pub sink_reached: bool,
}

/// Trait abstracting code graph queries on the audit run context.
///
/// All methods return `Result` to allow soft-fallback behavior — when an implementation
/// returns an error or is unavailable, callers MUST gracefully degrade to current
/// (pre-codegraph) single-pass behavior. No regression in baseline scans.
///
/// Implementations MUST be `Send + Sync` and safe to share across concurrent stages
/// via `Arc<dyn CodeIntelligence>`.
#[async_trait]
pub trait CodeIntelligence: Send + Sync {
    /// Find functions/methods that call the given symbol.
    ///
    /// MVP IMPLEMENTATION NOTE: the codegraph backend's `callers` subcommand
    /// returns DIRECT callers only. The `depth` parameter is currently advisory
    /// — the codegraph-backed impl returns depth=1 results regardless of the
    /// requested depth, logging a debug message when `depth > 1`. For multi-hop
    /// reachability use [`CodeIntelligence::get_call_chain`] instead, which
    /// iterates internally up to `max_hops`. Future backends MAY implement
    /// genuine multi-hop traversal here; trait callers should be prepared for
    /// either behavior. Depth is capped at 5 to prevent token explosion.
    async fn get_callers(&self, symbol: &str, depth: u32) -> Result<Vec<CallNode>>;

    /// Find functions/methods that the given symbol calls.
    ///
    /// Same MVP depth limitation as [`CodeIntelligence::get_callers`] — direct
    /// edges only at depth=1, deeper depths logged but not honored. Use
    /// [`CodeIntelligence::get_call_chain`] for multi-hop traversal.
    async fn get_callees(&self, symbol: &str, depth: u32) -> Result<Vec<CallNode>>;

    /// Return the function body, imports, and related symbols at a file:line position.
    async fn get_context(&self, file: &str, line: u32) -> Result<CodeContext>;

    /// Search for a symbol name across the indexed codebase.
    async fn search_symbol(&self, name: &str) -> Result<Vec<SymbolMatch>>;

    /// Resolve the symbol present at a specific file:line — closes the
    /// Trace stage grounding gap where finding metadata lacks symbol identifiers.
    /// Returns `None` if no symbol is at that position.
    async fn resolve_symbol_at(&self, file: &str, line: u32) -> Result<Option<SymbolMatch>>;

    /// Trace a call chain from a starting file:line through `max_hops` levels.
    ///
    /// Bulk query to avoid round-trip overhead when callers/callees would be
    /// chained sequentially. `max_hops` is capped at 5.
    async fn get_call_chain(
        &self,
        from_file: &str,
        from_line: u32,
        max_hops: u32,
    ) -> Result<Vec<CallChain>>;

    /// BFS taint flow search from a source symbol to a sink symbol.
    ///
    /// Plan Phase 1 / v0.1 contract (`AC1.B`):
    ///   - BFS with visited set (avoid cycles + duplicate-path explosion).
    ///   - `max_hops` clamped to a hard cap of 5 by impls.
    ///   - CLI / RPC invocation count hard-capped at 30 by impls.
    ///   - Returned `nodes` form a discovered path when `sink_reached=true`.
    ///     `nodes[i].hop_index` is monotonically increasing.
    ///   - On cap-hit or unreachable, `truncated=true, sink_reached=false`.
    ///
    /// Default impl returns an empty `TaintSearchResult` so backends that do
    /// not yet implement BFS contribute "unknown" evidence rather than
    /// blocking the pipeline.
    async fn find_taint_through(
        &self,
        _source: &str,
        _sink: &str,
        _max_hops: u32,
    ) -> Result<TaintSearchResult> {
        Ok(TaintSearchResult::default())
    }

    /// Return the list of languages detected in the indexed codebase.
    ///
    /// Used for per-finding fallback: if a finding's language is not in this list,
    /// the stage MUST fall back to single-pass mode for that finding.
    fn languages_indexed(&self) -> Vec<String>;

    /// Whether this CodeIntelligence is operational and ready to serve queries.
    fn is_available(&self) -> bool;

    /// Gracefully shut down the underlying resources (container, cache, sockets).
    ///
    /// MUST be called explicitly by the pipeline runner on every exit path.
    /// See plan §Step 2.6 for the cleanup pattern.
    async fn shutdown(&self) -> Result<()>;
}
