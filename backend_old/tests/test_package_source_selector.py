from scripts.package_source_selector import ProbeResult, order_candidates_by_probe


def test_order_candidates_by_probe_prefers_fast_success_and_deduplicates(monkeypatch):
    outcomes = {
        "https://slow.example/simple": ProbeResult(
            url="https://slow.example/simple", ok=True, latency_ms=90.0, matched_probe="/simple/"
        ),
        "https://fast.example/simple": ProbeResult(
            url="https://fast.example/simple", ok=True, latency_ms=10.0, matched_probe="/simple/"
        ),
        "https://down.example/simple": ProbeResult(
            url="https://down.example/simple", ok=False, latency_ms=None, matched_probe=None
        ),
    }

    monkeypatch.setattr(
        "scripts.package_source_selector.probe_candidate",
        lambda candidate, probe_paths, timeout_seconds=2.0: outcomes[candidate],
    )

    ordered = order_candidates_by_probe(
        "https://slow.example/simple, https://fast.example/simple, https://slow.example/simple, https://down.example/simple",
        probe_paths=["/simple/"],
    )

    assert ordered == [
        "https://fast.example/simple",
        "https://slow.example/simple",
        "https://down.example/simple",
    ]
