"""The part of the 金華47 menu the breakfast page offers: every set (套餐) and a few drinks.

The iding menu is one big normalized document (entrees, collections, options and
option items referring to each other by index). build_menu() picks out what the
page needs and keeps the indexes; cart_items() turns saved choices back into
iding cart items.
"""

STORE = "af0f1c4c"

SET_SUBCATEGORY = "套餐"
MAIN_COLLECTION = "主餐"
DRINK_COLLECTION = "飲料"

# Drinks offered with a set, in the order the page lists them: {Chinese name: (label, what it is)}.
DRINKS = {
    "紅茶": ("Black tea", "černý čaj"),
    "檸檬紅茶": ("Lemon black tea", "černý čaj s citronem"),
    "奶茶": ("Milk tea", "černý čaj s mlékem"),
    "無糖綠茶": ("Sugar free green tea", "zelený čaj bez cukru"),
    "冬瓜茶": ("Winter melon tea", "sladký nápoj z voskové tykve, jen studený"),
    "冬瓜綠茶": ("Winter melon green tea", "zelený čaj s voskovou tykví, jen studený"),
    "冬瓜檸檬": ("Winter melon lemon", "nápoj z voskové tykve s citronem"),
    "可樂": ("Coke", "Coca-Cola"),
    "鮮奶(冰)": ("Fresh milk", "čerstvé mléko, jen studené"),
}

# Czech names of the sets; a set missing here shows its Chinese name.
SET_LABELS = {
    "雞腿套餐": "Kuřecí stehno",
    "吃飽飽套餐": "Velký sytý set",
    "中式套餐": "Čínský set",
    "樂活套餐": "Lehký set",
    "兒童套餐": "Dětský set",
    "黑豬丹麥套餐": "Dánský toast s vepřovým",
    "法式套餐": "Francouzský toast",
    "牛肉堡套餐": "Hovězí burger",
    "軟法套餐": "Bageta s omeletou",
    "蘑菇麵套餐": "Nudle s houbovou omáčkou",
    "黑胡椒套餐": "Nudle s černým pepřem",
    "炸醬麵套餐": "Nudle zhajiang",
    "炸醬麵(小)套餐": "Nudle zhajiang, malé",
}

# Sets shown first, in the section "Oblíbené" (in this order).
FAVORITES = ("黑豬丹麥套餐", "炸醬麵套餐", "法式套餐")

# Parts of the set descriptions on iding ("自製雞腿+蒜香軟法+時蔬"); an unknown part stays in Chinese.
CONTENTS = {
    "自製雞腿": "domácí kuřecí stehno",
    "蒜香軟法": "česneková bageta",
    "時蔬": "zelenina",
    "炸醬麵加蛋": "nudle zhajiang s vejcem",
    "薄皮豬排": "tenký vepřový řízek",
    "蘿蔔糕": "ředkvový koláč",
    "蔥蛋": "omeleta s jarní cibulkou",
    "起司": "sýr",
    "豬排": "vepřový řízek",
    "薯餅起司蛋": "bramborák se sýrem a vejcem",
    "生菜沙拉(小)": "malý salát",
    "二個餐包": "dvě housky",
    "薯條": "hranolky",
    "四塊雞塊": "4 kuřecí nugetky",
    "草莓吐司": "toast s jahodovou marmeládou",
    "黑胡椒豬排丹麥土司": "dánský toast s vepřovým řízkem na černém pepři",
    "起司法式吐司": "francouzský toast se sýrem",
    "玉米蛋生菜沙拉": "salát s kukuřicí a vejcem",
    "牛肉堡抹花生": "hovězí burger s arašídovým máslem",
    "歐姆蛋軟法": "bageta s omeletou",
    "酥炸杏鮑菇": "smažené hlívy",
    "蘑菇麵": "nudle s houbovou omáčkou",
    "黑胡椒麵": "nudle s černým pepřem",
    "炸醬麵": "nudle zhajiang",
    "小炸醬麵": "malé nudle zhajiang",
    "蛋": "vejce",
}


def contents(note: str | None) -> str:
    """Czech version of an iding set description, part by part."""
    parts = [p.strip() for p in (note or "").replace("＋", "+").split("+") if p.strip()]
    return ", ".join(CONTENTS.get(p, p) for p in parts)


# Drink options: temperature 溫度 (cold = 冰 iced, hot = 溫 warm, the one before 熱 hot)
# and size 容量 (small = 中, large = 大).
TEMPERATURE = ("溫度", {"iced": "冰", "hot": "溫"})
SIZE = ("容量", {"small": "中", "large": "大"})


def build_menu(raw: dict, inventory: list | None = None) -> dict:
    """Sets and drinks from an /api/stores/menus response (+ /api/stores/inventories)."""
    menu = raw if "entrees" in raw else raw.get("data") or {}
    entrees = {e["index"]: e for e in menu.get("entrees", [])}
    collections = {c["index"]: c for c in menu.get("collections", [])}
    options = {o["index"]: o for o in menu.get("options", [])}
    items = {i["index"]: i for i in menu.get("option_items", [])}
    sold_out = {i.get("index") for i in inventory or [] if i.get("status") == -1}

    def choice(entree: dict, spec: tuple) -> dict | None:
        """{key: {option, item, price} or None} for one option group; None without the group."""
        option_name, wanted = spec
        group = next(
            (options[o] for o in entree.get("option_indexes", []) if options.get(o, {}).get("name") == option_name),
            None,
        )
        if group is None:
            return None
        by_name = {items[i]["name"]: items[i] for i in group.get("option_item_indexes", []) if i in items}
        return {
            key: {"option": group["index"], "item": by_name[name]["index"], "price": by_name[name].get("price") or 0}
            if name in by_name else None
            for key, name in wanted.items()
        }

    drinks: dict[int, dict] = {}
    sets = []
    subcategory = next((s for s in menu.get("subcategories", []) if s.get("name") == SET_SUBCATEGORY), {})
    for index in subcategory.get("entree_indexes", []):
        combo = entrees.get(index)
        if not combo or combo.get("disabled") or not combo.get("collection_indexes"):
            continue  # the set's main dish entry, not the set itself
        groups = {collections[c]["name"]: collections[c] for c in combo["collection_indexes"] if c in collections}
        main, drink = groups.get(MAIN_COLLECTION), groups.get(DRINK_COLLECTION)
        if not main or not drink:
            continue
        offered = []
        for drink_index in drink.get("entree_indexes", []):
            entree = entrees.get(drink_index) or {}
            if entree.get("name") not in DRINKS or entree.get("disabled"):
                continue
            offered.append(drink_index)
            if drink_index not in drinks:
                temperature = choice(entree, TEMPERATURE)
                drinks[drink_index] = {
                    "index": drink_index,
                    "name": entree["name"],
                    "label": DRINKS[entree["name"]][0],
                    "contents": DRINKS[entree["name"]][1],
                    "extra": entree.get("price_in_collection") or 0,  # added to the set price
                    # No temperature option at all (fresh milk): always cold, nothing to send.
                    "temperature": temperature or {"iced": None, "hot": None},
                    "hot": bool(temperature and temperature["hot"]),
                    "sizes": choice(entree, SIZE) or {"small": None, "large": None},
                    "sold_out": drink_index in sold_out,
                }
        main_index = main.get("default_entree_index")
        sets.append({
            "index": index,
            "name": combo["name"],
            "label": SET_LABELS.get(combo["name"], combo["name"]),
            "contents": contents(combo.get("photo_note")),
            "favorite": combo["name"] in FAVORITES,
            "price": combo.get("price") or 0,
            "main": {"collection": main["index"], "entree": main_index},
            "drink_collection": drink["index"],
            "drinks": offered,
            "sold_out": index in sold_out or main_index in sold_out,
        })

    order = list(DRINKS)
    return {
        "store": STORE,
        "menu_uuid": menu.get("uuid"),
        "version": menu.get("version"),
        # Favorites first in FAVORITES order, the rest as on iding (sort is stable).
        "sets": sorted(sets, key=lambda s: FAVORITES.index(s["name"]) if s["favorite"] else len(FAVORITES)),
        "drinks": sorted(drinks.values(), key=lambda d: order.index(d["name"])),
    }


def cart_items(raw: dict, picks: list[tuple[dict, int]]) -> tuple[list[dict], int]:
    """iding cart items for [(choice, quantity)] and our total, from the raw menu.

    Shaped like the items the iding.tw site sends when adding a set: every option of
    the main dish and the drink is listed, at its default unless it is the chosen
    temperature or size. Raises ValueError when a pick no longer fits the menu.
    """
    menu = raw if "entrees" in raw else raw.get("data") or {}
    uuid = menu.get("uuid")
    entrees = {e["index"]: e for e in menu.get("entrees", [])}
    collections = {c["index"]: c for c in menu.get("collections", [])}
    options = {o["index"]: o for o in menu.get("options", [])}
    items = {i["index"]: i for i in menu.get("option_items", [])}

    def ref(index: int, name: str) -> dict:
        return {"index": index, "menu_uuid": uuid, "name": name}

    def entree_options(entree: dict, wanted: dict[str, str]) -> tuple[list[dict], int]:
        """All options of an entree at their defaults, except wanted {option name: item name}."""
        chosen, extra = [], 0
        for option_index in entree.get("option_indexes", []):
            option = options.get(option_index)
            if not option:
                continue
            group = [items[i] for i in option.get("option_item_indexes", []) if i in items]
            if option["name"] in wanted:
                item = next((i for i in group if i["name"] == wanted[option["name"]]), None)
                if not item:
                    raise ValueError(f"{entree['name']}: volba {option['name']} {wanted[option['name']]} v menu není")
            else:
                item = items.get(option.get("default_option_index")) or (group[0] if group else None)
            if item:
                chosen.append({**ref(option["index"], option["name"]), "option_item": ref(item["index"], item["name"])})
                extra += item.get("price") or 0
        return chosen, extra

    def cart_entree(entree: dict, options_: list[dict], quantity: int) -> dict:
        price = entree.get("price") or 0
        return {
            **ref(entree["index"], entree["name"]),
            "entree_enable_point_redeem": 0, "entree_point_discount": 0, "entree_point_redeem": 0,
            "exclude_order_point_gain": 0, "isCartSimpleItem": False, "memo": "",
            "options": options_, "quantity": quantity, "subtotal": price, "total": price * quantity,
        }

    result, total = [], 0
    for choice, quantity in picks:
        combo = entrees.get(choice["set"])
        if not combo:
            raise ValueError("set už v menu není")
        groups = {collections[c]["name"]: collections[c] for c in combo.get("collection_indexes", []) if c in collections}
        main_group, drink_group = groups.get(MAIN_COLLECTION), groups.get(DRINK_COLLECTION)
        drink = entrees.get(choice["drink"])
        if not main_group or not drink_group or not drink or drink["index"] not in drink_group.get("entree_indexes", []):
            raise ValueError(f"{combo['name']}: pití k setu už v menu není")
        main = entrees[main_group["default_entree_index"]]
        main_options, main_extra = entree_options(main, {})
        wanted = {SIZE[0]: SIZE[1][choice["size"]]}
        if any(options.get(o, {}).get("name") == TEMPERATURE[0] for o in drink.get("option_indexes", [])):
            wanted[TEMPERATURE[0]] = TEMPERATURE[1][choice["temp"]]
        drink_options, drink_extra = entree_options(drink, wanted)
        subtotal = (combo.get("price") or 0) + (drink.get("price_in_collection") or 0) + main_extra + drink_extra
        result.append({
            **ref(combo["index"], combo["name"]),
            "entree_enable_point_redeem": 0, "entree_point_discount": 0, "entree_point_redeem": 0,
            "exclude_order_point_gain": 0,
            "collections": [
                {**ref(main_group["index"], main_group["name"]), "quantity": quantity,
                 "entree": cart_entree(main, main_options, quantity)},
                {**ref(drink_group["index"], drink_group["name"]), "quantity": quantity,
                 "entree": cart_entree(drink, drink_options, quantity)},
            ],
            "isCartSimpleItem": False, "memo": "", "quantity": quantity,
            "subtotal": subtotal, "total": subtotal * quantity, "upgrade": False,
        })
        total += subtotal * quantity
    return result, total


def describe(menu: dict, choice: dict) -> dict:
    """{"set", "drink", "text", "price"} for a saved choice, using the page menu from build_menu()."""
    chosen_set = next((s for s in menu["sets"] if s["index"] == choice["set"]), None)
    drink = next((d for d in menu["drinks"] if d["index"] == choice["drink"]), None)
    if not chosen_set or not drink:
        return {"text": "položka už v menu není", "price": 0}
    size = drink["sizes"].get(choice["size"]) or {}
    temp = "teplé" if choice["temp"] == "hot" else "studené"
    size_name = "velké" if choice["size"] == "large" else "malé"
    return {
        "set": chosen_set["label"],
        "drink": f"{drink['label']}, {temp}, {size_name}",
        "text": f"{chosen_set['label']} + {drink['label']}, {temp}, {size_name}",
        "price": chosen_set["price"] + drink["extra"] + (size.get("price") or 0),
    }
