//! Wire-format JSON types for the codegraph CLI (`-j/--json` flag).
//!
//! Schemas reverse-engineered from `@colbymchenry/codegraph@0.9.4` CLI output
//! during GATE-0 G0.3 probes. See `.omc/plans/ralplan-codegraph-integration-v2.md`
//! §G0.3 for raw probe transcripts.
//!
//! Wire types are deliberately distinct from public `types.rs` (CallNode etc.)
//! so the conversion layer in `codegraph_client.rs` can normalize CLI output
//! into the trait-facing representation.

use serde::{Deserialize, Serialize};

/// `codegraph query <pattern> -j` response — array of matched nodes with scores.
#[derive(Debug, Clone, Deserialize, Serialize)]
pub struct CgQueryItem {
    pub node: CgNode,
    #[serde(default)]
    pub score: f64,
}

/// `codegraph callers <symbol> -j` response.
#[derive(Debug, Clone, Deserialize)]
pub struct CgCallersResponse {
    #[serde(default)]
    pub symbol: String,
    #[serde(default)]
    pub callers: Vec<CgCallEdge>,
}

/// `codegraph callees <symbol> -j` response.
#[derive(Debug, Clone, Deserialize)]
pub struct CgCalleesResponse {
    #[serde(default)]
    pub symbol: String,
    #[serde(default)]
    pub callees: Vec<CgCallEdge>,
}

/// `codegraph impact <symbol> -j` response.
#[derive(Debug, Clone, Deserialize)]
pub struct CgImpactResponse {
    #[serde(default)]
    pub symbol: String,
    #[serde(default)]
    pub depth: u32,
    #[serde(default, rename = "nodeCount")]
    pub node_count: u32,
    #[serde(default, rename = "edgeCount")]
    pub edge_count: u32,
    #[serde(default)]
    pub affected: Vec<CgCallEdge>,
}

/// A single caller/callee edge entry. Compact shape used by callers, callees, impact.
#[derive(Debug, Clone, Deserialize)]
pub struct CgCallEdge {
    #[serde(default)]
    pub name: String,
    #[serde(default)]
    pub kind: String,
    #[serde(default, rename = "filePath")]
    pub file_path: String,
    #[serde(default, rename = "startLine")]
    pub start_line: u32,
}

/// Full node shape used by `query` (verbose schema with positional metadata).
#[derive(Debug, Clone, Deserialize, Serialize)]
pub struct CgNode {
    #[serde(default)]
    pub id: String,
    #[serde(default)]
    pub kind: String,
    #[serde(default)]
    pub name: String,
    #[serde(default, rename = "qualifiedName")]
    pub qualified_name: String,
    #[serde(default, rename = "filePath")]
    pub file_path: String,
    #[serde(default)]
    pub language: String,
    #[serde(default, rename = "startLine")]
    pub start_line: u32,
    #[serde(default, rename = "endLine")]
    pub end_line: u32,
    #[serde(default, rename = "startColumn")]
    pub start_column: u32,
    #[serde(default, rename = "endColumn")]
    pub end_column: u32,
    #[serde(default)]
    pub signature: Option<String>,
    #[serde(default)]
    pub visibility: Option<String>,
    #[serde(default, rename = "isExported")]
    pub is_exported: bool,
    #[serde(default, rename = "isAsync")]
    pub is_async: bool,
}

/// `codegraph files -j` response — array of file metadata.
#[derive(Debug, Clone, Deserialize)]
pub struct CgFileEntry {
    #[serde(default)]
    pub path: String,
    #[serde(default)]
    pub language: String,
    #[serde(default, rename = "nodeCount")]
    pub node_count: u32,
    #[serde(default)]
    pub size: u64,
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn parses_callees_response() {
        let s = r#"{
            "symbol": "main",
            "callees": [
                {"name": "render", "kind": "method", "filePath": "src/foo.ts", "startLine": 87}
            ]
        }"#;
        let parsed: CgCalleesResponse = serde_json::from_str(s).unwrap();
        assert_eq!(parsed.symbol, "main");
        assert_eq!(parsed.callees.len(), 1);
        assert_eq!(parsed.callees[0].name, "render");
        assert_eq!(parsed.callees[0].start_line, 87);
    }

    #[test]
    fn parses_query_response() {
        let s = r#"[
            {"node": {"id":"x","kind":"function","name":"foo","qualifiedName":"foo","filePath":"a.rs","language":"rust","startLine":1,"endLine":5,"startColumn":0,"endColumn":0,"isExported":true,"isAsync":false}, "score": 99.0}
        ]"#;
        let parsed: Vec<CgQueryItem> = serde_json::from_str(s).unwrap();
        assert_eq!(parsed.len(), 1);
        assert_eq!(parsed[0].node.name, "foo");
        assert!((parsed[0].score - 99.0).abs() < 1e-6);
    }

    #[test]
    fn parses_empty_callers() {
        let s = r#"{"symbol": "x", "callers": []}"#;
        let parsed: CgCallersResponse = serde_json::from_str(s).unwrap();
        assert!(parsed.callers.is_empty());
    }
}
