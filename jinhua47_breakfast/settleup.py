"""Minimal client for the Settle Up API (https://api.settleup.io/).

Settle Up is a Firebase app: the user signs in with Firebase Authentication
(email and password) and the Realtime Database is read and written over REST
with the ID token in ?auth=. Each app gets its own Web API key from the
developer portal (https://developers.settleup.io/): a sandbox key right after
registration, a live key only after the app was tested on the sandbox and
the request was reviewed. Sandbox and live are separate projects, so the
account, groups and members differ between them too.
"""

import json
import time
import urllib.error
import urllib.parse
import urllib.request

DATABASES = {
    "sandbox": "https://settle-up-sandbox.firebaseio.com",
    "live": "https://settle-up-live.firebaseio.com",
}
WEB_APPS = {"sandbox": "https://settle-up-sandbox-app.web.app/", "live": "https://settleup.app/"}
SIGN_IN = "https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword"
# Firebase Authentication error codes, as the user should read them.
AUTH_ERRORS = {
    "EMAIL_NOT_FOUND": "účet s tímhle e-mailem neexistuje",
    "INVALID_PASSWORD": "špatné heslo",
    "INVALID_LOGIN_CREDENTIALS": "špatný e-mail nebo heslo",
    "INVALID_EMAIL": "neplatný e-mail",
    "USER_DISABLED": "účet je zablokovaný",
    "TOO_MANY_ATTEMPTS_TRY_LATER": "moc pokusů, zkus to později",
    "PASSWORD_LOGIN_DISABLED": "přihlášení heslem není povolené",
}


class SettleUpError(Exception):
    """A failure worth showing to the user as is."""


def _request(method: str, url: str, body=None):
    request = urllib.request.Request(
        url,
        data=None if body is None else json.dumps(body).encode(),
        method=method,
        headers={"Content-Type": "application/json", "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            raw = response.read()
    except urllib.error.HTTPError as exc:
        raw_error = exc.read() or b""
        try:
            error = json.loads(raw_error).get("error")
        except (ValueError, AttributeError):
            error = None
        message = error.get("message") if isinstance(error, dict) else error
        raise SettleUpHTTPError(exc.code, str(message or exc.reason)) from exc
    except urllib.error.URLError as exc:
        raise SettleUpError(f"Settle Up není dostupný: {exc.reason}") from exc
    try:
        return json.loads(raw) if raw else None
    except ValueError as exc:
        raise SettleUpError("Settle Up vrátil neočekávanou odpověď (ne JSON).") from exc


class SettleUpHTTPError(SettleUpError):
    def __init__(self, code: int, message: str):
        super().__init__(f"Settle Up odpověděl chybou {code}: {message}")
        self.code, self.message = code, message


class SettleUp:
    def __init__(self, environment: str, api_key: str):
        if environment not in DATABASES:
            raise SettleUpError(f"Neznámé prostředí Settle Up „{environment}“.")
        if not api_key:
            raise SettleUpError("Chybí Web API klíč Settle Up (z developers.settleup.io).")
        self.environment, self.api_key = environment, api_key
        self.database = DATABASES[environment]
        self.uid = self.token = None
        self.expires = 0.0

    def login(self, email: str, password: str) -> str:
        """Sign in with email and password; returns the Firebase user id."""
        if not email or not password:
            raise SettleUpError("Vyplň e-mail i heslo k Settle Up.")
        try:
            reply = _request("POST", f"{SIGN_IN}?key={urllib.parse.quote(self.api_key)}",
                             {"email": email, "password": password, "returnSecureToken": True})
        except SettleUpHTTPError as exc:
            code = exc.message.split(" ")[0].split(":")[0]
            if "API key" in exc.message or code.startswith("API_KEY"):
                raise SettleUpError("Web API klíč Settle Up není platný (pro tohle prostředí).") from exc
            raise SettleUpError(f"Přihlášení do Settle Up selhalo: {AUTH_ERRORS.get(code, exc.message)}.") from exc
        self.uid, self.token = reply["localId"], reply["idToken"]
        self.expires = time.time() + int(reply.get("expiresIn") or 3600) - 60
        return self.uid

    def call(self, method: str, path: str, body=None):
        if not self.token or time.time() > self.expires:
            raise SettleUpError("Nepřihlášeno do Settle Up.")
        url = f"{self.database}/{path}.json?auth={urllib.parse.quote(self.token)}"
        try:
            return _request(method, url, body)
        except SettleUpHTTPError as exc:
            if exc.code in (401, 403):
                raise SettleUpError(f"Settle Up nepovolil {method} {path.split('/')[0]} "
                                    "(chybí oprávnění ve skupině?).") from exc
            raise

    def user_name(self) -> str:
        user = self.call("GET", f"users/{self.uid}") or {}
        return user.get("name") or user.get("email") or self.uid

    def groups(self) -> list[dict]:
        """Groups of the signed-in user: [{id, name, currency, member, level}], by the user's order."""
        listed = self.call("GET", f"userGroups/{self.uid}") or {}
        groups = []
        for group_id, entry in sorted(listed.items(), key=lambda kv: (kv[1] or {}).get("order", 0)):
            group = self.call("GET", f"groups/{group_id}") or {}
            permission = self.call("GET", f"permissions/{group_id}/{self.uid}") or {}
            groups.append({
                "id": group_id,
                "name": group.get("name") or group_id,
                "currency": group.get("convertedToCurrency") or "",
                "member": (entry or {}).get("member"),
                "level": permission.get("level"),
            })
        return groups

    def members(self, group_id: str) -> list[dict]:
        """Active members of a group: [{id, name}]."""
        members = self.call("GET", f"members/{group_id}") or {}
        return sorted(
            ({"id": member_id, "name": m.get("name") or member_id}
             for member_id, m in members.items() if (m or {}).get("active", True)),
            key=lambda m: m["name"].lower(),
        )

    def add_expense(self, group_id: str, *, purpose: str, amount, currency: str, paid_by: str,
                    shares: dict[str, float], when_ms: int, timezone: str, category: str = "🍔") -> str:
        """One expense paid by paid_by, split by weights {member_id: weight}; returns its id.

        A single item with weights instead of one item per person: Settle Up reads several
        items as main expense, tip and tax. Amounts and weights are strings in the API.
        """
        transaction = {
            "type": "expense",
            "purpose": purpose,
            "category": category,
            "currencyCode": currency,
            "dateTime": when_ms,
            "timezone": timezone,
            "fixedExchangeRate": False,
            "exchangeRates": {},
            "whoPaid": [{"memberId": paid_by, "weight": "1"}],
            "items": [{
                "amount": str(amount),
                "forWhom": [{"memberId": m, "weight": str(w)} for m, w in shares.items() if w],
            }],
        }
        reply = self.call("POST", f"transactions/{group_id}", transaction) or {}
        return reply.get("name") or ""
