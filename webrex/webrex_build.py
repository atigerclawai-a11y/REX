#!/opt/homebrew/bin/python3.11
"""WebRex — unified synapse graph builder.

Reads every knowledge silo (Obsidian vault, Hermes MASTERLIST + palace.db memories,
Claude memory files, Kanban tasks, Antigravity conversations, NotebookLM notebooks)
and emits one webrex_graph.json. Shared ENTITIES are the connective tissue: a concept
mentioned in a Claude memory AND a vault note AND a Kanban task becomes one node that
bridges all three systems. Read-only on every source. Best-effort per silo — a missing
or locked source never aborts the build."""
import os, re, sys, json, glob, sqlite3, subprocess, urllib.request, pathlib, datetime

HOME = pathlib.Path.home()
OUT = HOME / "Desktop/REX/webrex/webrex_graph.json"

# Canonical cross-system entities (the synapse bridges). (label, regex, case-sensitive)
ENTITIES = [
    ("Hermes", r"\bHerm(?:es|ie)\b", False),
    ("Rexxie", r"\bRexxie\b", False),
    ("Claude", r"\bClaude\b", False),
    ("Antigravity", r"\bAntigravity\b", False),
    ("Gemini", r"\bGemini\b", False),
    ("NotebookLM", r"\bNotebookLM\b", False),
    ("Kanban", r"\bKanban\b", False),
    ("Ollama", r"\bOllama\b", False),
    ("GHS", r"\bGHS\b", True),
    ("GOJ", r"\bGOJ\b", True),
    ("BBG", r"\bBBG\b", True),
    ("REX", r"\bREX\b", True),
    ("DataRex", r"\bDataRex\b", False),
    ("CLAUS", r"\bClau[s]\b", False),
    ("Jarvis", r"\bJarvis\b", False),
    ("Tiger Claw", r"\bTiger\s+Claw\b", False),
    ("Victoria", r"\bVictoria\b", False),
    ("Masha", r"\bMasha\b", False),
    ("Telegram", r"\bTelegram\b", False),
    ("Cloudflare", r"\bCloudflare(?:d)?\b", False),
    ("WebRex", r"\bWebRex\b", False),
    ("MASTERLIST", r"\bMASTERLIST\b", True),
]
_compiled = [(lab, re.compile(rx, 0 if cs else re.I)) for lab, rx, cs in ENTITIES]

SYSTEMS = ["Vault", "Hermes", "Claude", "Kanban", "Antigravity", "NotebookLM",
           "Skills", "Agents", "MCPs", "Integrations", "Bots", "Models", "Modules"]

nodes = {}   # id -> node dict
edges = []   # list of (from, to)

def add_node(nid, label, group, value=4, title=""):
    if nid not in nodes:
        nodes[nid] = {"id": nid, "label": label, "group": group, "value": value, "title": title or label}
    return nid

def add_edge(a, b):
    if a in nodes and b in nodes and a != b:
        edges.append({"from": a, "to": b})

def entities_in(text):
    found = set()
    for lab, rx in _compiled:
        if rx.search(text or ""):
            found.add(lab)
    return found

# system hubs
for s in SYSTEMS:
    add_node(f"sys:{s}", s, "system", value=40, title=f"{s} (knowledge silo)")
# entity hubs
for lab, _ in _compiled:
    add_node(f"ent:{lab}", lab, "entity", value=10, title=f"Entity: {lab}")

def link_item(nid, text):
    for e in entities_in(text):
        add_edge(nid, f"ent:{e}")

counts = {}

# 1) Obsidian vault — real files only (never symlink targets)
n = 0
vault = HOME / "Documents/GHS-Vault"
for p in vault.rglob("*.md"):
    if ".obsidian" in p.parts or "graphify-out" in p.parts or "Templates" in p.parts:
        continue
    if p.is_symlink():
        continue
    try:
        txt = p.read_text(errors="ignore")
    except Exception:
        continue
    nid = f"vault:{p.stem}"
    add_node(nid, p.stem[:40], "vault", value=5, title=f"Vault note: {p.name}")
    add_edge(nid, "sys:Vault")
    link_item(nid, p.name + " " + txt[:4000])
    n += 1
counts["vault_notes"] = n

# 2) Hermes — MASTERLIST entities + palace.db memories (grouped by room)
try:
    ml = (HOME / ".hermes/MASTERLIST.md").read_text(errors="ignore")
    add_node("hermes:MASTERLIST", "MASTERLIST", "hermes", value=18, title="Hermes brain (single source of truth)")
    add_edge("hermes:MASTERLIST", "sys:Hermes")
    link_item("hermes:MASTERLIST", ml[:20000])
except Exception:
    pass
m = 0
try:
    con = sqlite3.connect(f"file:{HOME}/.hermes/memories/palace.db?mode=ro", uri=True)
    rooms = {}
    for room, fact in con.execute("SELECT room, fact FROM memories"):
        rooms.setdefault(room or "general", []).append(fact or "")
        m += 1
    con.close()
    for room, facts in rooms.items():
        nid = f"hermes:room:{room}"
        add_node(nid, f"mem:{room}"[:30], "hermes", value=4 + min(len(facts), 12), title=f"Hermes memories — {room} ({len(facts)})")
        add_edge(nid, "sys:Hermes")
        link_item(nid, " ".join(facts)[:8000])
except Exception as e:
    counts["hermes_err"] = str(e)[:80]
counts["hermes_memories"] = m

# 3) Claude memory files
c = 0
for f in glob.glob(str(HOME / ".claude/projects/*/memory/*.md")):
    fn = os.path.basename(f)
    if fn == "MEMORY.md":
        continue
    try:
        txt = pathlib.Path(f).read_text(errors="ignore")
    except Exception:
        continue
    nid = f"claude:{fn[:-3]}"
    add_node(nid, fn[:-3][:34], "claude", value=5, title=f"Claude memory: {fn}")
    add_edge(nid, "sys:Claude")
    link_item(nid, fn + " " + txt[:4000])
    c += 1
counts["claude_memories"] = c

# 4) Kanban cards (hub_kanban.db) + tasks (kanban.db), whichever has rows
k = 0
for db, tbl, cols in [("hub_kanban.db", "cards", ("id", "title", "notes", "lane")),
                      ("kanban.db", "tasks", ("id", "title", "body", "status"))]:
    try:
        con = sqlite3.connect(f"file:{HOME}/.hermes/{db}?mode=ro", uri=True)
        for tid, title, body, lane in con.execute(f"SELECT {','.join(cols)} FROM {tbl}"):
            nid = f"kanban:{tid}"
            add_node(nid, (title or tid)[:34], "kanban", value=4, title=f"[{lane}] {title}")
            add_edge(nid, "sys:Kanban")
            link_item(nid, f"{title} {body or ''}"[:3000])
            k += 1
        con.close()
    except Exception as e:
        counts.setdefault("kanban_err", str(e)[:80])
counts["kanban_cards"] = k

# 5) Antigravity conversations (transcripts)
a = 0
for tr in glob.glob(str(HOME / ".gemini/antigravity-cli/brain/*/.system_generated/logs/transcript.jsonl")):
    cid = pathlib.Path(tr).parts[-4][:8]
    try:
        txt = pathlib.Path(tr).read_text(errors="ignore")[:8000]
    except Exception:
        txt = ""
    nid = f"antigravity:{cid}"
    add_node(nid, f"AG:{cid}", "antigravity", value=6, title=f"Antigravity conversation {cid}")
    add_edge(nid, "sys:Antigravity")
    link_item(nid, txt)
    a += 1
counts["antigravity_convos"] = a

# 6) NotebookLM notebooks (via nlm CLI, best-effort)
nb = 0
try:
    nlm = str(HOME / ".local/bin/nlm")
    if os.path.exists(nlm):
        r = subprocess.run([nlm, "notebook", "list", "--json"], capture_output=True, text=True, timeout=60)
        if r.returncode == 0 and r.stdout.strip().startswith(("[", "{")):
            data = json.loads(r.stdout)
            for d in (data.get("notebooks", data) if isinstance(data, dict) else data):
                title = d.get("title") or "(untitled)"
                nid = f"notebooklm:{d.get('id','')[:8]}"
                add_node(nid, title[:34] or "notebook", "notebooklm", value=10, title=f"NotebookLM: {title}")
                add_edge(nid, "sys:NotebookLM")
                link_item(nid, title)
                nb += 1
except Exception as e:
    counts["notebooklm_err"] = str(e)[:80]
if nb == 0:  # nlm auth can expire — fall back to the known nightly-handoff notebook
    add_node("notebooklm:a89a5e72", "Tiger Claw — Nightly Handoff", "notebooklm", value=12,
             title="NotebookLM: Tiger Claw Nightly Handoff (vault+MASTERLIST bundle)")
    add_edge("notebooklm:a89a5e72", "sys:NotebookLM")
    link_item("notebooklm:a89a5e72", "Tiger Claw Hermes MASTERLIST vault NotebookLM GHS GOJ handoff")
    nb = 1
counts["notebooklm_notebooks"] = nb

# 7) Tiger Claw registry — skills(352)/agents/mcps/integrations/bots/models/modules
#    Source of truth = hub /api/registry (aggregates ~/.claude/skills incl. ECC,
#    ~/.hermes/skills, plugins). Disk sweep fallback if the hub is down.
def _registry():
    try:
        sys.path.insert(0, os.path.expanduser("~/hermes-hub"))
        import importlib
        srv = importlib.import_module("server")
        ck = srv.SESSION_COOKIE + "=" + srv._make_token("kato")
        r = urllib.request.Request("http://127.0.0.1:9000/api/registry"); r.add_header("Cookie", ck)
        return json.loads(urllib.request.urlopen(r, timeout=30).read())
    except Exception as e:
        counts["registry_err"] = str(e)[:80]
        return {}

def add_cat(items, group, sysn, lk="name", dk="description", val=4):
    n = 0
    for it in items or []:
        if isinstance(it, str):
            name, desc = it, ""
        else:
            name = str(it.get(lk) or it.get("name") or "?"); desc = str(it.get(dk) or "")
        nid = f"{group}:{name}"
        add_node(nid, name[:30], group, value=val, title=f"{sysn[:-1]} · {name}: {desc[:140]}")
        add_edge(nid, f"sys:{sysn}")
        link_item(nid, name + " " + desc)
        n += 1
    return n

reg = _registry()
# SKILLS = union of full disk sweep (ALL roots incl ECC) + registry. The registry
# undercounts (352) vs disk (430) — disk is the superset, so sweep every root.
SKILL_ROOTS = ("~/.claude/skills", "~/.hermes/skills", "~/.claude/plugins", "~/Desktop/ECC/skills")
reg_skill_desc = {}
for s in (reg.get("skills") or []):
    if isinstance(s, dict):
        reg_skill_desc[s.get("name")] = str(s.get("description") or "")
    elif isinstance(s, str):
        reg_skill_desc.setdefault(s, "")
seen = set()
for root in SKILL_ROOTS:
    for f in glob.glob(os.path.expanduser(root + "/**/SKILL.md"), recursive=True):
        try:
            t = pathlib.Path(f).read_text(errors="ignore")
        except Exception:
            continue
        mn = re.search(r"^name:\s*(.+)$", t, re.M)
        name = (mn.group(1).strip().strip('"') if mn else pathlib.Path(f).parent.name)
        if name in seen:
            continue
        seen.add(name)
        md = re.search(r"^description:\s*(.+)$", t, re.M)
        desc = (md.group(1).strip().strip('"') if md else reg_skill_desc.get(name, ""))[:140]
        nid = f"skill:{name}"; add_node(nid, name[:30], "skill", value=4, title=f"Skill · {name}: {desc}")
        add_edge(nid, "sys:Skills"); link_item(nid, name + " " + desc)
# any registry-only skills not present on disk (future-proof; currently 0)
for name, desc in reg_skill_desc.items():
    if name and name not in seen:
        seen.add(name); nid = f"skill:{name}"
        add_node(nid, name[:30], "skill", value=4, title=f"Skill · {name}: {desc[:140]}")
        add_edge(nid, "sys:Skills"); link_item(nid, name + " " + (desc or ""))
counts["skills"] = len(seen)
# other categories from the registry (with agent disk fallback)
if reg.get("agents"):
    counts["agents"] = add_cat(reg.get("agents"), "agent", "Agents", val=5)
    counts["mcps"] = add_cat(reg.get("mcps"), "mcp", "MCPs")
    counts["integrations"] = add_cat(reg.get("integrations"), "integration", "Integrations")
    counts["bots"] = add_cat(reg.get("bots"), "bot", "Bots", val=5)
    counts["models"] = add_cat(reg.get("models"), "model", "Models", lk="provider", dk="models")
    counts["modules"] = add_cat(reg.get("modules"), "module", "Modules")
else:
    ag = 0
    for f in glob.glob(os.path.expanduser("~/.claude/agents/*.md")):
        try:
            t = pathlib.Path(f).read_text(errors="ignore")
        except Exception:
            continue
        name = os.path.basename(f)[:-3]
        md = re.search(r"^description:\s*(.+)$", t, re.M); desc = (md.group(1).strip().strip('"') if md else "")[:140]
        nid = f"agent:{name}"; add_node(nid, name[:30], "agent", value=5, title=f"Agent · {name}: {desc}")
        add_edge(nid, "sys:Agents"); link_item(nid, name + " " + desc); ag += 1
    counts["agents"] = ag

# size entity nodes by degree
deg = {}
for e in edges:
    deg[e["from"]] = deg.get(e["from"], 0) + 1
    deg[e["to"]] = deg.get(e["to"], 0) + 1
for nid, node in nodes.items():
    if node["group"] == "entity":
        node["value"] = 6 + min(deg.get(nid, 0), 40)

graph = {
    "generated": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
    "meta": {"counts": counts, "nodes": len(nodes), "edges": len(edges)},
    "nodes": list(nodes.values()),
    "edges": edges,
}
OUT.write_text(json.dumps(graph))
# also emit a JS file the local HTML can include without CORS (file:// fetch is blocked)
(OUT.parent / "webrex_data.js").write_text("window.WEBREX_GRAPH=" + json.dumps(graph) + ";")

# ── Post-process: build skill synapse graph for interactive visualization ──
_skill_nodes = [n for n in nodes.values() if n["id"].startswith("skill:")]
_entity_edges = {}
for e in edges:
    if e["from"].startswith("ent:") and e["to"] in {n["id"] for n in _skill_nodes}:
        _entity_edges.setdefault(e["from"], set()).add(e["to"])
    elif e["to"].startswith("ent:") and e["from"] in {n["id"] for n in _skill_nodes}:
        _entity_edges.setdefault(e["to"], set()).add(e["from"])

# Skill category mapping (same as the HTML)
_cats = {
    "GOJ": ["goj", "ocr-", "sign-in", "kitchen", "cyrillic", "carecenta", "driver-route", "attendance", "menu-"],
    "BBG": ["bbg", "reservation", "resy", "owner.com", "beer-garden", "olympus"],
    "Data Extraction": ["extract", "ghl", "hha", "web-extract", "scrape", "data-export", "portal"],
    "OSINT": ["osint", "investigat", "scout", "business-intel", "corporate-intel"],
    "Apple / Mac": ["apple", "imessage", "macos", "computer-use", "imsg", "remind", "find-my"],
    "Hub / Infra": ["tiger-claw", "jarvis", "hub", "rex-", "native-app", "hermes-infra", "gateway", "screensaver"],
    "DevOps": ["dashboard-health", "system-recovery", "cross-system", "pre-change", "backup", "fix-", "recover"],
    "Hermes Core": ["hermes-", "hermie-", "kanban-", "memory-system", "petdex", "telephony", "claust", "emergency-"],
    "Software Dev": ["plan", "spike", "tdd", "test-driven", "code-review", "simplify-code", "debug", "build-handoff"],
    "Creative": ["ascii", "comfyui", "songwrit", "heartmula", "p5js", "excalidraw", "manim", "design-visual", "baoyu", "humanizer"],
    "ML / AI": ["llama", "vllm", "huggingface", "eval", "weights-and-biases", "obliteratus", "audiocraft", "segment-anything"],
    "Productivity": ["airtable", "google-workspace", "notion", "powerpoint", "nano-pdf", "obsidian"],
    "Email": ["himalaya", "gmail", "imap", "smtp"],
    "GitHub": ["github", "gh-", "pr-"],
    "Research": ["arxiv", "blogwatcher", "notebooklm", "polymarket", "llm-wiki"],
    "Social": ["social-media", "instagram", "telegram-post"],
    "Smart Home": ["openhue", "hue"],
    "Media": ["youtube", "gif-search", "songsee"],
    "Red Team": ["godmode", "jailbreak"],
    "Data Science": ["jupyter", "notebook"],
    "Design": ["frontend-design", "brand-voice", "claude-design", "architecture-diagram", "design-md", "popular-web"],
    "General Dev": ["react", "django", "docker", "kubernetes", "python", "rust", "fastapi", "database", "api-", "security"],
}
def _categorize(nid):
    name = nid.replace("skill:", "").lower()
    for cat, pats in _cats.items():
        for p in pats:
            if p in name:
                return cat
    return "Other"

_skill_data = []
for s in _skill_nodes:
    sid = s["id"].replace("skill:", "")
    title = s.get("title", "")
    desc = ""; parts = title.split(":", 2)
    if len(parts) >= 3: desc = parts[2].strip()
    _skill_data.append({"id": sid, "cat": _categorize(s["id"]), "desc": desc[:120]})

# Build co-occurrence edges from entity bridges
_pair_weights = {}
for ent, sk_set in _entity_edges.items():
    sk_list = list(sk_set)
    for i in range(len(sk_list)):
        for j in range(i+1, len(sk_list)):
            pair = tuple(sorted([sk_list[i].replace("skill:", ""), sk_list[j].replace("skill:", "")]))
            _pair_weights[pair] = _pair_weights.get(pair, 0) + 1

# Add intra-category functional edges (dense: all-to-all for small cats, hub-and-spoke for large)
_cat_skills = {}
for s in _skill_data:
    _cat_skills.setdefault(s["cat"], []).append(s["id"])
for cat, sk_list in _cat_skills.items():
    n = len(sk_list)
    if n <= 12:
        for i in range(n):
            for j in range(i+1, n):
                pair = tuple(sorted([sk_list[i], sk_list[j]]))
                _pair_weights[pair] = _pair_weights.get(pair, 0) + 2
    else:
        for h in sk_list[:2]:
            for other in sk_list[2:]:
                pair = tuple(sorted([h, other]))
                _pair_weights[pair] = _pair_weights.get(pair, 0) + 2

# Add cross-category functional edges
_cross_pairs = [
    ("GOJ", "DevOps"), ("GOJ", "Hub / Infra"), ("GOJ", "Data Extraction"),
    ("GOJ", "Productivity"), ("GOJ", "Email"),
    ("BBG", "Email"), ("BBG", "Data Extraction"), ("BBG", "Productivity"),
    ("Data Extraction", "OSINT"), ("Data Extraction", "Productivity"),
    ("OSINT", "Research"), ("OSINT", "Social"),
    ("Hub / Infra", "Hermes Core"), ("Hub / Infra", "DevOps"),
    ("Hub / Infra", "Software Dev"), ("Hub / Infra", "Apple / Mac"),
    ("Hermes Core", "DevOps"), ("Hermes Core", "Software Dev"),
    ("Software Dev", "GitHub"), ("Software Dev", "General Dev"),
    ("General Dev", "GitHub"), ("General Dev", "ML / AI"),
    ("Creative", "Media"), ("Creative", "Design"), ("Creative", "ML / AI"),
    ("ML / AI", "Data Science"), ("ML / AI", "Research"),
    ("Productivity", "Email"), ("Productivity", "Design"),
    ("Red Team", "ML / AI"),
]
for cat_a, cat_b in _cross_pairs:
    sa = _cat_skills.get(cat_a, [])
    sb = _cat_skills.get(cat_b, [])
    if not sa or not sb: continue
    for i in range(min(3, len(sa))):
        for j in range(min(3, len(sb))):
            pair = tuple(sorted([sa[i], sb[j]]))
            _pair_weights[pair] = _pair_weights.get(pair, 0) + 1

_cat_colors = {
    "GOJ":"#1de9b6","BBG":"#ffd740","Data Extraction":"#40c4ff","OSINT":"#ff6e40",
    "Apple / Mac":"#a5d6ff","Hub / Infra":"#b388ff","DevOps":"#ff5252",
    "Hermes Core":"#d4af37","Software Dev":"#69f0ae","Creative":"#ff80ab",
    "ML / AI":"#448aff","Productivity":"#84ffff","Email":"#ea80fc","GitHub":"#ffffff",
    "Research":"#64ffda","Social":"#ffab40","Smart Home":"#ffff00","Media":"#e040fb",
    "Red Team":"#ff1744","Data Science":"#00e5ff","Design":"#f48fb1",
    "General Dev":"#90caf9","Other":"#78909c",
}

_cat_counts = {}
for s in _skill_data:
    _cat_counts[s["cat"]] = _cat_counts.get(s["cat"], 0) + 1

_edge_list = [{"source": a, "target": b, "weight": w} for (a, b), w in _pair_weights.items()]
_synapse = {
    "skills": _skill_data,
    "edges": _edge_list,
    "categories": {c: {"count": n, "color": _cat_colors.get(c, "#78909c")} for c, n in _cat_counts.items()}
}
(OUT.parent / "webrex_skill_graph.json").write_text(json.dumps(_synapse))
counts["synapse_edges"] = len(_edge_list)

# Auto-deploy to hub www directory for the website
_www = HOME / "hermes-hub/www"
if _www.is_dir():
    import shutil
    shutil.copy(OUT.parent / "webrex_skill_graph.json", _www / "webrex_skill_graph.json")
    counts["deployed"] = True

print(json.dumps({"nodes": len(nodes), "edges": len(edges), **counts}, indent=2))
