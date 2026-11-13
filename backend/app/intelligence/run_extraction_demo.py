
import json

from app.intelligence.extraction import _ask_ollama


source_text = """
Acme announced on June 10, 2025, that Acme Maps
would launch an offline navigation feature.

The company stated that the feature was developed
to help travelers navigate areas with limited internet
connectivity.

Acme reported that the feature became available
to users on June 10, 2025.
"""

try:
    result = _ask_ollama(source_text)

    print("\nRAW OLLAMA RESPONSE:")
    print(json.dumps(result, indent=2, ensure_ascii=False))

except Exception as error:
    print(f"\nERROR: {error}")
