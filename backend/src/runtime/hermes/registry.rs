use std::collections::HashMap;

use anyhow::{bail, Result};

use super::contracts::{AgentManifest, AgentRole};

pub const COMPAT_ALIASES: &[(&str, &str)] = &[
    ("business_logic_recon", "recon"),
    ("business_logic_analysis", "analysis"),
    ("business_logic", "analysis"),
];

pub struct CanonicalRegistry {
    manifests: HashMap<String, AgentManifest>,
}

impl CanonicalRegistry {
    pub fn from_discovered(manifests: Vec<AgentManifest>) -> Result<Self> {
        let mut map = HashMap::new();
        for manifest in manifests {
            let key = manifest.role.to_string();
            if map.contains_key(&key) {
                bail!("duplicate role in discovered manifests: {key}");
            }
            map.insert(key, manifest);
        }
        Ok(Self { manifests: map })
    }

    pub fn resolve_role(&self, key: &str) -> Option<&AgentManifest> {
        let canonical = COMPAT_ALIASES
            .iter()
            .find(|(alias, _)| *alias == key)
            .map(|(_, canonical)| *canonical)
            .unwrap_or(key);
        self.manifests.get(canonical)
    }

    pub fn canonical_roles(&self) -> Vec<&AgentRole> {
        self.manifests.values().map(|m| &m.role).collect()
    }

    pub fn all_known_keys(&self) -> Vec<&str> {
        let mut keys: Vec<&str> = self.manifests.keys().map(|s| s.as_str()).collect();
        for (alias, _) in COMPAT_ALIASES {
            keys.push(alias);
        }
        keys
    }
}
