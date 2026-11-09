
from app.research.event_extracter import extract_events

sample_text = """
Example Technologies announced the launch of its new product,
Example AI, on 15 October 2026.

The product helps businesses automate customer support.
The company stated that the launch aims to reduce response times.

Within the first month, the product was adopted by 50 businesses.
"""

events = extract_events(
    company_name="Example Technologies",
    source_text=sample_text
)

print("\nExtracted Events:")

for event in events:
    print(event.model_dump_json(indent=2))
