"""Jinhua47 breakfast add-on: web UI served through Home Assistant Ingress.

Inside Home Assistant the Ingress proxy is the only client. It adds headers
naming the logged-in Home Assistant user, so the add-on needs no login of its
own. Home Assistant admins are admins of the add-on: they assign each user's
phone on the add-on page (the add-on options can only offer fixed lists).

With --dev the server runs on a laptop with made-up users and phones: the
user comes from ?as=<name> and notifications are only printed.
"""

import argparse
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
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

SUPERVISOR = "http://supervisor"
INGRESS_PROXY_IP = "172.30.32.2"
HERE = Path(__file__).parent
PAGE = HERE / "index.html"
ADMIN_GROUP = "system-admin"
CACHE_SECONDS = 60

DEV_USERS = [
    {"id": "dev-David", "name": "David", "is_admin": True},
    {"id": "dev-Jana", "name": "Jana", "is_admin": False},
    {"id": "dev-Petr", "name": "Petr", "is_admin": False},
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
        self.settings = json.loads(self.settings_file.read_text()) if self.settings_file.exists() else {}
        self.settings.setdefault("phones", {})
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
        for key in ("iding_phone", "iding_password"):
            if not self.options.get(key):
                log(f"V nastavení chybí {key}.")

    def save_settings(self) -> None:
        tmp = self.settings_file.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.settings, ensure_ascii=False, indent=2))
        tmp.replace(self.settings_file)

    def users(self) -> list[dict]:
        """Active, non-system Home Assistant users, cached for a minute."""
        if self.dev:
            return DEV_USERS
        fetched_at, users = self._users
        if time.monotonic() - fetched_at < CACHE_SECONDS:
            return users
        (raw,) = websocket_commands({"type": "config/auth/list"})
        users = sorted(
            (
                {
                    "id": u["id"],
                    "name": u.get("name") or u.get("username") or u["id"],
                    "is_admin": ADMIN_GROUP in u.get("group_ids", []),
                }
                for u in raw
                if not u.get("system_generated") and u.get("is_active", True)
            ),
            key=lambda u: u["name"].lower(),
        )
        self._users = (time.monotonic(), users)
        return users

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

    def send_notification(self, service: str, name: str) -> None:
        payload = {
            "title": "Jinhua47 Snídaně",
            "message": f"Ahoj {name}, tohle je testovací oznámení z doplňku.",
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
            page = PAGE.read_text().replace("{{NAME}}", html.escape(self.header_user()["name"]))
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
        if route == "/api/notify":
            self.guarded(self.post_notify)
        elif route == "/api/admin/phones":
            self.guarded(self.post_phones, admin=True)
        else:
            self.send_error(404)

    def guarded(self, handler, admin: bool = False) -> None:
        """Run an API handler, turning Home Assistant failures into JSON errors."""
        try:
            user = self.current_user()
            if admin and not user["is_admin"]:
                self.send_json(403, {"error": "Tohle může jen administrátor Home Assistantu."})
                return
            handler(user)
        except urllib.error.HTTPError as exc:
            self.send_json(502, {"error": f"Home Assistant vrátil chybu {exc.code}."})
        except (urllib.error.URLError, OSError, RuntimeError) as exc:
            log(f"Chyba při komunikaci s Home Assistantem: {exc}")
            self.send_json(502, {"error": f"Home Assistant není dostupný: {exc}"})

    def get_me(self, user: dict) -> None:
        self.send_json(200, {**user, "phone": self.app.settings["phones"].get(user["id"])})

    def get_admin(self, user: dict) -> None:
        app = self.app
        self.send_json(200, {
            "users": [{**u, "phone": app.settings["phones"].get(u["id"])} for u in app.users()],
            "phones": app.phones(),
            "iding": {
                "phone": app.options.get("iding_phone") or "",
                "password_set": bool(app.options.get("iding_password")),
            },
        })

    def post_phones(self, user: dict) -> None:
        body = self.read_json()
        valid_users = {u["id"] for u in self.app.users()}
        valid_phones = {p["service"] for p in self.app.phones()}
        with self.app.lock:
            phones = self.app.settings["phones"]
            for user_id, service in body.items():
                if user_id not in valid_users or (service and service not in valid_phones):
                    continue
                if service:
                    phones[user_id] = service
                else:
                    phones.pop(user_id, None)
            self.app.save_settings()
        log(f"{user['name']} upravil přiřazení telefonů.")
        self.send_json(200, {"ok": True})

    def post_notify(self, user: dict) -> None:
        service = self.app.settings["phones"].get(user["id"])
        if not service:
            self.send_json(400, {"error": "Zatím nemáš přiřazený telefon. Přiřadí ti ho administrátor níže na této stránce."})
            return
        self.app.send_notification(service, user["name"])
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
