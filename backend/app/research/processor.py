"""Convert fetched HTML into meaningful plain text and page metadata."""

from dataclasses import dataclass

from bs4 import BeautifulSoup


@dataclass(frozen=True)
class ProcessedDocument:
    title: str | None
    text: str


def process_html(html: str) -> ProcessedDocument:
    soup = BeautifulSoup(html, "html.parser")
    title = soup.title.get_text(" ", strip=True) if soup.title else None

    for element in soup(
        ["script", "style", "nav", "footer", "header", "aside", "noscript", "svg"]
    ):
        element.decompose()

    main = soup.find("main") or soup.find("article") or soup.body or soup
    blocks = []
    for element in main.find_all(["h1", "h2", "h3", "p", "li"]):
        text = element.get_text(" ", strip=True)
        if text and (not blocks or blocks[-1] != text):
            blocks.append(text)

    if not blocks:
        blocks = [main.get_text(" ", strip=True)]

    text = "\n\n".join(part for part in blocks if part)
    return ProcessedDocument(title=title or None, text=text)


def extract_text(html: str) -> str:
    """Compatibility wrapper for existing callers that need text only."""
    return process_html(html).text
