"""Minimal client for the iding.tw web API (the same JSON calls the iding.tw site makes).

The API is not public: request shapes come from a recording of the site, so
expect them to change without notice. The session is a cookie set by login.
"""

import json
import urllib.error
import urllib.request
from http.cookiejar import CookieJar

BASE = "https://iding.tw"
APP_VERSION = "3.1.0"  # what the iding.tw site sends with login
USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"


class IdingError(Exception):
    """A failure worth showing to the user as is."""


class Iding:
    def __init__(self):
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(CookieJar()))

    def call(self, method: str, path: str, body: dict | None = None):
        request = urllib.request.Request(
            f"{BASE}{path}",
            data=None if body is None else json.dumps(body).encode(),
            method=method,
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
                "Origin": BASE,
                "Referer": f"{BASE}/",
                "User-Agent": USER_AGENT,
            },
        )
        try:
            with self.opener.open(request, timeout=20) as response:
                raw = response.read()
        except urllib.error.HTTPError as exc:
            raise IdingError(f"iding odpověděl chybou {exc.code}: {error_message(exc)}") from exc
        except urllib.error.URLError as exc:
            raise IdingError(f"iding není dostupný: {exc.reason}") from exc
        try:
            return json.loads(raw) if raw else None
        except ValueError as exc:
            raise IdingError("iding vrátil neočekávanou odpověď (ne JSON).") from exc

    def login(self, phone: str, password: str) -> dict:
        """Log in with phone and password; the session cookie stays in this client."""
        if not phone or not password:
            raise IdingError("Vyplň telefon i heslo k idingu.")
        check = self.call("POST", "/api/user/check", {"phone": phone})
        salt = (check or {}).get("salt")
        if not salt:
            raise IdingError("Účet s tímto telefonem iding nezná.")
        result = self.call("POST", "/api/user/login", {
            "app_version": APP_VERSION,
            "device_token": "",
            "model": "Home Assistant",
            "password": password,
            "phone": phone,
            "platform": "Chrome/131.0.0.0",
            "salt": salt,
        })
        if not (result or {}).get("user_id"):
            raise IdingError("Přihlášení se nepovedlo: " + json.dumps(result, ensure_ascii=False)[:200])
        return result

    def user(self) -> dict:
        """Profile of the logged-in user."""
        result = self.call("GET", "/api/user")
        return (result or {}).get("data") or {}


def error_message(exc: urllib.error.HTTPError) -> str:
    try:
        body = json.loads(exc.read() or b"{}")
    except ValueError:
        return exc.reason or ""
    if isinstance(body, dict):
        for key in ("message", "error", "msg", "detail"):
            if body.get(key):
                return str(body[key])
    return json.dumps(body, ensure_ascii=False)[:200]
