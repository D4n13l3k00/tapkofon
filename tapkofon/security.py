"""Password hashing, browser-bound forms and finite login attempts."""

import hashlib
import hmac
import ipaddress
import time
from collections import OrderedDict, deque

from argon2 import PasswordHasher, Type
from argon2.exceptions import InvalidHashError, VerificationError
from fastapi import Request

PASSWORD_MIN_LENGTH = 15
PASSWORD_MAX_LENGTH = 256
HASHER = PasswordHasher(time_cost=2, memory_cost=19456, parallelism=1, type=Type.ID)


def hash_password(password: str) -> str:
    return HASHER.hash(password)


def verify_password(encoded: str, password: str) -> bool:
    if not encoded or len(password) > PASSWORD_MAX_LENGTH:
        return False
    try:
        return HASHER.verify(encoded, password)
    except (VerificationError, InvalidHashError):
        return False


def token_digest(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def form_token(secret: bytes, browser: str, revision: int) -> str:
    return hmac.new(
        secret, f"{browser}:{revision}".encode(), hashlib.sha256
    ).hexdigest()


def is_local_request(request: Request) -> bool:
    # Check the actual peer and Host, not untrusted forwarding headers.
    if (
        request.url.hostname not in ("localhost", "127.0.0.1", "::1")
        or not request.client
    ):
        return False
    try:
        return ipaddress.ip_address(request.client.host).is_loopback
    except ValueError:
        return False


class AttemptLimiter:
    def __init__(self, limit: int = 5, window: int = 300):
        self.limit = limit
        self.window = window
        self.failures: OrderedDict[str, deque[float]] = OrderedDict()

    def blocked(self, peer: str) -> bool:
        now = time.monotonic()
        attempts = self.failures.get(peer)
        if attempts is None:
            return False
        while attempts and attempts[0] <= now - self.window:
            attempts.popleft()
        if not attempts:
            self.failures.pop(peer, None)
            return False
        return len(attempts) >= self.limit

    def fail(self, peer: str) -> None:
        self.failures.setdefault(peer, deque()).append(time.monotonic())
        self.failures.move_to_end(peer)
        while len(self.failures) > 1024:
            self.failures.popitem(last=False)

    def reset(self, peer: str) -> None:
        self.failures.pop(peer, None)
