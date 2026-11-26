"""Jinhua47 breakfast add-on: web UI served through Home Assistant Ingress.

Inside Home Assistant the Ingress proxy is the only client. It adds headers
naming the logged-in Home Assistant user, so the add-on needs no login of its
own. The only add-on option is who the admins are; admins manage everything
else (phones, nicknames, phrases, the iding account) on the add-on page,
stored in /data/settings.json. Members pick a set and a drink from the menu
loaded from iding; today's picks are kept in /data/choices.json and a ticker at
the top of the page shows everyone who has chosen. An admin approves the day's
picks, which locks them and fills the iding cart (no order is placed yet).

With --dev the server runs on a laptop with made-up users and phones: the
user comes from ?as=<name> and notifications are only printed.
"""

import argparse
import functools
import hashlib
import html
import json
import os
import random
import re
import signal
import sys
import threading
import time
import traceback
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import menu
from iding import Iding, IdingError

SUPERVISOR = "http://supervisor"
INGRESS_PROXY_IP = "172.30.32.2"
HERE = Path(__file__).parent
# Extra notification data per level (Companion app): "high" is delivered at once even when the phone
# saves power (Android priority/ttl, iOS time-sensitive); "alarm" also rings on Android's alarm
# channel, so it sounds even when the phone is silenced.
ALERT_DATA = {
    "high": {"ttl": 0, "priority": "high", "push": {"interruption-level": "time-sensitive"}},
    "alarm": {"ttl": 0, "priority": "high", "channel": "alarm_stream",
              "push": {"interruption-level": "time-sensitive"}},
}
# Own photos of the sets, named by set (photos/README.md); they win over iding's. First the add-on's
# config folder in Home Assistant (/addon_configs/<slug>/photos, uploaded there, not on GitHub),
# then the ones shipped with the add-on.
PHOTOS_DIR = HERE / "photos"
PHOTO_TYPES = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".webp": "image/webp"}
PHOTO_MAX_BYTES = 5_000_000
PAGE = HERE / "index.html"
ADMIN_GROUP = "system-admin"
CACHE_SECONDS = 60
ORDER_WATCH_SECONDS = int(os.environ.get("ORDER_WATCH_SECONDS", "60"))  # how often a paid order is checked
PICK_EPOCH = date(2026, 1, 1)  # daily picks (nicknames, phrases) are replayed from here
WAIT_SECONDS = 25  # how long /api/wait holds a request open when nothing changes
MENU_CACHE_SECONDS = 600  # the menu is ~450 KB; sold-out items show up within ten minutes
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
    # {user_id: "high" | "alarm"}: stronger notifications on that member's phone (default normal).
    "alerts": {},
    "iding": {"phone": "", "password": ""},
    "daily_notification_time": "07:00",
    "notification_phrases": [
        "co si dáš dneska k snídani?",
        "snídaně se sama neobjedná.",
        "dneska je ideální den na vajíčka.",
    ],
    "page_phrases": ["dneska ti to sluší.", "káva už čeká.", "vyber si něco dobrého."],
    # The ticker at the top of the page: one entry per member, a phrase by whether they have chosen.
    "ticker_chosen_phrases": ["má jasno.", "už se těší.", "vybral jako šampion."],
    "ticker_pending_phrases": ["pořád neví, co chce.", "zdržuje celou výpravu.", "ještě spí?"],
    # Tell admins (on their phone) once everyone else has chosen and the order waits for them.
    "notify_admin_ready": True,
    "test_mode": False,  # only admins see anything; everyone else gets a "Testovací režim" screen
}
TICKER_EMOJI = {
    "chosen": ["👍", "✅", "😋", "👌", "🥳"],
    "pending": ["😠", "👎", "😤", "🙄", "😴"],
}
# iding order_status values (from the site's code)
ORDER_SENT, ORDER_READY, ORDER_CLOSED, ORDER_CANCELLED = 1, 2, 3, 4
# Order stages after which the picks may be reopened and ordered again.
ORDER_REOPENABLE = ("cancelled",)
# Order stages announced to Home Assistant as events jinhua47_breakfast_<stage>.
ORDER_EVENTS = ("ordered", "paid", "ready", "closed", "cancelled")
TEMPERATURES = ("iced", "hot")
SIZES = ("small", "large")
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
    """One line in the add-on log, with local time (the Supervisor log has no timestamps)."""
    print(datetime.now(TZ).strftime("%Y-%m-%d %H:%M:%S"), *parts, flush=True)


def keep_running(loop):
    """Run a background loop forever; an unexpected error is logged and the loop restarts."""
    def run() -> None:
        while True:
            try:
                loop()
            except Exception:  # noqa: BLE001 - a dead thread would silently stop notifications
                log(f"Neočekávaná chyba ve smyčce {loop.__name__}, za minutu znovu:\n{traceback.format_exc()}")
                time.sleep(60)
    return run


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


@functools.lru_cache(maxsize=512)
def daily_pick(today: date, user_id: str, kind: str, items: tuple[str, ...]) -> str:
    """Nothing is stored: the picks are replayed day by day from PICK_EPOCH, each day choosing
    randomly (from a hash of day, user and kind) among the items other than the previous day's."""
    day = min(PICK_EPOCH, today)
    index = None
    while day <= today:
        seed = hashlib.sha256(f"{day}|{user_id}|{kind}".encode()).digest()
        allowed = [i for i in range(len(items)) if i != index] or [0]
        index = allowed[int.from_bytes(seed[:8]) % len(allowed)]
        day += timedelta(days=1)
    return items[index]


@functools.lru_cache(maxsize=64)
def daily_assignment(today: date, kind: str, user_ids: tuple[str, ...], items: tuple[str, ...]) -> dict[str, str]:
    """{user_id: item} for today: random, no two people the same and nobody the same as the day
    before, as far as the list allows (fewer items than people means some repeat).

    Replayed day by day from PICK_EPOCH like daily_pick(); each day tries seeded shuffles until
    one gives nobody their previous item, else keeps the one with the fewest repeats.
    """
    if not items or not user_ids:
        return {}
    previous: dict[str, int] = {}
    day = min(PICK_EPOCH, today)
    while day <= today:
        rng = random.Random(hashlib.sha256(f"{day}|{kind}".encode()).digest())
        best, best_repeats = None, 0
        for _ in range(60):
            order = list(range(len(items)))
            rng.shuffle(order)
            pick = {user_id: order[i % len(order)] for i, user_id in enumerate(user_ids)}
            repeats = sum(previous.get(u) == pick[u] for u in user_ids) if len(items) > 1 else 0
            if best is None or repeats < best_repeats:
                best, best_repeats = pick, repeats
            if not repeats:
                break
        previous = best
        day += timedelta(days=1)
    return {user_id: items[index] for user_id, index in previous.items()}


def is_paid(found: dict | None) -> bool:
    """Whether an order from the iding history is paid: payment_status 2, or already past payment
    (sent / ready / closed; an unpaid LINE Pay order shows order_status 101)."""
    if not found:
        return False
    return found.get("payment_status") == 2 or found.get("order_status") in (ORDER_SENT, ORDER_READY, ORDER_CLOSED)


class App:
    def __init__(self, dev: bool):
        # Bumped on every saved change; pages long-poll /api/wait to show it right away.
        self.version = 0
        self.changed = threading.Condition()
        self.dev = dev
        data_dir = HERE / "dev_data" if dev else Path("/data")
        data_dir.mkdir(exist_ok=True)
        self.settings_file = data_dir / "settings.json"
        self.menu_file = data_dir / "menu.json"  # last good menu, used while iding is down
        self.photo_cache = data_dir / "photos"  # iding's set photos, downloaded once
        # /config is the add-on's own config folder (config.yaml map: addon_config), /addon_configs/<slug> in HA.
        self.own_photos_dir = (HERE / "dev_config" if dev else Path("/config")) / "photos"
        self.photo_lock = threading.Lock()
        # Today's picks and the admin's approval: {"date", "choices": {user_id: ..}, "approved": {..} | None}
        self.choices_file = data_dir / "choices.json"
        stored_choices = json.loads(self.choices_file.read_text()) if self.choices_file.exists() else {}
        self._choices_date = stored_choices.get("date", "")
        self._choices: dict = stored_choices.get("choices", {})
        # {user_id: {"date", "choice"}}: each member's last pick from an earlier day ("Jako včera").
        self.previous: dict = stored_choices.get("previous", {})
        self.approved: dict | None = stored_choices.get("approved")
        # {"by", "at"} once an admin started today's ordering; until then members see only a notice.
        self.opened: dict | None = stored_choices.get("opened")
        # Whether today's invitation to members went out (only on the first opening of the day).
        self.invited: bool = stored_choices.get("invited", False)
        # Which "ready" notification each admin got today ("you" or "all"), so it is sent once.
        self.admin_notified: dict = stored_choices.get("admin_notified", {})
        # Today's iding order once placed: stage ordered -> awaiting_payment -> paid -> ready -> closed
        # (or cancelled), ids for LINE Pay, and who placed it (the only one notified about it).
        self.order: dict | None = stored_choices.get("order")
        self._iding: Iding | None = None  # logged-in client, reused while the session lasts
        self.iding_lock = threading.Lock()
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
        self._menu: tuple[float, dict | None] = (0.0, None)
        self.menu_lock = threading.Lock()

    def menu(self) -> dict:
        """Sets and drinks for the page, from iding, cached; falls back to the last good copy."""
        with self.menu_lock:
            fetched_at, cached = self._menu
            if cached and time.monotonic() - fetched_at < MENU_CACHE_SECONDS:
                return cached
            try:
                client = Iding()
                result = menu.build_menu(client.menu(menu.STORE), client.inventories(menu.STORE))
                if not result["sets"]:
                    raise IdingError("V menu idingu nejsou žádné sety.")
                self.menu_file.write_text(json.dumps(result, ensure_ascii=False))
                self.write_photo_names(result["sets"])
            except IdingError as exc:
                if not cached and self.menu_file.exists():
                    cached = json.loads(self.menu_file.read_text())
                if not cached:
                    raise
                log(f"Menu se nenačetlo, používám uložené: {exc}")
                result = {**cached, "stale": True}
            for item in result["sets"]:
                item["photo"] = self.photo_link(item)
            self._menu = (time.monotonic(), result)
            return result

    # --- set photos ------------------------------------------------------------

    def own_photo(self, set_slug: str) -> Path | None:
        """<slug>.jpg (or .jpeg, .png, .webp) from the config folder in HA, else from the add-on."""
        if not set_slug:
            return None
        return next((folder / f"{set_slug}{ext}" for folder in (self.own_photos_dir, PHOTOS_DIR)
                     for ext in PHOTO_TYPES if (folder / f"{set_slug}{ext}").is_file()), None)

    def write_photo_names(self, sets: list) -> None:
        """NAZVY.txt in the config photo folder: which file name belongs to which set."""
        lines = ["Vlastní fotky setů: soubor pojmenuj podle setu (.jpg, .jpeg, .png nebo .webp).",
                 "Fotka se na stránce ukáže do 10 minut, nebo hned po restartu doplňku.", ""]
        lines += [f"{item['slug']}.jpg    {item['label']}" for item in sets]
        text = "\n".join(lines) + "\n"
        names = self.own_photos_dir / "NAZVY.txt"
        try:
            self.own_photos_dir.mkdir(parents=True, exist_ok=True)
            if not names.is_file() or names.read_text() != text:
                names.write_text(text)
        except OSError as exc:
            log(f"Složku na vlastní fotky nejde připravit: {exc}")

    def photo_link(self, item: dict) -> str | None:
        """Relative URL of the set's photo for the page (own photo first, then iding's), or None.
        The ?v= part changes with the picture, so browsers may cache each version for long."""
        own = self.own_photo(item.get("slug", ""))
        if own:
            tag = f"{own.name}{own.stat().st_mtime_ns}"
        elif item.get("iding_photo"):
            tag = item["iding_photo"]
        else:
            return None
        return f"photo/{item['index']}?v={hashlib.sha1(tag.encode()).hexdigest()[:10]}"

    def photo(self, index: int) -> tuple[bytes, str] | None:
        """(image bytes, content type) of a set's photo; iding's is downloaded on first use and kept."""
        item = next((s for s in self.menu()["sets"] if s["index"] == index), None)
        if not item:
            return None
        own = self.own_photo(item.get("slug", ""))
        if own:
            return own.read_bytes(), PHOTO_TYPES[own.suffix]
        url = item.get("iding_photo")
        if not url:
            return None
        ext = Path(url).suffix.lower() if Path(url).suffix.lower() in PHOTO_TYPES else ".jpg"
        cached = self.photo_cache / f"{hashlib.sha1(url.encode()).hexdigest()}{ext}"
        with self.photo_lock:
            if not cached.is_file():
                request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
                with urllib.request.urlopen(request, timeout=15) as response:
                    kind = response.headers.get_content_type()
                    data = response.read(PHOTO_MAX_BYTES + 1)
                if not kind.startswith("image/") or len(data) > PHOTO_MAX_BYTES:
                    raise OSError(f"fotka {url} není obrázek do 5 MB ({kind}, {len(data)} B)")
                self.photo_cache.mkdir(exist_ok=True)
                cached.write_bytes(data)
                log(f"Fotka setu {item['label']} stažená z idingu ({len(data) // 1024} kB).")
        return cached.read_bytes(), PHOTO_TYPES[ext]

    # --- today's choices and the ticker -------------------------------------

    def choices(self) -> dict:
        """{user_id: choice} for today; yesterday's picks are dropped. Caller holds the lock."""
        today = str(self.today())
        if self._choices_date != today:
            if self._choices_date:  # keep the finished day's picks; a member who skipped it keeps an older one
                for user_id, choice in self._choices.items():
                    self.previous[user_id] = {"date": self._choices_date, "choice": choice}
            self._choices_date, self._choices, self.approved, self.admin_notified = today, {}, None, {}
            self.opened = None
            self.invited = False
            self.order = None
        return self._choices

    def is_open(self) -> bool:
        """True once an admin started today's ordering (it closes again at midnight)."""
        with self.lock:
            self.choices()
            return self.opened is not None

    def view(self, user: dict) -> str:
        """What the page shows the user: "open" (nickname, phrases, ticker, menu), or only a notice:
        "test" (test mode), "not_member" or "closed" (ordering not started). Admins always get "open"."""
        if user.get("is_admin"):
            return "open"
        if self.settings.get("test_mode"):
            return "test"
        if not self.is_member(user["id"]):
            return "not_member"
        return "open" if self.is_open() else "closed"

    def visible(self, user: dict) -> bool:
        return self.view(user) == "open"

    def open_ordering(self, by: str) -> bool:
        """Open today's ordering; True when members should be invited (first opening of the day)."""
        with self.lock:
            self.choices()
            if self.opened is None:
                self.opened = {"by": by, "at": datetime.now(TZ).strftime("%H:%M")}
            invite, self.invited = not self.invited, True
            self.save_choices()
            return invite

    def invite_members(self, opener_id: str) -> None:
        """"Ahoj <přezdívka>, <hláška z denních oznámení>" with "Klikni zde a objednej." to every
        member with a phone but the opener.

        In test mode only admins get it. Tapping opens the add-on page.
        """
        try:
            users = {u["id"]: u for u in self.users()}
        except (OSError, RuntimeError) as exc:
            log(f"Seznam uživatelů se nenačetl, pozvánky neodešly: {exc}")
            return
        phones = self.settings["phones"]
        sent, failed, skipped = [], [], []
        for user_id in self.settings["members"]:
            user, phone = users.get(user_id), phones.get(user_id)
            if not user:
                skipped.append(f"{user_id} (není v HA)")
                continue
            if user_id == opener_id:
                skipped.append(f"{user['name']} (zahájil)")
                continue
            if not phone:
                skipped.append(f"{user['name']} (nemá telefon)")
                continue
            if self.settings.get("test_mode") and not user["is_admin"]:
                skipped.append(f"{user['name']} (testovací režim)")
                continue
            title = self.notification_message(user_id, user["name"])
            try:
                self.send_notification(phone, "Klikni zde a objednej.", title=title, who=f"pozvánka {user['name']}")
                sent.append(user["name"])
            except (urllib.error.URLError, OSError):
                failed.append(user["name"])  # details logged by send_notification
        log("Pozvánky: odesláno " + (", ".join(sent) or "nikomu")
            + (f"; selhalo: {', '.join(failed)}" if failed else "")
            + (f"; bez pozvánky: {', '.join(skipped)}" if skipped else "") + ".")

    def clear_choices(self) -> int:
        """Drop everyone's picks for today (before approval); returns how many there were."""
        with self.lock:
            choices = self.choices()
            if self.approved is not None:
                raise IdingError("Objednávka je schválená. Nejdřív dej „Znovu otevřít výběr“.")
            count = len(choices)
            choices.clear()
            self.admin_notified = {}
            self.save_choices()
            return count

    def close_ordering(self) -> None:
        """Hide today's ordering from members again; picks, approval and the order stay."""
        with self.lock:
            self.choices()
            if self.opened is not None:
                self.opened = None
                self.save_choices()

    def is_locked(self) -> bool:
        """True once the admin approved today's order. Caller holds the lock."""
        self.choices()  # a new day unlocks
        return self.approved is not None

    def save_choices(self) -> None:
        tmp = self.choices_file.with_suffix(".tmp")
        state = {
            "date": self._choices_date,
            "choices": self._choices,
            "previous": self.previous,
            "approved": self.approved,
            "opened": self.opened,
            "invited": self.invited,
            "admin_notified": self.admin_notified,
            "order": self.order,
        }
        tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2))
        tmp.replace(self.choices_file)
        self.bump()

    def bump(self) -> None:
        """Something the pages show changed: wake every page waiting in /api/wait."""
        with self.changed:
            self.version += 1
            self.changed.notify_all()

    def wait_for_change(self, seen: int, timeout: float) -> int:
        """The current version, as soon as it differs from `seen` or after `timeout` seconds."""
        with self.changed:
            self.changed.wait_for(lambda: self.version != seen, timeout)
            return self.version

    def order_overview(self) -> dict:
        """For the admin: each member's pick, identical picks grouped, and the total."""
        page_menu = self.menu()
        names = {u["id"]: u["name"] for u in self.users()}
        with self.lock:
            choices = dict(self.choices())
            approved = self.approved
            opened = self.opened
            # The e-invoice carrier and payment ids stay in the add-on.
            order = {k: v for k, v in (self.order or {}).items() if k not in ("carrier", "bank_transaction_id")}
        members, groups = [], {}
        for user_id in self.settings["members"]:
            if user_id not in names:
                continue
            choice = choices.get(user_id)
            info = menu.describe(page_menu, choice) if choice else None
            members.append({"id": user_id, "name": names[user_id], "choice": info})
            if choice:
                key = (choice["set"], choice["drink"], choice["temp"], choice["size"])
                group = groups.setdefault(key, {**info, "quantity": 0, "names": []})
                group["quantity"] += 1
                group["names"].append(names[user_id])
        return {
            "members": members,
            "groups": list(groups.values()),
            "total": sum(g["price"] * g["quantity"] for g in groups.values()),
            "approved": approved,
            "opened": opened,
            "order": order or None,
        }

    def approve(self, by: str) -> dict:
        """Lock today's picks and put them into the iding cart (replacing it); nothing is ordered.

        Picks of members still in Home Assistant are grouped into cart items. iding then
        prices the cart itself (/api/orders/check), which is compared with our total.
        Raises IdingError (or ValueError for picks the menu no longer has); stays unlocked then.
        """
        names = {u["id"]: u["name"] for u in self.users()}
        with self.lock:
            if self.is_locked():
                raise IdingError("Objednávka už je schválená.")
            picks: dict[tuple, list] = {}
            for user_id in self.settings["members"]:
                choice = self.choices().get(user_id)
                if choice and user_id in names:
                    picks.setdefault((choice["set"], choice["drink"], choice["temp"], choice["size"]), [choice, 0])[1] += 1
        if not picks:
            raise IdingError("Zatím nikdo nemá vybráno.")
        account = self.settings["iding"]
        client = Iding()
        client.login(account["phone"], account["password"])
        raw = client.menu(menu.STORE)
        raw_menu = raw.get("data") or raw
        items, our_total = menu.cart_items(raw, [(c, q) for c, q in picks.values()])
        stored = client.set_cart(menu.STORE, items, raw_menu.get("sha1"))
        result = {
            "at": datetime.now(TZ).strftime("%H:%M"),
            "by": by,
            "items": sum(q for _, q in picks.values()),
            "our_total": our_total,
            "iding_total": None,
            "target_time": None,
            "warning": "",
        }
        try:  # a price check is a bonus: the cart is already filled
            target = client.first_pickup_time(menu.STORE, our_total)
            if not target:
                result["warning"] = "Obchod teď nenabízí žádný čas vyzvednutí, cenu iding nepotvrdil."
            else:
                check = client.check_order(menu.STORE, stored, target, raw_menu.get("version"))
                result["iding_total"], result["target_time"] = check.get("total"), target
                if check.get("total") != our_total:
                    result["warning"] = f"iding počítá {check.get('total')} NT$, my {our_total} NT$."
        except IdingError as exc:
            result["warning"] = f"Kontrola ceny na idingu selhala: {exc}"
        with self.lock:
            self.choices()
            self.approved = result
            self.save_choices()
        log(f"{by} schválil objednávku: {result['items']} ks, {our_total} NT$ v košíku na idingu."
            + (f" {result['warning']}" if result["warning"] else ""))
        return result

    def unlock(self) -> None:
        with self.lock:
            self.choices()
            if self.order and self.order["stage"] not in ORDER_REOPENABLE:
                raise IdingError("Objednávka už je odeslaná, výběr nejde znovu otevřít.")
            self.approved = None
            self.order = None
            self.save_choices()

    # --- ordering and LINE Pay ------------------------------------------------

    def with_iding(self, action):
        """Run action(client) with a logged-in iding client; log in again once if the session expired."""
        with self.iding_lock:
            for attempt in (1, 2):
                if self._iding is None:
                    account = self.settings["iding"]
                    client = Iding()
                    client.login(account["phone"], account["password"])
                    self._iding = client
                try:
                    return action(self._iding)
                except IdingError as exc:
                    if attempt == 2 or "401" not in str(exc):
                        raise
                    self._iding = None  # expired session: log in and try once more

    def pickup_times(self) -> dict:
        """Times offered for pickup of the approved order on the first day the store takes orders,
        every 5 minutes. They depend on the order total: a bigger order gets later times."""
        with self.lock:
            self.choices()
            total = (self.approved or {}).get("our_total") or 0
        windows = Iding().pickup_windows(menu.STORE, total)
        if not windows:
            return {"day": None, "today": False, "times": []}
        day, first, last = windows[0]
        start = datetime.strptime(first, "%H:%M")
        start += timedelta(minutes=-start.minute % 5)  # round up to whole 5 minutes
        end = datetime.strptime(last, "%H:%M")
        times = [first] if start.strftime("%H:%M") != first else []
        while start <= end:
            times.append(start.strftime("%H:%M"))
            start += timedelta(minutes=5)
        return {"day": day, "today": day == str(self.today()), "times": times}

    def set_order(self, only_id=None, **changes) -> dict:
        """Merge changes into today's order; with only_id, only while that order is still today's
        (the watcher must not bring back an order reset or replaced meanwhile), else {}."""
        with self.lock:
            self.choices()
            if only_id is not None and (self.order or {}).get("id") != only_id:
                return {}
            before = (self.order or {}).get("stage")
            self.order = {**(self.order or {}), **changes}
            self.save_choices()
            order = dict(self.order)
            items = (self.approved or {}).get("items")
        if order.get("stage") != before and order.get("stage") in ORDER_EVENTS:
            self.fire_order_event(order, items)
        return order

    def fire_order_event(self, order: dict, items) -> None:
        """Home Assistant event jinhua47_breakfast_<stage> (ordered, paid, ready, closed, cancelled)
        for automations; sent in the background and logged."""
        event = f"jinhua47_breakfast_{order['stage']}"
        target = order.get("target_time") or ""
        data = {
            "stage": order["stage"],
            "order_id": order.get("id"),
            "order_number": order.get("order_number"),
            "total": order.get("total"),
            "items": items,
            "pickup_time": target[-5:],
            "pickup": target,
            "by": order.get("by"),
            "by_user_id": order.get("by_id"),
        }

        def fire() -> None:
            log(f"Událost → {event}: {json.dumps(data, ensure_ascii=False)}")
            if self.dev:
                log(f"[dev] Událost → {event}: neposláno (dev režim)")
                return
            try:
                supervisor_call("POST", f"/core/api/events/{event}", data)
            except urllib.error.HTTPError as exc:
                body = exc.read().decode(errors="replace")[:300]
                log(f"Událost → {event}: Home Assistant odmítl (HTTP {exc.code}): {body}")
            except (urllib.error.URLError, OSError) as exc:
                log(f"Událost → {event}: selhalo: {exc}")
            else:
                log(f"Událost → {event}: Home Assistant přijal ✓")

        threading.Thread(target=fire, daemon=True).start()

    def place_order(self, user: dict, target_time: str) -> None:
        """Order the approved cart for pickup at target_time ("YYYY-MM-DD HH:MM") and ask LINE Pay.

        iding prices the cart first; when that differs from what was approved nothing is
        sent. The admin who orders gets the LINE Pay link on their phone.
        """
        with self.lock:
            if not self.is_locked():
                raise IdingError("Objednávku nejdřív schval.")
            if self.order and self.order["stage"] not in ORDER_REOPENABLE:
                raise IdingError("Objednávka už je odeslaná.")
            approved = dict(self.approved)
        page_menu = self.menu()

        def send(client: Iding):
            items = client.cart(menu.STORE)
            if not items:
                raise IdingError("Košík na idingu je prázdný. Otevři výběr znovu a schval objednávku.")
            check = client.check_order(menu.STORE, items, target_time, page_menu["version"])
            count = sum(item.get("quantity") or 0 for item in check.get("cart") or [])
            if check.get("total") != approved["our_total"] or count != approved["items"]:
                raise IdingError(
                    f"V košíku na idingu je {count} ks za {check.get('total')} NT$, schváleno bylo "
                    f"{approved['items']} ks za {approved['our_total']} NT$. Nic se neobjednalo; "
                    "otevři výběr znovu a schval objednávku."
                )
            log(f"iding spočítal košík: {count} ks za {check.get('total')} NT$, sedí se schválením; odesílám objednávku.")
            order = client.place_order(menu.STORE, check, target_time, page_menu["version"])
            if not order.get("id") or not order.get("item_name"):
                raise IdingError(f"iding objednávku nepřijal: {json.dumps(order, ensure_ascii=False)[:200]}")
            carrier = (check.get("user") or {}).get("carrier")
            # Saved before asking LINE Pay, so a failure there still shows the sent order.
            self.set_order(
                stage="ordered", id=order["id"], item_name=order["item_name"], total=order.get("total"),
                target_time=target_time, by=user["name"], by_id=user["id"], carrier=carrier,
                at=datetime.now(TZ).strftime("%H:%M"), order_number=None,
            )
            log(f"{user['name']} odeslal objednávku {order['id']} ({order.get('total')} NT$, {target_time}).")
            return client.line_pay_reserve(menu.STORE, order, carrier)

        reserve = self.with_iding(send)
        self.payment_reserved(reserve)

    def payment_reserved(self, reserve: dict) -> None:
        order = self.set_order(
            stage="awaiting_payment",
            bank_transaction_id=reserve["bank_transaction_id"],
            payment_url_app=reserve.get("payment_url_app"),
            payment_url_web=reserve.get("payment_url_web"),
        )
        log(f"LINE Pay připravil platbu k objednávce {order['id']} (transakce {order['bank_transaction_id']}).")
        self.notify_orderer(
            order,
            f"Objednávka odeslána: {order['total']} NT$, vyzvednutí v {order['target_time'][-5:]}. "
            "Ťukni a zaplať v LINE Pay.",
            url=order.get("payment_url_app") or order.get("payment_url_web"),
        )

    def retry_payment(self) -> None:
        """Ask LINE Pay again for an order that is sent but not paid (e.g. the first link expired)."""
        order = self.current_order(("ordered", "awaiting_payment"))
        reserve = self.with_iding(lambda client: client.line_pay_reserve(
            menu.STORE, {"item_name": order["item_name"]}, order.get("carrier")))
        self.payment_reserved(reserve)

    def current_order(self, stages: tuple) -> dict:
        with self.lock:
            self.choices()
            order = dict(self.order or {})
        if order.get("stage") not in stages:
            raise IdingError("Tohle teď u objednávky nejde.")
        return order

    def confirm_payment(self) -> None:
        """After the admin paid: mark the order paid, finishing the LINE Pay payment on iding if needed.

        The order on iding is checked first: when it was paid some other way (e.g. on iding.tw
        in a browser after the first LINE Pay attempt failed), our LINE Pay transaction is stale
        and confirming it would only fail.
        """
        order = self.current_order(("ordered", "awaiting_payment"))
        found = self.with_iding(lambda client: client.order_status(order["id"]))
        log(f"Objednávka {order['id']} na idingu: " + (
            f"order_status {found.get('order_status')}, payment_status {found.get('payment_status')}."
            if found else "nenalezena v historii."))
        if is_paid(found):
            self.mark_paid(found.get("order_number"), found.get("order_status"))
            return
        if not order.get("bank_transaction_id"):
            raise IdingError("Objednávka na idingu ještě není zaplacená. Dej „Nový odkaz na platbu“ a zaplať.")
        try:
            result = self.with_iding(lambda client: client.line_pay_confirm(
                menu.STORE, order["item_name"], order["bank_transaction_id"]))
        except IdingError as exc:
            raise IdingError(
                f"LINE Pay platbu nedokončil ({exc}). Tahle platba asi neprošla nebo vypršela: dej "
                "„Nový odkaz na platbu“ a zaplať znovu. Jestli jsi už zaplatil jinde (na iding.tw), "
                "zkus to za chvíli znovu, doplněk to pozná i sám do minuty."
            ) from exc
        log(f"Dokončení platby {order['id']}: payment_status {result.get('payment_status')}, "
            f"order_status {result.get('order_status')}, číslo {result.get('order_number')}.")
        if result.get("payment_status") != 2:
            raise IdingError(f"Platba zatím není zaplacená (stav {result.get('payment_status')}). "
                             "Schval ji v LINE a zkus to znovu.")
        self.mark_paid(result.get("order_number"), result.get("order_status"))

    def mark_paid(self, order_number, status) -> None:
        order = self.current_order(("ordered", "awaiting_payment"))
        order = self.set_order(stage="paid", order_number=order_number or order.get("order_number"), status=status)
        log(f"Objednávka {order['id']} zaplacena, číslo {order['order_number']}.")
        number = f" Číslo objednávky {order['order_number']}." if order.get("order_number") else ""
        self.notify_orderer(order, f"Zaplaceno ✓.{number} Vyzvednutí v {order['target_time'][-5:]}.")

    def cancel_order(self) -> None:
        """Cancel a sent but unpaid order on iding."""
        order = self.current_order(("ordered", "awaiting_payment"))
        self.with_iding(lambda client: client.cancel_order(order["id"]))
        self.set_order(stage="cancelled")
        log(f"Objednávka {order['id']} zrušena.")

    def reset_order(self, by: str) -> None:
        """Forget today's order in the add-on only, whatever its state on iding (nothing is sent there).

        For when the add-on is stuck (e.g. a payment that iding will no longer confirm and an
        order the store will not cancel). The approval is dropped too, so the picks stay but are
        unlocked; the watcher stops following the old order."""
        with self.lock:
            self.choices()
            order = self.order
            self.order = None
            self.approved = None
            self.save_choices()
        if order:
            log(f"{by} resetoval objednávku v doplňku (iding {order.get('id')}, stav {order.get('stage')}, "
                f"číslo {order.get('order_number') or '–'}); na idingu se nic nezměnilo.")
        else:
            log(f"{by} resetoval objednávku v doplňku (žádná nebyla).")

    def order_watch_loop(self) -> None:
        """Every minute check today's order on iding: an unpaid one that got paid elsewhere (iding.tw)
        becomes paid; a paid one notifies the orderer once it is ready for pickup."""
        while True:
            time.sleep(ORDER_WATCH_SECONDS)
            with self.lock:
                self.choices()
                order = dict(self.order or {})
            if order.get("stage") not in ("ordered", "awaiting_payment", "paid", "ready"):
                continue
            try:
                found = self.with_iding(lambda client: client.order_status(order["id"]))
            except IdingError as exc:
                log(f"Stav objednávky se nepodařilo zjistit: {exc}")
                continue
            if order["stage"] in ("ordered", "awaiting_payment"):
                if is_paid(found):
                    log(f"Objednávka {order['id']} je na idingu zaplacená (order_status {found.get('order_status')}, "
                        f"payment_status {found.get('payment_status')}).")
                    try:
                        self.mark_paid(found.get("order_number"), found.get("order_status"))
                    except IdingError:
                        pass  # the admin confirmed it meanwhile
                elif (found or {}).get("order_status") == ORDER_CANCELLED:
                    order = self.set_order(only_id=order["id"], stage="cancelled", status=ORDER_CANCELLED)
                    if order:
                        self.notify_orderer(order, "Nezaplacená objednávka byla na idingu zrušená.")
                continue
            status = (found or {}).get("order_status")
            if status != order.get("status"):
                log(f"Objednávka {order['id']} má na idingu stav {status}" + ("" if found else " (nenalezena)") + ".")
                order = self.set_order(only_id=order["id"], status=status)  # log each change once, not every minute
                if not order:
                    continue  # reset or replaced meanwhile
            if status in (ORDER_READY, ORDER_CLOSED) and order["stage"] == "paid":
                order = self.set_order(only_id=order["id"], stage="ready" if status == ORDER_READY else "closed",
                                       status=status)
                if order:
                    self.notify_orderer(order, "Snídaně je připravená k vyzvednutí"
                                        + (f" (číslo {order['order_number']})." if order.get("order_number") else "."))
            elif status == ORDER_CLOSED:
                self.set_order(only_id=order["id"], stage="closed", status=status)
            elif status == ORDER_CANCELLED:
                order = self.set_order(only_id=order["id"], stage="cancelled", status=status)
                if order:
                    self.notify_orderer(order, "Obchod objednávku zrušil"
                                        + (f" (číslo {order['order_number']})." if order.get("order_number") else "."))

    def notify_orderer(self, order: dict, message: str, url: str | None = None) -> None:
        """Progress goes only to the admin who placed the order, on their phone."""
        phone = self.settings["phones"].get(order.get("by_id"))
        if not phone:
            log(f"{order.get('by')} nemá telefon, oznámení se neposlalo: {message}")
            return
        try:
            self.send_notification(phone, message, url=url, who=f"objednávka {order.get('by')}")
        except (urllib.error.URLError, OSError):
            pass  # logged by send_notification

    def check_choice(self, body: dict) -> tuple[dict | None, str]:
        """(choice, "") when set, drink, temperature and size exist on today's menu, else (None, error)."""
        menu = self.menu()
        chosen_set = next((s for s in menu["sets"] if s["index"] == body.get("set")), None)
        if not chosen_set or chosen_set["sold_out"]:
            return None, "Tenhle set teď v nabídce není."
        drink = next(
            (d for d in menu["drinks"] if d["index"] == body.get("drink") and d["index"] in chosen_set["drinks"]),
            None,
        )
        if not drink or drink["sold_out"]:
            return None, "Tohle pití k setu teď není."
        temp, size = body.get("temp"), body.get("size")
        if temp not in TEMPERATURES or (temp == "hot" and not drink["hot"]):
            return None, "Tohle pití takhle teplé nejde."
        if size not in SIZES or not drink["sizes"].get(size):
            return None, "Tuhle velikost pití nemá."
        return {"set": chosen_set["index"], "drink": drink["index"], "temp": temp, "size": size}, ""

    def previous_choice(self, user_id: str) -> dict | None:
        """The member's last pick from an earlier day, described on today's menu, or None.

        {"choice", "title", "set", "drink", "price", "error"}; error says why it cannot be
        picked today (sold out, no longer on the menu), else "".
        """
        with self.lock:
            self.choices()
            entry = self.previous.get(user_id)
        if not entry:
            return None
        try:
            choice, error = self.check_choice(entry["choice"])
            info = menu.describe(self.menu(), entry["choice"])
        except IdingError:
            return None
        day = date.fromisoformat(entry["date"])
        if day == self.today() - timedelta(days=1):
            title = "Jako včera"
        else:
            weekday = ("po", "út", "st", "čt", "pá", "so", "ne")[day.weekday()]
            title = f"Jako minule ({weekday} {day.day}. {day.month}.)"
        return {
            "choice": choice or entry["choice"], "title": title, "error": error,
            "set": info.get("set") or info["text"], "drink": info.get("drink", ""), "price": info["price"],
        }

    def notify_admins_if_ready(self, actor_id: str) -> None:
        """After a pick changed: tell each admin with a phone when only they (or their approval) are missing.

        "you": everyone else has chosen, the admin (a member) has not. "all": everyone has
        chosen, the order waits for approval. Each situation is sent once; it can fire again
        after it stops being true (someone starts over). The admin whose own pick completed
        it gets nothing, they are on the page already.
        """
        if not self.settings.get("notify_admin_ready", True):
            return
        try:
            users = self.users()
        except (OSError, RuntimeError) as exc:
            log(f"Seznam uživatelů se nenačetl, správce neupozorním: {exc}")
            return
        known = {u["id"] for u in users}
        to_send = []
        with self.lock:
            if self.is_locked():
                return
            chosen = set(self.choices())
            members = [m for m in self.settings["members"] if m in known]
            for admin in (u for u in users if u["is_admin"]):
                others = [m for m in members if m != admin["id"]]
                situation = None
                if others and all(m in chosen for m in others):
                    situation = "you" if admin["id"] in members and admin["id"] not in chosen else "all"
                if situation is None:
                    self.admin_notified.pop(admin["id"], None)
                    continue
                if self.admin_notified.get(admin["id"]) == situation:
                    continue
                self.admin_notified[admin["id"]] = situation
                phone = self.settings["phones"].get(admin["id"])
                if admin["id"] == actor_id or not phone:
                    continue
                count = len([m for m in members if m in chosen])
                message = (
                    f"Ostatní už mají vybráno ({count}), chybíš jen ty. Pak můžeš objednávku schválit."
                    if situation == "you"
                    else f"Všichni mají vybráno ({count}), objednávka čeká na tvoje schválení."
                )
                to_send.append((admin["name"], phone, message))
            self.save_choices()
        for name, phone, message in to_send:
            try:
                self.send_notification(phone, message, who=f"správce {name}")
            except (urllib.error.URLError, OSError):
                pass  # logged by send_notification

    def ticker(self) -> list[dict]:
        """One entry per member for the scrolling bar: emoji, name and a phrase by status."""
        names = {u["id"]: u["name"] for u in self.users()}
        with self.lock:
            chosen = set(self.choices())
        # Every member gets both a "chosen" and a "pending" phrase (and emoji) for today, so whoever
        # is in which state, no two people show the same one.
        members = tuple(sorted(self.settings["members"]))
        today = self.today()

        def assigned(kind: str, items) -> dict[str, str]:
            return daily_assignment(today, kind, members, tuple(i.strip() for i in items if i and i.strip()))

        emoji = {kind: assigned(f"ticker_emoji_{kind}", TICKER_EMOJI[kind]) for kind in TICKER_EMOJI}
        phrases = {kind: assigned(f"ticker_{kind}", self.settings[f"ticker_{kind}_phrases"]) for kind in TICKER_EMOJI}
        entries = []
        for user_id in self.settings["members"]:
            if user_id not in names:
                continue  # deleted in Home Assistant
            kind = "chosen" if user_id in chosen else "pending"
            entries.append({
                "id": user_id,
                "name": names[user_id],
                "chosen": kind == "chosen",
                "emoji": emoji[kind].get(user_id, ""),
                "phrase": phrases[kind].get(user_id, ""),
            })
        return entries

    def startup(self) -> None:
        if self.dev:
            return
        try:
            self.panel_path = "/" + supervisor_call("GET", "/addons/self/info")["data"]["slug"]
            log(f"Vlastní fotky setů patří do /addon_configs{self.panel_path}/photos (názvy v NAZVY.txt).")
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
        """Pick one item per user and day: stable within the day, random across users and days,
        but never the same as the day before (when there are at least two items)."""
        items = tuple(i.strip() for i in items if i and i.strip())
        return daily_pick(self.today(), user_id, kind, items) if items else None

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
            users = self.users()
        except (OSError, RuntimeError) as exc:
            log(f"Seznam uživatelů se nenačetl, oznámení použijí jen přezdívky: {exc}")
            users = []
        names = {u["id"]: u["name"] for u in users}
        admins = {u["id"] for u in users if u.get("is_admin")}
        phones = self.settings["phones"]
        for user_id, service in [(m, phones[m]) for m in self.settings["members"] if m in phones]:
            if names and user_id not in names:
                continue  # deleted in Home Assistant; the admin sees it marked on the page
            if self.settings.get("test_mode") and user_id not in admins:
                continue  # test mode: nobody but the admins hears from the add-on
            try:
                self.send_notification(service, self.notification_message(user_id, names.get(user_id, "")),
                                       who=f"denní {names.get(user_id, user_id)}")
            except (urllib.error.URLError, OSError):
                pass  # logged by send_notification
        log("Denní oznámení odeslána.")

    def save_settings(self) -> None:
        tmp = self.settings_file.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.settings, ensure_ascii=False, indent=2))
        tmp.replace(self.settings_file)
        self.bump()

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

    def alert_level(self, service: str) -> str:
        """The strongest level set for the members on this phone ("alarm", "high" or "")."""
        alerts = self.settings.get("alerts", {})
        levels = {alerts.get(uid, "") for uid, phone in self.settings["phones"].items() if phone == service}
        return next((level for level in ("alarm", "high") if level in levels), "")

    def send_notification(self, service: str, message: str, url: str | None = None,
                          title: str = "Jinhua47 Snídaně", who: str = "", level: str | None = None) -> None:
        """Tapping opens `url` (e.g. the LINE Pay link), by default the add-on panel in the Companion app.

        Every notification is logged with its recipient, text and link, and whether Home Assistant
        accepted it; a failure is logged and then raised to the caller."""
        target = url or self.panel_path
        level = self.alert_level(service) if level is None else level  # level: the test uses the form's
        payload = {
            "title": title,
            "message": message,
            "data": {**({"url": target, "clickAction": target} if target else {}), **ALERT_DATA.get(level, {})},
        }
        recipient = f"{who} (notify.{service})" if who else f"notify.{service}"
        log(f"Oznámení → {recipient}: „{title}“ / „{message}“, odkaz {target or '–'}"
            + (f", důraz {level}" if level in ALERT_DATA else ""))
        if self.dev:
            log(f"[dev] {recipient}: neposláno (dev režim)")
            return
        try:
            supervisor_call("POST", f"/core/api/services/notify/{service}", payload)
        except urllib.error.HTTPError as exc:
            body = exc.read().decode(errors="replace")[:300]
            log(f"Oznámení → {recipient}: Home Assistant odmítl (HTTP {exc.code}): {body}")
            raise
        except (urllib.error.URLError, OSError) as exc:
            log(f"Oznámení → {recipient}: selhalo: {exc}")
            raise
        log(f"Oznámení → {recipient}: Home Assistant přijal ✓")


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

    def get_photo(self, index: str) -> None:
        """A set's photo (anyone who reaches the add-on through Ingress; they are not personal)."""
        try:
            found = self.app.photo(int(index)) if index.isdigit() else None
        except (IdingError, urllib.error.URLError, OSError) as exc:
            log(f"Fotku setu {index} nejde načíst: {exc}")
            self.send_error(502)
            return
        if not found:
            self.send_error(404)
            return
        data, kind = found
        self.send_response(200)
        self.send_header("Content-Type", kind)
        self.send_header("Cache-Control", "private, max-age=604800")  # the URL changes with the picture
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def send_json(self, status: int, body) -> None:
        data = json.dumps(body, ensure_ascii=False).encode()
        if status >= 400:  # whatever the page shows as an error is in the log too
            who = self.headers.get("X-Remote-User-Name") or self.headers.get("X-Remote-User-Display-Name") or ""
            error = body.get("error") if isinstance(body, dict) else body
            log(f"{self.command} {self.path.split('?')[0]} -> {status}" + (f" ({who})" if who else "") + f": {error}")
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
            try:
                user = self.current_user()
            except (urllib.error.URLError, OSError, RuntimeError, ValueError):
                user = {**user, "is_admin": False}
            view = self.app.view(user)
            visible = view == "open"
            member = self.app.is_member(user["id"])
            # Before the admin opens ordering, nothing personal goes into the page, not even the nickname.
            phrase = self.app.page_phrase(user["id"]) if visible else None
            page = (
                PAGE.read_text()
                .replace("{{NAME}}", html.escape(self.app.nickname(user["id"], user["name"])) if visible else "")
                .replace("{{PHRASE}}", html.escape(phrase or ""))
                .replace("{{PHRASE_HIDDEN}}", "" if phrase else "hidden")
                .replace("{{VIEW}}", view)
                .replace("{{VISIBLE_HIDDEN}}", "" if visible else "hidden")
                .replace("{{CLOSED_HIDDEN}}", "" if view == "closed" else "hidden")
                .replace("{{TEST_HIDDEN}}", "" if view == "test" else "hidden")
                .replace("{{TEST_BANNER_HIDDEN}}", "" if user.get("is_admin") and self.app.settings.get("test_mode") else "hidden")
                .replace("{{NOT_MEMBER_HIDDEN}}", "" if view == "not_member" or (visible and not member) else "hidden")
                .replace("{{MEMBER_HIDDEN}}", "" if member and visible else "hidden")
            )
            data = page.encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        elif route.startswith("/photo/"):
            self.get_photo(route.removeprefix("/photo/"))
        elif route == "/api/me":
            self.guarded(self.get_me)
        elif route == "/api/status":
            self.guarded(self.get_status)
        elif route == "/api/wait":
            self.guarded(self.get_wait)
        elif route == "/api/menu":
            try:
                self.send_json(200, self.app.menu())
            except IdingError as exc:
                self.send_json(502, {"error": f"Menu se nepodařilo načíst: {exc}"})
        elif route == "/api/admin":
            self.guarded(self.get_admin, admin=True)
        elif route == "/api/admin/order":
            self.guarded(self.get_order, admin=True)
        elif route == "/api/admin/pickup_times":
            self.guarded(self.get_pickup_times, admin=True)
        else:
            self.send_error(404)

    def do_POST(self):
        if not self.allowed():
            return
        route = self.route()
        if route == "/api/choice":
            self.guarded(self.post_choice)
        elif route == "/api/admin/approve":
            self.guarded(self.post_approve, admin=True)
        elif route == "/api/admin/open":
            self.guarded(self.post_open, admin=True)
        elif route == "/api/admin/close":
            self.guarded(self.post_close, admin=True)
        elif route == "/api/admin/clear":
            self.guarded(self.post_clear, admin=True)
        elif route == "/api/admin/unlock":
            self.guarded(self.post_unlock, admin=True)
        elif route == "/api/admin/order":
            self.guarded(self.post_place_order, admin=True)
        elif route == "/api/admin/pay_again":
            self.guarded(lambda user: self.order_action(user, self.app.retry_payment), admin=True)
        elif route == "/api/admin/confirm_payment":
            self.guarded(lambda user: self.order_action(user, self.app.confirm_payment), admin=True)
        elif route == "/api/admin/reset_order":
            self.guarded(lambda user: self.order_action(user, lambda: self.app.reset_order(user["name"])), admin=True)
        elif route == "/api/admin/cancel_order":
            self.guarded(lambda user: self.order_action(user, self.app.cancel_order), admin=True)
        elif route == "/api/admin/test_notify":
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

    def get_wait(self, user: dict) -> None:
        """Long poll: answers {"v": version} once anything changed since ?v=, or after WAIT_SECONDS."""
        query = dict(p.partition("=")[::2] for p in self.path.partition("?")[2].split("&") if p)
        try:
            seen = int(query.get("v", "-1"))
        except ValueError:
            seen = -1
        self.send_json(200, {"v": self.app.wait_for_change(seen, WAIT_SECONDS)})

    def get_status(self, user: dict) -> None:
        """The ticker for everyone, plus the caller's own choice for today."""
        self.send_json(200, self.status(user))

    def status(self, user: dict) -> dict:
        view = self.app.view(user)
        if view != "open":  # ordering not started, test mode or not a member: nothing about anyone
            return {"view": view, "ticker": [], "mine": None, "previous": None, "locked": False,
                    "stage": None, "pickup": ""}
        with self.app.lock:
            mine = self.app.choices().get(user["id"])
            locked = self.app.is_locked()
            order = self.app.order or {}
        return {
            "view": view,
            "test_mode": bool(self.app.settings.get("test_mode")),
            "ticker": self.app.ticker(),
            "mine": mine,
            "previous": self.app.previous_choice(user["id"]) if self.app.is_member(user["id"]) else None,
            "locked": locked,
            # For the ticker: how far today's order got, and when it is picked up.
            "stage": order.get("stage"),
            "pickup": (order.get("target_time") or "")[-5:],
        }

    def post_choice(self, user: dict) -> None:
        """Save the caller's pick for today, or drop it with {"clear": true}, until the admin approves."""
        app = self.app
        view = app.view(user)
        if view == "test":
            self.send_json(409, {"error": "Doplněk je v testovacím režimu."})
            return
        if not app.is_member(user["id"]):
            self.send_json(403, {"error": "Vybírat můžou jen strávníci."})
            return
        if view != "open":
            self.send_json(409, {"error": "Objednávky ještě nejsou otevřené."})
            return
        body = self.read_json()
        body = body if isinstance(body, dict) else {}
        choice = None
        if not body.get("clear"):
            try:
                choice, error = app.check_choice(body)
            except IdingError as exc:
                self.send_json(502, {"error": f"Menu se nepodařilo načíst: {exc}"})
                return
            if not choice:
                self.send_json(400, {"error": error})
                return
        with app.lock:
            if app.is_locked():
                self.send_json(409, {"error": "Správce už objednávku uzavřel, výběr nejde změnit."})
                return
            if choice:
                app.choices()[user["id"]] = choice
            else:
                app.choices().pop(user["id"], None)
            app.save_choices()
        log(f"{user['name']}: " + ("výběr uložen." if choice else "výběr smazán (začít znovu)."))
        self.send_json(200, self.status(user))
        app.notify_admins_if_ready(user["id"])

    def get_order(self, user: dict) -> None:
        try:
            self.send_json(200, self.app.order_overview())
        except IdingError as exc:
            self.send_json(502, {"error": f"Menu se nepodařilo načíst: {exc}"})

    def post_approve(self, user: dict) -> None:
        try:
            self.app.approve(user["name"])
        except IdingError as exc:
            self.send_json(502, {"error": str(exc)})
            return
        except ValueError as exc:  # a pick the current menu no longer has
            self.send_json(409, {"error": f"Výběr nesedí na aktuální menu: {exc}"})
            return
        self.get_order(user)

    def post_open(self, user: dict) -> None:
        invite = self.app.open_ordering(user["name"])
        log(f"{user['name']} zahájil objednávání.")
        if invite:  # in the background: a slow phone must not hold up the page
            threading.Thread(target=self.app.invite_members, args=(user["id"],), daemon=True).start()
        else:
            log("Pozvánky se dnes už posílaly, znovu se neposílají.")
        self.get_order(user)

    def post_clear(self, user: dict) -> None:
        def clear() -> None:
            count = self.app.clear_choices()
            log(f"{user['name']} smazal všechny dnešní výběry ({count}).")

        self.order_action(user, clear)

    def post_close(self, user: dict) -> None:
        self.app.close_ordering()
        log(f"{user['name']} uzavřel objednávání.")
        self.get_order(user)

    def post_unlock(self, user: dict) -> None:
        self.order_action(user, self.app.unlock, f"{user['name']} objednávku znovu otevřel.")

    def get_pickup_times(self, user: dict) -> None:
        try:
            self.send_json(200, self.app.pickup_times())
        except IdingError as exc:
            self.send_json(502, {"error": f"Časy vyzvednutí se nenačetly: {exc}"})

    def post_place_order(self, user: dict) -> None:
        body = self.read_json()
        when = str((body or {}).get("target_time") or "")

        def place() -> None:
            offered = self.app.pickup_times()
            if not offered["day"] or when not in {f"{offered['day']} {t}" for t in offered["times"]}:
                first = offered["times"][0] if offered["times"] else ""
                raise IdingError("Tenhle čas už obchod nenabízí" + (f", nejdřív teď {first}" if first else "")
                                 + ". Časy jsou obnovené, vyber znovu.")
            try:
                self.app.place_order(user, when)
            except IdingError as exc:
                if "kód 2128" not in str(exc):  # 訂單準備時間不足: not enough time to prepare the order
                    raise
                raise IdingError("Obchod na tuhle objednávku potřebuje víc času na přípravu. "
                                 "Časy jsou obnovené, vyber pozdější.") from exc

        self.order_action(user, place)

    def order_action(self, user: dict, action, message: str = "") -> None:
        """Run an ordering step; iding failures go back to the page as they are."""
        try:
            action()
        except IdingError as exc:
            self.send_json(502, {"error": str(exc)})
            return
        if message:
            log(message)
        self.get_order(user)

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
                    "alert": app.settings.get("alerts", {}).get(user_id, ""),
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
            "ticker_chosen_phrases": app.settings["ticker_chosen_phrases"],
            "ticker_pending_phrases": app.settings["ticker_pending_phrases"],
            "notify_admin_ready": app.settings["notify_admin_ready"],
            "test_mode": bool(app.settings.get("test_mode")),
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
            for key in ("notification_phrases", "page_phrases", "ticker_chosen_phrases", "ticker_pending_phrases"):
                settings[key] = clean_lines(body.get(key))
            settings["notify_admin_ready"] = bool(body.get("notify_admin_ready"))
            if bool(body.get("test_mode")) != bool(settings.get("test_mode")):
                log("Testovací režim " + ("zapnut." if body.get("test_mode") else "vypnut."))
            settings["test_mode"] = bool(body.get("test_mode"))
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
        alerts = settings.setdefault("alerts", {})
        if not isinstance(body, dict):
            return
        allowed = valid_users | set(settings["members"])
        members = [m for m in body if m in allowed and isinstance(body[m], dict)]
        for gone in set(settings["members"]) - set(members):
            phones.pop(gone, None)
            nicknames.pop(gone, None)
            alerts.pop(gone, None)
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
            if entry.get("alert") in ALERT_DATA:
                alerts[user_id] = entry["alert"]
            else:
                alerts.pop(user_id, None)

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
        self.app.send_notification(service, self.app.notification_message(target["id"], target["name"]),
                                   who=f"test {target['name']}", level=str(body.get("alert") or ""))
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
    threading.Thread(target=keep_running(app.daily_loop), daemon=True).start()
    threading.Thread(target=keep_running(app.order_watch_loop), daemon=True).start()
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
