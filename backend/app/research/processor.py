import re
from datetime import datetime, timezone
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit, urlunsplit


SKIP_TAGS = {
    "script",
    "style",
    "noscript",
    "svg",
    "canvas",
    "iframe",
    "nav",
    "footer",
    "header",
    "form",
    "button",
}

VOID_TAGS = {
    "area", "base", "br", "col", "embed", "hr", "img", "input",
    "link", "meta", "param", "source", "track", "wbr",
}

SKIP_BOILERPLATE_TERMS = {
    "cookie", "consent", "navigation", "navbar", "breadcrumb",
    "newsletter", "subscribe", "social-share", "share-buttons",
    "popup", "modal", "advertisement", "advert", "promo-banner",
}


BLOCK_TAGS = {
    "address",
    "article",
    "aside",
    "blockquote",
    "br",
    "dd",
    "div",
    "dl",
    "dt",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "li",
    "main",
    "ol",
    "p",
    "section",
    "table",
    "td",
    "th",
    "tr",
    "ul",
}


class _ReadableHTMLParser(HTMLParser):
    """Extract page metadata and readable text without external libraries."""

    def __init__(self):
        super().__init__(convert_charrefs=True)

        self.title_parts = []
        self.text_parts = []
        self.meta_description = None
        self.canonical_url = None
        self.publication_date = None

        self._ignored_element_stack = []
        self._inside_title = False

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        attributes = {
            key.lower(): value
            for key, value in attrs
            if key and value is not None
        }

        role = attributes.get("role", "").casefold()
        identifier = " ".join((attributes.get("id", ""), attributes.get("class", ""))).casefold()
        is_boilerplate = (
            tag in SKIP_TAGS
            or role in {"navigation", "banner", "contentinfo"}
            or any(term in identifier for term in SKIP_BOILERPLATE_TERMS)
        )
        if self._ignored_element_stack:
            if tag not in VOID_TAGS:
                self._ignored_element_stack.append(tag)
            return
        if is_boilerplate:
            if tag not in VOID_TAGS:
                self._ignored_element_stack.append(tag)
            return

        if tag == "title":
            self._inside_title = True

        if tag == "meta":
            name = attributes.get("name", "").lower()
            property_name = attributes.get("property", "").lower()
            if (
                name == "description"
                and self.meta_description is None
            ):
                self.meta_description = attributes.get("content")
            if self.publication_date is None and (
                name in {"date", "dc.date", "datepublished", "article:published_time"}
                or property_name in {"article:published_time", "og:published_time"}
            ):
                self.publication_date = attributes.get("content")

        if tag == "time" and self.publication_date is None:
            self.publication_date = attributes.get("datetime")

        if tag == "link":
            rel = {
                value.lower()
                for value in attributes.get("rel", "").split()
            }
            if "canonical" in rel:
                self.canonical_url = attributes.get("href")

        if tag in BLOCK_TAGS:
            self.text_parts.append("\n")

    def handle_endtag(self, tag):
        tag = tag.lower()

        if self._ignored_element_stack:
            for index in range(len(self._ignored_element_stack) - 1, -1, -1):
                if self._ignored_element_stack[index] == tag:
                    del self._ignored_element_stack[index:]
                    break
            return

        if tag == "title":
            self._inside_title = False

        if tag in BLOCK_TAGS:
            self.text_parts.append("\n")

    def handle_data(self, data):
        if self._ignored_element_stack:
            return

        if self._inside_title:
            self.title_parts.append(data)

        self.text_parts.append(data)


def _clean_text(value: str | None) -> str | None:
    if not isinstance(value, str):
        return None

    value = value.replace("\xa0", " ")
    value = re.sub(r"[ \t\r\f\v]+", " ", value)
    value = re.sub(r" *\n *", "\n", value)
    value = re.sub(r"\n{3,}", "\n\n", value)

    value = value.strip()

    return value or None


def _normalize_canonical_url(
    canonical_url: str | None,
    page_url: str | None,
) -> str | None:
    if not canonical_url:
        return None

    if not page_url:
        return None

    try:
        resolved = urljoin(page_url, canonical_url)
        canonical = urlsplit(resolved)
        original = urlsplit(page_url)

        if canonical.scheme.lower() not in {"http", "https"}:
            return None

        if not canonical.hostname:
            return None

        if canonical.username or canonical.password:
            return None

        # Only accept canonical URLs on the same hostname.
        if canonical.hostname.lower() != original.hostname.lower():
            return None

        return urlunsplit((
            canonical.scheme.lower(),
            canonical.netloc,
            canonical.path,
            canonical.query,
            "",
        ))

    except (ValueError, AttributeError):
        return None


def extract_page(html: str, page_url: str | None = None) -> dict:
    """
    Extract readable text and metadata from an HTML document.

    Returns:
        title
        content_text
        meta_description
        canonical_url

    The original page URL should be retained separately as the
    SourceDocument URL. Canonical URL is supplementary metadata only.
    """

    if not isinstance(html, str) or not html.strip():
        raise ValueError("HTML content cannot be empty.")

    parser = _ReadableHTMLParser()

    try:
        parser.feed(html)
        parser.close()
    except Exception as exc:
        raise ValueError(
            f"Could not parse HTML document: {exc}"
        ) from exc

    title = _clean_text(" ".join(parser.title_parts))
    content_text = _clean_text(" ".join(parser.text_parts))
    meta_description = _clean_text(parser.meta_description)

    canonical_url = _normalize_canonical_url(
        parser.canonical_url,
        page_url,
    )

    publication_date = None
    if isinstance(parser.publication_date, str):
        try:
            parsed_date = datetime.fromisoformat(
                parser.publication_date.strip().replace("Z", "+00:00")
            )
            publication_date = (
                parsed_date.replace(tzinfo=timezone.utc)
                if parsed_date.tzinfo is None
                else parsed_date.astimezone(timezone.utc)
            )
        except ValueError:
            publication_date = None

    return {
        "title": title,
        "content_text": content_text,
        "meta_description": meta_description,
        "canonical_url": canonical_url,
        "publication_date": publication_date,
    }


def extract_text(html: str) -> str:
    """Compatibility helper returning only readable webpage text."""

    return extract_page(html)["content_text"] or ""
