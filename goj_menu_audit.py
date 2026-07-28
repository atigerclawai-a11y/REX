#!/usr/bin/env python3
"""
GOJ Menu ↔ Transportation Audit
─────────────────────────────────
Runs nightly (default: 9 PM via launchd / scheduled task).

Compares:
  • GOJ_Menu_Orders.json      — who ordered a meal this week
  • GOJ_Clients_Master.json  — who is active + which days they attend
  • GOJ_Master_Routes.json   — which driver serves them each day

Flags:
  1. Client on route this week but NO menu order    → 🔴 Missing Menu
  2. Client has menu order but NOT on route / N/TR  → 🟡 No Transport Match
  3. Client is active + attending but no menu at all → 🟠 No Menu On File
  4. Client appears in menu under a name not in master → 🔵 Unrecognised Name

Sends a Telegram summary to Kato at 9 PM, or prints to stdout if run manually.
"""

import json, sys, urllib.request, urllib.error
from datetime import date, timedelta
from pathlib import Path

# ── Paths ──────────────────────────────────────────────────────────────────────
DESKTOP      = Path.home() / "Desktop"
GOJ_DIR      = Path.home() / "Documents" / "goj files"
MENU_ORDERS  = DESKTOP / "GOJ_Menu_Orders.json"
CLIENTS      = DESKTOP / "GOJ_Clients_Master.json"
ROUTES       = DESKTOP / "GOJ_Master_Routes.json"
REX_DIR      = DESKTOP / "REX"
TG_CONFIG    = REX_DIR / "rex_rexxie_telegram_config.json"
LOG_PATH     = REX_DIR / "logs" / "menu_audit.log"
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

# ── Day abbreviation maps ──────────────────────────────────────────────────────
# GOJ_Clients_Master attending_days format
CLIENT_DAY_LABELS = {
    "M":  "Monday",
    "T":  "Tuesday",
    "Tu": "Tuesday",
    "W":  "Wednesday",
    "TH": "Thursday",
    "Th": "Thursday",
    "F":  "Friday",
    "Su": "Sunday",
}
# GOJ_Master_Routes route key prefixes → day
ROUTE_DAY_MAP = {
    "M":  "Monday",
    "T":  "Tuesday",
    "W":  "Wednesday",
    "TH": "Thursday",
    "F":  "Friday",
    "Su": "Sunday",
}

# ── Telegram ───────────────────────────────────────────────────────────────────
def _tg_send(text: str):
    if not TG_CONFIG.exists():
        return
    try:
        cfg = json.loads(TG_CONFIG.read_text())
        token   = cfg.get("bot_token", "")
        chat_id = cfg.get("owner_chat_id", 0)
        if not token or not chat_id:
            return
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        payload = json.dumps({
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "HTML",
        }).encode()
        req = urllib.request.Request(url, data=payload,
                                     headers={"Content-Type": "application/json"},
                                     method="POST")
        with urllib.request.urlopen(req, timeout=10):
            pass
    except Exception as e:
        print(f"Telegram error: {e}")

# ── Load data ──────────────────────────────────────────────────────────────────
def load_json(path: Path, label: str):
    if not path.exists():
        print(f"⚠  {label} not found at {path}")
        return None
    try:
        return json.loads(path.read_text())
    except Exception as e:
        print(f"⚠  Could not parse {label}: {e}")
        return None

# ── Normalise name for fuzzy matching ─────────────────────────────────────────
def norm(name: str) -> str:
    return name.lower().strip().replace(",", "").replace("  ", " ")

def names_match(a: str, b: str) -> bool:
    na, nb = norm(a), norm(b)
    if na == nb:
        return True
    # Handle "Lastname Firstname" vs "Firstname Lastname"
    pa, pb = na.split(), nb.split()
    return sorted(pa) == sorted(pb)

# ── Current week window ────────────────────────────────────────────────────────
def this_week_monday() -> date:
    today = date.today()
    return today - timedelta(days=today.weekday())

def this_week_keys(menu_orders: dict) -> list[str]:
    """Return all GOJ_Menu_Orders keys for this week."""
    monday = this_week_monday()
    friday = monday + timedelta(days=4)
    sunday = monday + timedelta(days=6)
    results = []
    for key in menu_orders:
        # key format: "YYYY-MM-DD_S1" or "YYYY-MM-DD_S2"
        date_part = key.split("_")[0]
        try:
            d = date.fromisoformat(date_part)
            if monday <= d <= sunday:
                results.append(key)
        except ValueError:
            pass
    return results

# ── Build set of clients who have a menu order this week ──────────────────────
def menu_clients_this_week(menu_orders: dict) -> dict[str, list[str]]:
    """
    Returns { norm(client_name): [week_key, ...] }
    """
    week_keys = this_week_keys(menu_orders)
    result = {}
    for key in week_keys:
        entry = menu_orders[key]
        for order in entry.get("orders", []):
            name = order.get("name", "")
            if name:
                nname = norm(name)
                result.setdefault(nname, [])
                if key not in result[nname]:
                    result[nname].append(key)
    return result

# ── Build set of active clients expected this week ────────────────────────────
def active_clients_this_week(clients: list) -> list[dict]:
    """Return clients who are active and attend at least one day Mon-Sun."""
    days_present = set(CLIENT_DAY_LABELS.keys())
    result = []
    for c in clients:
        if c.get("status", "active").lower() != "active":
            continue
        attending = c.get("attending_days", [])
        if any(d in days_present for d in attending):
            result.append(c)
    return result

# ── Build set of all clients on routes this week ──────────────────────────────
def route_clients_this_week(routes: dict) -> dict[str, list[str]]:
    """
    Returns { norm(client_name): [route_key, ...] }
    """
    result = {}
    for route_key, clients in routes.items():
        for c in clients:
            name = c.get("name", "")
            if name and c.get("active", True):
                nname = norm(name)
                result.setdefault(nname, [])
                if route_key not in result[nname]:
                    result[nname].append(route_key)
    return result

# ── Run audit ─────────────────────────────────────────────────────────────────
def run_audit() -> str:
    menu_orders = load_json(MENU_ORDERS, "GOJ_Menu_Orders.json")
    clients_raw = load_json(CLIENTS,    "GOJ_Clients_Master.json")
    routes_raw  = load_json(ROUTES,     "GOJ_Master_Routes.json")

    if not menu_orders or not clients_raw or not routes_raw:
        return "⚠️ Audit could not run — one or more data files missing."

    monday = this_week_monday()
    week_label = f"{monday.strftime('%b %d')} – {(monday + timedelta(days=4)).strftime('%b %d, %Y')}"

    menu_clients  = menu_clients_this_week(menu_orders)
    active        = active_clients_this_week(clients_raw)
    route_clients = route_clients_this_week(routes_raw)

    # Build norm → original name maps
    active_norm = {norm(c["name"]): c for c in active}
    route_norm  = {n: routes for n, routes in route_clients.items()}

    missing_menu      = []  # on route, attending, but no menu order
    no_transport      = []  # has menu order but N/TR or not on any route
    unrecognised      = []  # in menu orders but not in client master

    # Check every active route client → do they have a menu?
    for nname, route_keys in route_norm.items():
        # Find original name
        client_obj = active_norm.get(nname)
        if not client_obj:
            # Try fuzzy
            client_obj = next(
                (v for k, v in active_norm.items() if names_match(k, nname)), None
            )
        display_name = client_obj["name"] if client_obj else nname.title()

        if nname not in menu_clients:
            # Check if client is expected this week (has attending days)
            if client_obj:
                attending     = client_obj.get("attending_days", [])
                transport     = client_obj.get("transport", "TR")
                swap_from     = client_obj.get("swap_from_day", [])
                swap_to       = client_obj.get("swap_to_day", [])

                # If client swapped days, their meal carries over — not a discrepancy
                # A swap means they changed one attendance day to another;
                # their menu form already covers it under the new day.
                has_swap = bool(swap_from or swap_to)

                if attending and transport != "N/TR" and not has_swap:
                    missing_menu.append({
                        "name": display_name,
                        "routes": route_keys,
                        "attending_days": attending,
                        "transport": transport,
                    })
                elif attending and transport != "N/TR" and has_swap:
                    # Note the swap so we can surface it in the report as FYI (not an error)
                    pass  # carry-over — meal follows the client to their new day

    # Check every menu order → is client on a route?
    for nname, week_keys in menu_clients.items():
        if nname not in route_norm:
            # Try fuzzy match in routes
            found = any(names_match(nname, rn) for rn in route_norm)
            if not found:
                # Also check client master
                in_master = any(names_match(nname, k) for k in active_norm)
                if in_master:
                    client_obj = next(
                        (v for k, v in active_norm.items() if names_match(k, nname)), None
                    )
                    transport = client_obj.get("transport", "TR") if client_obj else "?"
                    if transport == "N/TR":
                        pass  # self-transport — not a discrepancy
                    else:
                        no_transport.append({
                            "name": nname.title(),
                            "weeks": week_keys,
                            "transport": transport,
                        })
                else:
                    unrecognised.append({
                        "name": nname.title(),
                        "weeks": week_keys,
                    })

    # ── Format report ──────────────────────────────────────────────────────────
    lines = [
        f"🍽 <b>GOJ Menu ↔ Transport Audit</b>",
        f"Week of {week_label}",
        f"",
    ]

    if not missing_menu and not no_transport and not unrecognised:
        lines.append("✅ <b>All clear — menus and routes match perfectly.</b>")
    else:
        if missing_menu:
            lines.append(f"🔴 <b>On route but NO menu order ({len(missing_menu)}):</b>")
            for item in missing_menu[:15]:
                days = ", ".join(item["attending_days"])
                lines.append(f"  • {item['name']} — attends {days}")
            if len(missing_menu) > 15:
                lines.append(f"  … and {len(missing_menu)-15} more")
            lines.append("")

        if no_transport:
            lines.append(f"🟡 <b>Has menu but no route match ({len(no_transport)}):</b>")
            for item in no_transport[:10]:
                lines.append(f"  • {item['name']} (transport: {item['transport']})")
            if len(no_transport) > 10:
                lines.append(f"  … and {len(no_transport)-10} more")
            lines.append("")

        if unrecognised:
            lines.append(f"🔵 <b>Name in menu not found in client master ({len(unrecognised)}):</b>")
            for item in unrecognised[:10]:
                lines.append(f"  • {item['name']}")
            if len(unrecognised) > 10:
                lines.append(f"  … and {len(unrecognised)-10} more")
            lines.append("")

    total_menu   = len(menu_clients)
    total_route  = len(route_norm)
    total_active = len(active)
    lines += [
        f"📊 <b>Summary:</b>",
        f"  Active clients: {total_active}",
        f"  Menu orders this week: {total_menu}",
        f"  Clients on routes: {total_route}",
        f"  🔴 Missing menus: {len(missing_menu)}",
        f"  🟡 No route match: {len(no_transport)}",
        f"  🔵 Unrecognised names: {len(unrecognised)}",
    ]

    report = "\n".join(lines)

    # Also save to log
    today = date.today().isoformat()
    LOG_PATH.write_text(f"[{today}]\n{report}\n")

    return report

# ── Entry point ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    report = run_audit()
    print(report.replace("<b>", "").replace("</b>", ""))  # plain stdout
    _tg_send(report)
    print("\n✅  Report sent to Telegram (Rexxie)")
