"""Jinhua47 breakfast add-on: web UI served through Home Assistant Ingress.

Inside Home Assistant the Ingress proxy is the only client. It adds headers
naming the logged-in Home Assistant user, so the add-on needs no login of its
own. With --dev the server runs on a laptop: the user comes from ?as=<name>
and notifications are only printed.
"""

import argparse
import html
import json
import os
import signal
import sys
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

SUPERVISOR = "http://supervisor"
OPTIONS_FILE = Path("/data/options.json")
INGRESS_PROXY_IP = "172.30.32.2"
PAGE = Path(__file__).with_name("index.html")


def log(*parts) -> None:
    print(*parts, flush=True)


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


class App:
    def __init__(self, dev: bool):
        self.dev = dev
        self.options = (
            {"notify_service": "mobile_app_dev_telefon"} if dev else json.loads(OPTIONS_FILE.read_text())
        )
        self.panel_path = ""  # sidebar URL of this add-on, used as the notification tap target

    @property
    def notify_service(self) -> str:
        """Option value as a bare service name: 'notify.mobile_app_x' -> 'mobile_app_x'."""
        value = (self.options.get("notify_service") or "").strip()
        return value.removeprefix("notify.")

    def startup(self) -> None:
        if self.dev:
            return
        try:
            info = supervisor_call("GET", "/addons/self/info")["data"]
            self.panel_path = f"/{info['slug']}"
            wanted = bool(self.options.get("show_in_sidebar", True))
            if info.get("ingress_panel") != wanted:
                supervisor_call("POST", "/addons/self/options", {"ingress_panel": wanted})
                log(f"Postranní panel: {'zobrazen' if wanted else 'skryt'}")
        except (urllib.error.URLError, KeyError, ValueError) as exc:
            log(f"Nastavení postranního panelu selhalo: {exc}")

    def notify_services(self) -> list[str]:
        """Phone notify services Home Assistant offers (mobile_app_*)."""
        if self.dev:
            return ["mobile_app_dev_telefon"]
        for domain in supervisor_call("GET", "/core/api/services"):
            if domain["domain"] == "notify":
                return sorted(s for s in domain["services"] if s.startswith("mobile_app_"))
        return []

    def send_notification(self, name: str) -> None:
        service = self.notify_service
        payload = {
            "title": "Jinhua47 Snídaně",
            "message": f"Ahoj {name}, tohle je testovací oznámení z doplňku.",
            # Tapping the notification opens the add-on panel in the Companion app.
            "data": {"url": self.panel_path, "clickAction": self.panel_path} if self.panel_path else {},
        }
        if self.dev:
            log(f"[dev] notify.{service or '(nenastaveno)'}: {json.dumps(payload, ensure_ascii=False)}")
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

    def user(self) -> dict:
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

    def send_json(self, status: int, body: dict) -> None:
        data = json.dumps(body, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if not self.allowed():
            return
        route = self.path.partition("?")[0]
        if route in ("/", "/index.html"):
            page = PAGE.read_text().replace("{{NAME}}", html.escape(self.user()["name"]))
            data = page.encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        else:
            self.send_error(404)

    def do_POST(self):
        if not self.allowed():
            return
        if self.path.partition("?")[0] != "/api/notify":
            self.send_error(404)
            return
        app = self.app
        if not app.notify_service:
            self.send_json(400, {
                "error": "V nastavení doplňku není vyplněný telefon (notify_service).",
                "available": app.notify_services(),
            })
            return
        try:
            app.send_notification(self.user()["name"])
        except urllib.error.HTTPError as exc:
            available = app.notify_services()
            missing = app.notify_service not in available
            self.send_json(502, {
                "error": f"Služba notify.{app.notify_service} neexistuje." if missing
                else f"Home Assistant vrátil chybu {exc.code}.",
                "available": available,
            })
            return
        except urllib.error.URLError as exc:
            self.send_json(502, {"error": f"Home Assistant není dostupný: {exc.reason}"})
            return
        self.send_json(200, {"ok": True, "service": f"notify.{app.notify_service}"})


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
