import hashlib
import os

RATE_LIMIT = int(os.getenv("RATE_LIMIT_PER_HOUR", "5"))

_store: dict = {}


def hash_ip(ip: str) -> str:
    return hashlib.sha256(ip.encode()).hexdigest()


def is_rate_limited(ip: str) -> bool:
    """Return True if this IP has exceeded RATE_LIMIT requests in the current hour."""
    raise NotImplementedError


def record_request(ip: str) -> None:
    """Increment the request count for this IP."""
    raise NotImplementedError
