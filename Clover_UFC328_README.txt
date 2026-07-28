BOARDWALK BEER GARDEN — UFC 328 FIGHT NIGHT MENU
Clover Bulk Import — Quick Setup Guide
========================================================

WHAT'S IN THE BUNDLE
--------------------
1) Clover_UFC328_Items.csv          39 menu items
2) Clover_UFC328_Modifier_Groups.csv 19 modifiers across 8 groups
3) Clover_UFC328_README.txt          this file

EVERY ITEM is pre-tagged with:
  • Category:     "UFC 328 Fight Night"
  • Print Label:  HOT or COLD (per the routing below)
  • Description:  full menu copy

ROUTING
-------
  HOT printer  → Appetizers, Soups, Burgers, Mains, Specials, Sides
  COLD printer → Salads, Desserts

========================================================
ONE-TIME PREP IN CLOVER  (do this ONCE before importing)
========================================================

  A. CREATE THE PRINTER LABELS
     Web Dashboard → Setup → Order Receipts → Printers
     Add two label printers (or rename existing labels) named:
        HOT
        COLD
     The names in Clover MUST match the CSV exactly (case-sensitive).
     If your printers are named differently (e.g. "Kitchen", "Salad
     Station"), open Clover_UFC328_Items.csv and find/replace HOT and
     COLD with your printer label names before importing.

  B. CREATE THE CATEGORY  (optional — Clover auto-creates if missing)
     Web Dashboard → Inventory → Categories → + Add Category
     Name: UFC 328 Fight Night

  C. CONFIRM YOUR CLOVER PLAN ALLOWS CSV IMPORT
     Register Lite plans sometimes restrict bulk import. If the import
     option doesn't appear in the menu (step 2 below), you'll need to
     either upgrade or import items manually.

========================================================
IMPORT STEPS
========================================================

STEP 1 — Import Modifier Groups FIRST
  Web Dashboard → Inventory → Modifier Groups
  Click the ⋯ (more) menu in the top-right → "Import"
  Upload: Clover_UFC328_Modifier_Groups.csv
  Confirm groups appear: Wing Sauce, Add Chicken, Nachos Protein,
  Pelmeni Style, Mains Side, Steak Temp, Salad Add-Ons, Caesar Add-Ons

STEP 2 — Import Items
  Web Dashboard → Inventory → Items
  Click the ⋯ (more) menu in the top-right → "Import Items"
  Upload: Clover_UFC328_Items.csv
  Review the preview — Clover will show you exactly what will be
  created. Confirm.

STEP 3 — Verify
  Inventory → Categories → "UFC 328 Fight Night" — should show all 39 items.
  Open one item (e.g. Wings (8)) and confirm:
    • Price is correct
    • Category = UFC 328 Fight Night
    • Print Labels = HOT (or COLD for salads/desserts)
    • Modifier Group is attached (where applicable)

STEP 4 — Test print
  From the Register, ring up one item from each printer label and
  confirm it fires to the correct station.

========================================================
ITEMS BY SECTION (for reference)
========================================================

APPETIZERS
  $ 38.00  [ HOT]  Boardwalk Sampler
  $ 20.00  [ HOT]  Wings (8)
  $ 14.00  [ HOT]  Cheese Quesadilla
  $ 22.00  [ HOT]  Nachos Supreme
  $ 18.00  [ HOT]  Jumbo Mozzarella Sticks
  $ 14.00  [ HOT]  Fried Pickles
  $ 21.00  [ HOT]  Head-On Shrimp
  $ 18.00  [ HOT]  Pelmeni
  $ 15.00  [ HOT]  Pelmeni (Potato)

SOUPS
  $ 18.00  [ HOT]  Solyanka
  $ 16.00  [ HOT]  Borscht

BURGER CORNER
  $ 16.00  [ HOT]  Classic Boardwalk Burger
  $ 18.00  [ HOT]  Cheeseburger
  $ 20.00  [ HOT]  Bacon Cheeseburger
  $ 19.00  [ HOT]  BBQ Burger
  $ 17.00  [ HOT]  Chicken Burger
  $ 26.00  [ HOT]  Juicy Lucy

GRILLED MAINS
  $ 25.00  [ HOT]  Salo Board
  $ 19.00  [ HOT]  Dry Fish Board
  $ 18.00  [ HOT]  Bratwurst
  $ 24.00  [ HOT]  Chicken Shawarma
  $ 26.00  [ HOT]  Full Roasted Baby Chicken
  $ 62.00  [ HOT]  Ribeye Steak
  $ 46.00  [ HOT]  Skirt Steak
  $ 30.00  [ HOT]  Salmon Steak
  $ 22.00  [ HOT]  Lula Kebab (one long)
  $ 27.00  [ HOT]  Chilahach (4 pc)

SPECIALS
  $ 36.00  [ HOT]  Grilled Octopus
  $ 38.00  [ HOT]  Branzino

SALADS
  $ 18.00  [COLD]  Garden Salad
  $ 19.00  [COLD]  Greek Salad
  $ 14.00  [COLD]  Caesar Salad
  $ 36.00  [COLD]  Skirt Steak Salad

SIDELINE
  $  8.00  [ HOT]  Mashed Potatoes
  $ 10.00  [ HOT]  Wasabi Mashed Potatoes
  $ 10.00  [ HOT]  Grilled Vegetables
  $  7.00  [ HOT]  Fries

SWEET VICTORY
  $ 12.00  [COLD]  Cheesecake
  $  7.00  [COLD]  Zefir in Chocolate (3 pc)

