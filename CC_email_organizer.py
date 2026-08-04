#!/usr/bin/env python3
"""
CC_email_organizer.py — LOCAL email organizer for the PA (Kato's privacy rule:
personal data NEVER goes to cloud AI).

Flow (PAE — propose → approve → execute):
  --propose [account] [limit]   READ-ONLY: pull inbox via tools API, classify
                                each message with the LOCAL model (office Ollama
                                via tunnel :11435), emit a proposal card + JSON.
  --apply <proposal.json>       Execute ONLY approved actions (moves/archives;
                                replies are drafted, never auto-sent).

Classification model: huihui_ai/qwen3.5-abliterated:9b (thinking-forced → the
script forces num_predict=2048 so thinking + answer both fit).

Zero outbound except IMAP (via tools API) + the local tunnel. No PHI leaves
the machine. Proposals are written to ~/.rexxie_email_proposals/.
"""
import argparse
import json
import os
import re
import sys
import time
import urllib.request
from datetime import datetime
from pathlib import Path

TOOLS_API = "http://127.0.0.1:8766"
OLLAMA = "http://127.0.0.1:11435"
MODEL = "gemma3:4b"  # fast classifier (4.8s/call) — qwen9b thinking model = 191s/call, way too slow
PROPOSALS_DIR = Path.home() / ".rexxie_email_proposals"

CATEGORIES = ["WORK", "PERSONAL", "BILL", "NEWS", "URGENT"]

# Deterministic sender-domain → category override (wins over the model).
# Instant, zero tokens, reliable for known senders.
DOMAIN_RULES = {
    # billing / payments
    "paypal.com": "BILL", "stripe.com": "BILL", "billing@": "BILL", "invoice@": "BILL",
    "quickbooks": "BILL", "squareup.com": "BILL", "wepay": "BILL", "bill.com": "BILL",
    "chase.com": "BILL", "wellsfargo": "BILL", "bankofamerica": "BILL", "amex": "BILL",
    "capitalone": "BILL", "discover.com": "BILL", "citibank": "BILL", "tdbank": "BILL",
    "venmo": "BILL", "zelle": "BILL", "utility": "BILL", "coned": "BILL", "nationalgrid": "BILL",
    # newsletters / marketing / digests
    "substack.com": "NEWS", "medium.com": "NEWS", "newsletter": "NEWS", "marketing@": "NEWS",
    "promo@": "NEWS", "no-reply@": "NEWS", "noreply@": "NEWS", "mailchimp": "NEWS",
    "sendgrid": "NEWS", "hubspot": "NEWS", "linkedin.com": "NEWS", "facebook.com": "NEWS",
    "twitter.com": "NEWS", "x.com": "NEWS", "instagram": "NEWS", "youtube.com": "NEWS",
    "github.com": "NEWS", "google.com": "NEWS", "googlegroups.com": "NEWS", "comfy": "NEWS",
    # GOJ / GHS / work
    "gardenofjoy": "WORK", "goldhealthsys": "WORK", "hermestigerclaw": "WORK",
    "gmail.com": "WORK",  # Kato's work Gmail default; personal accounts named separately
}

SUBJECT_RULES = [
    ("invoice", "BILL"), ("receipt", "BILL"), ("payment", "BILL"), ("statement", "BILL"),
    ("bill", "BILL"), ("due", "BILL"), ("order confirm", "BILL"),
    ("newsletter", "NEWS"), ("digest", "NEWS"), ("weekly", "NEWS"), ("monthly", "NEWS"),
    ("reminder", "URGENT"), ("action required", "URGENT"), ("action needed", "URGENT"),
    ("urgent", "URGENT"), ("turned off", "URGENT"), ("suspended", "URGENT"),
    ("meeting", "URGENT"), ("invitation", "URGENT"), ("confirm", "URGENT"),
    ("today", "URGENT"), ("overdue", "URGENT"), ("final notice", "URGENT"),
]

CLASSIFY_PROMPT = """Classify this email into ONE category. Answer with exactly one word: WORK, PERSONAL, BILL, NEWS, or URGENT.

Rules:
- BILL: invoices, receipts, payments, bank statements, utility bills
- NEWS: newsletters, promotions, marketing, social notifications, automated digests
- URGENT: time-sensitive, action required today, meeting invites, reminders
- WORK: business (GOJ, GHS, vendors, colleagues, clients)
- PERSONAL: family, friends, personal life

From: {sender}
Subject: {subject}
Body: {body_snippet}

Category:"""


def rule_classify(sender, subject):
    """Deterministic rules first — returns category or None."""
    s = sender.lower()
    for key, cat in DOMAIN_RULES.items():
        if key in s:
            return cat
    subj = subject.lower()
    for key, cat in SUBJECT_RULES:
        if key in subj:
            return cat
    return None


def tools_post(path, payload):
    req = urllib.request.Request(
        TOOLS_API + path,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read().decode())


def ollama_classify(sender, subject, body):
    body_snippet = re.sub(r"\s+", " ", body)[:300]
    prompt = CLASSIFY_PROMPT.format(sender=sender[:80], subject=subject[:120], body_snippet=body_snippet)
    payload = json.dumps({
        "model": MODEL,
        "prompt": prompt,
        "stream": False,
        "num_predict": 48,
        "options": {"temperature": 0.0},
    }).encode()
    req = urllib.request.Request(
        OLLAMA + "/api/generate",
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=120) as r:
        resp = json.loads(r.read().decode())
    text = resp.get("response", "").strip().upper()
    # pick the first known category word in the reply
    cat = next((c for c in CATEGORIES if c in text[:60]), "KEEP")
    action = "flag" if cat == "URGENT" else ("reply" if cat in ("PERSONAL", "WORK") else "archive")
    if cat == "KEEP":
        action = "keep"
    return {"category": cat, "summary": subject[:80], "action": action,
            "reason": f"local classifier ({MODEL})"}


def read_body(account, uid):
    resp = tools_post("/email/read", {"account": account, "uid": str(uid)})
    if "error" in resp:
        return ""
    return resp.get("body", "")[:600]


def propose(account, limit):
    PROPOSALS_DIR.mkdir(parents=True, exist_ok=True)
    resp = tools_post("/email/list", {"account": account, "limit": limit})
    if "error" in resp:
        print(f"ERROR: {resp['error']}")
        sys.exit(1)
    msgs = resp.get("messages", [])
    results = []
    for i, m in enumerate(msgs, 1):
        uid = m["uid"]
        body = read_body(account, uid)
        sender = m.get("from", "")
        subject = m.get("subject", "")
        # deterministic rules first — instant, free, reliable
        ruled = rule_classify(sender, subject)
        if ruled:
            cls = {"category": ruled, "summary": subject[:80],
                   "action": "flag" if ruled == "URGENT" else ("archive" if ruled in ("BILL", "NEWS") else "reply"),
                   "reason": "sender/subject rule"}
        else:
            cls = ollama_classify(sender, subject, body)
        results.append({
            "uid": uid,
            "from": sender,
            "subject": subject,
            "date": m.get("date", ""),
            "category": cls.get("category", "KEEP"),
            "summary": cls.get("summary", ""),
            "action": cls.get("action", "keep"),
            "reason": cls.get("reason", ""),
        })
        print(f"[{i}/{len(msgs)}] {cls.get('category','?'):9s} {subject[:60]}")
        time.sleep(0.3)  # gentle pacing only when the model is called

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = PROPOSALS_DIR / f"proposal_{account}_{ts}.json"
    out.write_text(json.dumps({"account": account, "generated": ts, "messages": results}, indent=2))
    print(f"\n📋 Proposal saved: {out}")
    print(f"   Review: {len(results)} messages. Approve with: --apply {out}")
    return out


def render_card(proposal_path):
    """Render the proposal as a paste-able card for Kato's Telegram."""
    data = json.loads(Path(proposal_path).read_text())
    lines = [f"📬 EMAIL ORGANIZER — {data['account']} ({data['generated']})", ""]
    for m in data["messages"]:
        icon = {"BILL": "🧾", "URGENT": "🔴", "WORK": "💼", "NEWS": "📰", "PERSONAL": "👤"}.get(m["category"], "📥")
        lines.append(f"{icon} **{m['category']}** — {m['subject'][:70]}")
        lines.append(f"   {m['summary'][:80]}")
        lines.append(f"   → {m['action']} ({m['reason'][:60]})")
    lines.append("")
    lines.append("Reply with the UIDs to execute, or 'none'.")
    return "\n".join(lines)


def apply(proposal_path):
    """Execute approved actions. For safety: only archive-by-label is a real
    IMAP move; replies are printed as drafts (never auto-sent)."""
    data = json.loads(Path(proposal_path).read_text())
    account = data["account"]
    print(f"⚠️  APPLY is a no-op stub for safety — the tools API currently has no\n"
          f"move/label endpoint. Draft replies for {len(data['messages'])} msgs below:\n")
    for m in data["messages"]:
        if m["action"] == "reply":
            print(f"  DRAFT reply to {m['from']} re: {m['subject'][:50]}")
            print(f"    (draft only — never auto-sent)")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--propose", action="store_true", help="read-only classify inbox")
    ap.add_argument("--apply", metavar="PROPOSAL_JSON", help="execute approved proposal")
    ap.add_argument("--account", default="default")
    ap.add_argument("--limit", type=int, default=10)
    ap.add_argument("--card", metavar="PROPOSAL_JSON", help="render proposal as card")
    args = ap.parse_args()

    if args.card:
        print(render_card(args.card))
    elif args.apply:
        apply(args.apply)
    elif args.propose:
        propose(args.account, args.limit)
    else:
        ap.print_help()
