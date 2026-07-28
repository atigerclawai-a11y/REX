#!/usr/bin/env python3
"""Victoria Batch Caller v3 — hardcodes working config, reads key from .env only."""
import http.client, ssl, json, sqlite3, sys
from pathlib import Path
from datetime import date, timedelta

# ── Hardcoded config (working values) ──
FROM_NUMBER = "+164****3781"
AGENT_ID = "agent_26e3746829ae6e174f4a012bbd"
TEST_PHONE = "+134****2860"

# ── Read API key from .env ──
env_text = (Path.home() / "Desktop" / "REX" / ".env").read_text()
API_KEY = ""
for line in env_text.splitlines():
    if line.startswith("RETELL_API_KEY="):
        API_KEY = line.split("=", 1)[1].strip().strip('"').strip("'")
        break

# ── Date ──
TOMORROW = date.today() + timedelta(days=1)
MONTHS_RU = ["января","февраля","марта","апреля","мая","июня","июля","августа","сентября","октября","ноября","декабря"]
TOMORROW_STR = f"{TOMORROW.day} {MONTHS_RU[TOMORROW.month-1]} {TOMORROW.year}"

DB_PATH = Path.home() / "Documents" / "goj files" / "dashboard" / "auth_tracker.db"
REPORT_PATH = Path.home() / "Desktop" / "REX" / "CC_victoria_report.html"
CTX = ssl.create_default_context()

def call_retell(phone: str, name: str) -> dict:
    payload = json.dumps({
        "from_number": FROM_NUMBER,
        "to_number": phone,
        "override_agent_id": AGENT_ID,
        "ignore_e164_validation": True,
        "metadata": {"call_type": "tomorrow", "client_name": name},
        "retell_llm_dynamic_variables": {"client_name": name, "tomorrow_date": TOMORROW_STR}
    }).encode("utf-8")
    
    conn = http.client.HTTPSConnection("api.retellai.com", timeout=15, context=CTX)
    conn.request("POST", "/v2/create-phone-call", body=payload, headers={
        "Content-Type": "application/json", "Authorization": f"Bearer {API_KEY}"
    })
    resp = conn.getresponse()
    body = resp.read().decode("utf-8")
    conn.close()
    data = json.loads(body)
    if resp.status >= 400:
        return {"call_id": None, "status": "failed", "error": body[:200]}
    return {"call_id": data.get("call_id"), "status": data.get("call_status", "initiated")}

def format_phone(raw: str) -> str:
    if raw.startswith("+"): return raw
    return "+1" + "".join(c for c in raw if c.isdigit())

def log_call(phone, call_id, status, error=""):
    with sqlite3.connect(str(DB_PATH)) as db:
        db.execute("INSERT INTO victoria_call_log(call_type,phone_number,retell_call_id,status,notes) VALUES(?,?,?,?,?)",
                   ("tomorrow_confirmation", phone, call_id, status, error))
        db.commit()

def get_clients():
    with sqlite3.connect(str(DB_PATH)) as db:
        db.row_factory = sqlite3.Row
        return [dict(r) for r in db.execute("""
            SELECT DISTINCT c.name, c.phone FROM client_schedule s
            JOIN clients c ON s.client_name = c.name
            WHERE s.day_of_week = 'TH' AND c.phone IS NOT NULL AND c.phone != ''
        """).fetchall()]

def report(results):
    total = len(results)
    ok = sum(1 for r in results if r.get("call_id"))
    rows = ""
    for r in results:
        cid = r.get("call_id") or "—"
        cls = "ok" if cid != "—" else "fail"
        rows += f'<tr><td>{r["name"]}</td><td>{r["phone"]}</td><td>{cid}</td><td class="{cls}">{r.get("status","")}</td><td>{r.get("error","")[:100]}</td></tr>\n'
    html = f"""<!DOCTYPE html><html><head><meta charset="utf-8"><title>Victoria {TOMORROW}</title>
<style>body{{background:#0d1117;color:#c9d1d9;font-family:-apple-system,sans-serif;margin:20px}}h1{{color:#58a6ff}}table{{width:100%;border-collapse:collapse}}th,td{{padding:8px 12px;border-bottom:1px solid #30363d}}th{{color:#8b949e}}.ok{{color:#3fb950}}.fail{{color:#f85149}}.stats{{display:flex;gap:20px;margin:15px 0}}.stat{{background:#161b22;padding:12px 20px;border-radius:6px}}.stat span{{font-size:24px;font-weight:bold}}</style></head><body>
<h1>📞 Victoria — Tomorrow Confirmation</h1><p>{TOMORROW} ({TOMORROW_STR})</p>
<div class="stats"><div class="stat">✅ <span class="ok">{ok}</span></div><div class="stat">❌ <span class="fail">{total-ok}</span></div><div class="stat">📊 <span>{total}</span></div></div>
<table><tr><th>Name</th><th>Phone</th><th>Call ID</th><th>Status</th><th>Error</th></tr>{rows}</table></body></html>"""
    REPORT_PATH.write_text(html)
    print(f"📄 {REPORT_PATH}")

if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "test"
    
    if mode == "test":
        print(f"🧪 {TEST_PHONE}")
        r = call_retell(TEST_PHONE, "Kato")
        print(f"   call_id={r.get('call_id')} status={r.get('status')}")
        if r.get("error"): print(f"   {r['error']}")
        log_call(TEST_PHONE, r.get("call_id"), r.get("status"), r.get("error", ""))
    
    elif mode == "run":
        clients = get_clients()
        print(f"📞 {len(clients)} clients for {TOMORROW} ({TOMORROW_STR})")
        results = []
        for i, c in enumerate(clients):
            phone = format_phone(c["phone"])
            print(f"  [{i+1}/{len(clients)}] {c['name']} → {phone}", end=" ", flush=True)
            r = call_retell(phone, c["name"])
            r["name"], r["phone"] = c["name"], phone
            results.append(r)
            log_call(phone, r.get("call_id"), r.get("status"), r.get("error", ""))
            print("✅" if r.get("call_id") else "❌")
        report(results)
    
    elif mode == "preview":
        clients = get_clients()
        print(f"📋 {len(clients)} for {TOMORROW} ({TOMORROW_STR})")
        for c in clients[:10]:
            print(f"  {c['name']} — {c['phone']}")
        if len(clients) > 10: print(f"  ...+{len(clients)-10}")
