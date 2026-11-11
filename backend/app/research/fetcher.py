"""Polite public-web fetching with robots checks and explicit failure data."""

from dataclasses import dataclass
import time
from urllib.robotparser import RobotFileParser
from urllib.parse import urljoin, urlsplit, urlunsplit

import requests


USER_AGENT = "NEXUS-Research/0.1"
REQUEST_TIMEOUT = 12
ROBOTS_CACHE_TTL = 3600
_ROBOTS_CACHE = {}


@dataclass(frozen=True)
class FetchResult:
    requested_url: str
    final_url: str
    content: str | None = None
    status_code: int | None = None
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.content is not None and self.error is None


def _robots_policy(origin: str) -> tuple[RobotFileParser | None, str | None]:
    cached = _ROBOTS_CACHE.get(origin)
    if cached and cached[0] > time.monotonic():
        return cached[1], cached[2]

    parts = urlsplit(origin)
    robots_url = urlunsplit((parts.scheme, parts.netloc, "/robots.txt", "", ""))
    parser = RobotFileParser(robots_url)
    try:
        response = requests.get(
            robots_url,
            timeout=REQUEST_TIMEOUT,
            headers={"User-Agent": USER_AGENT},
        )
    except requests.RequestException as error:
        result = (None, f"Could not verify robots.txt: {error}")
        _ROBOTS_CACHE[origin] = (time.monotonic() + ROBOTS_CACHE_TTL, *result)
        return result

    if response.status_code in (401, 403, 429) or response.status_code >= 500:
        result = (None, f"robots.txt returned HTTP {response.status_code}; access denied")
        _ROBOTS_CACHE[origin] = (time.monotonic() + ROBOTS_CACHE_TTL, *result)
        return result
    if response.status_code >= 400:
        parser.parse([])
    else:
        parser.parse(response.text.splitlines())
    result = (parser, None)
    _ROBOTS_CACHE[origin] = (time.monotonic() + ROBOTS_CACHE_TTL, *result)
    return result


def is_url_allowed(url: str) -> tuple[bool, str | None]:
    """Check robots policy. Fail closed when access policy cannot be verified."""
    parts = urlsplit(url)
    origin = urlunsplit((parts.scheme, parts.netloc, "", "", ""))
    parser, error = _robots_policy(origin)
    if error:
        return False, error
    if not parser or not parser.can_fetch(USER_AGENT, url):
        return False, "URL is disallowed by robots.txt"
    return True, None


def fetch_url(url: str) -> FetchResult:
    current_url = url
    for _ in range(6):
        allowed, policy_error = is_url_allowed(current_url)
        if not allowed:
            return FetchResult(url, current_url, error=policy_error)
        try:
            response = requests.get(
                current_url,
                timeout=REQUEST_TIMEOUT,
                headers={
                    "User-Agent": USER_AGENT,
                    "Accept": "text/html,application/xhtml+xml,text/plain;q=0.9,*/*;q=0.5",
                },
                allow_redirects=False,
            )
        except requests.RequestException as error:
            return FetchResult(url, current_url, error=f"Request failed: {error}")

        if response.is_redirect or response.is_permanent_redirect:
            location = response.headers.get("Location")
            if not location:
                return FetchResult(
                    url, current_url, status_code=response.status_code,
                    error="Redirect response did not include a Location header",
                )
            current_url = urljoin(current_url, location)
            continue

        try:
            response.raise_for_status()
        except requests.HTTPError as error:
            return FetchResult(
                url, current_url, status_code=response.status_code, error=str(error)
            )

        content_type = response.headers.get("Content-Type", "").lower()
        if content_type and not any(
            kind in content_type
            for kind in (
                "text/html",
                "application/xhtml+xml",
                "text/plain",
                "application/xml",
                "text/xml",
            )
        ):
            return FetchResult(
                url, current_url, status_code=response.status_code,
                error=f"Unsupported content type: {content_type}",
            )
        return FetchResult(
            url, current_url, content=response.text,
            status_code=response.status_code,
        )
    return FetchResult(url, current_url, error="Too many redirects")
