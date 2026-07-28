# CC_PAE_PROPOSALS_june4.md
# Gold Health Systems — PAE Proposals Awaiting Kato Approval
# Generated: June 4, 2026 — Phase Builder Session
# Propose → Approve → Execute

---

## Existing PAE Proposals (from CC_PHASE_STATUS.md)

- **PAE-1**: Switch Hermie to Gemma 4 28B — see CC_PHASE_STATUS.md §PAE-1
- **PAE-2**: Install hermes-dreaming plugin — command ready at `CC_install_hermes_dreaming.command`
- **PAE-3**: Activate rex_unified_enforcer.py — swap line 84 in rex_rexxie_telegram_bot.py

---

## NEW PAE-4: Fix launchd Nightly Job WorkingDirectory

**Problem:** 38+ consecutive nightly backup failures since Apr 20.
Root cause: launchd jobs running from `~/Desktop/REX` path — macOS TCC
blocks `getcwd` for launchd agents with Desktop paths.

**Impact:** No automated offsite backup since Apr 20. Evening GOJ reports unreliable.

**Change:** Add `WorkingDirectory` key to affected plists, pointing to `~/.rex-venv/`
working area (already used for launchd production venv).

**Files affected:**
- `~/Library/LaunchAgents/com.rex.backend.plist`
- `~/Library/LaunchAgents/com.goj.datarex.plist`
- Any other launchd jobs with backup/report scripts

**Exact change (after approval):**
```bash
# 1. For each failing plist, add:
#    <key>WorkingDirectory</key>
#    <string>/Users/mainsobhelper</string>
# 2. Reload plist
# 3. Verify next run succeeds

# CC_fix_launchd_workdir.command will be built after PAE approval
```

**Reversible:** Yes — remove WorkingDirectory key  
**Pre-req:** None — safe to execute any time  
**Verification:** Next launchd run at 5AM → no getcwd error in log

---

## NEW PAE-5: Activate Jarvis HUD (Phase 19)

**Problem:** Phase 19 (Jarvis HUD) shows plists exist but exited clean. No plist
names found in ~/Library/LaunchAgents/ matching jarvis/tigerclaw/hud.

**Step 1 — Confirm TigerClaw API:**
```bash
curl -s http://localhost:27226/health
# Expect: 200 OK with JSON. If not: need to find/restart TigerClaw plist.
```

**Step 2 — Find Jarvis plist:**
```bash
ls ~/Library/LaunchAgents/ | grep -iE "jarvis|tiger|hud"
find ~/Desktop -name "*.plist" 2>/dev/null | grep -iE "jarvis|tiger"
```

**Step 3 — If plist found, load it (after approval):**
```bash
launchctl load ~/Library/LaunchAgents/[jarvis-plist-name].plist
sleep 15
# Verify: curl http://localhost:[jarvis-port]/health
```

**Step 4 — Connect to Command Center Phase 2 (P2-D/P2-E)**

**Reversible:** Yes — launchctl unload  
**Pre-req:** TigerClaw :27226 must be responding  
**Verification:** Jarvis HUD renders in browser + receives stats from TigerClaw

---

## NEW PAE-6: Wire akc_tokenizer_v2 as Gate 1 (Enable Secure Mode)

**File built:** `CC_akc_tokenizer_v2.py` (June 4, 2026 — this session)

**Change required in backend/main.py:**
```python
# In the Secure Mode chat pipeline, replace the stub tokenizer with:
from CC_akc_tokenizer_v2 import Gate1Firewall

# In the chat handler (Secure Mode path):
firewall = Gate1Firewall(session_id=request.session_id)
safe_text, token_map = firewall.inbound(user_message)
# ... LLM call with safe_text ...
final_response = firewall.outbound(llm_response)
```

**Pre-req:** Run self-test first:
```bash
cd ~/Desktop/REX
source ~/debate-chamber/.venv/bin/activate
python CC_akc_tokenizer_v2.py
# All 6 tests should pass.
# Optionally install Presidio for NER mode:
# pip install presidio-analyzer presidio-anonymizer spacy --break-system-packages
# python -m spacy download en_core_web_lg
```

**Impact:** Gate 1 active — Secure Mode PHI can now flow to cloud AI (tokenized).
This is the most important Gate in the entire system.

**Reversible:** Yes — revert import in main.py  
**Verification:** Send a message with a test name+SSN → verify token in outbound log → verify restoration in response

---

## NEW PAE-7: Activate Phase 14/15 Backend in main.py

**Files built (June 4, 2026):**
- `core/business_isolation.py` — Phase 14
- `backend/rex_profiles.py` — Phase 14
- `backend/rex_agent_forge.py` — Phase 15
- `state/business_registry.json`, `state/venture_registry.json`, `state/profiles.json`
- `state/agent_forge_registry.json`

**Change required in backend/main.py startup:**
```python
from core.business_isolation import get_isolation_enforcer
from backend.rex_profiles import ProfileEngine
from backend.rex_agent_forge import AgentForge

# In startup lifespan:
isolation_enforcer = get_isolation_enforcer()
profile_engine = ProfileEngine()
agent_forge = AgentForge()

# Add REST endpoints:
@app.get("/api/profiles")
async def get_profiles():
    return profile_engine.status()

@app.get("/api/forge/agents")
async def list_agents():
    return {"agents": agent_forge.list_agents()}
```

**Reversible:** Yes — remove imports and endpoints  
**Verification:** `curl http://localhost:8000/api/profiles` → returns business context list

---

## NEW PAE-8: Activate Phase 17 WebRex Backend

**Files built (June 4, 2026):**
- `backend/rex_webrex_topology.py`
- `backend/rex_webrex_ops.py`
- `state/webrex_topology.json`, `state/webrex_operations.json`

**Change required in backend/main.py:**
```python
from backend.rex_webrex_topology import WebrexTopology
from backend.rex_webrex_ops import WebrexOps

webrex_topology = WebrexTopology()
webrex_ops = WebrexOps()

@app.get("/api/webrex/topology")
async def get_topology():
    return webrex_topology.get_live_topology()

@app.get("/api/webrex/ops")
async def get_ops():
    return webrex_ops.ops_summary()
```

**Reversible:** Yes  
**Verification:** `curl http://localhost:8000/api/webrex/topology` → returns topology JSON

---

*All PAE proposals require Kato's explicit approval before execution.*
*Reply with: "PAE-[N] approved" or "PAE-[N] rejected".*
*Hermes will then proceed with Execute phase only after approval.*
