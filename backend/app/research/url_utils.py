"""URL normalization shared by research discovery and persistence."""

from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


TRACKING_PARAMETERS = {"fbclid", "gclid", "mc_cid", "mc_eid"}


def normalize_url(url: str) -> str:
    """Canonicalize an HTTP(S) URL while retaining meaningful query data."""
    if not isinstance(url, str) or not url.strip():
        return ""

    try:
        parts = urlsplit(url.strip())
        port = parts.port
    except (ValueError, UnicodeError):
        return ""

    scheme = parts.scheme.lower()
    try:
        hostname = (parts.hostname or "").encode("idna").decode("ascii").lower()
    except UnicodeError:
        return ""
    if (
        scheme not in {"http", "https"}
        or not hostname
        or parts.username
        or parts.password
    ):
        return ""

    hostname = hostname.removeprefix("www.")
    formatted_host = f"[{hostname}]" if ":" in hostname else hostname
    netloc = formatted_host
    if port and not (scheme == "http" and port == 80) and not (
        scheme == "https" and port == 443
    ):
        netloc = f"{formatted_host}:{port}"

    query = urlencode(
        [
            (key, value)
            for key, value in parse_qsl(parts.query, keep_blank_values=True)
            if not key.casefold().startswith("utm_")
            and key.casefold() not in TRACKING_PARAMETERS
        ],
        doseq=True,
    )
    path = parts.path.rstrip("/")
    return urlunsplit((scheme, netloc, path, query, ""))
