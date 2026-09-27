"""
Short code generation.

We generate random Base62 codes (rather than encoding a sequential DB id)
so codes are not trivially enumerable/guessable (basic security hardening
against link scraping/enumeration of other users' short URLs).
"""
import secrets
import string

_ALPHABET = string.ascii_letters + string.digits  # Base62
RESERVED_CODES = {
    "api", "health", "docs", "openapi.json", "redoc", "favicon.ico", "static",
}


def generate_code(length: int) -> str:
    return "".join(secrets.choice(_ALPHABET) for _ in range(length))


def is_reserved(code: str) -> bool:
    return code.lower() in RESERVED_CODES
