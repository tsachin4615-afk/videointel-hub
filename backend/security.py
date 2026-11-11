import hmac
import os

API_SECRET = os.getenv("API_SECRET_KEY") or os.getenv("SECRET_KEY") or "videointel-local-insecure-secret"


def verify_token(provided_token: str | None) -> bool:
    if not provided_token:
        return False
    return hmac.compare_digest(str(provided_token).strip(), API_SECRET.strip())


def sanitize_input(text: str | None) -> str:
    if text is None:
        return ""
    return "".join(ch for ch in str(text) if ch.isprintable()).strip()
