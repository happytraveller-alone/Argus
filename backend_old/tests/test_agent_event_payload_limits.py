import app.services.agent.event_manager as event_manager


def test_truncate_payload_respects_2mb_limit():
    small = "a" * 150_000
    value, truncated = event_manager._truncate_payload(small)
    assert value == small
    assert truncated is False

    huge = "b" * (event_manager.MAX_EVENT_PAYLOAD_CHARS + 123)
    value, truncated = event_manager._truncate_payload(huge)
    assert truncated is True
    assert len(value) == event_manager.MAX_EVENT_PAYLOAD_CHARS
