from app.research.discovery import discover_sources
from app.research.fetcher import fetch_url
from app.research.processor import extract_text


urls = discover_sources("https://example.com")

print("DISCOVERED:")
for url in urls:
    print(url)

html = fetch_url(urls[0])

if html:
    text = extract_text(html)

    print("\nEXTRACTED TEXT:")
    print(text[:500])