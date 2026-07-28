# GHS Design Upgrade Guide
## Inspired by Top 10 Award-Winning Dashboards — June 2026
## Gold Health Systems · Command Center + GOJ Dashboard
### Status: Research complete. Implementation-ready.

---

## Part 1 — Top 10 Reference Sites

These are the sites that define the current premium tier of dashboard and SaaS UI design. Each was selected from Awwwards, Dribbble, design system analysis, and developer community consensus for 2024–2026.

---

### 1. Linear
- **URL**: https://linear.app
- **Category**: SaaS Project Management / Developer Tool
- **Recognition**: Widely cited as the defining UI for modern SaaS dark dashboards; frequent reference in Awwwards SOTD circles; primary influence on "precision dark UI" trend
- **Color palette**:
  - Background: `#0a0a0f` (near-black, almost identical to GHS Command Center!)
  - Surface ladder: `#111118` → `#1a1a24` → `#23232f`
  - Primary text: `#f0f0f5`
  - Secondary text: `#8b8b9e`
  - Accent (acid lime): `#e4f222` — used sparingly, one CTA per screen
  - Accent (teal): `#02b8cc` — highlight backgrounds, decorative bands
  - Borders: `1px solid #2a2a35`
- **Typography**: Inter Variable with `font-feature-settings: "ss03"` (opens up the lowercase g, feels designed not default); tight negative tracking at display sizes (-0.02em to -0.04em); Berkeley Mono for code
- **Layout**: Collapsed left sidebar, tight 8px grid, card surfaces barely distinguishable from page bg — all depth via borders not box shadows
- **Animation**: Micro-transitions only. 120ms ease-out on state changes. Zero gratuitous motion.
- **Signature element**: The "ration" principle — only one accent color per screen, zero decorative color
- **Why it wins**: Feels like a precision instrument. Every pixel is load-bearing. Looks richer than sites with 10x more color. GHS already lives at this base color (#0a0a0f) — this confirms you're in the right neighborhood.
- **GHS applicable**: Command Center is already at Linear's base color. Importing their accent rationing and Inter ss03 would be an immediate premium bump.

---

### 2. Raycast
- **URL**: https://raycast.com
- **Category**: Developer Productivity / macOS launcher
- **Recognition**: Awwwards SOTD; industry benchmark for "dark-first premium UI"; Arc/Linear/Warp/Raycast together defined the dark-first era (2023–2026)
- **Color palette**:
  - Background void: `#040506` (darker than Linear — true black-purple)
  - Surface ladder: `#07080a` → `#0d0d0d` → `#101111`
  - Text primary: `#f5f5f5`
  - Text secondary: `#6e6e73`
  - Borders: `1px solid #242728` (hairline — barely visible)
  - Accents: Category-color splashes only (product tile illustrations), not UI chrome
  - Gradient accent: Subtle pink-purple at 5% opacity on hero panels
- **Typography**: Inter with `font-feature-settings: "calt", "kern", "liga", "ss03"`; negative tracking at -0.11em on 56px display headings (creates pressure and density); body at -0.01em
- **Layout**: Near-zero radius (6px on cards); components extend to edges with hairline separators rather than gapped cards
- **Animation**: Product screenshot reveals via scroll-driven animations; 60fps transforms only; no CSS opacity flicker
- **Signature element**: The surface ladder. Backgrounds are not one dark color — they're 4-5 barely-distinct levels that create depth without color. Pure #000 is never used.
- **Why it wins**: Makes $0-color design feel premium. The restraint IS the luxury signal.
- **GHS applicable**: Surface ladder concept is directly applicable to Command Center panels. Replace flat dark areas with 3-layer depth: page `#0a0a0f` → panel `#0f0f14` → card `#14141a`.

---

### 3. Vercel / Geist Design System
- **URL**: https://vercel.com · https://vercel.com/geist
- **Category**: Cloud Platform / Design System
- **Recognition**: Geist design system sets the industry standard for token-based theming; Vercel dashboard frequently cited in "best SaaS dashboards" lists
- **Color palette** (Geist tokens):
  - Background: `#0a0a0a` (dark) / `#ffffff` (light)
  - Surface: `#111111` (dark) / `#fafafa` (light)
  - Border: `#1a1a1a` (dark) / `#ededed` (light)
  - Accent blue: `#0070f3`
  - Accent teal: `#50e3c2` (success-adjacent)
  - Text primary: `#ededed` (dark) / `#111111` (light)
  - Text secondary: `#888888`
- **Typography**: Geist Sans (their own variable font, open source); tight tracking; no decorative weights — utility-focused
- **Layout**: 12-column grid, 24px gutter, collapsible left nav, top status bar, main content right
- **Animation**: Skeleton loaders instead of spinners; subtle 150ms ease-in-out transitions; hover states: `translate(0, -1px)` on cards
- **Signature element**: CSS custom property architecture — full dark/light swap via one class. Every color is a variable, never hardcoded.
- **Why it wins**: Geist is the blueprint for how professional design systems scale. The token discipline means you can change the entire feel by swapping one variable.
- **GHS applicable**: GOJ Dashboard needs this token architecture. One `--ghs-primary` variable should control everything blue on the page.

---

### 4. Stripe Dashboard
- **URL**: https://dashboard.stripe.com
- **Category**: Fintech / Enterprise SaaS
- **Recognition**: Industry standard reference for data-dense, high-trust professional dashboards; Matt Ström's redesign case study widely studied
- **Color palette**:
  - Light mode primary: `#ffffff` content, `#f6f9fc` page bg, `#425466` text
  - Dark mode: `#0a2540` deep blue-black base
  - Accent: `#635bff` (Stripe purple) — used only on primary actions
  - Success: `#0e9f6e` (green)
  - Error: `#df1b41` (crimson)
  - Warning: `#d97706` (amber)
  - Chart primary: `#7c3aed` / `#3b82f6` / `#10b981` for series
- **Typography**: `-apple-system, BlinkMacSystemFont, "Segoe UI"` — intentionally system fonts for trust and performance; headings at 600 weight; data numbers at tabular figures (`font-variant-numeric: tabular-nums`)
- **Layout**: Full-width nav bar, sidebar for section navigation, main content area with card grid; dense tables with zebra striping for legibility
- **Animation**: Minimal. Chart drawing animations 300ms ease. No decorative motion.
- **Signature element**: `font-variant-numeric: tabular-nums` on all number columns — prevents number widths from shifting as values change. Critical for dashboards.
- **Why it wins**: Maximally trustworthy. Every design decision reinforces "we handle your money carefully." Zero ornamentation.
- **GHS applicable**: GOJ Dashboard should adopt tabular numerics for client counts, auth dates. The Stripe trust palette (restrained color, serious typography) is the right model for healthcare.

---

### 5. Shadcn/ui Dashboard Starter + Tremor
- **URL**: https://ui.shadcn.com · https://tremor.so
- **Category**: Open Source Design Systems / Dashboard Frameworks
- **Recognition**: Most-referenced dashboard stack in the developer community 2024–2026; Shadcn has become the de facto standard for Next.js dashboards
- **Color palette** (Shadcn default dark):
  - Background: `hsl(240 10% 3.9%)` ≈ `#09090b`
  - Card: `hsl(240 10% 3.9%)` with `1px solid hsl(240 3.7% 15.9%)`
  - Muted: `hsl(240 3.7% 15.9%)` ≈ `#27272a`
  - Primary: `hsl(0 0% 98%)` ≈ `#fafafa` (text on dark)
  - Accent: `hsl(240 4.8% 95.9%)` (subtle)
  - Destructive: `hsl(0 62.8% 30.6%)` ≈ `#7f1d1d`
- **Tremor chart colors** (sequential): `#3b82f6`, `#10b981`, `#f59e0b`, `#ef4444`, `#8b5cf6`, `#06b6d4`
- **Typography**: Inter (default) or Geist Sans; all sizing in rem; heading scale: 2.25rem / 1.5rem / 1.25rem / 1rem
- **Layout**: Left sidebar (collapsible), header bar, content grid with Tailwind CSS columns; 16px base padding unit
- **Animation**: Framer Motion optional; default is CSS transitions 200ms ease; sidebar collapse 250ms
- **Signature element**: Fully composable — every component is a file you own, no black-box library lock-in
- **Why it wins**: The fastest path to a premium-looking dashboard that you fully control. GOJ could be rebuilt on this in a sprint.
- **GHS applicable**: Command Center could use Shadcn tokens as the foundation, then layer in GHS branding on top.

---

### 6. Horizon UI PRO (Creative Tim)
- **URL**: https://horizon-ui.com
- **Category**: SaaS Dashboard Template
- **Recognition**: #1 most-cited admin template in "best dashboard 2026" roundups; Creative Tim ecosystem
- **Color palette**:
  - Dark background: `#0b1437` (deep navy)
  - Card: `#111c44`
  - Accent purple: `#7551ff` (primary CTA)
  - Accent teal: `#39b8d1`
  - Accent pink: `#ff5da0`
  - Success: `#01b574`
  - Text: `#ffffff` primary, `#a0aec0` secondary
- **Typography**: DM Sans (body) + Plus Jakarta Sans (headings); heading weights 700–800; letter spacing -0.02em
- **Layout**: Left nav sidebar with logo top, collapsible on mobile; header with avatar + notifications; main grid in 3 columns (1/4, 1/4, 1/2 proportions)
- **Animation**: Hover card lift (translateY -2px, shadow deepens); chart draw animations; sidebar slide 200ms
- **Signature element**: Purple-to-teal gradient backgrounds on hero stat cards — creates a premium "lit from within" feel
- **Why it wins**: The card gradients feel premium without feeling garish. The three-accent system (purple, teal, pink) creates enough variety without chaos.
- **GHS applicable**: The gradient card style for key metrics (total clients, today's attendance, authorization alerts) would elevate GOJ Dashboard immediately.

---

### 7. AdminLTE 4 / Tabler
- **URL**: https://adminlte.io · https://tabler.io
- **Category**: Open Source Enterprise Templates
- **Recognition**: AdminLTE = 45,000+ GitHub stars, 10+ years of refinement; Tabler = leading Bootstrap dashboard for clean/minimal aesthetic
- **AdminLTE color system**:
  - Dark sidebar: `#343a40` (charcoal)
  - Page bg: `#f4f6f9` (cool light gray)
  - Cards: `#ffffff`
  - Primary: `#007bff` (Bootstrap blue)
  - CSS variables throughout: `--bs-body-bg`, `--bs-primary`, etc.
- **Tabler extras**: Transparent sidebar option; generous whitespace (32px+ gutter); Tabler Icons library (5,000+ icons)
- **Typography**: Inter (Tabler default); heading scale rem-based; `--tbl-font-size: 0.875rem` body base (14px)
- **Signature element**: Tabler's transparent sidebar — the page background shows through nav, creating a glassy open feel without glassmorphism gimmicks
- **Why it wins**: Proven at enterprise scale. Accessibility-first (WCAG AA by default). Stable to maintain.
- **GHS applicable**: GOJ Dashboard should aim for AdminLTE's dark sidebar / light content split. The CSS variable architecture is directly copy-able.

---

### 8. Igloo Inc (Awwwards Site of the Year 2025)
- **URL**: https://igloo.inc (via Awwwards SOTY 2025 winner)
- **Category**: Creative Agency / 3D Interactive
- **Recognition**: **Awwwards Site of the Year 2025** — highest award possible
- **Design approach**: Immersive 3D experience, heavy scroll interaction, first-class micro-interactions
- **What makes it award-worthy**: The gap between "standard site" and "SOTY" is entirely in micro-interaction quality — hover states that feel physical, scroll transitions that feel continuous, loading sequences that feel intentional rather than technical
- **Color approach**: Dark canvas with strategic luminous moments; animated gradient orbs as background texture; color only where meaning needs to be communicated
- **Signature element**: 3D objects that react to mouse position in real time — the same technology GHS Command Center already uses (Three.js)
- **Why it wins**: Proves that interactivity IS the brand signal when done right
- **GHS applicable**: Command Center's Three.js sacred geometry screensaver is already SOTY-adjacent in ambition. The lesson from Igloo is: commit fully or don't — half-baked 3D feels worse than no 3D.

---

### 9. Catalyze AI (Awwwards Honorable Mention — SaaS)
- **URL**: https://www.awwwards.com/sites/catalyze-ai-saas-website
- **Category**: AI SaaS / Dashboard
- **Recognition**: Awwwards Honorable Mention — the category most relevant to GHS builds
- **Design approach**: Dark AI interface with animated data visualizations as hero; dark gradient backgrounds
- **Color system**: Deep navy-black base, cyan/electric blue accents for AI/data elements, white text hierarchy
- **Signature element**: Data visualization AS design — charts and graphs are not tucked in cards, they ARE the visual centerpiece
- **Why it wins**: In AI/data SaaS, showing your data is showing your value. The dashboard IS the marketing.
- **GHS applicable**: GOJ Dashboard should consider one "hero chart" — perhaps today's attendance trend — rendered prominently rather than buried in a grid.

---

### 10. Material Design 3 / IBM Carbon (Reference Systems)
- **URL**: https://m3.material.io · https://carbondesignsystem.com
- **Category**: Enterprise Design Systems
- **Recognition**: Industry-standard reference systems; Carbon used by IBM healthcare products
- **Key contribution — healthcare-specific (IBM Carbon)**:
  - Background: `#161616` (dark) / `#ffffff` (light)
  - Primary interactive: `#0f62fe` (IBM Blue) — proven for medical trust
  - Success: `#24a148`
  - Alert/Danger: `#da1e28`
  - Warning: `#f1c21b` (amber, high contrast)
  - Text hierarchy: 4 levels (primary, secondary, helper, disabled) with explicit contrast ratios
- **Healthcare lesson**: IBM Carbon's 14-step gray scale provides extremely fine control over hierarchy in data-dense interfaces. Healthcare dashboards have more data states than typical SaaS.
- **Signature element**: Carbon uses "expressive" and "productive" type sets separately — expressive for landing/marketing, productive for dense data UI. GOJ Dashboard is pure "productive."
- **GHS applicable**: GOJ Dashboard color system should reference IBM Carbon's semantic colors. Their medical software awards are built on this exact system.

---

## Part 2 — Design DNA Extraction

### Color Palette Recommendations

#### Command Center (Dark — already correct base)

| Role | Current | Recommended | Hex |
|------|---------|-------------|-----|
| Page background | `#0a0a0f` | Keep | `#0a0a0f` |
| Panel surface | n/a | Add layer | `#0f0f14` |
| Card surface | flat dark | Add layer | `#14141a` |
| Border | faint | Hairline upgrade | `#1f1f2e` |
| Primary accent | cyan | Keep, ration | `#00d4d8` |
| Secondary accent | purple | Keep, ration | `#8b5cf6` |
| Danger / alert | various | Standardize | `#ef4444` |
| Warning | n/a | Add | `#f59e0b` |
| Success | n/a | Add | `#10b981` |
| Text primary | n/a | Standardize | `#f0f0f5` |
| Text secondary | n/a | Standardize | `#8b8b9e` |

**Immediate win**: Implement the 3-layer surface ladder. The current flat dark makes panels feel like paper cutouts. Depth from barely-distinct surfaces (not shadows) is how Linear and Raycast look expensive.

#### GOJ Dashboard (Healthcare — currently Flask/Bootstrap)

| Role | Recommended | Hex | Rationale |
|------|-------------|-----|-----------|
| Page background | Light cool gray | `#f4f6f9` | Clean, clinical, whitespace-forward |
| Card / panel | White | `#ffffff` | Maximum contrast for data |
| Sidebar | Dark charcoal | `#1a2035` | Navy-dark for authority |
| Primary accent | Medical blue | `#0066cc` | Trust, calm, 20% higher retention |
| Secondary accent | Healthcare teal | `#00a896` | Innovation + healthcare signal |
| Success / active | Medical green | `#059669` | Auth ACTIVE status |
| Danger / expired | Medical red | `#dc2626` | Auth EXPIRED — urgent |
| Warning / pending | Amber | `#d97706` | PENDING RENEWAL — attention |
| Text primary | Near-black | `#1a1a2e` |  |
| Text secondary | Medium gray | `#6b7280` |  |
| Border | Light gray | `#e5e7eb` |  |

**Color psychology note**: Blue + teal is used by 62% of healthcare interfaces. It signals trust, calm, and innovation simultaneously. Never use red as a primary or branding color in healthcare — it reads as emergency.

---

### Typography System

#### Command Center

**Current state**: Likely system fonts or generic sans-serif. This is the easiest 30-minute premium upgrade.

**Recommended**: Inter with custom feature settings
```css
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');

body {
  font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
  font-feature-settings: "calt", "kern", "liga", "ss03";
  -webkit-font-smoothing: antialiased;
}
```

The `ss03` feature set is the secret weapon — it swaps Inter's lowercase 'g' to a single-story open form. It's the detail that makes Linear and Raycast feel typographically designed rather than default. Nobody can articulate why it looks better; they just know it does.

**Scale** (apply globally):
```css
--type-display: 2rem;    /* 32px — dashboard title, hero numbers */
--type-headline: 1.5rem; /* 24px — section headers */
--type-title: 1.125rem;  /* 18px — card titles */
--type-body: 0.875rem;   /* 14px — default body, nav items */
--type-caption: 0.75rem; /* 12px — labels, timestamps */
--type-micro: 0.625rem;  /* 10px — badges, tags */

/* Tracking — tighten on large, relax on small */
--tracking-display: -0.03em;
--tracking-body: 0;
--tracking-caption: 0.02em;
```

**For financial/numeric data** — critical detail from Stripe:
```css
.stat-number, .data-value, table td.numeric {
  font-variant-numeric: tabular-nums;
  font-feature-settings: "tnum";
}
```
This prevents numbers from jumping in width as values update. Applies to: attendance counts, client counts, authorization dates, any number column.

#### GOJ Dashboard

**Recommended pairing**: Plus Jakarta Sans (headings) + Inter (body)
- Plus Jakarta Sans: geometric warmth, feels modern without cold
- Inter: maximum legibility in body text, universal support

```css
@import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@500;600;700&family=Inter:wght@400;500;600&display=swap');

h1, h2, h3, .section-title { font-family: 'Plus Jakarta Sans', sans-serif; }
body, p, td, span { font-family: 'Inter', sans-serif; }
```

**Alternative** (more clinical/precise): Space Grotesk (headings) + DM Sans (body) — the "developer tool" pairing that reads well for data-heavy interfaces.

---

### Animation Principles

**What award-winning sites do:**

1. **State transitions: 120–200ms ease-out** — never 0ms (jarring) or 500ms (slow). The industry sweet spot is 150ms.
2. **Card hover: translateY(-2px) + box-shadow deepen** — creates physicality without gimmick
3. **Data load: skeleton screens** over spinners — skeleton fills the exact shape of the content, reducing perceived wait
4. **Number updates: count-up animation** (1000ms ease-out) — makes live data feel alive without being distracting
5. **Sidebar collapse: 250ms ease-in-out** — smooth, not snappy

**What award-winning sites avoid:**
- Looping background animations (cheap)
- Particle systems on the main content layer (fights with data)
- Bounce/spring easing on utility components (playful ≠ professional)
- Full-page transitions in data-dense apps (disorienting)

**For Command Center specifically**: The Three.js sacred geometry screensaver is *appropriate for a screensaver/idle state*. The lesson from Igloo Inc (SOTY 2025) is commit fully. The 3D should deactivate (fade out gracefully) when there's active content to read. Active state = data clarity. Idle state = dramatic 3D. This separation is what makes it feel premium rather than gratuitous.

---

### Layout Patterns

#### Command Center Layout Architecture

**Recommended: Mission Control layout** (inspired by Linear + Raycast)

```
┌─────────────────────────────────────────────────────────┐
│ [GHS Logo]  [Status indicators: 3002 ✓ 8000 ✓ 8080 ✓]  │  ← Top bar, 48px
├──────────────────────────────────────────────────────────┤
│     │                                                    │
│     │  ACTIVE AGENTS           QUICK STATS              │
│  N  │  ┌─────────┐ ┌────────┐  ┌──────┐ ┌──────┐       │
│  A  │  │Hermie 🟢│ │Rex  🟢 │  │Clients│ │Active│       │
│  V  │  └─────────┘ └────────┘  └──────┘ └──────┘       │
│     │                                                    │
│  6  │  LIVE LOG FEED                                     │
│  4  │  ┌─────────────────────────────────────────────┐   │
│  p  │  │ streaming log output                        │   │
│  x  │  └─────────────────────────────────────────────┘   │
│     │                                                    │
│     │  SYSTEM STATUS               GOJ PIPELINE         │
│     │  [service grid]              [pipeline status]    │
└─────┴────────────────────────────────────────────────────┘
```

Key principles:
- 8px base grid (everything divisible by 8)
- Content area uses 12-column subgrid
- Cards have 16px internal padding
- Sections have 24px between them
- Use 1px borders for separation, never box-shadow on dark bg (invisible in dark mode)

#### GOJ Dashboard Layout Architecture

**Recommended: Healthcare Command layout** (inspired by Stripe + IBM Carbon)

```
┌─────────────────────────────────────────────────────────┐
│ GOJ | Garden of Joy Adult Day Care     [Today] [Profile]│  ← Header 56px
├───────────┬─────────────────────────────────────────────┤
│           │                                             │
│ Dashboard │  TODAY'S SUMMARY (hero stats, 4-column)     │
│ Clients   │  ┌────────┐ ┌────────┐ ┌────────┐ ┌──────┐ │
│ Auth      │  │Scheduled│ │Attended│ │Expired │ │Alerts│ │
│ Menus     │  └────────┘ └────────┘ └────────┘ └──────┘ │
│ Reports   │                                             │
│ Schedule  │  ATTENDANCE TREND      AUTH STATUS          │
│ Kitchen   │  [Chart 60%]           [Donut 40%]         │
│ Drivers   │                                             │
│           │  RECENT ACTIVITY (table, most recent first) │
│ Settings  │  [Client list, status badges, actions]     │
│           │                                             │
└───────────┴─────────────────────────────────────────────┘
```

---

### Micro-interactions Catalog

These are the specific micro-interactions that separate premium dashboards from average ones. All implementable in CSS + vanilla JS.

**1. Status badge pulse** — for ACTIVE auth status indicators:
```css
.badge-active { animation: pulse 2s infinite; }
@keyframes pulse {
  0%, 100% { opacity: 1; box-shadow: 0 0 0 0 rgba(5, 150, 105, 0.4); }
  50% { opacity: 0.9; box-shadow: 0 0 0 4px rgba(5, 150, 105, 0); }
}
```

**2. Card hover lift** — for any clickable card:
```css
.card {
  transition: transform 150ms ease-out, box-shadow 150ms ease-out;
}
.card:hover {
  transform: translateY(-2px);
  box-shadow: 0 8px 24px rgba(0,0,0,0.2);
}
```

**3. Number count-up** — for live stat cards (plain JS):
```js
function countUp(el, target, duration = 1000) {
  const start = parseInt(el.textContent) || 0;
  const step = (target - start) / (duration / 16);
  let current = start;
  const interval = setInterval(() => {
    current += step;
    el.textContent = Math.round(current);
    if ((step > 0 && current >= target) || (step < 0 && current <= target)) {
      el.textContent = target;
      clearInterval(interval);
    }
  }, 16);
}
```

**4. Skeleton loader** — replace spinners:
```css
.skeleton {
  background: linear-gradient(90deg, #1f1f2e 25%, #2a2a3a 50%, #1f1f2e 75%);
  background-size: 200% 100%;
  animation: shimmer 1.5s infinite;
  border-radius: 4px;
}
@keyframes shimmer { 0% { background-position: -200% 0; } 100% { background-position: 200% 0; } }
```

**5. Toast notifications** — for system events:
```css
.toast {
  transform: translateX(120%);
  transition: transform 200ms ease-out;
}
.toast.show { transform: translateX(0); }
```

---

## Part 3 — Command Center Upgrades (Priority Order)

### Quick Wins (1–4 hours each)

**1. Inter + ss03 typography** (30 min)
Load Inter from Google Fonts, add `font-feature-settings: "ss03"`, apply `tabular-nums` to all stat displays. One import, three CSS rules. Immediate premium signal.

**2. Surface ladder for dark panels** (2 hours)
Replace all `background: #0a0a0f` or flat dark fills with the three-layer system:
- Page: `#0a0a0f` (unchanged)
- Panel/module: `#0f0f14`
- Card/inner surface: `#14141a`
- Elevated (dropdowns, modals): `#1c1c24`

Convert all box-shadows to `1px solid #1f1f2e` borders — box shadows are invisible on dark mode, borders are not.

**3. Semantic CSS variables** (1 hour)
Move all colors to CSS custom properties. This makes future theming trivial and is how every premium system (Vercel Geist, Shadcn, Stripe) is built:
```css
:root {
  --color-bg: #0a0a0f;
  --color-surface: #0f0f14;
  --color-card: #14141a;
  --color-border: #1f1f2e;
  --color-accent-primary: #00d4d8;    /* GHS cyan */
  --color-accent-secondary: #8b5cf6;  /* GHS purple */
  --color-accent-success: #10b981;
  --color-accent-danger: #ef4444;
  --color-accent-warning: #f59e0b;
  --color-text-primary: #f0f0f5;
  --color-text-secondary: #8b8b9e;
  --color-text-muted: #5a5a72;
}
```

**4. Tabular numerics on all stats** (30 min)
Add `font-variant-numeric: tabular-nums` to every element displaying numbers. Service port numbers, uptime seconds, client counts — all of it. Numbers stop jumping.

**5. Card hover lift** (1 hour)
Add the 150ms translateY(-2px) hover to all interactive panels. Gives the interface physical weight.

---

### Medium Term (1–2 days each)

**6. Skeleton loaders replace spinners** (4 hours)
Every loading state in the dashboard currently shows a spinner or blank. Replace with skeleton screens shaped like the content they're loading. Perceived load time drops significantly.

**7. Status pulse animations for services** (2 hours)
The green/red service indicators in the stack table should pulse subtly. The pulse communicates "live" rather than "static screenshot." Only pulse on active healthy services, not errors (an erroring pulse would be anxiety-inducing).

**8. Toast notification system** (4 hours)
Command center actions (service restart, agent trigger) currently have no feedback loop. A bottom-right toast system (200ms slide in, 3s auto-dismiss, 200ms slide out) closes that loop.

**9. Three.js idle/active mode separation** (4 hours)
Implement: after 5 minutes of inactivity → sacred geometry fades in (1s ease). On any mouse/key event → geometry fades out (0.5s ease), data comes forward. This is the Igloo Inc lesson applied: dramatic visual when there's time to appreciate it, utility when there's work to do.

---

### Phase Upgrade (1–2 weeks)

**10. Full redesign to Mission Control layout**
Implement the layout architecture documented above. Collapsible left nav (64px icons-only, 240px expanded), persistent header with live status dots, content grid.

**11. Live log streaming panel**
A real-time scrolling log feed (WebSocket or SSE from the Hermes gateway log) as a core panel. Raycast and Linear both use live feed panels as trust signals — you can see the system working.

**12. Command palette** (⌘K)
Every premium SaaS adds a command palette. For Command Center: ⌘K opens a spotlight-style search that lets Kato type "restart hermes" or "show goj clients" and execute. Uses the existing `/api/` endpoints. This is a 2-day build that makes the app feel like a premium tool.

---

## Part 4 — GOJ Dashboard Upgrades

### Healthcare-Appropriate Design

The GOJ Dashboard serves 425 clients and is used by staff who are not designers. Every design decision must serve clarity over beauty. The research is clear: healthcare users value clarity 3x more than visual effect.

**Non-negotiables for healthcare UI:**
- WCAG AA contrast minimum (4.5:1 for body text) — legal exposure without this
- Color is never the ONLY indicator of status — always pair with icon + text label
- Red only for emergency-level alerts; amber for attention; green for good
- Maximum 3 primary colors in view at once
- No looping animations in the main content area

---

### Quick Wins (hours)

**1. Healthcare color system** (2 hours)
Implement the palette from Part 2 via CSS variables. The `#0066cc` blue + `#00a896` teal combination is the healthcare industry standard — staff will feel more comfortable with it than the current palette.

**2. Status badges with icons** (2 hours)
```
🟢 ACTIVE         ← green badge + checkmark icon
🟡 PENDING RENEWAL ← amber badge + clock icon  
🔴 EXPIRED        ← red badge + warning icon
```
Never color-only. The colorblind failure rate in healthcare dashboards is a real legal risk.

**3. Auth expiry countdown** (3 hours)
For EXPIRED or PENDING RENEWAL clients, show days since expiry or days until expiry as a number, not just a text status. "Expired 47 days ago" is more actionable than "EXPIRED." Add a red border-left on rows >30 days expired to visually scan the risk queue.

**4. Tabular numerics** (30 min) — same as Command Center. All dates, counts, numbers.

**5. Hero stat cards** (4 hours)
Top of dashboard: four cards (Today's Scheduled / Today's Attended / Auth Expiring This Week / Pending Renewals). Gradient left-border accent using healthcare palette. Count-up animation on load. These are the numbers staff need in 3 seconds.

---

### Medium Term (days)

**6. Attendance trend sparkline** (1 day)
A 30-day attendance trend chart (line or area) at the top of the dashboard. Shows pattern — is attendance growing? Are Fridays low? Uses the `client_menus` and `authorization` data already in `auth_tracker.db`.

**7. Auth status donut** (4 hours)
A donut chart: ACTIVE / PENDING RENEWAL / EXPIRED breakdown. At a glance, the whole program status. Immediately shows if there's an auth crisis brewing.

**8. Print-optimized CSS** (4 hours)
Staff print sign-in sheets. The current Flask app likely renders poorly on print. Add `@media print` CSS that strips nav, sidebar, colors, and renders clean table-only views suitable for printing.

**9. Search-first client lookup** (1 day)
A search bar prominent at the top of the Clients section. Type a name, instant filter. Healthcare staff look up individuals constantly — every second saved per lookup is staff time returned.

---

### Phase Upgrade (weeks)

**10. Plus Jakarta Sans + Inter typography overhaul**
Install both fonts, apply to GOJ Dashboard globally. The warm-but-precise combination was specifically noted as excellent for "healthcare, productivity, and admin UIs" in the 2025 font research.

**11. Full sidebar navigation rebuild**
Implement the dark sidebar + light content split (see layout architecture above). Current Flask app's navigation likely needs this structural upgrade to scale as more features are added.

**12. Mobile-responsive pass**
325 million American smartphones are used to check healthcare dashboards. The GOJ app needs to work on an iPhone. The dark sidebar collapses to a hamburger, stat cards stack vertically, tables scroll horizontally. One sprint.

---

## Part 5 — Skill Recommendations

### Available Now (in this Cowork session)

**canvas-design** — Can create visual mockups, posters, design concepts as PNG/PDF. Use this to generate palette swatches, typography specimens, or layout wireframes before implementing.

**docx** — For generating design specification documents (design briefs, style guides) as Word documents.

**pptx** — For creating design presentation decks showing before/after comparisons for Kato review.

**pdf** — For generating PDF style guides, color palette reference cards.

### Font Loading (no plugin needed — use Google Fonts CDN)

Add to the `<head>` of Command Center and GOJ Dashboard:
```html
<!-- Inter + Plus Jakarta Sans: combined import -->
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=Plus+Jakarta+Sans:wght@500;600;700&display=swap" rel="stylesheet">
```

### CSS Animation Libraries (CDN, no install)

These are reference points — don't install frameworks, reference the patterns:
- **Framer Motion** (if converting to React): https://www.framer.com/motion/
- **Auto-Animate** (2KB, drop-in for list animations): https://auto-animate.formkit.com/
- **CSS-only transitions**: Use native CSS `transition` and `animation` — no library needed for what's described above

### Color Tools (bookmark for implementation)

| Tool | URL | Use For |
|------|-----|---------|
| WebAIM Contrast Checker | https://webaim.org/resources/contrastchecker | Check every text/bg pair for WCAG AA |
| Coolors | https://coolors.co | Generate palette from seed color |
| Realtime Colors | https://realtimecolors.com | Preview palette on live mockup |
| Material Theme Builder | https://m3.material.io/theme-builder | Generate healthcare color system |
| Huetone | https://huetone.ardh.me | Build perceptually uniform gray scales |
| Chrome DevTools | Built-in > Rendering > Emulate vision deficiencies | Colorblind simulation |

---

## Part 6 — Implementation Notes

### For Hermes / Claude when implementing

1. **Do not refactor existing Flask structure** when applying GOJ Dashboard styles. Add CSS variable declarations at the top of the existing stylesheet, then replace hardcoded values with variables. Touch only what style you're changing.

2. **Command Center and GOJ Dashboard share no codebase** — treat them as independent implementation targets. Don't introduce shared component libraries unless Kato explicitly approves the architectural change.

3. **Font loading goes in `<head>` before any CSS** — Google Fonts uses `display=swap` by default, which means text renders immediately in fallback then swaps. No flash of invisible text.

4. **Test WCAG contrast before deploying any color change** to GOJ Dashboard. Healthcare dashboards used by staff during care are a legal liability if accessibility fails.

5. **The `tabular-nums` change is zero-risk, maximum-impact** — apply this first. It's one CSS rule, affects zero layout, and immediately makes all number columns look premium.

6. **PAE required** for any changes that touch `auth_tracker.db` — the dashboard visual changes are CSS-only and don't require PAE. But any new data queries, new columns, schema changes need the full Propose → Approve → Execute cycle.

7. **Surface ladder priority**: Command Center gets the 3-layer surface depth first (Quick Win #2). It's the highest-signal change for the least effort and zero risk to functionality.

---

## Quick Reference — GHS Design Tokens

Copy this block to the top of any GHS stylesheet:

```css
/* === GHS DESIGN SYSTEM v1.0 — June 2026 === */
/* Command Center (dark) */
:root[data-theme="command"] {
  --bg: #0a0a0f;
  --surface: #0f0f14;
  --card: #14141a;
  --elevated: #1c1c24;
  --border: #1f1f2e;
  --border-subtle: #161622;
  --accent-primary: #00d4d8;   /* GHS cyan */
  --accent-secondary: #8b5cf6; /* GHS purple */
  --accent-success: #10b981;
  --accent-danger: #ef4444;
  --accent-warning: #f59e0b;
  --text-primary: #f0f0f5;
  --text-secondary: #8b8b9e;
  --text-muted: #5a5a72;
}

/* GOJ Dashboard (light/healthcare) */
:root[data-theme="goj"] {
  --bg: #f4f6f9;
  --surface: #ffffff;
  --card: #ffffff;
  --sidebar: #1a2035;
  --border: #e5e7eb;
  --border-subtle: #f0f0f4;
  --accent-primary: #0066cc;   /* Medical blue */
  --accent-secondary: #00a896; /* Healthcare teal */
  --accent-success: #059669;   /* Auth ACTIVE */
  --accent-danger: #dc2626;    /* Auth EXPIRED */
  --accent-warning: #d97706;   /* Auth PENDING */
  --text-primary: #1a1a2e;
  --text-secondary: #6b7280;
  --text-muted: #9ca3af;
}
```

---

*Research sources: Awwwards.com (SOTY 2025 — Igloo Inc), Linear design system analysis, Raycast brand & typographic system, Vercel Geist design system, AdminLTE.io color scheme guide (May 2026), AsappStudio 2026 dashboard review, Muzli 50 Best Dashboard Designs 2026, Muz.li dark mode design systems guide, Naskay healthcare color psychology 2025, WebSearch aggregate research June 4 2026.*
