#!/usr/bin/env python3
"""
Boardwalk Beer Garden — UFC 328 Fight Night Menu
Clover bulk import script (Merchant REST API)

USAGE
-----
    python3 clover_import.py <MERCHANT_ID> <API_TOKEN> [--region=us|eu] [--dry-run]

WHERE TO GET MERCHANT_ID + API_TOKEN
------------------------------------
1. Log in to https://www.clover.com/dashboard (use the merchant account
   you want this menu added to).
2. Top-right account menu → your merchant ID is shown (a 13-char string
   like "ABC123DEF4567").
3. Setup → API Tokens → "Create New Token"
        Name:        REX Menu Import
        Permissions: Inventory  (READ + WRITE)
   Click Generate, then copy the token string immediately
   (Clover only shows it once).

After you've successfully run this script, REVOKE the token from the
same screen — you don't need it anymore.

REGION
------
US merchants:  --region=us   (default; api.clover.com)
EU merchants:  --region=eu   (api.eu.clover.com)

WHAT IT DOES
------------
1. Creates a category "UFC 328 Fight Night" (or reuses if it exists).
2. Creates 8 modifier groups + 19 modifiers, only if they don't exist yet.
3. Creates 39 items, attaches each to:
        • the new category
        • its modifier group(s)  (where applicable)
        • its print label HOT or COLD
4. Print labels HOT and COLD are created automatically if missing
   (you'll still need to map each label to a physical printer in
   Clover's Setup → Order Receipts → Printers).

The script is idempotent — running it twice will not duplicate the
category, modifier groups, or print labels (but it WILL create
duplicate items, so don't re-run unless you delete the items first).
"""

import sys
import json
import time
import argparse
import urllib.request
import urllib.error

# ── Menu data ───────────────────────────────────────────────────────────
CATEGORY_NAME = "UFC 328 Fight Night"

# (name, price_cents, description, modifier_group_name_or_None, print_label)
ITEMS = [
    # APPETIZERS — HOT
    ("Boardwalk Sampler",       3800, "A generous platter of wings, cheese quesadilla, mozzarella sticks & fried pickles — perfect for sharing.", None,             "HOT"),
    ("Wings (8)",               2000, "Crispy chicken wings, your choice of Buffalo, BBQ, or Plain. Served with celery and ranch.",                "Wing Sauce",     "HOT"),
    ("Cheese Quesadilla",       1400, "Flour tortilla stuffed with melted cheese and grilled to golden perfection.",                                 "Add Chicken",    "HOT"),
    ("Nachos Supreme",          2200, "Tortilla chips loaded with cheese, jalapeños, tomatoes, onions and sour cream.",                              "Nachos Protein", "HOT"),
    ("Jumbo Mozzarella Sticks", 1800, "Extra-large herb-seasoned breaded mozzarella sticks, fried golden, served with marinara.",                    None,             "HOT"),
    ("Fried Pickles",           1400, "Crispy dill pickle spears in flavorful breading, served with ranch dipping sauce.",                           None,             "HOT"),
    ("Head-On Shrimp",          2100, "Whole shrimp sautéed in garlic butter sauce, finished with fresh lemon.",                                     None,             "HOT"),
    ("Pelmeni",                 1800, "Traditional Russian dumplings filled with seasoned meat. Served fried or boiled.",                             "Pelmeni Style",  "HOT"),
    ("Pelmeni (Potato)",        1500, "Traditional dumplings filled with savory mashed potato. Served fried or boiled.",                              "Pelmeni Style",  "HOT"),
    # SOUPS — HOT
    ("Solyanka", 1800, "Bold and savory Russian soup with cured meats, crisp pickles, olives and capers in a rich tomato-beef broth.", None, "HOT"),
    ("Borscht",  1600, "Classic Ukrainian beet soup with fresh vegetables, herbs and a dollop of sour cream.",                          None, "HOT"),
    # BURGERS — HOT (all served with fries)
    ("Classic Boardwalk Burger", 1600, "Juicy beef patty with lettuce, tomato, onion, pickles and our signature sauce on a toasted bun. Served with fries.", None, "HOT"),
    ("Cheeseburger",             1800, "Classic beef burger topped with melted American cheese, lettuce, tomato and onion. Served with fries.",                None, "HOT"),
    ("Bacon Cheeseburger",       2000, "Beef patty with crispy bacon, melted cheese, lettuce, tomato and onion. Served with fries.",                          None, "HOT"),
    ("BBQ Burger",               1900, "Beef patty glazed with smoky BBQ sauce, melted cheese, crispy onions and pickles. Served with fries.",                None, "HOT"),
    ("Chicken Burger",           1700, "Grilled chicken breast with lettuce, tomato and mayo on a toasted bun. Served with fries.",                            None, "HOT"),
    ("Juicy Lucy",               2600, "Half-pound beef patty stuffed with melted cheese that oozes out with every bite. Served with fries.",                  None, "HOT"),
    # GRILLED MAINS — HOT
    ("Salo Board",                2500, "Traditional Ukrainian cured pork fat with bread, pickles and garlic. Choice of mashed potatoes or grilled vegetables.", "Mains Side", "HOT"),
    ("Dry Fish Board",            1900, "Assortment of dried & smoked fish, perfect with beer. Choice of mashed potatoes or grilled vegetables.",                "Mains Side", "HOT"),
    ("Bratwurst",                 1800, "Juicy grilled pork sausage with coleslaw and spicy mustard. Choice of mashed potatoes or grilled vegetables.",         "Mains Side", "HOT"),
    ("Chicken Shawarma",          2400, "Tender marinated chicken grilled and wrapped with garlic sauce, pickles and warm pita. Choice of side.",               "Mains Side", "HOT"),
    ("Full Roasted Baby Chicken", 2600, "Whole baby chicken marinated in signature spices, roasted until golden and juicy. Choice of side.",                    "Mains Side", "HOT"),
    ("Ribeye Steak",              6200, "30 oz bone-out ribeye, grilled to your preference. Choice of side.",                                                   "Steak Temp",  "HOT"),
    ("Skirt Steak",               4600, "Grilled skirt steak with our famous chimichurri sauce. Choice of side.",                                               "Steak Temp",  "HOT"),
    ("Salmon Steak",              3000, "Fresh salmon steak, simply grilled to highlight natural flavor. Choice of side.",                                      "Mains Side", "HOT"),
    ("Lula Kebab (one long)",     2200, "Seasoned ground meat kebab, flame-grilled to perfection. Choice of side.",                                             "Mains Side", "HOT"),
    ("Chilahach (4 pc)",          2700, "Tender marinated grilled meat chunks with bold flavor. Choice of side.",                                               "Mains Side", "HOT"),
    # SPECIALS — HOT
    ("Grilled Octopus", 3600, "Tender grilled octopus with olive oil, garlic and herbs.", None, "HOT"),
    ("Branzino",        3800, "Whole Mediterranean sea bass, grilled and seasoned simply.", None, "HOT"),
    # SALADS — COLD
    ("Garden Salad",      1800, "Crisp mixed greens, cucumbers, cherry tomatoes and red onions with house dressing.", "Salad Add-Ons",  "COLD"),
    ("Greek Salad",       1900, "Tomatoes, cucumbers, olives, feta and red onions with olive oil and oregano.",        "Salad Add-Ons",  "COLD"),
    ("Caesar Salad",      1400, "Crisp romaine, parmesan, croutons and classic Caesar dressing.",                      "Caesar Add-Ons", "COLD"),
    ("Skirt Steak Salad", 3600, "Grilled skirt steak over mixed greens with vegetables and house dressing.",           None,             "COLD"),
    # SIDELINE — HOT
    ("Mashed Potatoes",        800,  "Creamy buttery mashed potatoes.",                            None, "HOT"),
    ("Wasabi Mashed Potatoes", 1000, "Mashed potatoes with house wasabi-horseradish blend.",       None, "HOT"),
    ("Grilled Vegetables",     1000, "Seasonal market vegetables grilled with olive oil & salt.", None, "HOT"),
    ("Fries",                  700,  "Hand-cut, double-fried, golden and crisp.",                  None, "HOT"),
    # SWEET VICTORY — COLD
    ("Cheesecake",                1200, "Rich and creamy New York-style cheesecake with graham cracker crust.",   None, "COLD"),
    ("Zefir in Chocolate (3 pc)", 700,  "Light and airy Russian fruit meringue cookies covered in chocolate.",   None, "COLD"),
]

# (group_name, show_by_default_modifier_count, [(name, price_cents)])
# All groups behave as forced/optional based on the modifier group's
# minRequired field below.
MODIFIER_GROUPS = [
    # name,             min, max, show_by_default, [(modifier name, price_cents)]
    ("Wing Sauce",      1, 1, True, [("Buffalo", 0), ("BBQ", 0), ("Plain", 0)]),
    ("Add Chicken",     0, 1, False, [("Add Grilled Chicken", 500)]),
    ("Nachos Protein",  1, 1, True, [("Chicken", 0), ("Pork", 0)]),
    ("Pelmeni Style",   1, 1, True, [("Fried", 0), ("Boiled", 0)]),
    ("Mains Side",      1, 1, True, [("Mashed Potatoes", 0), ("Grilled Vegetables", 0)]),
    ("Steak Temp",      1, 1, True, [("Rare", 0), ("Medium-Rare", 0), ("Medium", 0), ("Medium-Well", 0), ("Well-Done", 0)]),
    ("Salad Add-Ons",   0, 2, False, [("Add Grilled Chicken", 500), ("Add Shrimp", 800)]),
    ("Caesar Add-Ons",  0, 2, False, [("Add Grilled Chicken", 500), ("Add Shrimp", 800)]),
]

# ── HTTP plumbing ───────────────────────────────────────────────────────
class CloverError(Exception):
    pass

class CloverAPI:
    def __init__(self, mid, token, region="us", dry_run=False):
        self.mid = mid
        self.token = token
        self.dry_run = dry_run
        host = "api.clover.com" if region == "us" else "api.eu.clover.com"
        self.base = f"https://{host}/v3/merchants/{mid}"
        self.headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    def request(self, method, path, body=None):
        url = self.base + path
        if self.dry_run and method != "GET":
            print(f"  [dry-run] {method} {url}  body={json.dumps(body) if body else '-'}")
            return {}
        data = json.dumps(body).encode("utf-8") if body is not None else None
        req = urllib.request.Request(url, data=data, headers=self.headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                raw = resp.read().decode("utf-8")
                return json.loads(raw) if raw else {}
        except urllib.error.HTTPError as e:
            err_body = e.read().decode("utf-8", errors="replace")
            raise CloverError(f"HTTP {e.code} on {method} {path}\n  {err_body}")
        except urllib.error.URLError as e:
            raise CloverError(f"Network error on {method} {path}: {e}")

    def get(self, path):     return self.request("GET",    path)
    def post(self, path, b): return self.request("POST",   path, b)
    def put(self, path, b):  return self.request("PUT",    path, b)
    def delete(self, path):  return self.request("DELETE", path)

# ── High-level helpers ─────────────────────────────────────────────────
def find_or_create_category(api, name):
    print(f"\n[1/4] Category: '{name}'")
    res = api.get(f"/categories?filter=name={urllib.parse.quote(name)}")
    elements = res.get("elements", []) if isinstance(res, dict) else []
    for c in elements:
        if c.get("name") == name:
            print(f"  ✓ exists (id={c['id']})")
            return c["id"]
    new = api.post("/categories", {"name": name})
    print(f"  ✓ created (id={new.get('id')})")
    return new.get("id")

def find_or_create_print_label(api, label):
    res = api.get("/tag_labels")
    for t in res.get("elements", []) if isinstance(res, dict) else []:
        if t.get("name") == label:
            return t["id"]
    new = api.post("/tag_labels", {"name": label})
    return new.get("id")

def ensure_print_labels(api):
    print("\n[2/4] Print labels: HOT, COLD")
    ids = {}
    for label in ("HOT", "COLD"):
        ids[label] = find_or_create_print_label(api, label)
        print(f"  ✓ {label}  (id={ids[label]})")
    return ids

def find_or_create_modifier_groups(api):
    print(f"\n[3/4] Modifier groups: {len(MODIFIER_GROUPS)} groups")
    existing = {}
    res = api.get("/modifier_groups?expand=modifiers")
    for g in res.get("elements", []) if isinstance(res, dict) else []:
        existing[g.get("name")] = g
    out = {}
    for name, mn, mx, show_by_default, mods in MODIFIER_GROUPS:
        if name in existing:
            g = existing[name]
            print(f"  ✓ '{name}' exists (id={g['id']})")
        else:
            g = api.post("/modifier_groups", {
                "name": name,
                "minRequired": mn,
                "maxAllowed": mx,
                "showByDefault": show_by_default,
            })
            print(f"  ✓ '{name}' created (id={g.get('id')})")
        out[name] = g["id"]
        # ensure modifiers exist within the group
        existing_mods = {}
        if "modifiers" in g and isinstance(g.get("modifiers"), dict):
            for m in g["modifiers"].get("elements", []):
                existing_mods[m.get("name")] = m
        for mname, mprice in mods:
            if mname in existing_mods:
                continue
            api.post(f"/modifier_groups/{g['id']}/modifiers", {
                "name": mname,
                "price": mprice,
            })
            print(f"      + {mname} (+${mprice/100:.2f})")
    return out

def create_items(api, category_id, mod_group_ids, print_label_ids):
    print(f"\n[4/4] Items: {len(ITEMS)}")
    for i, (name, price, desc, mod_group, label) in enumerate(ITEMS, 1):
        item = api.post("/items", {
            "name": name,
            "price": price,
            "priceType": "FIXED",
            "defaultTaxRates": True,
            "alternateName": "",
        })
        item_id = item.get("id")
        # Description is set on the item via PUT (some Clover API responses
        # don't accept it on create)
        if desc:
            api.post(f"/items/{item_id}", {"id": item_id, "alternateName": desc[:255]})
        # Attach to category
        api.post(f"/category_items", {"elements": [
            {"category": {"id": category_id}, "item": {"id": item_id}}
        ]})
        # Attach print label
        if label in print_label_ids:
            api.post(f"/tag_item", {"elements": [
                {"tag": {"id": print_label_ids[label]}, "item": {"id": item_id}}
            ]})
        # Attach modifier group
        if mod_group and mod_group in mod_group_ids:
            api.post(f"/items/{item_id}/modifier_groups", {
                "id": mod_group_ids[mod_group]
            })
        print(f"  {i:2d}/{len(ITEMS)}  ✓ {name}  ${price/100:.2f}  [{label}]"
              + (f"  +{mod_group}" if mod_group else ""))
        # gentle pacing — Clover API rate limit is generous but be polite
        time.sleep(0.05)

# ── main ──────────────────────────────────────────────────────────────
def main():
    p = argparse.ArgumentParser(description="Bulk-create UFC 328 menu in Clover.")
    p.add_argument("merchant_id")
    p.add_argument("api_token")
    p.add_argument("--region", choices=["us", "eu"], default="us")
    p.add_argument("--dry-run", action="store_true",
                   help="Print API calls without making them")
    args = p.parse_args()

    api = CloverAPI(args.merchant_id, args.api_token,
                    region=args.region, dry_run=args.dry_run)
    print(f"Clover region: {args.region}")
    print(f"Merchant ID:   {args.merchant_id}")
    print(f"Mode:          {'DRY-RUN (no changes)' if args.dry_run else 'LIVE'}")

    try:
        category_id     = find_or_create_category(api, CATEGORY_NAME)
        print_label_ids = ensure_print_labels(api)
        mod_group_ids   = find_or_create_modifier_groups(api)
        create_items(api, category_id, mod_group_ids, print_label_ids)
    except CloverError as e:
        print(f"\n✗ ERROR: {e}", file=sys.stderr)
        sys.exit(1)

    print(f"""
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
✅  Done — {len(ITEMS)} items added to '{CATEGORY_NAME}'
    Print labels HOT and COLD created.
    Don't forget:
      1. Map HOT and COLD to your physical printers under
         Setup → Order Receipts → Printers.
      2. Revoke the API token from Setup → API Tokens
         (you no longer need it).
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
""")

if __name__ == "__main__":
    import urllib.parse
    main()
