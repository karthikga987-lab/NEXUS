
import certifi
import ipaddress
import logging
import socket
import ssl
import threading
import time
import urllib.error
import urllib.request
from urllib.parse import urljoin, urlsplit
from urllib.robotparser import RobotFileParser


logger = logging.getLogger(__name__)

REQUEST_TIMEOUT = 15
MAX_RESPONSE_BYTES = 2 * 1024 * 1024
MAX_REDIRECTS = 5

ROBOTS_CACHE_SECONDS = 60 * 60
ROBOTS_CONTENT_TYPES = {"text/plain", "text/html"}

USER_AGENT = "NEXUS-Research/0.1"

HTML_CONTENT_TYPES = {
    "text/html",
    "application/xhtml+xml",
}

ERROR_PAGE_MARKERS = (
    "page not found",
    "404 not found",
    "404 - not found",
    "this page doesn't exist",
    "this page does not exist",
    "we couldn't find that page",
    "we could not find that page",
)


class UnsafeURLError(ValueError):
    """Raised when a URL is not safe to fetch."""


def _deny_all_robots_policy() -> RobotFileParser:
    """Create a robots policy that disallows every URL."""

    parser = RobotFileParser()
    parser.parse([
        "User-agent: *",
        "Disallow: /",
    ])
    parser._nexus_policy_unavailable = True

    return parser

class SafeRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Follow redirects only after validating the destination."""

    max_repeats = MAX_REDIRECTS
    max_redirections = MAX_REDIRECTS

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        destination = urljoin(req.full_url, newurl)
        _validate_public_url(destination)

        return super().redirect_request(
            req,
            fp,
            code,
            msg,
            headers,
            destination,
        )


# Cache format:
# origin -> (expiry_monotonic_time, RobotFileParser)
_robots_cache: dict[str, tuple[float, RobotFileParser]] = {}
_robots_cache_lock = threading.Lock()


def _validate_public_url(url: str) -> tuple[str, int]:
    """Validate an HTTP(S) URL and reject private or local destinations."""

    if not isinstance(url, str) or not url.strip():
        raise UnsafeURLError("A URL is required.")

    try:
        parsed = urlsplit(url.strip())

        if parsed.scheme.lower() not in {"http", "https"}:
            raise UnsafeURLError("Only HTTP and HTTPS URLs are allowed.")

        if not parsed.hostname:
            raise UnsafeURLError("URL must contain a hostname.")

        if parsed.username or parsed.password:
            raise UnsafeURLError("URLs containing credentials are not allowed.")

        hostname = parsed.hostname.encode("idna").decode("ascii").lower()
        port = parsed.port or (443 if parsed.scheme.lower() == "https" else 80)

        if not 1 <= port <= 65535:
            raise UnsafeURLError("URL contains an invalid port.")

    except UnsafeURLError:
        raise
    except (ValueError, UnicodeError) as exc:
        raise UnsafeURLError("URL is malformed.") from exc

    try:
        addresses = socket.getaddrinfo(
            hostname,
            port,
            type=socket.SOCK_STREAM,
        )
    except socket.gaierror as exc:
        raise UnsafeURLError(
            "Could not resolve the URL hostname."
        ) from exc

    if not addresses:
        raise UnsafeURLError(
            "URL hostname did not resolve to an address."
        )

    for address_info in addresses:
        address = ipaddress.ip_address(address_info[4][0])

        if not address.is_global:
            raise UnsafeURLError(
                "Requests to private, local, or reserved IP addresses are blocked."
            )

    return hostname, port


def _build_opener():
    """Build an opener that validates redirect destinations and TLS."""

    ssl_context = ssl.create_default_context(
        cafile=certifi.where()
    )

    return urllib.request.build_opener(
        SafeRedirectHandler,
        urllib.request.HTTPSHandler(context=ssl_context),
    )


def _origin_for_url(url: str) -> str:
    """Return the scheme and authority used for robots policy lookup."""

    parsed = urlsplit(url)

    return f"{parsed.scheme.lower()}://{parsed.netloc.lower()}"


def _robots_allows(parser: RobotFileParser, url: str) -> bool:
    """Evaluate the most specific matching robots.txt rule."""

    from urllib.parse import unquote, urlparse, quote

    if parser.disallow_all:
        return False

    if parser.allow_all:
        return True

    if not parser.last_checked:
        return False

    parsed_url = urlparse(unquote(url))
    path = urlparse(url).path or "/"

    if parsed_url.params:
        path += ";" + parsed_url.params

    if parsed_url.query:
        path += "?" + parsed_url.query

    if parsed_url.fragment:
        path += "#" + parsed_url.fragment

    path = quote(path)

    matching_entry = next(
        (
            entry
            for entry in parser.entries
            if entry.applies_to(USER_AGENT)
        ),
        parser.default_entry,
    )

    if matching_entry is None:
        return True

    matching_rules = [
        rule
        for rule in matching_entry.rulelines
        if rule.applies_to(path)
    ]

    if not matching_rules:
        return True

    most_specific_length = max(
        len(rule.path)
        for rule in matching_rules
    )

    most_specific_rules = [
        rule
        for rule in matching_rules
        if len(rule.path) == most_specific_length
    ]

    return any(
        rule.allowance
        for rule in most_specific_rules
    )

def _fetch_robots_policy(origin: str) -> RobotFileParser:
    """
    Fetch and parse robots.txt without calling fetch_url().

    A missing robots.txt (404/410) means no robots restrictions.
    Access-denied, server errors, unsafe redirects, and network
    failures fail closed: ordinary pages will not be fetched.
    """

    robots_url = f"{origin}/robots.txt"

    try:
        _validate_public_url(robots_url)

        request = urllib.request.Request(
            robots_url,
            headers={
                "User-Agent": USER_AGENT,
                "Accept": "text/plain, text/html",
            },
            method="GET",
        )

        with _build_opener().open(
            request,
            timeout=REQUEST_TIMEOUT,
        ) as response:
            status_code = getattr(response, "status", 200)

            if status_code < 200 or status_code >= 300:
                logger.warning(
                    "Robots policy request returned HTTP %s for %s",
                    status_code,
                    origin,
                )
                return _deny_all_robots_policy()

            content_length = response.headers.get("Content-Length")

            if content_length:
                try:
                    if int(content_length) > MAX_RESPONSE_BYTES:
                        logger.warning(
                            "Robots.txt exceeds the response size limit: %s",
                            origin,
                        )
                        return _deny_all_robots_policy()
                except ValueError:
                    pass

            raw_content = response.read(MAX_RESPONSE_BYTES + 1)

            if len(raw_content) > MAX_RESPONSE_BYTES:
                logger.warning(
                    "Robots.txt exceeds the response size limit: %s",
                    origin,
                )
                return _deny_all_robots_policy()

            charset = response.headers.get_content_charset() or "utf-8"

            try:
                content = raw_content.decode(
                    charset,
                    errors="replace",
                )
            except LookupError:
                content = raw_content.decode(
                    "utf-8",
                    errors="replace",
                )

            parser = RobotFileParser()
            parser.set_url(robots_url)
            parser.parse(content.splitlines())

            return parser

    except urllib.error.HTTPError as exc:
        if exc.code in {404, 410}:
            logger.info(
                "No robots.txt found for %s; allowing public-page access",
                origin,
            )
            parser = RobotFileParser()
            parser.parse(["User-agent: *"])
            return parser

        logger.warning(
            "Robots.txt returned HTTP %s for %s; denying crawling",
            exc.code,
            origin,
        )
        return _deny_all_robots_policy()

    except Exception as exc:
        logger.warning(
            "Could not safely retrieve robots.txt for %s: %s; denying crawling",
            origin,
            exc,
        )
        return _deny_all_robots_policy()


def _get_robots_policy(origin: str) -> RobotFileParser:
    """Get a cached robots policy or retrieve a fresh one."""

    now = time.monotonic()

    with _robots_cache_lock:
        cached = _robots_cache.get(origin)

        if cached and cached[0] > now:
            return cached[1]

    # Do network I/O outside the lock so unrelated origins
    # can retrieve their robots policies concurrently.
    parser = _fetch_robots_policy(origin)

    with _robots_cache_lock:
        _robots_cache[origin] = (
            time.monotonic() + ROBOTS_CACHE_SECONDS,
            parser,
        )

    return parser


def _is_allowed_by_robots(url: str) -> bool:
    """Check whether the NEXUS crawler may fetch this URL."""

    return _robots_decision(url)[0]


def _robots_decision(url: str) -> tuple[bool, str | None]:
    """Return a safe reason when robots policy prevents a fetch."""

    try:
        parser = _get_robots_policy(_origin_for_url(url))

        allowed = _robots_allows(parser, url)

        if not allowed:
            logger.info(
                "Robots.txt disallows NEXUS from fetching %s",
                url,
            )

        if allowed:
            return True, None

        if getattr(parser, "_nexus_policy_unavailable", False):
            return False, "Robots policy unavailable; crawling denied."

        return False, "Robots policy denied this URL."

    except Exception:
        logger.exception(
            "Could not evaluate robots policy for %s; denying crawling",
            url,
        )
        return False, "Robots policy unavailable; crawling denied."


def _looks_like_error_page(html: str) -> bool:
    """Detect common branded not-found pages that return HTTP 200."""

    normalized = " ".join(html.lower().split())

    return any(marker in normalized for marker in ERROR_PAGE_MARKERS)


def fetch_url(
    url: str,
    allowed_content_types: set[str] | None = None,
) -> str | None:
    """
    Fetch a public webpage or text resource.

    By default, only HTML content types are accepted.
    Callers can explicitly allow XML or plain text for resources
    such as sitemaps and robots.txt.

    Robots.txt is checked before fetching ordinary resources.
    The robots.txt file itself bypasses this check to avoid recursion.

    Returns decoded content on success or None on failure.
    """

    result = fetch_url_with_diagnostics(
        url,
        allowed_content_types=allowed_content_types,
    )
    return result["content"]


def fetch_url_with_diagnostics(
    url: str,
    allowed_content_types: set[str] | None = None,
) -> dict[str, str | None]:
    """Fetch a page and return safe, categorized diagnostics on failure.

    Diagnostic text deliberately omits URLs, response bodies, and network
    addresses so it can safely be included in research results.
    """
    if allowed_content_types is None:
        accepted_types = HTML_CONTENT_TYPES
    else:
        accepted_types = {
            content_type.lower().strip()
            for content_type in allowed_content_types
        }

        if not accepted_types:
            logger.warning("No content types allowed for %s", url)
            return {
                "content": None,
                "reason": "Invalid content type configuration.",
            }

    try:
        _validate_public_url(url)

        parsed = urlsplit(url)
        is_robots_file = parsed.path.lower() == "/robots.txt"

        if not is_robots_file:
            robots_allowed, robots_reason = _robots_decision(url)
            if not robots_allowed:
                return {
                    "content": None,
                    "reason": robots_reason,
                }

        request = urllib.request.Request(
            url,
            headers={
                "User-Agent": USER_AGENT,
                "Accept": ", ".join(sorted(accepted_types)),
            },
            method="GET",
        )

        with _build_opener().open(
            request,
            timeout=REQUEST_TIMEOUT,
        ) as response:
            status_code = getattr(response, "status", 200)

            if status_code < 200 or status_code >= 300:
                logger.warning(
                    "Skipping unsuccessful HTTP response from %s: %s",
                    response.geturl(),
                    status_code,
                )
                return {
                    "content": None,
                    "reason": f"HTTP error ({status_code}).",
                }

            content_type = response.headers.get_content_type().lower()

            if content_type not in accepted_types:
                logger.info(
                    "Skipping unsupported content type from %s: %s",
                    response.geturl(),
                    content_type,
                )
                return {
                    "content": None,
                    "reason": f"Invalid content type ({content_type}).",
                }

            content_length = response.headers.get("Content-Length")

            if content_length:
                try:
                    if int(content_length) > MAX_RESPONSE_BYTES:
                        logger.warning(
                            "Skipping oversized response: %s",
                            response.geturl(),
                        )
                        return {
                            "content": None,
                            "reason": "Response exceeded the size limit.",
                        }
                except ValueError:
                    pass

            raw_content = response.read(MAX_RESPONSE_BYTES + 1)

            if len(raw_content) > MAX_RESPONSE_BYTES:
                logger.warning(
                    "Response exceeded the size limit: %s",
                    response.geturl(),
                )
                return {
                    "content": None,
                    "reason": "Response exceeded the size limit.",
                }

            charset = response.headers.get_content_charset() or "utf-8"

            try:
                content = raw_content.decode(
                    charset,
                    errors="replace",
                )
            except LookupError:
                content = raw_content.decode(
                    "utf-8",
                    errors="replace",
                )

            if (
                content_type in HTML_CONTENT_TYPES
                and _looks_like_error_page(content)
            ):
                logger.info(
                    "Skipping branded not-found page: %s",
                    response.geturl(),
                )
                return {
                    "content": None,
                    "reason": "HTTP error page content.",
                }

            return {"content": content, "reason": None}

    except UnsafeURLError as exc:
        logger.warning("Rejected URL %s: %s", url, exc)
        return {"content": None, "reason": "Unsafe URL."}

    except urllib.error.HTTPError as exc:
        logger.warning("HTTP error fetching %s: %s", url, exc.code)
        return {"content": None, "reason": f"HTTP error ({exc.code})."}

    except urllib.error.URLError as exc:
        logger.warning("Could not fetch %s: %s", url, exc.reason)
        reason = exc.reason
        if isinstance(reason, (TimeoutError, socket.timeout)):
            return {"content": None, "reason": "Request timed out."}
        return {"content": None, "reason": "Network fetch failure."}

    except (TimeoutError, socket.timeout) as exc:
        logger.warning("Request timed out for %s: %s", url, exc)
        return {"content": None, "reason": "Request timed out."}

    except OSError as exc:
        logger.warning("Network error fetching %s: %s", url, exc)
        return {"content": None, "reason": "Network fetch failure."}

    except Exception:
        logger.exception("Unexpected error fetching %s", url)
        return {"content": None, "reason": "Other fetch failure."}
