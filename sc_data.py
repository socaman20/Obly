"""
Star Citizen's lookup data: where to ask, and what the answer means.

The machinery is in voiceui/datacache.py -- caching, the fallback ladder, the
one-button refresh. This file is the part that knows what a commodity is.

SOURCES (surveyed 2026-09-04, see "Star Citizen Data Sources 2026-09-04.md")
---------------------------------------------------------------------------
PRIMARY  UEX Corp -- api.uexcorp.space/2.0
         The only source covering commodities, ship purchase AND rental prices
         and 826 terminals together. Sends Cache-Control: max-age=86400, so we
         cache for a day rather than polling.

BACKUP   star-citizen.wiki -- api.star-citizen.wiki/api/v2
         A genuinely independent second source, and the one Kabutopz's app
         uses. Only listed where it actually answers the same question; a
         "backup" that returns a different shape is worse than none.

NOT USED erkul.games -- their API replies "third-party access is not
         authorized". Reachable is not permitted.
         regolith.rocks -- shut down permanently 1 June 2026.

HONESTY
-------
UEX's own words: "Data is community-maintained and may not reflect live
servers." Every answer we show carries the game build it belongs to and how old
the copy is. Same reason our commands carry `verified: false` -- a confident
wrong answer costs a player a cargo hold.
"""
from __future__ import annotations

import os
import sys

# Self-bootstrapping: this module must import on its own, not only after
# gui.py has already put _shared on the path. Depending on another module's
# import side effect is the trap that bit gui.py the first time.
_SHARED = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "_shared"))
if os.path.isdir(os.path.join(_SHARED, "voiceui")) and _SHARED not in sys.path:
    sys.path.insert(0, _SHARED)

from voiceui.datacache import DAY, Endpoint    # noqa: E402

UEX = "https://api.uexcorp.space/2.0"
WIKI = "https://api.star-citizen.wiki/api/v2"

# Attribution UEX asks for, shown in the UI rather than buried in a licence.
ATTRIBUTION = "Trade data by UEX Corp (uexcorp.space) · community-maintained"
DISCLAIMER = ("Community-reported data. It may not match live servers, and it "
              "lags behind game patches.")

ENDPOINTS = [
    Endpoint("game_versions", "Game version",
             primary=f"{UEX}/game_versions", unwrap="data", max_age=DAY // 4),

    Endpoint("commodities", "Commodities",
             primary=f"{UEX}/commodities", unwrap="data"),

    # No wiki backup here on purpose: it answers the same question in a
    # different SHAPE (no `name_full`, different price linkage), so falling
    # back to it hands the UI rows it cannot read. A backup has to be
    # schema-compatible to be a backup.
    Endpoint("vehicles", "Ships and vehicles",
             primary=f"{UEX}/vehicles", unwrap="data"),

    Endpoint("vehicles_purchases_prices", "Ship purchase prices",
             primary=f"{UEX}/vehicles_purchases_prices", unwrap="data"),

    Endpoint("vehicles_rentals_prices", "Ship rental prices",
             primary=f"{UEX}/vehicles_rentals_prices", unwrap="data"),

    Endpoint("terminals", "Terminals and locations",
             primary=f"{UEX}/terminals", unwrap="data"),

    # 23,930 rows and a few MB. Cached like everything else, so the size is
    # paid once a day rather than on every question.
    Endpoint("items_prices_all", "Ship components and items",
             primary=f"{UEX}/items_prices_all", unwrap="data"),

    Endpoint("categories", "Item categories",
             primary=f"{UEX}/categories", unwrap="data"),

    # 2,593 rows: what every terminal buys and sells, at what price, with how
    # much stock. This is the whole basis of route planning.
    Endpoint("commodities_prices_all", "Commodity prices by terminal",
             primary=f"{UEX}/commodities_prices_all", unwrap="data"),
]

# UEX ships human-readable place names on every price row, so a location never
# has to be resolved from an id. Most specific first -- a player wants the shop
# name, and the planet only to know which one it is on.
PLACE_FIELDS = ("terminal_name", "city_name", "space_station_name",
                "outpost_name", "moon_name", "planet_name", "star_system_name")


def place_of(row) -> str:
    """"Astro Armada - Area 18, ArcCorp, Stanton" from a price row."""
    parts, seen = [], set()
    for f in ("terminal_name", "city_name", "space_station_name",
              "outpost_name", "moon_name", "planet_name", "star_system_name"):
        v = row.get(f)
        if v and v not in seen:
            seen.add(v)
            parts.append(v)
    return ", ".join(parts[:3]) if parts else "location unknown"


def game_version(cache) -> str:
    """The build UEX believes its data describes. Stamped onto every answer."""
    res = cache.get(ENDPOINTS[0])
    for row in res.rows:
        if isinstance(row, dict) and row.get("live"):
            return str(row["live"])
    return "unknown"


def find_ship(cache, query: str, limit: int = 8) -> list:
    """Name search over ships, with purchase and rental prices attached."""
    q = (query or "").strip().lower()
    if not q:
        return []

    ships = cache.get(ENDPOINTS[2]).rows
    buys = cache.get(ENDPOINTS[3]).rows
    rents = cache.get(ENDPOINTS[4]).rows

    hits = [s for s in ships
            if q in str(s.get("name_full") or s.get("name") or "").lower()][:limit]

    out = []
    for s in hits:
        sid = s.get("id")
        out.append({
            "name": s.get("name_full") or s.get("name"),
            "scu": s.get("scu"),
            # Where, and for how much -- a count of locations tells a player
            # nothing they can act on.
            "buy": [{"where": place_of(b), "price": b.get("price_buy") or 0}
                    for b in buys if b.get("id_vehicle") == sid],
            "rent": [{"where": place_of(r), "price": r.get("price_rent") or 0}
                     for r in rents if r.get("id_vehicle") == sid],
        })
        out[-1]["buy"].sort(key=lambda x: x["price"] or 9e9)
        out[-1]["rent"].sort(key=lambda x: x["price"] or 9e9)
    return out


def find_component(cache, query: str, limit: int = 10) -> list:
    """Ship components and items: what it is, where to buy it, what it costs.

    Answers "where do I get a better cooler" -- the question that follows
    "where do I buy the ship".
    """
    q = (query or "").strip().lower()
    if not q:
        return []

    prices = cache.get(ENDPOINTS[6]).rows
    cats = {c.get("id"): c for c in cache.get(ENDPOINTS[7]).rows}

    by_item = {}
    for row in prices:
        name = str(row.get("item_name") or "")
        cat = cats.get(row.get("id_category")) or {}
        cat_name = str(cat.get("name") or "")
        # A player types "cooler"; the parts are called Cryo-Star XL, FullFrost
        # and Gelid. Matching only the item name answers "nothing found" to a
        # perfectly reasonable question.
        if q not in name.lower() and q not in cat_name.lower()                 and q.rstrip("s") not in cat_name.lower():
            continue
        rec = by_item.setdefault(name, {
            "name": name,
            "category": cat_name,
            "section": cat.get("section", ""),
            "at": [],
        })
        if row.get("price_buy"):
            rec["at"].append({"where": row.get("terminal_name") or "unknown",
                              "price": row["price_buy"]})

    out = list(by_item.values())
    for r in out:
        r["at"].sort(key=lambda x: x["price"])
    out.sort(key=lambda r: (not r["at"], r["name"]))
    return out[:limit]


def find_commodity(cache, query: str, limit: int = 8) -> list:
    """Name search over commodities. `is_extractable` is the mining flag."""
    q = (query or "").strip().lower()
    if not q:
        return []
    rows = cache.get(ENDPOINTS[1]).rows
    hits = [c for c in rows if q in str(c.get("name", "")).lower()]
    hits.sort(key=lambda c: (not c.get("is_extractable"), c.get("name", "")))
    return hits[:limit]


# --------------------------------------------------------------- routes

def _terminal_index(cache):
    return {t.get("id"): t for t in cache.get(ENDPOINTS[8]).rows} if False         else {t.get("id"): t for t in cache.get(ENDPOINTS[5]).rows}


def _where(term) -> dict:
    """Flatten a terminal into the bits a player needs to fly there."""
    if not term:
        return {"name": "unknown", "system": "?", "body": ""}
    body = (term.get("city_name") or term.get("space_station_name")
            or term.get("outpost_name") or term.get("moon_name")
            or term.get("planet_name") or "")
    return {
        "name": term.get("name") or "unknown",
        "system": term.get("star_system_name") or "?",
        "body": body,
    }


def find_routes(cache, commodity="", from_system="", to_system="",
                cargo_scu=0, budget=0, limit=12) -> list:
    """Buy here, sell there. Ranked by what you actually make on the run.

    Profit is per SCU, then multiplied by whatever the run can really carry:
    the smaller of your hold, the stock on the shelf, and what your budget
    can afford. A route that shows a huge margin on two units in stock is a
    lie, and it is the most common way these tools mislead people.
    """
    rows = cache.get(ENDPOINTS[8]).rows
    terms = {t.get("id"): t for t in cache.get(ENDPOINTS[5]).rows}

    cq = (commodity or "").strip().lower()
    fs = (from_system or "").strip().lower()
    ts = (to_system or "").strip().lower()

    buys, sells = {}, {}
    for r in rows:
        name = str(r.get("commodity_name") or "")
        if cq and cq not in name.lower():
            continue
        term = terms.get(r.get("id_terminal"))
        sysname = str((term or {}).get("star_system_name") or "").lower()

        if r.get("price_buy") and r.get("scu_buy"):
            if not fs or fs in sysname:
                buys.setdefault(name, []).append((r, term))
        if r.get("price_sell"):
            if not ts or ts in sysname:
                sells.setdefault(name, []).append((r, term))

    out = []
    for name, blist in buys.items():
        for srow, sterm in sells.get(name, []):
            for brow, bterm in blist:
                margin = (srow.get("price_sell") or 0) - (brow.get("price_buy") or 0)
                if margin <= 0:
                    continue
                stock = brow.get("scu_buy") or 0
                units = stock
                if cargo_scu:
                    units = min(units, cargo_scu)
                if budget and brow.get("price_buy"):
                    units = min(units, int(budget // brow["price_buy"]))
                if units <= 0:
                    continue
                out.append({
                    "commodity": name,
                    "buy_price": brow.get("price_buy"),
                    "sell_price": srow.get("price_sell"),
                    "margin": margin,
                    "units": units,
                    "total": margin * units,
                    "stock": stock,
                    "frm": _where(bterm),
                    "to": _where(sterm),
                })

    # Best single run first. Same commodity from the same place appears once.
    out.sort(key=lambda r: -r["total"])
    seen, top = set(), []
    for r in out:
        k = (r["commodity"], r["frm"]["name"], r["to"]["name"])
        if k in seen:
            continue
        seen.add(k)
        top.append(r)
        if len(top) >= limit:
            break
    return top


def systems_with_positions(cache):
    """Star systems and their x/y/z, for drawing a route on a map.

    UEX carries no coordinates at all -- only hierarchy. star-citizen.wiki
    does, for 30 systems. So the galaxy view is real geometry; anything
    inside a system is a schematic, and should not pretend otherwise.
    """
    return cache.get(SYSTEM_MAP).rows


SYSTEM_MAP = Endpoint(
    "star_systems_map", "Star system positions",
    primary=f"{WIKI}/starsystems?limit=100", unwrap="data", max_age=DAY * 7)
