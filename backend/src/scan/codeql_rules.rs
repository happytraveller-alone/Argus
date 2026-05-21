use anyhow::Result;

use crate::{db::scan_rule_assets, state::{AppState, ScanRuleAsset}};

const CODEQL_ENGINE: &str = "codeql";
const CODEQL_RULE_SOURCE_KINDS: &[&str] = &["internal_query_pack"];

pub async fn load_rule_assets(state: &AppState) -> Result<Vec<ScanRuleAsset>> {
    scan_rule_assets::load_assets_by_engine(state, CODEQL_ENGINE, CODEQL_RULE_SOURCE_KINDS).await
}
