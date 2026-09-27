"""
Input validation and abuse-prevention checks applied when a new short URL
is created.

Checks performed:
1. Scheme allow-list (http/https only) - rejects javascript:, data:, file:,
   etc. which could otherwise be used for phishing/XSS-style redirects.
2. Length limit - avoids abuse via pathologically long inputs.
3. Hostname required and not a bare IP-literal loopback/link-local address -
   reduces risk of the service being used to probe internal infrastructure
   via crafted redirects.
4. Domain blocklist - simple denylist loaded from config/blocklist.txt.
"""
import ipaddress
from pathlib import Path
from urllib.parse import urlparse

from app.config import settings

ALLOWED_SCHEMES = {"http", "https"}
DISALLOWED_HOSTNAMES = {"localhost"}


def _load_blocklist() -> set[str]:
    path = Path(settings.blocklist_path)
    if not path.exists():
        return set()
    lines = path.read_text(encoding="utf-8").splitlines()
    return {
        line.strip().lower()
        for line in lines
        if line.strip() and not line.strip().startswith("#")
    }


_BLOCKLIST = _load_blocklist()


def _is_blocked_host(hostname: str) -> bool:
    hostname = hostname.lower()
    return any(hostname == d or hostname.endswith(f".{d}") for d in _BLOCKLIST)


def _is_disallowed_ip_literal(hostname: str) -> bool:
    """Blocks both known local hostnames (e.g. 'localhost') and private/
    loopback/link-local IP literals."""
    if hostname.lower() in DISALLOWED_HOSTNAMES:
        return True
    try:
        ip = ipaddress.ip_address(hostname)
    except ValueError:
        return False  # not an IP literal, i.e. a normal hostname
    return ip.is_loopback or ip.is_link_local or ip.is_private or ip.is_reserved


def validate_original_url(url: str) -> str:
    """Returns the validated URL or raises ValueError with a user-facing reason."""
    if len(url) > settings.max_original_url_length:
        raise ValueError(f"original_url exceeds max length of {settings.max_original_url_length}")

    parsed = urlparse(url)
    if parsed.scheme.lower() not in ALLOWED_SCHEMES:
        raise ValueError(
            f"Unsupported URL scheme '{parsed.scheme}'. Allowed: {sorted(ALLOWED_SCHEMES)}"
        )
    if not parsed.hostname:
        raise ValueError("original_url must include a hostname")
    if _is_disallowed_ip_literal(parsed.hostname):
        raise ValueError("original_url must not point to a private/loopback/link-local address")
    if _is_blocked_host(parsed.hostname):
        raise ValueError("original_url domain is not allowed")

    return url


def reload_blocklist_for_tests() -> None:
    """Test helper to re-read the blocklist file after it changes on disk."""
    global _BLOCKLIST
    _BLOCKLIST = _load_blocklist()
