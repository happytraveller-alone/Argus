from app.services.llm_rule.git_manager import get_mirror_candidates


def test_get_mirror_candidates_multiple_prefix_order_and_dedup():
    original_url = "https://github.com/example/repo.git"

    candidates = get_mirror_candidates(
        original_url,
        enabled=True,
        mirror_prefixes="https://a.example, https://a.example,https://b.example",
        allow_hosts="github.com",
        allow_auth_url=False,
        fallback_to_origin=False,
    )

    assert candidates == [
        "https://a.example/https://github.com/example/repo.git",
        "https://b.example/https://github.com/example/repo.git",
    ]


def test_get_mirror_candidates_without_fallback_does_not_append_origin():
    original_url = "https://github.com/example/repo.git"

    candidates = get_mirror_candidates(
        original_url,
        enabled=True,
        mirror_prefixes="https://a.example,https://b.example",
        allow_hosts="github.com",
        allow_auth_url=False,
        fallback_to_origin=False,
    )

    assert original_url not in candidates


def test_get_mirror_candidates_with_fallback_appends_origin():
    original_url = "https://github.com/example/repo.git"

    candidates = get_mirror_candidates(
        original_url,
        enabled=True,
        mirror_prefixes="https://a.example,https://b.example",
        allow_hosts="github.com",
        allow_auth_url=False,
        fallback_to_origin=True,
    )

    assert candidates == [
        "https://a.example/https://github.com/example/repo.git",
        "https://b.example/https://github.com/example/repo.git",
        original_url,
    ]


def test_get_mirror_candidates_falls_back_to_single_prefix_when_prefixes_missing():
    original_url = "https://github.com/example/repo.git"

    candidates = get_mirror_candidates(
        original_url,
        enabled=True,
        mirror_prefix="https://single.example",
        mirror_prefixes="",
        allow_hosts="github.com",
        allow_auth_url=False,
        fallback_to_origin=False,
    )

    assert candidates == ["https://single.example/https://github.com/example/repo.git"]


def test_get_mirror_candidates_respects_allow_auth_url_false():
    original_url = "https://token@github.com/example/repo.git"

    candidates = get_mirror_candidates(
        original_url,
        enabled=True,
        mirror_prefixes="https://a.example,https://b.example",
        allow_hosts="github.com",
        allow_auth_url=False,
        fallback_to_origin=True,
    )

    assert candidates == [original_url]


def test_get_mirror_candidates_non_allow_host_returns_origin_only():
    original_url = "https://gitlab.com/example/repo.git"

    candidates = get_mirror_candidates(
        original_url,
        enabled=True,
        mirror_prefixes="https://a.example,https://b.example",
        allow_hosts="github.com",
        allow_auth_url=False,
        fallback_to_origin=True,
    )

    assert candidates == [original_url]
