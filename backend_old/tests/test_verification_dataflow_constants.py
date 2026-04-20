from app.services.agent.verification_dataflow import (
    REAL_DATAFLOW_EVIDENCE_LIST_FIELDS,
    REAL_DATAFLOW_PLACEHOLDER_VALUES,
    REAL_DATAFLOW_REQUIRED_FIELDS,
)


def test_verification_dataflow_constants_stay_stable():
    assert REAL_DATAFLOW_REQUIRED_FIELDS == (
        "source",
        "sink",
        "sink_reachable",
        "upstream_call_chain",
        "sink_trigger_condition",
        "attacker_flow",
    )
    assert REAL_DATAFLOW_EVIDENCE_LIST_FIELDS == (
        "taint_flow",
        "evidence_chain",
    )
    assert REAL_DATAFLOW_PLACEHOLDER_VALUES == (
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
