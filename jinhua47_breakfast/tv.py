"""The "Snídaně TV" dashboard in Home Assistant and the sensor it shows.

The add-on keeps sensor.jinhua47_breakfast up to date (state = how far today's order got, attributes =
what the dashboard shows) and creates the dashboard itself on start. Casting it (cast.show_lovelace_view)
is left to the user's own automations.
"""

ENTITY_ID = "sensor.jinhua47_breakfast"
DASHBOARD_PATH = "snidane-tv"  # Home Assistant wants a hyphen in a dashboard's url_path
VIEW_PATH = "stav"
# Bump when the layout below changes: the dashboard is rewritten once on the next start, unless the
# user removed MARKER from it (then it is theirs and stays as it is).
LAYOUT_VERSION = 1
MARKER = "jinhua47_breakfast_layout"
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

_E = f"{{% set e = '{ENTITY_ID}' %}}"

_HEADLINE_CARD = _E + """
<center>

# {{ state_attr(e, 'emoji') or '🥐' }} {{ state_attr(e, 'headline') or 'Snídaně' }}

## {{ state_attr(e, 'detail') or '' }}

{% for o in state_attr(e, 'earlier') or [] %}
{{ o.text }}

{% endfor %}
{% if state_attr(e, 'tip') %}
> 💡 {{ state_attr(e, 'tip') }}
{% endif %}
</center>
"""

_CHOSEN_CARD = _E + """
## ✅ Vybráno ({{ state_attr(e, 'chosen_count') or 0 }} z {{ state_attr(e, 'member_count') or 0 }})
{% for p in state_attr(e, 'picks') or [] %}
- **{{ p.name }}**: {{ p.text }}
{% else %}
Zatím nikdo.
{% endfor %}
"""

_PENDING_CARD = _E + """
## ⏳ Ještě nevybrali
{% for name in state_attr(e, 'pending') or [] %}
- {{ name }}
{% else %}
Všichni mají vybráno 🥳
{% endfor %}
"""

_ORDER_CARD = _E + """
## 🧾 Objednávka
{% for g in state_attr(e, 'groups') or [] %}
- {{ g.quantity }}× {{ g.text }}
{% endfor %}

**{{ state_attr(e, 'items') or 0 }} ks, {{ state_attr(e, 'total') or 0 }} NT$**
{%- if state_attr(e, 'ordered_by') %} · objednal(a) {{ state_attr(e, 'ordered_by') }}{% endif %}
"""


def _markdown(content: str) -> dict:
    return {"type": "markdown", "content": content.strip() + "\n"}


def _when(states: list[str], card: dict) -> dict:
    return {
        "type": "conditional",
        "conditions": [{"condition": "state", "entity": ENTITY_ID, "state": states}],
        "card": card,
    }


def dashboard_config() -> dict:
    """The dashboard: one full-screen view (good for casting) with the headline on top, below it who
    picked what while choosing, and what is ordered once approved."""
    return {
        MARKER: LAYOUT_VERSION,
        "title": "Snídaně TV",
        "views": [{
            "title": "Stav",
            "path": VIEW_PATH,
            "icon": "mdi:food-croissant",
            "type": "panel",
            "cards": [{
                "type": "vertical-stack",
                "cards": [
                    _markdown(_HEADLINE_CARD),
                    _when(["choosing"], {
                        "type": "horizontal-stack",
                        "cards": [_markdown(_CHOSEN_CARD), _markdown(_PENDING_CARD)],
                    }),
                    _when(["approved", "ordered", "awaiting_payment", "paid", "ready"], _markdown(_ORDER_CARD)),
                ],
            }],
        }],
    }


def ensure_dashboard(ws, log) -> None:
    """Create the dashboard when it is missing and write its layout when it is new or older than
    LAYOUT_VERSION. ws(*commands) runs websocket commands (raises RuntimeError on failure)."""
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
