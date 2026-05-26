use std::collections::HashMap;

use serde::{Deserialize, Serialize};

use super::types::{HuntTask, ReconOutput, ValidatedFinding};

#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct CoverageStatus {
    pub tasks_dispatched: u32,
    pub findings_total: u32,
    pub findings_confirmed: u32,
    pub gaps_observed: u32,
}

#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct CoverageMatrix {
    pub cells: HashMap<(String, String), CoverageStatus>,
    pub subsystems: Vec<String>,
    pub attack_classes: Vec<String>,
}

impl CoverageMatrix {
    #[must_use]
    pub fn new() -> Self {
        Self::default()
    }

    #[must_use]
    pub fn build_from_recon(recon: &ReconOutput) -> Self {
        let subsystems: Vec<String> = recon.subsystems.iter().map(|s| s.name.clone()).collect();
        let mut attack_classes: Vec<String> = recon
            .initial_tasks
            .iter()
            .map(|t| t.attack_class.clone())
            .collect();
        attack_classes.sort();
        attack_classes.dedup();

        let mut cells: HashMap<(String, String), CoverageStatus> = HashMap::new();
        for sub in &subsystems {
            for ac in &attack_classes {
                cells.insert((sub.clone(), ac.clone()), CoverageStatus::default());
            }
        }

        // Count tasks_dispatched per cell from initial_tasks
        for task in &recon.initial_tasks {
            // A task belongs to a subsystem if any of its target_files starts with the subsystem path
            for sub in &recon.subsystems {
                let matches = task
                    .target_files
                    .iter()
                    .any(|f| f.starts_with(&sub.path) || sub.path == "/" || sub.path.is_empty());
                if matches {
                    if let Some(cell) =
                        cells.get_mut(&(sub.name.clone(), task.attack_class.clone()))
                    {
                        cell.tasks_dispatched += 1;
                    }
                }
            }
        }

        Self {
            cells,
            subsystems,
            attack_classes,
        }
    }

    pub fn update_with_findings(&mut self, findings: &[ValidatedFinding]) {
        for vf in findings {
            let file = &vf.finding.file;
            let vuln_class = &vf.finding.vuln_class;
            let confirmed = vf.validation_status == "confirmed";

            for sub in &self.subsystems {
                // Match subsystem: check if file path starts with subsystem name or is contained
                let sub_matches =
                    file.contains(sub.as_str()) || sub == "project_archive" || sub.is_empty();
                if sub_matches {
                    if let Some(cell) = self.cells.get_mut(&(sub.clone(), vuln_class.clone())) {
                        cell.findings_total += 1;
                        if confirmed {
                            cell.findings_confirmed += 1;
                        }
                    }
                }
            }
        }
    }

    pub fn update_with_hunt_output(&mut self, tasks: &[HuntTask]) {
        for task in tasks {
            for sub in &self.subsystems.clone() {
                let matches = task.target_files.iter().any(|f| f.contains(sub.as_str()))
                    || sub == "project_archive"
                    || sub.is_empty();
                if matches {
                    if let Some(cell) = self
                        .cells
                        .get_mut(&(sub.clone(), task.attack_class.clone()))
                    {
                        cell.tasks_dispatched += 1;
                    }
                }
            }
        }
    }

    #[must_use]
    pub fn light_subsystems(&self) -> Vec<String> {
        self.subsystems
            .iter()
            .filter(|sub| {
                self.attack_classes.iter().all(|ac| {
                    self.cells
                        .get(&((*sub).clone(), ac.clone()))
                        .map_or(true, |c| c.findings_confirmed == 0)
                })
            })
            .cloned()
            .collect()
    }

    #[must_use]
    pub fn light_attack_classes(&self) -> Vec<String> {
        self.attack_classes
            .iter()
            .filter(|ac| {
                self.subsystems.iter().all(|sub| {
                    self.cells
                        .get(&(sub.clone(), (*ac).clone()))
                        .map_or(true, |c| c.findings_confirmed == 0)
                })
            })
            .cloned()
            .collect()
    }

    #[must_use]
    pub fn to_prompt_payload(&self) -> serde_json::Value {
        let coverage: Vec<serde_json::Value> = self
            .subsystems
            .iter()
            .flat_map(|sub| {
                self.attack_classes.iter().map(move |ac| {
                    let status = self.cells.get(&(sub.clone(), ac.clone()));
                    serde_json::json!({
                        "subsystem": sub,
                        "attack_class": ac,
                        "tasks": status.map_or(0, |s| s.tasks_dispatched),
                        "confirmed": status.map_or(0, |s| s.findings_confirmed),
                    })
                })
            })
            .collect();

        serde_json::json!({
            "subsystems": self.subsystems,
            "attack_classes": self.attack_classes,
            "coverage": coverage,
            "light_subsystems": self.light_subsystems(),
            "light_attack_classes": self.light_attack_classes(),
        })
    }

    #[must_use]
    pub fn to_report_summary(&self) -> serde_json::Value {
        let total_tasks: u32 = self.cells.values().map(|c| c.tasks_dispatched).sum();
        let total_confirmed: u32 = self.cells.values().map(|c| c.findings_confirmed).sum();
        let total_findings: u32 = self.cells.values().map(|c| c.findings_total).sum();

        serde_json::json!({
            "subsystem_count": self.subsystems.len(),
            "attack_class_count": self.attack_classes.len(),
            "total_tasks_dispatched": total_tasks,
            "total_findings": total_findings,
            "total_confirmed": total_confirmed,
            "light_subsystems": self.light_subsystems(),
            "light_attack_classes": self.light_attack_classes(),
        })
    }
}
