"""Jinhua47 breakfast add-on: web UI served through Home Assistant Ingress.

Inside Home Assistant the Ingress proxy is the only client. It adds headers
naming the logged-in Home Assistant user, so the add-on needs no login of its
own. The only add-on option is who the admins are; admins manage everything
else (phones, nicknames, phrases, the iding account) on the add-on page,
stored in /data/settings.json.

With --dev the server runs on a laptop with made-up users and phones: the
user comes from ?as=<name> and notifications are only printed.
"""

import argparse
import hashlib
import html
import json
import os
import re
import signal
import sys
import threading
import time
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from iding import Iding, IdingError

SUPERVISOR = "http://supervisor"
INGRESS_PROXY_IP = "172.30.32.2"
HERE = Path(__file__).parent
PAGE = HERE / "index.html"
ADMIN_GROUP = "system-admin"
CACHE_SECONDS = 60
# The daily notification goes out at most this long after its time, so a
# restart later in the day does not send a stale morning reminder.
DAILY_WINDOW = timedelta(hours=1)

try:  # the Supervisor passes Home Assistant's time zone in TZ; otherwise use the system's
    TZ = ZoneInfo(os.environ["TZ"])
except (KeyError, ValueError, ZoneInfoNotFoundError):
    TZ = datetime.now().astimezone().tzinfo

TIME_RE = re.compile(r"([01]?\d|2[0-3]):([0-5]\d)")

DEFAULT_SETTINGS = {
    "members": [],  # Home Assistant user ids taking part, in the order the admin added them
    "phones": {},
    "nicknames": {},
    "iding": {"phone": "", "password": ""},
    "daily_notification_time": "07:00",
    "notification_phrases": [
        "co si dáš dneska k snídani?",
        "snídaně se sama neobjedná.",
        "dneska je ideální den na vajíčka.",
    ],
    "page_phrases": ["dneska ti to sluší.", "káva už čeká.", "vyber si něco dobrého."],
}
# Settings that were add-on options up to 0.4.0, copied over once.
MIGRATED_OPTIONS = ("daily_notification_time", "notification_phrases", "page_phrases")

DEV_USERS = [
    {"id": "dev-David", "name": "David", "username": "david", "ha_admin": True},
    {"id": "dev-Jana", "name": "Jana", "username": "jana", "ha_admin": False},
    {"id": "dev-Petr", "name": "Petr", "username": "petr", "ha_admin": False},
]
DEV_PHONES = [
    {"service": "mobile_app_davids_iphone", "label": "David's iPhone"},
    {"service": "mobile_app_pixel_8", "label": "Pixel 8"},
]


def log(*parts) -> None:
    print(*parts, flush=True)


def slugify(text: str) -> str:
    """Close enough to Home Assistant's slugify for mobile_app service names."""
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")


def clean_lines(value) -> list[str]:
    """A list of non-empty stripped strings from a list (or newline-separated text)."""
    if isinstance(value, str):
        value = value.split("\n")
    return [str(v).strip() for v in value or [] if str(v).strip()]


def supervisor_call(method: str, path: str, body: dict | None = None):
    request = urllib.request.Request(
        f"{SUPERVISOR}{path}",
        data=None if body is None else json.dumps(body).encode(),
        method=method,
        headers={
            "Authorization": f"Bearer {os.environ['SUPERVISOR_TOKEN']}",
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(request, timeout=15) as response:
        raw = response.read()
    return json.loads(raw) if raw else None


def websocket_commands(*commands: dict) -> list:
    """Run Home Assistant websocket commands and return their results in order."""
    import websocket  # websocket-client; only installed in the add-on image

    ws = websocket.create_connection("ws://supervisor/core/websocket", timeout=15)
    try:
        ws.recv()  # auth_required
        ws.send(json.dumps({"type": "auth", "access_token": os.environ["SUPERVISOR_TOKEN"]}))
        if json.loads(ws.recv()).get("type") != "auth_ok":
            raise RuntimeError("websocket auth failed")
        results = []
        for number, command in enumerate(commands, start=1):
            ws.send(json.dumps({"id": number, **command}))
            while True:  # skip events and other replies
                reply = json.loads(ws.recv())
                if reply.get("id") == number and reply.get("type") == "result":
                    break
            if not reply.get("success"):
                raise RuntimeError(f"{command['type']}: {reply.get('error')}")
            results.append(reply["result"])
        return results
    finally:
        ws.close()


class App:
    def __init__(self, dev: bool):
        self.dev = dev
        data_dir = HERE / "dev_data" if dev else Path("/data")
        data_dir.mkdir(exist_ok=True)
        self.settings_file = data_dir / "settings.json"
        options_file = data_dir / "options.json"
        self.options = json.loads(options_file.read_text()) if options_file.exists() else {}
        stored = json.loads(self.settings_file.read_text()) if self.settings_file.exists() else {}
        self.settings = json.loads(json.dumps(DEFAULT_SETTINGS)) | stored  # deep copy of defaults
        if "members" not in stored:  # up to 0.5.0 everyone was listed; keep those already set up
            self.settings["members"] = list(dict.fromkeys([*self.settings["phones"], *self.settings["nicknames"]]))
        self.migrate_options(stored)
        self.lock = threading.Lock()
        self.panel_path = ""  # sidebar URL of this add-on, used as the notification tap target
        self._users: tuple[float, list] = (0.0, [])

    def startup(self) -> None:
        if self.dev:
            return
        try:
            self.panel_path = "/" + supervisor_call("GET", "/addons/self/info")["data"]["slug"]
        except (urllib.error.URLError, KeyError, ValueError) as exc:
            log(f"Nepodařilo se zjistit adresu panelu: {exc}")
        if not (self.settings["iding"]["phone"] and self.settings["iding"]["password"]):
            log("Účet iding není vyplněný (nastaví ho správce na stránce doplňku).")
        try:
            self.check_admins()
        except (OSError, RuntimeError) as exc:
            log(f"Seznam uživatelů se nenačetl: {exc}")

    def migrate_options(self, stored: dict) -> None:
        """Copy settings that used to be add-on options (up to 0.4.0) unless already stored."""
        changed = False
        for key in MIGRATED_OPTIONS:
            if key not in stored and key in self.options:
                self.settings[key] = self.options[key]
                changed = True
        if "iding" not in stored and (self.options.get("iding_phone") or self.options.get("iding_password")):
            self.settings["iding"] = {
                "phone": self.options.get("iding_phone") or "",
                "password": self.options.get("iding_password") or "",
            }
            changed = True
        if changed:
            log("Nastavení z konfigurace doplňku přesunuto na stránku doplňku.")
            self.save_settings()

    # --- daily nickname and phrases ---------------------------------------

    @staticmethod
    def today() -> date:
        return datetime.now(TZ).date()

    def pick(self, user_id: str, kind: str, items: list[str]) -> str | None:
        """Pick one item per user and day: stable within the day, different across users and days."""
        items = [i.strip() for i in items if i and i.strip()]
        if not items:
            return None
        seed = hashlib.sha256(f"{self.today()}|{user_id}|{kind}".encode()).digest()
        return items[int.from_bytes(seed[:8]) % len(items)]

    def nickname(self, user_id: str, fallback: str) -> str:
        return self.pick(user_id, "nickname", self.settings["nicknames"].get(user_id, [])) or fallback

    def page_phrase(self, user_id: str) -> str | None:
        return self.pick(user_id, "page", self.settings["page_phrases"])

    def notification_message(self, user_id: str, name: str) -> str:
        hello = f"Ahoj {self.nickname(user_id, name)}"
        phrase = self.pick(user_id, "notification", self.settings["notification_phrases"])
        return f"{hello}, {phrase}" if phrase else f"{hello}!"

    # --- daily notification -----------------------------------------------

    def daily_time(self) -> tuple[int, int] | None:
        """The configured time as (hour, minute); None when empty (notification off)."""
        match = TIME_RE.fullmatch((self.settings["daily_notification_time"] or "").strip())
        return (int(match[1]), int(match[2])) if match else None

    def daily_loop(self) -> None:
        """Re-reads the time every round, so a change on the page applies right away."""
        log(f"Časové pásmo: {getattr(TZ, 'key', None) or datetime.now(TZ).tzname()}.")
        while True:
            when = self.daily_time()
            now = datetime.now(TZ)
            if when and self.settings.get("last_daily") != str(now.date()):
                due = now.replace(hour=when[0], minute=when[1], second=0, microsecond=0)
                if due <= now < due + DAILY_WINDOW:
                    self.send_daily()
            time.sleep(30)

    def send_daily(self) -> None:
        with self.lock:
            self.settings["last_daily"] = str(self.today())
            self.save_settings()
        try:
            names = {u["id"]: u["name"] for u in self.users()}
        except (OSError, RuntimeError) as exc:
            log(f"Seznam uživatelů se nenačetl, oznámení použijí jen přezdívky: {exc}")
            names = {}
        phones = self.settings["phones"]
        for user_id, service in [(m, phones[m]) for m in self.settings["members"] if m in phones]:
            if names and user_id not in names:
                continue  # deleted in Home Assistant; the admin sees it marked on the page
            try:
                self.send_notification(service, self.notification_message(user_id, names.get(user_id, "")))
            except (urllib.error.URLError, OSError) as exc:
                log(f"Denní oznámení na notify.{service} selhalo: {exc}")
        log("Denní oznámení odeslána.")

    def save_settings(self) -> None:
        tmp = self.settings_file.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.settings, ensure_ascii=False, indent=2))
        tmp.replace(self.settings_file)

    def admin_names(self) -> set[str]:
        """The `admins` option, lowercased; empty means every Home Assistant admin."""
        return {str(a).strip().lower() for a in self.options.get("admins") or [] if str(a).strip()}

    def is_admin(self, user: dict) -> bool:
        admins = self.admin_names()
        if not admins:
            return user["ha_admin"]
        return bool(admins & {str(user.get(k) or "").lower() for k in ("username", "name", "id")})

    def users(self) -> list[dict]:
        """Active, non-system Home Assistant users, cached for a minute."""
        if self.dev:
            raw_users = DEV_USERS
        else:
            fetched_at, users = self._users
            if time.monotonic() - fetched_at < CACHE_SECONDS:
                return users
            (raw,) = websocket_commands({"type": "config/auth/list"})
            raw_users = [
                {
                    "id": u["id"],
                    "name": u.get("name") or u.get("username") or u["id"],
                    "username": u.get("username") or "",
                    "ha_admin": ADMIN_GROUP in u.get("group_ids", []),
                }
                for u in raw
                if not u.get("system_generated") and u.get("is_active", True)
            ]
        users = sorted(
            ({**u, "is_admin": self.is_admin(u)} for u in raw_users),
            key=lambda u: u["name"].lower(),
        )
        self._users = (time.monotonic(), users)
        return users

    def check_admins(self) -> None:
        """Log `admins` entries that match nobody, so a typo does not silently lock everyone out."""
        admins = self.admin_names()
        if not admins:
            log("Správci: všichni administrátoři Home Assistantu.")
            return
        users = self.users()
        known = {str(u.get(k) or "").lower() for u in users for k in ("username", "name", "id")}
        for name in sorted(admins - known):
            log(f"Správce „{name}“ z nastavení neodpovídá žádnému uživateli Home Assistantu.")
        log("Správci: " + (", ".join(u["name"] for u in users if u["is_admin"]) or "nikdo"))

    def is_member(self, user_id: str) -> bool:
        return user_id in self.settings["members"]

    def user(self, user_id: str) -> dict | None:
        return next((u for u in self.users() if u["id"] == user_id), None)

    def phones(self) -> list[dict]:
        """mobile_app notify services, labelled with the phone's device name where it matches."""
        if self.dev:
            return DEV_PHONES
        services, devices = websocket_commands(
            {"type": "get_services"}, {"type": "config/device_registry/list"}
        )
        names = {}
        for device in devices:
            for name in (device.get("name"), device.get("name_by_user")):
                if name:
                    names[f"mobile_app_{slugify(name)}"] = device.get("name_by_user") or name
        return sorted(
            ({"service": s, "label": names.get(s, s)} for s in services.get("notify", {}) if s.startswith("mobile_app_")),
            key=lambda p: p["label"].lower(),
        )

    def send_notification(self, service: str, message: str) -> None:
        payload = {
            "title": "Jinhua47 Snídaně",
            "message": message,
            # Tapping the notification opens the add-on panel in the Companion app.
            "data": {"url": self.panel_path, "clickAction": self.panel_path} if self.panel_path else {},
        }
        if self.dev:
            log(f"[dev] notify.{service}: {json.dumps(payload, ensure_ascii=False)}")
            return
        supervisor_call("POST", f"/core/api/services/notify/{service}", payload)


class Handler(BaseHTTPRequestHandler):
    app: App

    def log_message(self, fmt, *args):  # quieter than the default access log
        if self.app.dev:
            super().log_message(fmt, *args)

    def allowed(self) -> bool:
        """Outside dev mode accept only the Ingress proxy, which authenticates the user."""
        if self.app.dev or self.client_address[0] == INGRESS_PROXY_IP:
            return True
        self.send_error(403)
        return False

    def header_user(self) -> dict:
        """Id and name of the logged-in user, from Ingress headers (or ?as= in dev mode)."""
        if self.app.dev:
            query = self.path.partition("?")[2]
            params = dict(p.partition("=")[::2] for p in query.split("&") if p)
            name = urllib.request.unquote(params.get("as", "David"))
            return {"id": f"dev-{name}", "name": name}
        h = self.headers
        return {
            "id": h.get("X-Remote-User-Id", ""),
            "name": h.get("X-Remote-User-Display-Name") or h.get("X-Remote-User-Name") or "neznámý",
        }

    def current_user(self) -> dict:
        """header_user plus is_admin, which needs the Home Assistant user list."""
        user = self.header_user()
        known = self.app.user(user["id"]) or {}
        return {**user, "is_admin": known.get("is_admin", False)}

    def send_json(self, status: int, body) -> None:
        data = json.dumps(body, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def read_json(self):
        length = int(self.headers.get("Content-Length") or 0)
        return json.loads(self.rfile.read(length) or b"{}")

    def route(self) -> str:
        return self.path.partition("?")[0]

    def do_GET(self):
        if not self.allowed():
            return
        route = self.route()
        if route in ("/", "/index.html"):
            user = self.header_user()
            phrase = self.app.page_phrase(user["id"])
            page = (
                PAGE.read_text()
                .replace("{{NAME}}", html.escape(self.app.nickname(user["id"], user["name"])))
                .replace("{{PHRASE}}", html.escape(phrase or ""))
                .replace("{{PHRASE_HIDDEN}}", "" if phrase else "hidden")
                .replace("{{NOT_MEMBER_HIDDEN}}", "hidden" if self.app.is_member(user["id"]) else "")
            )
            data = page.encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        elif route == "/api/me":
            self.guarded(self.get_me)
        elif route == "/api/admin":
            self.guarded(self.get_admin, admin=True)
        else:
            self.send_error(404)

    def do_POST(self):
        if not self.allowed():
            return
        route = self.route()
        if route == "/api/admin/test_notify":
            self.guarded(self.post_test_notify, admin=True)
        elif route == "/api/admin/settings":
            self.guarded(self.post_settings, admin=True)
        elif route == "/api/admin/iding_test":
            self.guarded(self.post_iding_test, admin=True)
        else:
            self.send_error(404)

    def guarded(self, handler, admin: bool = False) -> None:
        """Run an API handler, turning Home Assistant failures into JSON errors."""
        try:
            user = self.current_user()
            if admin and not user["is_admin"]:
                self.send_json(403, {"error": "Tohle může jen správce doplňku."})
                return
            handler(user)
        except ValueError:
            self.send_json(400, {"error": "Neplatný požadavek (JSON)."})
        except urllib.error.HTTPError as exc:
            self.send_json(502, {"error": f"Home Assistant vrátil chybu {exc.code}."})
        except (urllib.error.URLError, OSError, RuntimeError) as exc:
            log(f"Chyba při komunikaci s Home Assistantem: {exc}")
            self.send_json(502, {"error": f"Home Assistant není dostupný: {exc}"})

    def get_me(self, user: dict) -> None:
        self.send_json(200, {**user, "is_member": self.app.is_member(user["id"])})

    def get_admin(self, user: dict) -> None:
        app = self.app
        ha_users = {u["id"]: u for u in app.users()}
        members = app.settings["members"]
        self.send_json(200, {
            # Members are stored by Home Assistant user id; the name is looked up fresh, so
            # renaming someone in Home Assistant never breaks the link.
            "members": [
                {
                    **ha_users.get(user_id, {"id": user_id, "name": "smazaný uživatel", "is_admin": False}),
                    "missing": user_id not in ha_users,
                    "phone": app.settings["phones"].get(user_id),
                    "nicknames": app.settings["nicknames"].get(user_id, []),
                }
                for user_id in members
            ],
            "candidates": [{"id": u["id"], "name": u["name"]} for u in ha_users.values() if u["id"] not in members],
            "phones": app.phones(),
            "admins_from_option": bool(app.admin_names()),
            "admins": [u["name"] for u in ha_users.values() if u["is_admin"]],
            "daily_notification_time": app.settings["daily_notification_time"],
            "notification_phrases": app.settings["notification_phrases"],
            "page_phrases": app.settings["page_phrases"],
            # The password never leaves the add-on; the page only learns whether one is set.
            "iding": {
                "phone": app.settings["iding"]["phone"],
                "password_set": bool(app.settings["iding"]["password"]),
            },
        })

    def post_settings(self, user: dict) -> None:
        """Save the settings page. An empty iding password keeps the stored one."""
        body = self.read_json()
        when = str(body.get("daily_notification_time") or "").strip()
        if when and not TIME_RE.fullmatch(when):
            self.send_json(400, {"error": f"Čas oznámení „{when}“ není ve tvaru HH:MM."})
            return
        valid_users = {u["id"] for u in self.app.users()}
        valid_phones = {p["service"] for p in self.app.phones()}
        app = self.app
        with app.lock:
            settings = app.settings
            if when != settings["daily_notification_time"]:
                settings.pop("last_daily", None)  # a new time may fire again today
            settings["daily_notification_time"] = when
            for key in ("notification_phrases", "page_phrases"):
                settings[key] = clean_lines(body.get(key))
            iding = body.get("iding") or {}
            settings["iding"]["phone"] = str(iding.get("phone") or "").strip()
            if iding.get("password"):
                settings["iding"]["password"] = str(iding["password"])
            elif iding.get("clear_password"):
                settings["iding"]["password"] = ""
            self.save_users(body.get("users") or {}, valid_users, valid_phones)
            app.save_settings()
        log(f"{user['name']} uložil nastavení.")
        self.send_json(200, {"ok": True, "password_set": bool(app.settings["iding"]["password"])})

    def post_iding_test(self, user: dict) -> None:
        """Try logging in to iding with the typed phone/password (or the stored password)."""
        body = self.read_json()
        phone = str(body.get("phone") or "").strip()
        password = str(body.get("password") or "") or self.app.settings["iding"]["password"]
        try:
            client = Iding()
            client.login(phone, password)
            profile = client.user()
        except IdingError as exc:
            self.send_json(400, {"error": str(exc)})
            return
        name = profile.get("name") or phone
        log(f"Přihlášení do idingu ověřeno ({name}).")
        self.send_json(200, {"ok": True, "name": name})

    def save_users(self, body: dict, valid_users: set, valid_phones: set) -> None:
        """Apply {user_id: {"phone": service or "", "nicknames": [..]}}; caller holds the lock.

        The keys are the new member list, in order. A removed member's phone and
        nicknames are deleted. Existing members whose Home Assistant account is gone
        may stay (so the admin can see and remove them); new ones must exist.
        """
        settings = self.app.settings
        phones, nicknames = settings["phones"], settings["nicknames"]
        if not isinstance(body, dict):
            return
        allowed = valid_users | set(settings["members"])
        members = [m for m in body if m in allowed and isinstance(body[m], dict)]
        for gone in set(settings["members"]) - set(members):
            phones.pop(gone, None)
            nicknames.pop(gone, None)
        settings["members"] = members
        for user_id in members:
            entry = body[user_id]
            service = entry.get("phone") or ""
            if not service:
                phones.pop(user_id, None)
            elif service in valid_phones:
                phones[user_id] = service
            names = clean_lines(entry.get("nicknames"))
            if names:
                nicknames[user_id] = names
            else:
                nicknames.pop(user_id, None)

    def post_test_notify(self, user: dict) -> None:
        """Send a user's notification of the day to the phone picked in the form (saved or not)."""
        body = self.read_json()
        target = self.app.user(str(body.get("user_id") or ""))
        service = str(body.get("phone") or "")
        if not target:
            self.send_json(400, {"error": "Neznámý uživatel."})
            return
        if not service:
            self.send_json(400, {"error": f"{target['name']} nemá vybraný telefon."})
            return
        if service not in {p["service"] for p in self.app.phones()}:
            self.send_json(400, {"error": f"Telefon notify.{service} v Home Assistantu není."})
            return
        self.app.send_notification(service, self.app.notification_message(target["id"], target["name"]))
        self.send_json(200, {"ok": True, "service": f"notify.{service}"})


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dev", action="store_true", help="local run without Home Assistant")
    parser.add_argument("--host", default=None)
    parser.add_argument("--port", type=int, default=8099)
    args = parser.parse_args()

    # The Supervisor stops the add-on with SIGTERM; exit without a traceback.
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
    app = App(dev=args.dev)
    app.startup()
    threading.Thread(target=app.daily_loop, daemon=True).start()
    Handler.app = app
    host = args.host or ("127.0.0.1" if args.dev else "0.0.0.0")
    server = ThreadingHTTPServer((host, args.port), Handler)
    log(f"Běží na http://{host}:{args.port}" + (" (dev)" if args.dev else ""))
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    sys.exit(0)


if __name__ == "__main__":
    main()
