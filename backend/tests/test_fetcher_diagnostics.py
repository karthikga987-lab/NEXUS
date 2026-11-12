from email.message import Message
import socket
import urllib.error

from app.research import fetcher


class _Response:
    status = 200

    def __init__(self, content_type, content=b"<html>ok</html>"):
        self.headers = Message()
        self.headers["Content-Type"] = content_type
        self.content = content

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self, size=-1):
        return self.content[:size]

    def geturl(self):
        return "https://public.example/page"


class _Opener:
    def __init__(self, outcome):
        self.outcome = outcome

    def open(self, request, timeout):
        if isinstance(self.outcome, Exception):
            raise self.outcome
        return self.outcome


def _allow_fetch(monkeypatch, outcome):
    monkeypatch.setattr(fetcher, "_validate_public_url", lambda url: None)
    monkeypatch.setattr(fetcher, "_robots_decision", lambda url: (True, None))
    monkeypatch.setattr(
        fetcher, "_build_opener", lambda: _Opener(outcome)
    )


def test_fetch_diagnostic_classifies_unsafe_url(monkeypatch):
    monkeypatch.setattr(
        fetcher,
        "_validate_public_url",
        lambda url: (_ for _ in ()).throw(fetcher.UnsafeURLError("private host")),
    )

    result = fetcher.fetch_url_with_diagnostics("http://localhost/private")

    assert result == {"content": None, "reason": "Unsafe URL."}
    assert "localhost" not in result["reason"]


def test_fetch_diagnostic_classifies_robots_denial(monkeypatch):
    monkeypatch.setattr(fetcher, "_validate_public_url", lambda url: None)
    monkeypatch.setattr(
        fetcher,
        "_robots_decision",
        lambda url: (False, "Robots policy denied this URL."),
    )

    result = fetcher.fetch_url_with_diagnostics("https://public.example/page")

    assert result["content"] is None
    assert result["reason"] == "Robots policy denied this URL."


def test_fetch_diagnostic_classifies_http_error_without_response_body(
    monkeypatch,
):
    error = urllib.error.HTTPError(
        "https://public.example/private-path",
        403,
        "Forbidden",
        Message(),
        None,
    )
    _allow_fetch(monkeypatch, error)

    result = fetcher.fetch_url_with_diagnostics("https://public.example/page")

    assert result == {"content": None, "reason": "HTTP error (403)."}
    assert "private-path" not in result["reason"]


def test_fetch_diagnostic_classifies_timeout(monkeypatch):
    _allow_fetch(monkeypatch, socket.timeout("internal address detail"))

    result = fetcher.fetch_url_with_diagnostics("https://public.example/page")

    assert result == {"content": None, "reason": "Request timed out."}


def test_fetch_diagnostic_classifies_invalid_content_type(monkeypatch):
    _allow_fetch(monkeypatch, _Response("application/pdf"))

    result = fetcher.fetch_url_with_diagnostics("https://public.example/page")

    assert result == {
        "content": None,
        "reason": "Invalid content type (application/pdf).",
    }


def test_legacy_fetch_url_still_returns_html(monkeypatch):
    _allow_fetch(monkeypatch, _Response("text/html", b"<html>ok</html>"))

    assert fetcher.fetch_url("https://public.example/page") == "<html>ok</html>"
