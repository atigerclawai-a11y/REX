#!/usr/bin/env python3
"""Precious Metals Collection Tracker — inventory, market prices, portfolio analysis.
Usage: python3 metals.py add "2021 Gold Eagle 1oz" --metal gold --weight 1 --unit oz --paid 1850
       python3 metals.py portfolio
       python3 metals.py market
       python3 metals.py assess
"""

import json, sys, os, requests
from datetime import datetime, date

DB = os.path.expanduser("~/.hermes/rexxie_vault/metals_inventory.json")
VAULT = os.path.expanduser("~/.hermes/rexxie_vault/metals")

PRICE_API = "https://api.gold-api.com/price/{}"
METAL_SYMBOLS = {"gold": "XAU", "silver": "XAG", "platinum": "XPT", "palladium": "XPD"}
UNIT_MAP = {"oz": 1, "troy_oz": 1, "ozt": 1, "gram": 0.0321507, "g": 0.0321507, "kg": 32.1507}

os.makedirs(VAULT, exist_ok=True)

def load_db():
    if not os.path.exists(DB):
        return {"items": [], "last_market_update": None}
    with open(DB) as f:
        return json.load(f)

def save_db(db):
    with open(DB, 'w') as f:
        json.dump(db, f, indent=2, default=str)

def fetch_spot_prices():
    prices = {}
    for metal, symbol in METAL_SYMBOLS.items():
        try:
            r = requests.get(PRICE_API.format(symbol), timeout=10)
            r.raise_for_status()
            prices[metal] = float(r.json().get("price", 0))
        except Exception:
            prices[metal] = 0
    return prices

def cmd_add(description, metal, weight, unit, paid, date_str=None):
    db = load_db()
    ozt = weight * UNIT_MAP.get(unit.lower(), 1)
    item = {
        "description": description,
        "metal": metal.lower(),
        "weight_ozt": round(ozt, 4),
        "weight_display": f"{weight} {unit}",
        "purchase_price_usd": float(paid),
        "purchase_date": date_str or date.today().isoformat(),
        "purchase_price_per_ozt": round(float(paid) / ozt, 2) if ozt > 0 else 0,
        "id": len(db["items"]) + 1,
    }
    db["items"].append(item)
    save_db(db)
    return f"Added: {description} ({metal}, {item['weight_display']}, paid ${paid})"

def cmd_portfolio():
    db = load_db()
    spots = fetch_spot_prices()

    if not db["items"]:
        return "# Portfolio\n\nNo items yet. Add with: metals.py add ..."

    lines = ["# Metals Portfolio\n"]
    total_paid = sum(i["purchase_price_usd"] for i in db["items"])
    total_value = sum(i["weight_ozt"] * spots.get(i["metal"], 0) for i in db["items"])

    for item in db["items"]:
        spot = spots.get(item["metal"], 0)
        current = item["weight_ozt"] * spot
        gain = current - item["purchase_price_usd"]
        gain_pct = (gain / item["purchase_price_usd"] * 100) if item["purchase_price_usd"] > 0 else 0
        lines.append(f"## {item['description']}")
        lines.append(f"- **{item['metal'].title()}** — {item['weight_display']}")
        lines.append(f"- Paid: ${item['purchase_price_usd']:,.2f} → Now: ${current:,.2f} (${gain:+,.2f} / {gain_pct:+.1f}%)")
        lines.append(f"- Purchased: {item['purchase_date']}\n")

    total_gain = total_value - total_paid
    total_pct = (total_gain / total_paid * 100) if total_paid > 0 else 0
    summary = f"**Total Paid:** ${total_paid:,.2f} | **Current:** ${total_value:,.2f} | **{total_gain:+,.2f} ({total_pct:+.1f}%)**"
    lines.insert(1, summary + "\n")
    lines.insert(1, f"**Updated:** {datetime.now().isoformat()}\n")

    path = os.path.join(VAULT, "portfolio.md")
    with open(path, 'w') as f:
        f.write("\n".join(lines))
    return "\n".join(lines)

def cmd_market():
    spots = fetch_spot_prices()
    lines = ["# Precious Metals Market\n", f"**Updated:** {datetime.now().isoformat()}\n"]
    emojis = {"gold": "🟡", "silver": "⚪", "platinum": "🔵", "palladium": "🟣"}
    for metal, price in sorted(spots.items()):
        e = emojis.get(metal, "⚫")
        lines.append(f"| {e} **{metal.title()}** | **${price:,.2f}**/oz |")

    path = os.path.join(VAULT, "market.md")
    with open(path, 'w') as f:
        f.write("\n".join(lines))
    return "\n".join(lines)

def cmd_assess():
    db = load_db()
    spots = fetch_spot_prices()

    alloc = {}
    for item in db["items"]:
        m = item["metal"]
        alloc[m] = alloc.get(m, 0) + item["weight_ozt"] * spots.get(m, 0)

    total_val = sum(alloc.values()) or 1
    alloc_lines = []
    for metal, val in sorted(alloc.items(), key=lambda x: x[1], reverse=True):
        pct = val / total_val * 100
        alloc_lines.append(f"- **{metal.title()}:** {pct:.0f}% (${val:,.0f})")

    gsr = spots.get("gold", 0) / spots.get("silver", 0) if spots.get("silver", 0) > 0 else 0

    assessment = f"""# Metals Assessment

## Allocation
{chr(10).join(alloc_lines or ['No items in collection'])}

## Spot Prices
| Metal | Price/oz |
|-------|---------|
| Gold | ${spots.get('gold', 0):,.2f} |
| Silver | ${spots.get('silver', 0):,.2f} |
| Platinum | ${spots.get('platinum', 0):,.2f} |
| Palladium | ${spots.get('palladium', 0):,.2f} |

## Key Ratios
- **Gold/Silver Ratio:** {gsr:.1f} ({'Silver undervalued — historical avg ~60' if gsr > 70 else 'Gold relatively cheap' if gsr < 45 else 'Neutral range'})

## Action Items
- Set price alerts at key levels
- Rebalance if single metal exceeds 80% of portfolio
- Update inventory after every purchase or sale
"""
    path = os.path.join(VAULT, "assessment.md")
    with open(path, 'w') as f:
        f.write(assessment)
    return assessment

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: metals.py [add|portfolio|market|assess] ...")
        sys.exit(1)

    cmd = sys.argv[1]

    if cmd == "add":
        import argparse
        parser = argparse.ArgumentParser()
        parser.add_argument("description")
        parser.add_argument("--metal", required=True)
        parser.add_argument("--weight", type=float, required=True)
        parser.add_argument("--unit", default="oz")
        parser.add_argument("--paid", type=float, required=True)
        parser.add_argument("--date")
        args = parser.parse_args(sys.argv[2:])
        print(cmd_add(args.description, args.metal, args.weight, args.unit, args.paid, args.date))

    elif cmd in ("portfolio", "market", "assess"):
        print(globals()[f"cmd_{cmd}"]())

    else:
        print(f"Unknown: {cmd}")