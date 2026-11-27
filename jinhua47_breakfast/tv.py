"""The "Snídaně TV" dashboard in Home Assistant and the sensor it shows.

The add-on keeps sensor.jinhua47_breakfast up to date (state = how far today's order got, attributes =
what the dashboard shows) and creates the dashboard itself on start. Casting it (cast.show_lovelace_view)
is left to the user's own automations.

The progress bar is a small custom card (progress-card.js), registered as a dashboard resource with
the script itself in a data: URL. So it needs no file in Home Assistant's config (no access to it), and
a Chromecast loads it like any other resource (it could not load it through the add-on's ingress).
"""

import base64
from pathlib import Path

ENTITY_ID = "sensor.jinhua47_breakfast"
DASHBOARD_PATH = "snidane-tv"  # Home Assistant wants a hyphen in a dashboard's url_path
VIEW_PATH = "stav"
# Bump when the layout below changes: the dashboard is rewritten once on the next start, unless the
# user removed MARKER from it (then it is theirs and stays as it is).
LAYOUT_VERSION = 5
MARKER = "jinhua47_breakfast_layout"
MEDIA_PLAYER = "media_player.spotify_david_rothbauer"  # media-control card at the bottom
WEATHER = "weather.home"  # weather-forecast card at the bottom left
CARD_SOURCE = Path(__file__).parent / "progress-card.js"
CARD_TYPE = "custom:jinhua47-progress-card"
WHITE_THEME_TYPE = "custom:jinhua47-white-theme"  # also in progress-card.js
# Our resource is recognised by this prefix (the card= parameter is ignored by browsers).
CARD_URL_PREFIX = "data:text/javascript;charset=utf-8;card=jinhua47-progress-card;base64,"
STATE_REFRESH_SECONDS = 60  # also re-creates the sensor soon after Home Assistant restarts and forgets it

# state: (emoji, headline)
HEADLINES = {
    "idle": ("😴", "Objednávání ještě nezačalo"),
    "choosing": ("🍳", "Vybírá se snídaně"),
    "approved": ("🔒", "Výběr je uzavřený"),
    "ordered": ("🧾", "Objednáno, čeká se na zaplacení"),
    "awaiting_payment": ("🧾", "Objednáno, čeká se na zaplacení"),
    "paid": ("✅", "Zaplaceno"),
    "ready": ("🎉", "Připraveno k vyzvednutí!"),
    "closed": ("😋", "Vyzvednuto, dobrou chuť"),
    "cancelled": ("❌", "Objednávka je zrušená"),
}

# The progress bar's steps; each is green once reached, grey until then.
STEPS = ("Otevřeno", "Uzavřeno", "Objednáno", "K vyzvednutí")
ORDER_SENT = ("ordered", "awaiting_payment", "paid", "ready", "closed")


def _when_text(stamp: str) -> dict:
    """{"date": "MM/DD", "time": "HH:MM"} from "YYYY-MM-DD HH:MM"."""
    if len(stamp) < 16:
        return {"date": "", "time": ""}
    return {"date": f"{stamp[5:7]}/{stamp[8:10]}", "time": stamp[11:16]}


def progress_steps(day: str, opened: dict | None, approved: dict | None, order: dict) -> tuple[list[dict], str]:
    """Today's progress bar: [{label, done, date, time}] (empty before ordering opens), and
    "MM/DD HH:MM" when the order was cancelled. day is today ("YYYY-MM-DD"); opened and approved
    carry only "HH:MM". A step reached without a known time (e.g. picked up without being marked
    ready first, or ordering closed again after approval) is done without a time."""
    stage = order.get("stage")
    times = order.get("stage_times") or {}
    if stage == "cancelled":
        when = _when_text(times.get("cancelled", ""))
        return [], f"{when['date']} {when['time']}".strip()
    ordered_at = times.get("ordered") or (f"{day} {order['at']}" if order.get("at") else "")
    reached = (
        (bool(opened or approved or stage), f"{day} {opened['at']}" if (opened or {}).get("at") else ""),
        (bool(approved or stage), f"{day} {approved['at']}" if (approved or {}).get("at") else ""),
        (stage in ORDER_SENT, ordered_at),
        (stage in ("ready", "closed"), times.get("ready") or times.get("closed") or ""),
    )
    if not reached[0][0]:
        return [], ""
    return [
        {"label": label, "done": done, **_when_text(at if done else "")}
        for label, (done, at) in zip(STEPS, reached)
    ], ""


_E = f"{{% set e = '{ENTITY_ID}' %}}"

_HEADLINE_CARD = _E + """
<center>

### {{ now().strftime('%H:%M') }} · {{ ['pondělí', 'úterý', 'středa', 'čtvrtek', 'pátek', 'sobota', 'neděle'][now().weekday()] }} {{ now().day }}. {{ now().month }}.

# {{ state_attr(e, 'emoji') or '🥐' }} {{ state_attr(e, 'headline') or 'Snídaně' }}

{% if state_attr(e, 'detail') %}
## {{ state_attr(e, 'detail') }}
{% endif %}

</center>
"""

_CHOSEN_CARD = _E + """
## Mají vybráno
{% for p in state_attr(e, 'picks') or [] %}
- **{{ p.name }}**: {{ p.short or p.text }}
{% else %}
Zatím nikdo.
{% endfor %}
"""

# The names on one large line: what people look for on the TV from across the room, in little height.
_PENDING_CARD = _E + """
## Ještě nevybrali
{% if state_attr(e, 'pending') %}
### {{ state_attr(e, 'pending') | join(', ') }}
{% else %}
Všichni mají vybráno 🥳
{% endif %}
"""

# Who has what, so everyone finds their own breakfast at pickup.
_ORDER_CARD = _E + """
## Objednávka
{% for p in state_attr(e, 'picks') or [] %}
- **{{ p.name }}**: {{ p.text }}
{% endfor %}

**{{ state_attr(e, 'items') or 0 }} ks, {{ state_attr(e, 'total') or 0 }} NT$**
"""


def _markdown(content: str, **options) -> dict:
    return {"type": "markdown", "content": content.strip() + "\n", **options}


def _when(states: list[str], card: dict) -> dict:
    return {
        "type": "conditional",
        "conditions": [{"condition": "state", "entity": ENTITY_ID, "state": states}],
        "card": card,
    }


def _shown(entity: str, card: dict) -> dict:
    """The card, hidden rather than a warning on the TV while its entity is unavailable (e.g. Spotify
    logged out)."""
    return {
        "type": "conditional",
        "conditions": [{"condition": "state", "entity": entity, "state_not": ["unavailable", "unknown"]}],
        "card": card,
    }


def dashboard_config() -> dict:
    """The dashboard, for a 16:9 screen (a Chromecast renders it at about 1280×720): one full-screen
    view in two columns. Left: the time, how far the order got, the progress bar and the weather. Right:
    who picked what while choosing, what is ordered once approved, and the music player below."""
    left = [
        _markdown(_HEADLINE_CARD),
        _when(["choosing", "approved", *ORDER_SENT],  # cancelled: the headline says it
              {"type": CARD_TYPE, "entity": ENTITY_ID}),
        _shown(WEATHER, {
            "type": "weather-forecast",
            "entity": WEATHER,
            "show_current": True,
            "show_forecast": True,
            "forecast_type": "hourly",
            "forecast_slots": 12,
        }),
    ]
    right = [
        _when(["choosing"], {
            "type": "vertical-stack",
            "cards": [_markdown(_CHOSEN_CARD), _markdown(_PENDING_CARD)],
        }),
        _when(["approved", "ordered", "awaiting_payment", "paid", "ready"], _markdown(_ORDER_CARD)),
        _shown(MEDIA_PLAYER, {"type": "media-control", "entity": MEDIA_PLAYER}),
        {"type": WHITE_THEME_TYPE},  # invisible: forces white over the HA theme
    ]
    return {
        MARKER: LAYOUT_VERSION,
        "title": "Snídaně TV",
        "views": [{
            "title": "Stav",
            "path": VIEW_PATH,
            "icon": "mdi:food-croissant",
            "type": "panel",
            "background": "#ffffff",  # all white on the TV (the default theme's page is light grey)
            "cards": [{
                "type": "horizontal-stack",
                "cards": [
                    {"type": "vertical-stack", "cards": left},
                    {"type": "vertical-stack", "cards": right},
                ],
            }],
        }],
    }


def ensure_dashboard(ws, log) -> None:
    """Create the dashboard when it is missing and write its layout when it is new or older than
    LAYOUT_VERSION, then register the progress card. ws(*commands) runs websocket commands
    (raises RuntimeError on failure)."""
    ensure_layout(ws, log)
    try:  # Home Assistant answered above, so a failure here is not worth retrying
        register_card(ws, log)
    except (OSError, RuntimeError) as exc:
        log(f"Kartu stavu objednávky se nepodařilo zaregistrovat: {exc}")


def register_card(ws, log) -> None:
    """Register progress-card.js as a dashboard resource (a data: URL holding the script), or update
    it when the card changed in a new version."""
    url = CARD_URL_PREFIX + base64.b64encode(CARD_SOURCE.read_bytes()).decode()
    (resources,) = ws({"type": "lovelace/resources"})
    mine = next((r for r in resources if str(r.get("url", "")).startswith(CARD_URL_PREFIX)), None)
    if mine is None:
        ws({"type": "lovelace/resources/create", "res_type": "module", "url": url})
        log("Karta stavu objednávky zaregistrována jako zdroj dashboardů.")
    elif mine.get("url") != url:
        ws({"type": "lovelace/resources/update", "resource_id": mine["id"], "res_type": "module", "url": url})
        log("Karta stavu objednávky aktualizována.")


def ensure_layout(ws, log) -> None:
    """The dashboard and its layout (see ensure_dashboard)."""
    (dashboards,) = ws({"type": "lovelace/dashboards/list"})
    if not any(d.get("url_path") == DASHBOARD_PATH for d in dashboards):
        ws({
            "type": "lovelace/dashboards/create",
            "url_path": DASHBOARD_PATH,
            "title": "Snídaně TV",
            "icon": "mdi:television",
            "show_in_sidebar": True,
            "require_admin": False,
        })
        log(f"Dashboard /{DASHBOARD_PATH} založen.")
    try:
        (current,) = ws({"type": "lovelace/config", "url_path": DASHBOARD_PATH})
    except RuntimeError as exc:
        if "config_not_found" not in str(exc):
            raise
        current = None
    marker = current.get(MARKER) if isinstance(current, dict) else None
    if current is not None and marker is None:
        log(f"Dashboard /{DASHBOARD_PATH} nemá značku {MARKER}, je upravený ručně: nechávám ho, jak je.")
        return
    if current is not None and isinstance(marker, int) and marker >= LAYOUT_VERSION:
        log(f"Dashboard /{DASHBOARD_PATH} je aktuální (rozvržení {marker}).")
        return
    ws({"type": "lovelace/config/save", "url_path": DASHBOARD_PATH, "config": dashboard_config()})
    log(f"Dashboard /{DASHBOARD_PATH} zapsán (rozvržení {LAYOUT_VERSION}); "
        f"k castování: dashboard_path {DASHBOARD_PATH}, view_path {VIEW_PATH}.")
