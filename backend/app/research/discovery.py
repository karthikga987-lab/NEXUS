from urllib.parse import urljoin


def discover_sources(website: str) -> list[str]:
    """
    Return useful public URLs starting from the company's website.
    """

    sources = []

    # Add the company's main website
    sources.append(website)

    # Try common public pages
    common_pages = [
        "/about",
        "/news",
        "/blog",
        "/press",
    ]

    for page in common_pages:
        sources.append(urljoin(website, page))

    return sources