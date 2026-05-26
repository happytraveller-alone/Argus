//! Token budget enforcement for the two-pass Trace stage.
//!
//! Per the spec, two-pass stages receive **1.5x** the current single-pass budget.
//! The budget is split:
//!   - Pass 1 (retrieval direction): **25%** of the 1.5x allocation
//!   - Pass 2 (reasoning on evidence): **75%** of the 1.5x allocation
//!
//! If Pass 1 exceeds its share, the stage aborts two-pass execution and falls
//! back to the existing single-pass behavior for that finding. This preserves
//! the no-regression principle from the plan.
//!
//! See `.omc/plans/ralplan-codegraph-integration-v2.md` §Step 1.3, §AC-TB.

use std::sync::atomic::{AtomicU64, Ordering};

/// Per-pass token allocation as a fraction of the two-pass budget.
const PASS_1_FRACTION: f64 = 0.25;
const PASS_2_FRACTION: f64 = 0.75;

/// Multiplier applied to the single-pass base budget when running two-pass.
pub const TWO_PASS_MULTIPLIER: f64 = 1.5;

/// Which pass is being checked when calling `enforce`.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Pass {
    /// LLM directs retrieval queries from finding metadata.
    Retrieval,
    /// LLM reasons over retrieved evidence and produces final verdict.
    Reasoning,
}

/// Error returned when a pass would exceed its allocated token budget.
#[derive(Debug, Clone, thiserror::Error)]
#[error("token budget exceeded for {pass:?}: used={used} cap={cap}")]
pub struct BudgetExceeded {
    pub pass: Pass,
    pub used: u64,
    pub cap: u64,
}

/// Tracks token usage across a two-pass stage execution.
///
/// Construct with `new(base_budget)` where `base_budget` is the original
/// single-pass token budget for the stage. Internally allocates `1.5x` and
/// splits across retrieval/reasoning passes.
pub struct TokenBudget {
    pass1_cap: u64,
    pass2_cap: u64,
    pass1_used: AtomicU64,
    pass2_used: AtomicU64,
}

impl TokenBudget {
    /// Construct a new budget tracker from the single-pass base budget.
    pub fn new(base_budget: u64) -> Self {
        let total = (base_budget as f64 * TWO_PASS_MULTIPLIER) as u64;
        Self {
            pass1_cap: (total as f64 * PASS_1_FRACTION) as u64,
            pass2_cap: (total as f64 * PASS_2_FRACTION) as u64,
            pass1_used: AtomicU64::new(0),
            pass2_used: AtomicU64::new(0),
        }
    }

    /// Record `tokens` consumed by `pass`. Returns `BudgetExceeded` if the
    /// pass's running total would exceed its cap. Caller should abort the
    /// two-pass flow and fall back to single-pass on error.
    pub fn record(&self, pass: Pass, tokens: u64) -> Result<(), BudgetExceeded> {
        let (used_counter, cap) = match pass {
            Pass::Retrieval => (&self.pass1_used, self.pass1_cap),
            Pass::Reasoning => (&self.pass2_used, self.pass2_cap),
        };
        let new_used = used_counter.fetch_add(tokens, Ordering::Relaxed) + tokens;
        if new_used > cap {
            Err(BudgetExceeded {
                pass,
                used: new_used,
                cap,
            })
        } else {
            Ok(())
        }
    }

    /// Return the cap allocated to the given pass.
    #[must_use]
    pub fn cap(&self, pass: Pass) -> u64 {
        match pass {
            Pass::Retrieval => self.pass1_cap,
            Pass::Reasoning => self.pass2_cap,
        }
    }

    /// Return current usage for the given pass.
    #[must_use]
    pub fn used(&self, pass: Pass) -> u64 {
        match pass {
            Pass::Retrieval => self.pass1_used.load(Ordering::Relaxed),
            Pass::Reasoning => self.pass2_used.load(Ordering::Relaxed),
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn splits_budget_into_passes() {
        let budget = TokenBudget::new(1000);
        // base 1000 * 1.5 = 1500 total; 25% pass1 = 375; 75% pass2 = 1125
        assert_eq!(budget.cap(Pass::Retrieval), 375);
        assert_eq!(budget.cap(Pass::Reasoning), 1125);
    }

    #[test]
    fn records_under_cap() {
        let budget = TokenBudget::new(1000);
        assert!(budget.record(Pass::Retrieval, 100).is_ok());
        assert!(budget.record(Pass::Retrieval, 100).is_ok());
        assert_eq!(budget.used(Pass::Retrieval), 200);
    }

    #[test]
    fn rejects_over_cap() {
        let budget = TokenBudget::new(1000);
        // pass1 cap = 375
        assert!(budget.record(Pass::Retrieval, 200).is_ok());
        let err = budget.record(Pass::Retrieval, 200).unwrap_err();
        assert_eq!(err.pass, Pass::Retrieval);
        assert_eq!(err.used, 400);
        assert_eq!(err.cap, 375);
    }

    #[test]
    fn passes_track_independently() {
        let budget = TokenBudget::new(1000);
        budget.record(Pass::Retrieval, 300).unwrap();
        budget.record(Pass::Reasoning, 500).unwrap();
        assert_eq!(budget.used(Pass::Retrieval), 300);
        assert_eq!(budget.used(Pass::Reasoning), 500);
    }
}
