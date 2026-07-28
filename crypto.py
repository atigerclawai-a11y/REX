#!/usr/bin/env python3
"""Crypto Market Tracker — portfolio, live prices, assessment.
Uses CoinGecko (free, no API key).
Usage: python3 crypto.py add bitcoin --amount 0.5 --paid 35000
       python3 crypto.py portfolio
       python3 crypto.py price bitcoin
       python3 crypto.py assess
"""

import json, sys, os, requests
from datetime import datetime, date

DB = os.path.expanduser("~/.hermes/rexxie_vault/crypto_inventory.json")
VAULT = os.path.expanduser("~/.hermes/rexxie_vault/crypto")
COINGECKO = "https://api.coingecko.com/api/v3"
os.makedirs(VAULT, exist_ok=True)

# Common coin ID mappings
COIN_IDS = {
    "btc": "bitcoin", "bitcoin": "bitcoin",
    "eth": "ethereum", "ethereum": "ethereum",
    "sol": "solana", "solana": "solana",
    "xrp": "ripple", "ripple": "ripple",
    "doge": "dogecoin", "dogecoin": "dogecoin",
    "ada": "cardano", "cardano": "cardano",
    "dot": "polkadot", "polkadot": "polkadot",
    "avax": "avalanche-2", "avalanche": "avalanche-2",
    "usdc": "usd-coin", "usdt": "tether",
    "link": "chainlink", "chainlink": "chainlink",
    "matic": "matic-network", "pol": "matic-network",
    "atom": "cosmos", "cosmos": "cosmos",
    "uni": "uniswap", "uniswap": "uniswap",
    "shib": "shiba-inu", "ape": "apecoin",
    "ltc": "litecoin", "litecoin": "litecoin",
    "near": "near", "near-protocol": "near",
    "op": "optimism", "optimism": "optimism",
    "arb": "arbitrum", "arbitrum": "arbitrum",
    "sui": "sui", "apt": "aptos", "aptos": "aptos",
    "trx": "tron", "tron": "tron",
    "bnb": "binancecoin", "binance": "binancecoin",
    "xlm": "stellar", "stellar": "stellar",
}

def load_db():
    if not os.path.exists(DB):
        return {"items": []}
    with open(DB) as f:
        return json.load(f)

def save_db(db):
    with open(DB, 'w') as f:
        json.dump(db, f, indent=2, default=str)

def get_coin_id(name):
    return COIN_IDS.get(name.lower(), name.lower().replace(" ", "-"))

def fetch_prices(coin_ids):
    """Bulk fetch prices from CoinGecko."""
    ids_str = ",".join(coin_ids)
    try:
        r = requests.get(
            f"{COINGECKO}/simple/price",
            params={"ids": ids_str, "vs_currencies": "usd", "include_24hr_change": "true"},
            timeout=15
        )
        r.raise_for_status()
        return r.json()
    except Exception:
        return {}

def cmd_add(coin, amount, paid, date_str=None):
    db = load_db()
    coin_id = get_coin_id(coin)
    amount = float(amount)
    paid = float(paid)
    item = {
        "coin": coin.lower(),
        "coin_id": coin_id,
        "amount": amount,
        "purchase_price": paid,
        "total_paid": round(amount * paid, 2),
        "purchase_date": date_str or date.today().isoformat(),
        "id": len(db["items"]) + 1,
    }
    db["items"].append(item)
    save_db(db)
    return f"Added: {amount} {coin.upper()} @ ${paid:,.2f} (${item['total_paid']:,.2f})"

def cmd_price(coin):
    coin_id = get_coin_id(coin)
    prices = fetch_prices([coin_id])
    data = prices.get(coin_id, {})
    price = data.get("usd", 0)
    change = data.get("usd_24h_change", 0)
    emoji = "📈" if change >= 0 else "📉"
    return f"{emoji} **{coin.upper()}** — **${price:,.2f}** (24h: {change:+.2f}%)"

def cmd_portfolio():
    db = load_db()
    if not db["items"]:
        return "# Crypto Portfolio\n\nNo holdings yet."

    coin_ids = list(set(i["coin_id"] for i in db["items"]))
    prices = fetch_prices(coin_ids)

    lines = ["# Crypto Portfolio\n", f"**Updated:** {datetime.now().isoformat()}\n"]
    total_paid = 0
    total_value = 0

    for item in db["items"]:
        price = prices.get(item["coin_id"], {}).get("usd", 0)
        change = prices.get(item["coin_id"], {}).get("usd_24h_change", 0)
        current = item["amount"] * price
        gain = current - item["total_paid"]
        gain_pct = (gain / item["total_paid"] * 100) if item["total_paid"] > 0 else 0
        total_paid += item["total_paid"]
        total_value += current

        lines.append(f"## {item['coin'].upper()}")
        lines.append(f"- **{item['amount']}** @ ${item['purchase_price']:,.2f} → now ${price:,.2f} (24h: {change:+.1f}%)")
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
        return "# Crypto Assessment\n\nNo holdings."

    coin_ids = list(set(i["coin_id"] for i in db["items"]))
    prices = fetch_prices(coin_ids)

    total_paid = sum(i["total_paid"] for i in db["items"])
    total_value = sum(i["amount"] * prices.get(i["coin_id"], {}).get("usd", 0) for i in db["items"])

    alloc = {}
    for item in db["items"]:
        val = item["amount"] * prices.get(item["coin_id"], {}).get("usd", 0)
        alloc[item["coin"]] = alloc.get(item["coin"], 0) + val
    total = sum(alloc.values()) or 1

    alloc_lines = []
    for coin, val in sorted(alloc.items(), key=lambda x: x[1], reverse=True):
        pct = val / total * 100
        change = prices.get(get_coin_id(coin), {}).get("usd_24h_change", 0)
        price = prices.get(get_coin_id(coin), {}).get("usd", 0)
        alloc_lines.append(f"| {coin.upper()} | {pct:.0f}% | ${price:,.2f} | {change:+.1f}% |")

    # Get BTC dominance
    btc_price = 0
    try:
        r = requests.get(f"{COINGECKO}/global", timeout=10)
        btc_dom = r.json().get("data", {}).get("market_cap_percentage", {}).get("btc", 0)
        btc_price = prices.get("bitcoin", {}).get("usd", 0)
    except Exception:
        btc_dom = 0

    assessment = f"""# Crypto Assessment

## Holdings
| Coin | Allocation | Price | 24h |
|------|-----------|-------|-----|
{chr(10).join(alloc_lines)}

## Market Indicators
- **BTC Dominance:** {btc_dom:.1f}%
- **BTC Price:** ${btc_price:,.2f}

## Summary
- **Total Paid:** ${total_paid:,.2f}
- **Current Value:** ${total_value:,.2f}
- **Gain/Loss:** ${total_value - total_paid:+,.2f} ({(total_value/total_paid-1)*100:+.1f}%)

## Action Items
- Monitor BTC dominance — above 60% suggests altcoin opportunities
- Take profits on positions with > 100% gain
- Consider stablecoin allocation for dry powder
"""
    path = os.path.join(VAULT, "assessment.md")
    with open(path, 'w') as f:
        f.write(assessment)
    return assessment

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: crypto.py [add|portfolio|price|assess] ...")
        sys.exit(1)

    cmd = sys.argv[1]

    if cmd == "add":
        import argparse
        parser = argparse.ArgumentParser()
        parser.add_argument("coin")
        parser.add_argument("--amount", type=float, required=True)
        parser.add_argument("--paid", type=float, required=True)
        parser.add_argument("--date")
        args = parser.parse_args(sys.argv[2:])
        print(cmd_add(args.coin, args.amount, args.paid, args.date))

    elif cmd == "price":
        print(cmd_price(sys.argv[2]))

    elif cmd in ("portfolio", "assess"):
        print(globals()[f"cmd_{cmd}"]())

    else:
        print(f"Unknown: {cmd}")