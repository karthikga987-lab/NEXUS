"""Guards for the unauthenticated, local-only internal document feature."""

import ipaddress
import os

from fastapi import HTTPException, Request


def local_internal_sources_enabled() -> bool:
    value = os.getenv("NEXUS_ENABLE_LOCAL_INTERNAL_SOURCES", "0")
    return value.strip().casefold() in {"1", "true", "yes", "on"}


def is_loopback_request(request: Request) -> bool:
    # Do not infer a loopback client through a proxy-provided forwarding header.
    if any(
        request.headers.get(name)
        for name in ("forwarded", "x-forwarded-for", "x-real-ip")
    ):
        return False
    client = request.client
    if client is None or not client.host:
        return False

    host = client.host.strip().strip("[]").casefold()
    if host == "localhost":
        return True

    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def require_local_internal_access(request: Request) -> None:
    """Require explicit opt-in and a loopback peer for internal records."""
    if not local_internal_sources_enabled():
        raise HTTPException(
            status_code=403,
            detail=(
                "Local internal document access is disabled. Set "
                "NEXUS_ENABLE_LOCAL_INTERNAL_SOURCES=1 for trusted local use."
            ),
        )

    if not is_loopback_request(request):
        raise HTTPException(
            status_code=403,
            detail="Internal document access is restricted to loopback clients.",
        )


def require_loopback_for_internal_evidence(request: Request) -> None:
    """Do not expose opted-in internal evidence through remote AI requests."""
    require_local_internal_access(request)
