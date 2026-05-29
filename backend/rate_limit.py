import hashlib
import os
import time

RATE_LIMIT = int(os.getenv("RATE_LIMIT_PER_HOUR", "5"))

_store: dict[str, list[float]] = {}


def hash_ip(ip: str) -> str:
    return hashlib.sha256(ip.encode()).hexdigest()


_LOCAL = {"127.0.0.1", "::1", "localhost"}


def is_rate_limited(ip: str) -> bool:
    if ip in _LOCAL:
        return False
    h = hash_ip(ip)
    now = time.time()
    recent = [t for t in _store.get(h, []) if t > now - 3600]
    return len(recent) >= RATE_LIMIT


def record_request(ip: str) -> None:
    if ip in _LOCAL:
        return
    h = hash_ip(ip)
    now = time.time()
    recent = [t for t in _store.get(h, []) if t > now - 3600]
    recent.append(now)
    _store[h] = recent
