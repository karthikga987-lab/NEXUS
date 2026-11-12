
import urllib.error

import pytest

from app.research import fetcher


@pytest.fixture(autouse=True)
def clear_robots_cache():
    """Keep every test independent of previously cached policies."""
    with fetcher._robots_cache_lock:
        fetcher._robots_cache.clear()

    yield

    with fetcher._robots_cache_lock:
        fetcher._robots_cache.clear()


def make_policy(*lines):
    """Create a robots parser from test rules."""
    parser = fetcher.RobotFileParser()
    parser.parse(list(lines))
    return parser


def test_allowed_path_is_permitted(monkeypatch):
    parser = make_policy(
        "User-agent: *",
        "Disallow: /private/",
    )

    monkeypatch.setattr(
        fetcher,
        "_get_robots_policy",
        lambda origin: parser,
    )

    assert fetcher._is_allowed_by_robots(
        "https://example.com/products"
    )


def test_disallowed_path_is_blocked(monkeypatch):
    parser = make_policy(
        "User-agent: *",
        "Disallow: /private/",
    )

    monkeypatch.setattr(
        fetcher,
        "_get_robots_policy",
        lambda origin: parser,
    )

    assert not fetcher._is_allowed_by_robots(
        "https://example.com/private/report"
    )


def test_allow_rule_overrides_broader_disallow(monkeypatch):
    parser = make_policy(
        "User-agent: *",
        "Disallow: /products/",
        "Allow: /products/public/",
    )

    monkeypatch.setattr(
        fetcher,
        "_get_robots_policy",
        lambda origin: parser,
    )

    assert fetcher._is_allowed_by_robots(
        "https://example.com/products/public/item"
    )

    assert not fetcher._is_allowed_by_robots(
        "https://example.com/products/private/item"
    )


def test_missing_robots_file_allows_crawling(monkeypatch):
    def raise_404(*args, **kwargs):
        raise urllib.error.HTTPError(
            "https://example.com/robots.txt",
            404,
            "Not Found",
            {},
            None,
        )

    monkeypatch.setattr(
        fetcher,
        "_validate_public_url",
        lambda url: ("example.com", 443),
    )

    monkeypatch.setattr(
        fetcher,
        "_build_opener",
        lambda: type(
            "FakeOpener",
            (),
            {"open": staticmethod(raise_404)},
        )(),
    )

    parser = fetcher._fetch_robots_policy(
        "https://example.com"
    )

    assert parser.can_fetch(
        fetcher.USER_AGENT,
        "https://example.com/products",
    )


def test_server_error_fails_closed(monkeypatch):
    def raise_503(*args, **kwargs):
        raise urllib.error.HTTPError(
            "https://example.com/robots.txt",
            503,
            "Service Unavailable",
            {},
            None,
        )

    monkeypatch.setattr(
        fetcher,
        "_validate_public_url",
        lambda url: ("example.com", 443),
    )

    monkeypatch.setattr(
        fetcher,
        "_build_opener",
        lambda: type(
            "FakeOpener",
            (),
            {"open": staticmethod(raise_503)},
        )(),
    )

    parser = fetcher._fetch_robots_policy(
        "https://example.com"
    )

    assert not parser.can_fetch(
        fetcher.USER_AGENT,
        "https://example.com/products",
    )


def test_network_failure_fails_closed(monkeypatch):
    def raise_network_error(*args, **kwargs):
        raise urllib.error.URLError("Connection failed")

    monkeypatch.setattr(
        fetcher,
        "_validate_public_url",
        lambda url: ("example.com", 443),
    )

    monkeypatch.setattr(
        fetcher,
        "_build_opener",
        lambda: type(
            "FakeOpener",
            (),
            {"open": staticmethod(raise_network_error)},
        )(),
    )

    parser = fetcher._fetch_robots_policy(
        "https://example.com"
    )

    assert not parser.can_fetch(
        fetcher.USER_AGENT,
        "https://example.com/products",
    )


def test_robots_policy_is_cached(monkeypatch):
    calls = []

    parser = make_policy(
        "User-agent: *",
        "Disallow: /private/",
    )

    def fake_fetch(origin):
        calls.append(origin)
        return parser

    monkeypatch.setattr(
        fetcher,
        "_fetch_robots_policy",
        fake_fetch,
    )

    first = fetcher._get_robots_policy(
        "https://example.com"
    )

    second = fetcher._get_robots_policy(
        "https://example.com"
    )

    assert first is second
    assert calls == ["https://example.com"]
