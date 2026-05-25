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

pub mod codegraph_client;
pub mod types;

use anyhow::Result;
use async_trait::async_trait;

pub use types::{CallChain, CallNode, CodeContext, SymbolMatch};

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
    /// Find all functions/methods that call the given symbol, up to `depth` hops.
    ///
    /// Depth is capped at 5 inside the implementation to prevent token explosion.
    async fn get_callers(&self, symbol: &str, depth: u32) -> Result<Vec<CallNode>>;

    /// Find all functions/methods that the given symbol calls, up to `depth` hops.
    ///
    /// Depth is capped at 5 inside the implementation.
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
