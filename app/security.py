"""Login, session cookie, CSRF protection, throttling and security headers."""
from __future__ import annotations

import hashlib
import hmac
import time
from urllib.parse import urlparse

from fastapi import HTTPException, Request
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from .config import Settings

COOKIE = "hpe_session"
CSRF_HEADER = "x-requested-with"
CSRF_VALUE = "roomlit"

CSP = (
    "default-src 'self'; img-src 'self' data: blob:; style-src 'self' 'unsafe-inline'; "
    "script-src 'self'; connect-src 'self'; font-src 'self' data:; object-src 'none'; "
    "base-uri 'none'; form-action 'self'; frame-ancestors 'none'"
)


class Auth:
    def __init__(self, cfg: Settings):
        self.cfg = cfg
        self._ser = URLSafeTimedSerializer(cfg.secret_key, salt="roomlit-session")
        self._fails: dict[str, list[float]] = {}
        self._locked: dict[str, float] = {}

    # ---- credentials (constant time, on digests so length does not leak)
    @staticmethod
    def _digest(s: str) -> bytes:
        return hashlib.sha256(s.encode("utf-8")).digest()

    def check(self, username: str, password: str) -> bool:
        ok_u = hmac.compare_digest(self._digest(username.strip().lower()), self._digest(self.cfg.username.lower()))
        ok_p = hmac.compare_digest(self._digest(password), self._digest(self.cfg.password))
        return ok_u and ok_p

    # ---- throttling
    def locked_for(self, ip: str) -> int:
        until = self._locked.get(ip, 0.0)
        left = int(until - time.time())
        if left <= 0:
            self._locked.pop(ip, None)
            return 0
        return left

    def record_failure(self, ip: str) -> None:
        now = time.time()
        window = [t for t in self._fails.get(ip, []) if now - t < 900] + [now]
        self._fails[ip] = window
        if len(window) >= 6:
            self._locked[ip] = now + 900
            self._fails.pop(ip, None)

    def record_success(self, ip: str) -> None:
        self._fails.pop(ip, None)

    # ---- session cookie
    def issue(self, username: str) -> str:
        return self._ser.dumps({"u": username})

    def read(self, token: str | None) -> str | None:
        if not token:
            return None
        try:
            data = self._ser.loads(token, max_age=self.cfg.session_hours * 3600)
        except (BadSignature, SignatureExpired):
            return None
        u = data.get("u") if isinstance(data, dict) else None
        return u if u == self.cfg.username else None


def client_ip(request: Request) -> str:
    return request.client.host if request.client else "?"


class SecurityMiddleware:
    """Pure ASGI (does not buffer streaming uploads): CSRF guard + security headers."""

    def __init__(self, app, cfg: Settings):
        self.app = app
        self.cfg = cfg

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        headers = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope["headers"]}
        method = scope["method"]
        path = scope["path"]
        if method not in ("GET", "HEAD", "OPTIONS") and path.startswith("/api/"):
            origin = headers.get("origin")
            bad = headers.get(CSRF_HEADER) != CSRF_VALUE
            if origin and not bad:
                host = headers.get("host", "")
                bad = urlparse(origin).netloc != host
            if bad:
                return await self._reject(send)

        https = scope.get("scheme") == "https" or headers.get("x-forwarded-proto") == "https"

        async def send_wrapped(message):
            if message["type"] == "http.response.start":
                h = message.setdefault("headers", [])
                extra = {
                    "x-content-type-options": "nosniff",
                    "x-frame-options": "DENY",
                    "referrer-policy": "no-referrer",
                    "x-robots-tag": "noindex, nofollow",
                    "content-security-policy": CSP,
                    "permissions-policy": "camera=(), microphone=(), geolocation=()",
                    "cross-origin-opener-policy": "same-origin",
                }
                if https:
                    extra["strict-transport-security"] = "max-age=31536000"
                if path.startswith("/api/") or path == "/":
                    extra["cache-control"] = "no-store" if "cache-control" not in {k.decode().lower() for k, _ in h} else None
                for k, v in extra.items():
                    if v is not None:
                        h.append((k.encode(), v.encode()))
            await send(message)

        await self.app(scope, receive, send_wrapped)

    @staticmethod
    async def _reject(send):
        body = b'{"error":"csrf","message":"Request blocked"}'
        await send({"type": "http.response.start", "status": 403,
                    "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode())]})
        await send({"type": "http.response.body", "body": body})
