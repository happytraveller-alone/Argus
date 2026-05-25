//! Shared types for the code intelligence layer.
//!
//! Returned by `CodeIntelligence` trait methods. JSON-serializable for round-trip
//! through LLM prompts in the two-pass retrieval pattern.

use serde::{Deserialize, Serialize};

/// A node in the call graph — represents a function or method.
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct CallNode {
    pub symbol: String,
    pub file: String,
    pub line: u32,
    pub language: String,
    /// Depth from the original query symbol (0 = the symbol itself, 1 = direct caller/callee, …)
    pub depth: u32,
}

/// Structured code context at a file:line position.
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct CodeContext {
    pub file: String,
    pub line: u32,
    /// The enclosing function/method body, if any.
    pub function_body: Option<String>,
    /// Import statements visible at this position.
    pub imports: Vec<String>,
    /// Related symbols (referenced types, callees, etc.).
    pub related_symbols: Vec<SymbolMatch>,
}

/// A symbol match returned by `search_symbol` or `resolve_symbol_at`.
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct SymbolMatch {
    pub symbol: String,
    pub file: String,
    pub line: u32,
    pub language: String,
    /// Symbol kind: "function", "method", "class", "struct", "trait", etc.
    pub kind: String,
}

/// A traced call chain from a source position through N hops.
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct CallChain {
    /// Ordered list of nodes in the chain; first = source, last = sink reached.
    pub nodes: Vec<CallNode>,
    /// Whether the chain terminated at `max_hops` (true) or reached a leaf (false).
    pub truncated: bool,
}
