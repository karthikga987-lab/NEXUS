
from google import genai
from google.genai import types

from app.core.config import settings

client = genai.Client(
    api_key=settings.gemini_api_key,
    http_options=types.HttpOptions(timeout=30000)
)

print("Testing Gemini connection...", flush=True)

response = client.models.generate_content(
    model="gemini-3.6-flash",
    contents="Reply with exactly: Gemini connection successful"
)

print("Response received:", response.text)
