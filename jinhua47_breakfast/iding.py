"""Minimal client for the iding.tw web API (the same JSON calls the iding.tw site makes).

The API is not public: request shapes come from a recording of the site, so
expect them to change without notice. The session is a cookie set by login.
"""

import json
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
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
            raw_error = exc.read() or b""
            where = f"{method} {path.partition('?')[0]}"
            # The whole reply goes to the log: iding's short message rarely says which field it dislikes.
            print(f"iding {where} -> {exc.code}: {raw_error[:1000].decode(errors='replace')}", flush=True)
            raise IdingError(f"iding ({where}) odpověděl chybou {exc.code}: {error_message(raw_error, exc.reason)}") from exc
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

    def menu(self, store: str) -> dict:
        """The store's whole menu (public, no login needed)."""
        return self.call("GET", f"/api/stores/menus?identifier={store}&order_type=0") or {}

    def inventories(self, store: str) -> list:
        """Stock per entree; status -1 means sold out (public)."""
        result = self.call("GET", f"/api/stores/inventories?identifier={store}")
        return result if isinstance(result, list) else []

    def pickup_windows(self, store: str, total: int = 0) -> list[tuple[str, str, str]]:
        """Take-out windows the store offers as (day, first, last), e.g. ("2026-11-24", "10:25", "12:44").

        total is the cart total in NT$, as the site sends it: a bigger order needs longer to prepare,
        so the first time comes later (0 gives the times for the smallest order)."""
        result = self.call("POST", "/api/stores/avail_times", {"data": {"identifier": store, "total": total}}) or {}
        windows = []
        for slot in result.get("0") or []:  # order type 0 = take-out; "2026-11-24#10:25#12:44"
            day, first, last, *_ = f"{slot}###".split("#")
            if day and first and last:
                windows.append((day, first, last))
        return windows

    def first_pickup_time(self, store: str, total: int = 0) -> str | None:
        """The earliest take-out time the store offers for a cart of total NT$, as "YYYY-MM-DD HH:MM"."""
        windows = self.pickup_windows(store, total)
        return f"{windows[0][0]} {windows[0][1]}" if windows else None

    def cart(self, store: str) -> list[dict]:
        """The cart's items as iding stores them (logged in)."""
        return (self.call("GET", f"/api/carts/{store}") or {}).get("items") or []

    def place_order(self, store: str, check: dict, target_time: str, menu_version) -> dict:
        """Send the order (logged in), unpaid, to be paid with LINE Pay.

        `check` is the /api/orders/check answer for the same cart and time: the site sends
        its cart and the account's e-invoice carrier back as they are.
        """
        return self.call("POST", "/api/orders", {
            "identifier": store,
            "cart": check.get("cart") or [],
            "coupons": [],
            "menu_version": menu_version,
            "order_type": 0,
            "payment_type": 6,
            "point_redeem": 0,
            "carrier": (check.get("user") or {}).get("carrier"),
            "target_time": target_time,
        }) or {}

    def line_pay_reserve(self, store: str, order: dict, carrier) -> dict:
        """Ask LINE Pay for a payment of the order: payment_url_app/web, bank_transaction_id."""
        item_name = order["item_name"]
        # The site encodes the order id twice in confirm_url ('#' -> %2523).
        twice = urllib.parse.quote(urllib.parse.quote(item_name, safe=""), safe="")
        result = self.call("POST", "/api/payment/line_pay", {
            "identifier": store,
            "cancel_url": f"{BASE}/store/{store}?cart=true",
            "carrier": carrier,
            "confirm_url": f"{BASE}/store/{store}/line_pay?order_id={twice}"
                           f"&redirect_to={urllib.parse.quote(f'/store/{store}', safe='')}",
            "order_id": item_name,
        }) or {}
        reserve = result.get("reserve") or {}
        if reserve.get("status") != 0 or not reserve.get("bank_transaction_id"):
            raise IdingError(f"LINE Pay platbu nepřipravil: {reserve.get('message') or result}")
        return reserve

    def line_pay_confirm(self, store: str, item_name: str, bank_transaction_id: str) -> dict:
        """Finish a LINE Pay payment the payer approved; payment_status 2 = paid."""
        return self.call("POST", "/api/payment/line_pay_confirm", {
            "identifier": store,
            "order_id": item_name,
            "bank_transaction_id": bank_transaction_id,
        }) or {}

    def cancel_order(self, order_id: int) -> None:
        """Cancel an order (the site's cancelOrder); meant for unpaid ones."""
        self.call("DELETE", f"/api/orders/{order_id}")

    def order_status(self, order_id: int) -> dict | None:
        """The order from the account's history (in progress first): order_status, order_number..."""
        for status_filter in ("in_progress", "completed"):
            result = self.call(
                "GET", f"/api/orders/histories?page=1&per_page=30&status_filter={status_filter}"
            ) or {}
            for order in result.get("results") or []:
                if order.get("id") == order_id:
                    return order
        return None

    def set_cart(self, store: str, items: list[dict], menu_sha1: str) -> list[dict]:
        """Replace the whole cart (logged in); returns the items as iding stored them.

        Like the site, send the whole cart object: besides the items iding wants the
        menu's sha1, the quantity per set and the total, or it answers 傳入參數錯誤.
        """
        selected: dict[str, int] = {}
        for item in items:
            selected[str(item["index"])] = selected.get(str(item["index"]), 0) + item["quantity"]
        result = self.call("PATCH", f"/api/carts/{store}", {
            "items": items,
            "selected_entree_map": selected,
            "total": sum(item["total"] for item in items),
            "menu_version": None,
            "sha1": menu_sha1,
            "modify_time": datetime.now().astimezone().isoformat(timespec="seconds"),
        }) or {}
        return result.get("items") or []

    def check_order(self, store: str, cart: list[dict], target_time: str, menu_version) -> dict:
        """iding's own price for the cart (logged in); places nothing."""
        result = self.call("POST", "/api/orders/check", {
            "identifier": store,
            "cart": cart,
            "order_type": 0,  # take-out
            "target_time": target_time,
            "menu_version": menu_version,
            "payment_type": 6,  # LINE Pay
            "point_redeem": 0,
        }) or {}
        return result.get("data", result) if isinstance(result, dict) else {}


def error_message(raw: bytes, reason: str) -> str:
    try:
        body = json.loads(raw or b"{}")
    except ValueError:
        return reason or ""
    if isinstance(body, dict):
        # iding puts its own error code in data.status (e.g. 1172, 5013); the message may be just "Server Error".
        code = body.get("data", {}).get("status") if isinstance(body.get("data"), dict) else None
        for key in ("message", "msg", "detail", "error"):
            if body.get(key) and body[key] is not True:
                return str(body[key]) + (f" (kód {code})" if code is not None else "")
    return json.dumps(body, ensure_ascii=False)[:200]
