//! AgentFlow runtime adapter for Argus intelligent-audit P1.
//!
//! This module intentionally keeps AgentFlow as an execution adapter only: Argus
//! owns task state, events, findings, checkpoints, reports, and all user-facing
//! APIs. The adapter accepts only Argus business JSON and rejects static-scan
//! bootstrap/candidate inputs at every boundary.

pub mod importer;
pub mod pipeline;
pub mod preflight;
pub mod runner;
