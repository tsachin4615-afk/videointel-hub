import hmac
import hashlib
import os

API_SECRET = os.getenv("API_SECRET_KEY", "videointel-local-insecure-secret")

def verify_token(provided_token: str) -> bool:
    if not provided_token:
        return False
    return hmac.compare_digest(provided_token, API_SECRET)

def sanitize_input(text: str) -> str:
    if not text:
        return ""
    # Strip potential control characters while preserving standard unicode text
    return "".join(ch for ch in text if ch.isprintable()).strip()
