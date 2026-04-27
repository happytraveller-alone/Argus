use serde::{Deserialize, Serialize};
use serde_json::{json, Value};

pub const P1_TOPOLOGY_VERSION: &str = "agentflow-p1-v1";

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq)]
pub struct PipelineNode {
    pub id: String,
    pub role: String,
    pub name: String,
    pub depends_on: Vec<String>,
}

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq)]
pub struct PipelineSpec {
    pub topology_version: String,
    pub target: String,
    pub nodes: Vec<PipelineNode>,
}

pub fn render_p1_pipeline() -> PipelineSpec {
    PipelineSpec {
        topology_version: P1_TOPOLOGY_VERSION.to_string(),
        target: "local_or_controlled_container".to_string(),
        nodes: vec![
            PipelineNode {
                id: "context_prepare".to_string(),
                role: "env-inter".to_string(),
                name: "Context Prepare".to_string(),
                depends_on: Vec::new(),
            },
            PipelineNode {
                id: "scope_recon".to_string(),
                role: "env-inter".to_string(),
                name: "Scope Recon".to_string(),
                depends_on: vec!["context_prepare".to_string()],
            },
            PipelineNode {
                id: "vulnerability_analysis".to_string(),
                role: "vuln-reasoner".to_string(),
                name: "Vulnerability Analysis".to_string(),
                depends_on: vec!["scope_recon".to_string()],
            },
            PipelineNode {
                id: "verification_loop".to_string(),
                role: "vuln-reasoner".to_string(),
                name: "Verification Loop".to_string(),
                depends_on: vec!["vulnerability_analysis".to_string()],
            },
            PipelineNode {
                id: "report".to_string(),
                role: "audit-reporter".to_string(),
                name: "Audit Reporter".to_string(),
                depends_on: vec!["verification_loop".to_string()],
            },
        ],
    }
}

pub fn render_p1_pipeline_json() -> Value {
    let spec = render_p1_pipeline();
    json!({
        "runtime": "agentflow",
        "topology_version": spec.topology_version,
        "target": spec.target,
        "nodes": spec.nodes,
        "boundary": {
            "remote_target": false,
            "serve_enabled": false,
            "dynamic_experts": false,
        }
    })
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct PipelineValidationError {
    pub reason_code: &'static str,
    pub message: String,
}

pub fn validate_p1_pipeline(spec: &PipelineSpec) -> Result<(), PipelineValidationError> {
    if spec.target != "local_or_controlled_container" {
        return Err(PipelineValidationError {
            reason_code: "remote_target_forbidden",
            message: "P1 只允许 local 或受控 container target".to_string(),
        });
    }
    let mut roles = spec
        .nodes
        .iter()
        .map(|node| node.role.as_str())
        .collect::<Vec<_>>();
    roles.sort_unstable();
    roles.dedup();
    for required in ["env-inter", "vuln-reasoner", "audit-reporter"] {
        if !roles.contains(&required) {
            return Err(PipelineValidationError {
                reason_code: "pipeline_invalid",
                message: format!("P1 pipeline 缺少必需 AgentFlow role: {required}"),
            });
        }
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn agentflow_pipeline_has_fixed_p1_roles_and_boundaries() {
        let spec = render_p1_pipeline();
        validate_p1_pipeline(&spec).unwrap();
        let json = render_p1_pipeline_json();
        assert_eq!(json["boundary"]["serve_enabled"], false);
        assert_eq!(json["boundary"]["remote_target"], false);
        assert_eq!(json["boundary"]["dynamic_experts"], false);
    }
}
