# REX Developer Handoff
## Continue.dev + DYAD Setup Guide

---

## What Is REX?

REX is a sovereign AI operating layer built for GOJ (Garden of Joy Adult Day Care, Brooklyn).
It runs **100% locally** — no cloud, no API keys, no data leaving the building.

**Core stack:**
- **Backend:** FastAPI + SQLite (`backend/main.py`, `backend/storage.py`)
- **Frontend:** React single-page app (`frontend/src/App.jsx` — ~4,000 lines)
- **AI Agent:** Rexxie Telegram bot (`backend/rexxie_telegram.py`)
- **Marketing site:** Next.js 14 (`website/`)
- **Models:** Ollama running locally on port 11434

---

## Folder Structure

```
REX/
├── backend/
│   ├── main.py              # FastAPI app, all API routes, RBAC logic
│   ├── storage.py           # SQLite DB layer (staff_users, sessions, documents)
│   ├── rex_role_auth.py     # Role registry (chairman, admin, director, staff)
│   ├── rexxie_telegram.py   # Rexxie bot (morning reports, alerts, classification)
│   ├── rex_ocr_engine.py    # OCR + document classification
│   └── rex_email_watcher.py # Gmail PDF auto-classifier
│
├── frontend/
│   └── src/
│       └── App.jsx          # Entire React frontend (dashboard, RBAC, panels)
│
├── website/                 # Next.js marketing site
│   ├── app/
│   │   ├── layout.jsx       # Root layout with fonts + metadata
│   │   └── page.jsx         # Assembles all section components
│   ├── components/
│   │   ├── GoldEgg.jsx      # Animated SVG brand mark (phases 0/1/2)
│   │   ├── Nav.jsx          # Fixed nav with mobile menu
│   │   ├── Hero.jsx         # Full-screen hero
│   │   ├── Features.jsx     # 8-card feature grid
│   │   ├── About.jsx        # Story + orbital egg
│   │   ├── Process.jsx      # 4-step how it works
│   │   ├── OSVision.jsx     # Interactive desktop widget mockup
│   │   ├── Proof.jsx        # Metrics + trust section
│   │   ├── FinalCTA.jsx     # Waitlist signup with hatching egg
│   │   └── Footer.jsx       # Minimal dark footer
│   └── tailwind.config.js   # Gold palette + custom animations
│
├── .continue/
│   └── config.json          # Continue.dev config (Ollama-backed)
│
├── FRESH_START.command      # Resets auth tokens only (keeps all data)
├── START_REX.command        # Starts backend + Rexxie
└── DEVELOPER_HANDOFF.md     # This file
```

---

## Setting Up Continue.dev

Continue.dev is a VS Code extension that gives you an AI coding assistant powered by your local Ollama models.

### Install
1. Open VS Code
2. Go to Extensions (⇧⌘X)
3. Search `Continue` → install the one by Continue.dev
4. The config is already at `REX/.continue/config.json` — Continue.dev will find it automatically when you open the REX folder

### Using Continue.dev with REX

| Shortcut | Action |
|----------|--------|
| `⌘I` | Inline edit — select code, press to ask Continue to modify it |
| `⌘L` | Open chat panel |
| `Tab` | Accept autocomplete suggestion |
| `@codebase` | Index entire REX codebase for context |
| `/rex-review` | Run REX-specific security + architecture review on selection |
| `/rexxie-check` | Review Rexxie bot logic |

### First time setup
After installing, run in VS Code terminal:
```bash
ollama pull codellama:7b       # fast autocomplete
ollama pull nomic-embed-text   # codebase embeddings
ollama pull mistral            # main chat model
```

Then in the Continue panel, click `@codebase` → `Index codebase` to let it learn REX.

---

## Setting Up DYAD

DYAD is a visual React editor — it lets you see and edit React components with a live preview without touching code directly.

### Install
```bash
npm install -g dyad
```

### Start for the marketing website
```bash
cd ~/Desktop/REX/website
dyad .
```

Open `http://localhost:3000` in your browser. DYAD shows a split view:
- Left: component tree (click any component to select it)
- Right: live preview with click-to-edit

### Key components to edit in DYAD

| Component | What to change |
|-----------|----------------|
| `Hero.jsx` | Headline text, CTA button copy |
| `Features.jsx` | Feature card titles, descriptions, icons |
| `OSVision.jsx` | Widget content, widget colors |
| `Proof.jsx` | Metrics numbers, quote text |
| `FinalCTA.jsx` | Waitlist form, feature chips |
| `Footer.jsx` | Link structure, tagline |

### Editing with DYAD
1. Click any element in the preview to select it
2. The code highlights in the left panel
3. Edit the JSX directly — preview updates live
4. Save when done

---

## Key Architecture Rules (Don't Break These)

### RBAC
```javascript
// In App.jsx — these roles see EVERYTHING
const PRIVILEGED_ROLES = ['chairman', 'admin', 'director']

// Staff only see panels explicitly granted in their panel_permissions JSON
// Panels: attendance, calendar, documents, gmail, telegram, edi, upload
```

### Auth flow
```python
# All protected endpoints in main.py follow this pattern:
token = (authorization or "").replace("Bearer ", "")
session = _get_session(token)
if not session:
    raise HTTPException(status_code=401)
```

### Staff Compliance (NEVER expose to regular staff)
```python
# In main.py — only chairman/admin/director can see this
@app.get("/api/staff/compliance")
def staff_compliance(authorization):
    if not _is_privileged(session):
        raise HTTPException(status_code=403, detail="Restricted.")
```

### Local-first rule
- Never add `fetch()` calls to external APIs
- Never send user data, documents, or operational records outside localhost
- Ollama runs on `http://localhost:11434` — keep it that way

---

## Running REX Locally

```bash
# Start everything
~/Desktop/REX/START_REX.command

# Reset auth only (keeps all data)
~/Desktop/REX/FRESH_START.command

# Default credentials after reset:
# Username: chairman
# Password: chairman2026
```

Backend runs on: `http://localhost:8000`
Frontend runs on: `http://localhost:8000` (served by FastAPI)

---

## Database

SQLite at `~/Desktop/REX/data/rex.db`

Key tables:
- `staff_users` — employees, roles, panel_permissions (JSON array)
- `_active_sessions` — live auth tokens (in-memory dict in main.py)
- `documents` — classified document records
- `goj_signins` — daily attendance
- `classification_patterns` — OCR pattern store (200 rolling examples)

---

## Rexxie (Telegram Bot)

Rexxie is the 24/7 AI agent. She lives in Telegram and:
- Sends morning operations reports at 6 AM
- Fires compliance expiry alerts (staff certifications about to expire)
- Handles document classification questions
- Escalates critical issues to Kato directly

Config in: `backend/rexxie_telegram.py`
Telegram token: stored in `~/.rex/telegram_token` or `.env`

---

## Marketing Website Deploy

The website deploys to Railway.

```bash
cd ~/Desktop/REX/website
npm run build   # verify build first
# Push to GitHub → Railway auto-deploys
```

Or manually:
```bash
npm start  # runs on port 3000
```

---

## What's In Active Development

- **REX OS** — desktop widget layer (draggable widgets, private search, system guardian)
- **Email PDF Watcher** — `rex_email_watcher.py`, runs as background process
- **Multi-facility support** — Blueprint architecture for onboarding facility #2

---

*Built by Kato & REX Intelligence. For questions: run Rexxie.*
