#!/usr/bin/env python3
"""Stock Market Tracker — portfolio, live prices, assessment.
Uses Yahoo Finance (free, no API key).
Usage: python3 stocks.py add AAPL --shares 10 --paid 185.50
       python3 stocks.py portfolio
       python3 stocks.py price AAPL
       python3 stocks.py assess
"""

import json, sys, os, requests
from datetime import datetime, date

DB = os.path.expanduser("~/.hermes/rexxie_vault/stocks_inventory.json")
VAULT = os.path.expanduser("~/.hermes/rexxie_vault/stocks")
os.makedirs(VAULT, exist_ok=True)

def load_db():
    if not os.path.exists(DB):
        return {"items": []}
    with open(DB) as f:
        return json.load(f)

def save_db(db):
    with open(DB, 'w') as f:
        json.dump(db, f, indent=2, default=str)

def fetch_price(symbol):
    """Get live stock price via Yahoo Finance."""
    try:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?interval=1d&range=1d"
        headers = {"User-Agent": "Mozilla/5.0"}
        r = requests.get(url, headers=headers, timeout=10)
        data = r.json()
        price = data["chart"]["result"][0]["meta"]["regularMarketPrice"]
        name = data["chart"]["result"][0]["meta"].get("longName", symbol)
        prev = data["chart"]["result"][0]["meta"].get("previousClose", price)
        return {"symbol": symbol.upper(), "name": name, "price": price, "previous_close": prev, "change_pct": (price - prev) / prev * 100}
    except Exception as e:
        return {"symbol": symbol.upper(), "name": symbol, "price": 0, "previous_close": 0, "change_pct": 0, "error": str(e)[:100]}

def cmd_add(symbol, shares, paid, date_str=None):
    db = load_db()
    shares = float(shares)
    paid = float(paid)
    item = {
        "symbol": symbol.upper(),
        "shares": shares,
        "purchase_price": paid,
        "total_paid": round(shares * paid, 2),
        "purchase_date": date_str or date.today().isoformat(),
        "id": len(db["items"]) + 1,
    }
    db["items"].append(item)
    save_db(db)
    return f"Added: {shares} {symbol.upper()} @ ${paid} (${item['total_paid']})"

def cmd_price(symbol):
    info = fetch_price(symbol)
    emoji = "📈" if info["change_pct"] >= 0 else "📉"
    return f"{emoji} **{info['name']} ({info['symbol']})** — **${info['price']:,.2f}** ({info['change_pct']:+.2f}%)"

def cmd_portfolio():
    db = load_db()
    if not db["items"]:
        return "# Stock Portfolio\n\nNo holdings yet."

    lines = ["# Stock Portfolio\n", f"**Updated:** {datetime.now().isoformat()}\n"]
    
    symbols = list(set(i["symbol"] for i in db["items"]))
    prices = {}
    for sym in symbols:
        info = fetch_price(sym)
        prices[sym] = info

    total_paid = 0
    total_value = 0

    for item in db["items"]:
        info = prices.get(item["symbol"], {"price": 0})
        current = item["shares"] * info["price"]
        gain = current - item["total_paid"]
        gain_pct = (gain / item["total_paid"] * 100) if item["total_paid"] > 0 else 0
        total_paid += item["total_paid"]
        total_value += current

        lines.append(f"## {info.get('name', item['symbol'])} ({item['symbol']})")
        lines.append(f"- **{item['shares']} shares** @ ${item['purchase_price']:,.2f} → now ${info['price']:,.2f}")
        lines.append(f"- Paid: ${item['total_paid']:,.2f} | Value: ${current:,.2f} | {gain:+,.2f} ({gain_pct:+.1f}%)")
        lines.append("")

    total_gain = total_value - total_paid
    total_pct = (total_gain / total_paid * 100) if total_paid > 0 else 0
    summary = f"**Total: ${total_paid:,.2f} → ${total_value:,.2f} ({total_gain:+,.2f} / {total_pct:+.1f}%)**"
    lines.insert(2, summary + "\n")

    path = os.path.join(VAULT, "portfolio.md")
    with open(path, 'w') as f:
        f.write("\n".join(lines))
    return "\n".join(lines)

def cmd_assess():
    db = load_db()
    if not db["items"]:
        return "# Stock Assessment\n\nNo holdings."

    symbols = list(set(i["symbol"] for i in db["items"]))
    prices = {sym: fetch_price(sym) for sym in symbols}

    total_paid = sum(i["total_paid"] for i in db["items"])
    total_value = sum(i["shares"] * prices[i["symbol"]]["price"] for i in db["items"])

    # Allocation
    alloc = {}
    for item in db["items"]:
        alloc[item["symbol"]] = alloc.get(item["symbol"], 0) + item["shares"] * prices[item["symbol"]]["price"]
    total = sum(alloc.values()) or 1

    alloc_lines = []
    for sym, val in sorted(alloc.items(), key=lambda x: x[1], reverse=True):
        pct = val / total * 100
        info = prices[sym]
        alloc_lines.append(f"| {sym} | {pct:.0f}% | ${info['price']:,.2f} | {info['change_pct']:+.1f}% |")

    assessment = f"""# Stock Assessment

## Holdings
| Symbol | Allocation | Price | Today |
|--------|-----------|-------|-------|
{chr(10).join(alloc_lines)}

## Summary
- **Total Paid:** ${total_paid:,.2f}
- **Current Value:** ${total_value:,.2f}
- **Gain/Loss:** ${total_value - total_paid:+,.2f} ({(total_value/total_paid-1)*100:+.1f}%)

## Action Items
- Review positions with losses > 20%
- Consider profit-taking on positions with gains > 50%
- Rebalance if any single stock exceeds 30% of portfolio
"""
    path = os.path.join(VAULT, "assessment.md")
    with open(path, 'w') as f:
        f.write(assessment)
    return assessment

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: stocks.py [add|portfolio|price|assess] ...")
        sys.exit(1)

    cmd = sys.argv[1]

    if cmd == "add":
        import argparse
        parser = argparse.ArgumentParser()
        parser.add_argument("symbol")
        parser.add_argument("--shares", type=float, required=True)
        parser.add_argument("--paid", type=float, required=True)
        parser.add_argument("--date")
        args = parser.parse_args(sys.argv[2:])
        print(cmd_add(args.symbol, args.shares, args.paid, args.date))

    elif cmd == "price":
        print(cmd_price(sys.argv[2]))

    elif cmd in ("portfolio", "assess"):
        print(globals()[f"cmd_{cmd}"]())

    else:
        print(f"Unknown: {cmd}")