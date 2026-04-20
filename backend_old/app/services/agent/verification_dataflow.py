from typing import Tuple


REAL_DATAFLOW_REQUIRED_FIELDS: Tuple[str, ...] = (
    "source",
    "sink",
    "sink_reachable",
    "upstream_call_chain",
    "sink_trigger_condition",
    "attacker_flow",
)

REAL_DATAFLOW_EVIDENCE_LIST_FIELDS: Tuple[str, ...] = (
    "taint_flow",
    "evidence_chain",
)

REAL_DATAFLOW_PLACEHOLDER_VALUES: Tuple[str, ...] = (
    "source",
    "sink",
    "input",
    "user_input",
    "todo",
    "none",
    "null",
    "unknown",
    "n/a",
    "na",
    "-",
)


__all__ = [
    "REAL_DATAFLOW_REQUIRED_FIELDS",
    "REAL_DATAFLOW_EVIDENCE_LIST_FIELDS",
    "REAL_DATAFLOW_PLACEHOLDER_VALUES",
]
