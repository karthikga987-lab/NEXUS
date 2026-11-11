"""Shared URL canonicalization for discovery and source identity."""

from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


TRACKING_PARAMETERS = {"fbclid", "gclid", "mc_cid", "mc_eid"}


def normalize_url(url: str) -> str:
    """Normalize equivalent HTTP URLs while preserving meaningful query data."""
    try:
        parts = urlsplit(url.strip())
        port = parts.port
    except ValueError:
        return ""
    scheme = parts.scheme.lower()
    hostname = (parts.hostname or "").lower().removeprefix("www.")
    if scheme not in {"http", "https"} or not hostname:
        return ""

    formatted_host = f"[{hostname}]" if ":" in hostname else hostname
    netloc = formatted_host
    if port and not (scheme == "http" and port == 80) and not (
        scheme == "https" and port == 443
    ):
        netloc = f"{formatted_host}:{port}"

    query = urlencode([
        (key, value)
        for key, value in parse_qsl(parts.query, keep_blank_values=True)
        if not key.lower().startswith("utm_")
        and key.lower() not in TRACKING_PARAMETERS
    ])
    path = parts.path.rstrip("/")
    return urlunsplit((scheme, netloc, path, query, ""))
