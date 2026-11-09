import requests

def fetch_url(url: str) -> str | None:
    print(f"Trying to fetch: {url}", flush=True)

    try:
        response = requests.get(
            url,
            timeout=10,
            headers={
                "User-Agent": "NEXUS-Research/0.1"
            },
        )

        response.raise_for_status()

        print(f"Successfully fetched: {url}", flush=True)
        return response.text

    except requests.RequestException as error:
        print(f"Failed to fetch {url}: {error}", flush=True)
        return None