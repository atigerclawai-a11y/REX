# CC_clover_research.md — Clover POS AI Integration Research
# Gold Health Systems · June 5 2026
# Best tools/approaches for automated menu management at BBG

---

## Bottom Line

You already have the winning approach in `clover_import.py`. The Clover REST API v3 is the only reliable, production-ready path. Zapier dropped Clover in 2020. n8n has no native Clover node. The Python wrapper library (clover-api-python) is barely maintained. A Clover MCP server exists but is experimental.

**Recommendation**: Extend `clover_import.py` into a proper reusable module (`CC_clover_menu.py`) + wire it into n8n via HTTP Request nodes. Optionally test the Clover MCP server for Hermes natural-language menu changes.

---

## Option 1: Direct Clover REST API v3 (Your Current Approach — BEST)

**What you have**: `~/Desktop/REX/clover_import.py` — already working, imports UFC 328 menu (39 items, 19 modifiers) using Merchant ID `C051UQ41540458` + API token.

**Key endpoints to add**:

```
# Items
GET  /v3/merchants/{mId}/items          — fetch current menu
POST /v3/merchants/{mId}/items          — create item
PUT  /v3/merchants/{mId}/items/{itemId} — update item (name, price, description)

# Pricing
PATCH /v3/merchants/{mId}/items/{itemId} — update price field

# Modifiers
POST /v3/merchants/{mId}/modifier_groups            — create group
POST /v3/merchants/{mId}/items/{itemId}/modifier_groups — link to item

# Bulk native import (Clover Dashboard only, not API)
— Excel .xls/.xlsx, max 5MB, works for mass initial load
— Clover Dashboard → Inventory → Import Items

# Categories
GET/POST /v3/merchants/{mId}/categories
POST /v3/merchants/{mId}/categories/{catId}/items   — add item to category

# Availability (86ing)
PATCH /v3/merchants/{mId}/items/{itemId} → { "available": false }
```

**What to build**: `CC_clover_menu.py` — a clean module with:
- `get_all_items()` — full menu dump
- `create_item(name, price, category, modifiers=[])` — add single item
- `update_price(item_id, new_price)` — price change
- `bulk_create_items(items_list)` — batch from dict/CSV
- `toggle_availability(item_id, available=True)` — 86 item
- `sync_category(category_name, items_list)` — full category replace

**Sources**:
- [Clover Inventory API docs](https://docs.clover.com/dev/docs/working-with-inventory)
- [Managing items and item groups](https://docs.clover.com/dev/docs/managing-items-item-groups)
- [Modifier groups](https://docs.clover.com/dev/docs/managing-modifier-groups-modifiers)
- [Bulk import via Excel](https://docs.clover.com/dev/docs/importing-inventory)

---

## Option 2: Clover MCP Server (Experimental — Worth Testing)

A Clover MCP server (`busybee3333/clover-mcp-2026-complete`) was found on Lobehub claiming **71 API tools** covering the full Clover API — items, orders, customers, modifiers, payments, inventory — all accessible via natural language through an MCP client.

**If this works**, it means you could tell Hermes: *"Update the BBG summer menu — add Modelo Especial at $8, remove the Bud Light pitcher, change the nachos price to $14"* and it executes directly.

**Install (to test)**:
```bash
# Via npx (standard MCP pattern)
npx busybee3333-clover-mcp-2026-complete

# Requires env vars:
CLOVER_API_KEY=<your_token>
CLOVER_MERCHANT_ID=C051UQ41540458
CLOVER_BASE_URL=https://api.clover.com  # or sandbox
```

**Wire into Hermes** at `~/.hermes/profiles/cloud/config.yaml` under the `mcp_servers` section.

**Caveat**: Lobehub page returned empty when fetched — this may be very new or broken. Needs hands-on testing first. Do not trust it for production menu changes without verification.

---

## Option 3: n8n HTTP Request Node (Quick Win for Automation)

No native Clover node in n8n exists. But your existing 6 n8n workflows can hit Clover REST API via **HTTP Request** nodes.

**Pattern for n8n**:
```
Trigger (schedule/webhook) 
  → HTTP Request (GET /v3/merchants/{mId}/items, Auth: Bearer token)
  → Function Node (transform/filter) 
  → HTTP Request (POST/PUT /v3/merchants/{mId}/items)
  → Telegram notification to @Hermes_Cloud_May_bot
```

**Use cases**:
- Weekly seasonal menu swap (scheduled trigger)
- Auto-86 items when inventory runs out (webhook from stock system)
- Sync menu from Google Sheet → Clover (Sheets trigger → Clover POST)

**Sources**: No native Clover n8n template found. Use HTTP Request node + Clover REST API directly.

---

## Option 4: Make.com (if you need a GUI no-code solution)

Make.com (formerly Integromat) has native Clover integration. Can trigger on Clover events (new order, payment) and push actions to Clover (create items, update inventory).

More robust than Zapier for this. Not relevant for your stack since you have n8n.

---

## Option 5: Third-Party Commercial Tools

### Checkmate (restaurant ordering aggregator)
- Syncs Clover menu to DoorDash, Uber Eats, etc.
- Auto-syncs every hour, or instant via button
- Has AI-powered digital menu boards (upsell-based)
- **Relevant if BBG does online ordering** — if you want menu changes in Clover to cascade to delivery platforms automatically
- [Clover Menu Management Guide – Checkmate](https://support.itsacheckmate.com/hc/en-us/articles/8194089585435-Clover-Menu-Management-Guide)

### WISK (bar inventory management)
- Imports Clover menu items, modifiers, categories, prices
- Auto-syncs on scheduled updates
- Tracks actual vs theoretical inventory consumption
- **Relevant if BBG wants real-time bar inventory tracking**
- [WISK + Clover](https://www.wisk.ai/pos/clover)

### Apicbase (food cost & recipe management)
- Clover integration for food cost calculation
- More kitchen-ops focused, less BBG bar menu automation
- [Apicbase + Clover](https://get.apicbase.com/integrations/clover/)

---

## Python Library: clover-api-python

GitHub: [mattlisiv/clover-api-python](https://github.com/mattlisiv/clover-api-python)

```python
from cloverapi.cloverapi_client import CloverApiClient
api_client = CloverApiClient(
    api_key='YOUR_TOKEN',
    merchant_id='C051UQ41540458',
    api_url='https://api.clover.com'
)
# Then: api_client.inventory_service.<method>()
```

**Verdict**: 11 stars, 10 forks, low activity. The lib itself notes it "may be subtly broken." Your existing `clover_import.py` uses raw `requests` calls which is more reliable. Skip this library, extend what you have.

---

## Recommended Build: CC_clover_menu.py

**PAE Proposal** (pending approval):

**Propose**: Build `CC_clover_menu.py` as a proper REX module:
- Reads Clover API token from macOS Keychain (not hardcoded)
- Full CRUD for items, modifiers, categories, pricing
- JSON/dict input for bulk operations
- Dry-run mode (prints changes without executing)
- n8n-friendly: exposes as FastAPI routes at REX `/api/clover/*`

**What exists now**: `clover_import.py` — single-purpose event import, hardcoded token, no dry-run.

**Gap**: No general-purpose menu management, no REX integration, no n8n hookup.

**Approve?** → Build `CC_clover_menu.py` + REX endpoint + n8n template.

---

## Zapier — DEAD END

Zapier officially dropped Clover support in 2020. Do not pursue.

---

*Research completed June 5 2026. Sources verified.*
