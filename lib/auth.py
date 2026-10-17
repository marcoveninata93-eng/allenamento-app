"""Login: token casuale per dispositivo (salvato come hash in settings.json) e limite ai tentativi.
Logica pura, testabile senza Streamlit."""
from __future__ import annotations

import hashlib
import hmac
import secrets
import time
from typing import Callable


def token_hash(token: str) -> str:
    return hashlib.sha256(("allenamento-device:" + token).encode()).hexdigest()


def new_device(name: str, created: str) -> tuple[str, dict]:
    """Ritorna (token in chiaro da dare al browser, record da salvare: solo l'hash)."""
    token = secrets.token_urlsafe(32)
    rec = {"id": secrets.token_hex(4), "name": (name or "Dispositivo").strip()[:40], "created": created,
           "hash": token_hash(token)}
    return token, rec


def verify_token(token: str | None, devices: list[dict] | None) -> dict | None:
    if not token or not isinstance(token, str) or len(token) > 200:
        return None
    h = token_hash(token)
    for d in devices or []:
        if isinstance(d, dict) and hmac.compare_digest(str(d.get("hash", "")), h):
            return d
    return None


def revoke(devices: list[dict], device_id: str) -> list[dict]:
    return [d for d in devices if d.get("id") != device_id]


def check_password(given: str, expected: str) -> bool:
    return bool(expected) and hmac.compare_digest(given.encode(), expected.encode())


class RateLimiter:
    """Al massimo `max_fails` password errate in `window` secondi; poi blocco fino a scadenza."""

    def __init__(self, max_fails: int = 5, window: float = 600, clock: Callable[[], float] = time.time):
        self.max_fails, self.window, self.clock = max_fails, window, clock
        self.fails: list[float] = []

    def _prune(self) -> None:
        now = self.clock()
        self.fails = [t for t in self.fails if now - t < self.window]

    def locked_for(self) -> float:
        """Secondi di attesa rimasti (0 = si può provare)."""
        self._prune()
        if len(self.fails) < self.max_fails:
            return 0.0
        return max(0.0, self.window - (self.clock() - self.fails[0]))

    def fail(self) -> None:
        self._prune()
        self.fails.append(self.clock())

    def success(self) -> None:
        self.fails.clear()
