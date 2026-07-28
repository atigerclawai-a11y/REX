#!/usr/bin/env python3
"""
REX Queue Processor — Mac-side daemon
======================================
Runs every 15 minutes via launchd (full Mac network access).

What it does:
  1. Reads prompt files from ~/Desktop/REX/ai_queue/*.prompt
  2. Calls nemobot at localhost:5000 for each AI (Grok/ChatGPT/Gemini)
  3. Saves responses to ~/Desktop/REX/training_reports/
  4. Sends Telegram notification to Chairman
  5. Optionally sends email (configure smtp in rex_queue_config.json)
  6. Moves processed files to ai_queue/processed/

Prompt file format (JSON, written by Sunday Cowork task):
  {
    "ai": "grok",
    "topic": "Real-Time Knowledge & Current Events Integration",
    "day": "tuesday",
    "date": "2026-03-31",
    "prompt": "You are training REX..."
  }

Usage:
  python3 rex_queue_processor.py          # process queue
  python3 rex_queue_processor.py --test   # test nemobot + telegram connections
  python3 rex_queue_processor.py --status # show queue status
"""

import sys
import os
import json
import logging
import shutil
import smtplib
import urllib.request
import urllib.error
from datetime import datetime
from pathlib import Path
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# ── Paths ─────────────────────────────────────────────────────────────────────
REX_DIR    = Path(__file__).parent
CONFIG_PATH = REX_DIR / "rex_queue_config.json"

def load_config() -> dict:
    if not CONFIG_PATH.exists():
        raise FileNotFoundError(f"Config not found: {CONFIG_PATH}")
    return json.loads(CONFIG_PATH.read_text())

CFG = load_config()

QUEUE_DIR   = Path(CFG["paths"]["queue_dir"]).expanduser()
REPORTS_DIR = Path(CFG["paths"]["reports_dir"]).expanduser()
LOG_FILE    = Path(CFG["paths"]["log_file"]).expanduser()
DONE_DIR    = QUEUE_DIR / "processed"

QUEUE_DIR.mkdir(parents=True, exist_ok=True)
REPORTS_DIR.mkdir(parents=True, exist_ok=True)
DONE_DIR.mkdir(parents=True, exist_ok=True)

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(str(LOG_FILE), mode="a"),
    ],
)
log = logging.getLogger("rex-queue")

# ── Nemobot caller ────────────────────────────────────────────────────────────

def call_nemobot(prompt: str, ai_name: str) -> str:
    """
    Send a prompt to nemobot's local Flask API.
    Tries the configured endpoint, with fallbacks for common Flask patterns.
    """
    nb_cfg = CFG["nemobot"]
    base_url = nb_cfg["url"]
    prompt_key = nb_cfg.get("prompt_key", "prompt")
    model_key = nb_cfg.get("model_key", "model")
    response_key = nb_cfg.get("response_key", "response")
    timeout = nb_cfg.get("timeout_seconds", 120)

    model = CFG.get("ai_models", {}).get(ai_name, "")
    body = {prompt_key: prompt}
    if model:
        body[model_key] = model
    body["ai"] = ai_name  # always include the AI name

    payload = json.dumps(body).encode("utf-8")
    headers = {"Content-Type": "application/json"}

    # Optional API key auth (e.g. nemobot or LibreChat requires a bearer token)
    api_key = nb_cfg.get("api_key", "").strip()
    if api_key:
        hdr_name   = nb_cfg.get("api_key_header", "Authorization")
        hdr_prefix = nb_cfg.get("api_key_prefix", "Bearer ")
        headers[hdr_name] = f"{hdr_prefix}{api_key}"

    req = urllib.request.Request(
        base_url,
        data=payload,
        headers=headers,
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read())
            # Try common response key patterns
            for key in [response_key, "response", "content", "text", "result", "output", "message"]:
                if key in data:
                    return data[key]
            # If no known key found, return the full response as string
            return json.dumps(data)
    except urllib.error.HTTPError as e:
        body_text = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Nemobot HTTP {e.code}: {body_text[:200]}")
    except urllib.error.URLError as e:
        raise RuntimeError(f"Nemobot unreachable at {base_url}: {e.reason}")

# ── Telegram sender ───────────────────────────────────────────────────────────

def send_telegram(message: str) -> bool:
    tg = CFG["telegram"]
    token = tg.get("token", "")
    chat_id = tg.get("chat_id", "")
    if not token or not chat_id:
        log.warning("Telegram not configured in rex_queue_config.json")
        return False

    # Telegram has a 4096 char limit
    if len(message) > 4000:
        message = message[:3990] + "\n...[truncated]"

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = json.dumps({
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "HTML",
    }).encode("utf-8")

    req = urllib.request.Request(
        url, data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            result = json.loads(resp.read())
            if result.get("ok"):
                log.info("Telegram sent successfully")
                return True
            log.error(f"Telegram error: {result}")
            return False
    except Exception as e:
        log.error(f"Telegram send failed: {e}")
        return False

def send_telegram_file(caption: str, filename: str, content: str) -> bool:
    """Send a text file as a Telegram document attachment."""
    tg = CFG["telegram"]
    token = tg.get("token", "")
    chat_id = tg.get("chat_id", "")
    if not token or not chat_id:
        return False

    import io
    url = f"https://api.telegram.org/bot{token}/sendDocument"
    file_bytes = content.encode("utf-8")

    boundary = "----REXBoundary"
    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="chat_id"\r\n\r\n'
        f"{chat_id}\r\n"
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="caption"\r\n\r\n'
        f"{caption}\r\n"
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="document"; filename="{filename}"\r\n'
        f"Content-Type: text/plain\r\n\r\n"
    ).encode() + file_bytes + f"\r\n--{boundary}--\r\n".encode()

    req = urllib.request.Request(
        url, data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            result = json.loads(resp.read())
            return result.get("ok", False)
    except Exception as e:
        log.error(f"Telegram file send failed: {e}")
        return False

# ── Email sender ──────────────────────────────────────────────────────────────

def send_email(subject: str, body: str) -> bool:
    em_cfg = CFG.get("email", {})
    if not em_cfg.get("enabled", False):
        log.info("Email disabled in config — skipping")
        return False

    app_password = em_cfg.get("app_password", "").strip()
    if not app_password:
        log.warning("Email app_password not set in rex_queue_config.json")
        return False

    try:
        username = em_cfg["username"]
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"]    = username
        msg["To"]      = username
        msg.attach(MIMEText(body, "plain"))

        with smtplib.SMTP(em_cfg["smtp_host"], em_cfg["smtp_port"]) as server:
            server.ehlo()
            server.starttls()
            server.login(username, app_password)
            server.send_message(msg)

        log.info(f"Email sent: {subject}")
        return True
    except Exception as e:
        log.error(f"Email send failed: {e}")
        return False

# ── Rexxie private notification ──────────────────────────────────────────────
REXXIE_TG_CONFIG = Path.home() / "Desktop" / "REX" / "rex_rexxie_telegram_config.json"

ANALYSIS_ICONS = {
    "compare":   "⚖️",
    "mistakes":  "🔍",
    "learn":     "📚",
    "summarize": "📋",
    "full":      "🧠",
}

def _send_training_result_via_rexxie(orig_filename: str, analysis_type: str,
                                      response: str, report_file: str) -> bool:
    """
    Send training document analysis results privately to Kato via Rexxie bot.
    Sends a header message, then the analysis in chunks (≤4096 chars each).
    """
    if not REXXIE_TG_CONFIG.exists():
        log.warning("Rexxie config not found — cannot send training result")
        return False

    try:
        d = json.loads(REXXIE_TG_CONFIG.read_text())
        token   = d.get("bot_token", "")
        chat_id = d.get("owner_chat_id", 0)
    except Exception as e:
        log.error(f"Rexxie config read error: {e}")
        return False

    if not token or not chat_id:
        return False

    def _tg_send(text: str) -> bool:
        url     = f"https://api.telegram.org/bot{token}/sendMessage"
        payload = json.dumps({"chat_id": chat_id, "text": text, "parse_mode": "HTML"}).encode()
        req     = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"}, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                return json.loads(resp.read()).get("ok", False)
        except Exception as e:
            log.error(f"Rexxie TG send failed: {e}")
            return False

    icon  = ANALYSIS_ICONS.get(analysis_type, "🧠")
    fname = Path(orig_filename).name

    # Header message
    header = (
        f"🐢 <b>Training Analysis Complete</b>\n\n"
        f"{icon} <b>{fname}</b>\n"
        f"Analysis: {analysis_type.title()} · Saved as <code>{report_file}</code>\n\n"
        f"<i>Reading the results now…</i>"
    )
    _tg_send(header)

    # Send the analysis in 3800-char chunks to stay under TG limit
    chunk_size = 3800
    chunks = [response[i:i+chunk_size] for i in range(0, len(response), chunk_size)]
    for i, chunk in enumerate(chunks):
        prefix = f"📄 <b>Part {i+1}/{len(chunks)}:</b>\n\n" if len(chunks) > 1 else ""
        _tg_send(f"{prefix}{chunk}")

    log.info(f"Training result sent via Rexxie: {fname} ({len(chunks)} message(s))")
    return True


# ── Queue processor ───────────────────────────────────────────────────────────

def process_queue() -> dict:
    """
    Find and process all .prompt files in the queue directory.
    Returns a summary dict of results.
    """
    prompt_files = sorted(QUEUE_DIR.glob("*.prompt"))
    if not prompt_files:
        log.info("Queue empty — nothing to process")
        return {"processed": 0, "errors": 0, "skipped": 0}

    log.info(f"Found {len(prompt_files)} prompt file(s) in queue")
    results = {"processed": [], "errors": [], "skipped": []}

    for pf in prompt_files:
        try:
            data = json.loads(pf.read_text(encoding="utf-8"))
        except Exception as e:
            log.error(f"Could not parse {pf.name}: {e}")
            results["errors"].append(pf.name)
            continue

        ai_name = data.get("ai", "unknown")
        topic   = data.get("topic", "training")
        day     = data.get("day", "unknown")
        date_str = data.get("date", datetime.today().strftime("%Y-%m-%d"))
        prompt  = data.get("prompt", "")

        if not prompt:
            log.warning(f"Empty prompt in {pf.name} — skipping")
            results["skipped"].append(pf.name)
            continue

        log.info(f"Calling nemobot for {ai_name.upper()} ({topic[:50]}...)")

        try:
            response = call_nemobot(prompt, ai_name)
        except Exception as e:
            log.error(f"Nemobot call failed for {ai_name}: {e}")
            results["errors"].append(f"{ai_name}: {e}")
            continue

        # Determine prompt type (training doc vs. normal AI curriculum)
        prompt_type     = data.get("type", "curriculum")
        is_training_doc = prompt_type == "chairman_training"
        orig_filename   = data.get("original_filename", "document")
        analysis_type   = data.get("analysis_type", "full")

        # Save response to training_reports/
        if is_training_doc:
            output_filename = f"TRAINING_{date_str}_{Path(orig_filename).stem[:40]}.txt"
        else:
            output_filename = f"{ai_name}_{day}.txt"

        output_path = REPORTS_DIR / output_filename
        output_content = (
            f"AI: {ai_name}\n"
            f"Date: {date_str}\n"
            f"Topic: {topic}\n"
            f"Type: {prompt_type}\n"
            + (f"Source File: {orig_filename}\nAnalysis Type: {analysis_type}\n" if is_training_doc else "")
            + f"Source: nemobot via rex_queue_processor.py\n"
            f"Generated: {datetime.now().isoformat()}\n"
            f"\n{response}\n"
        )
        output_path.write_text(output_content, encoding="utf-8")
        log.info(f"Saved: {output_filename} ({len(response):,} chars)")

        # For chairman training docs — send privately via Rexxie Telegram immediately
        if is_training_doc and data.get("notify_rexxie"):
            _send_training_result_via_rexxie(
                orig_filename=orig_filename,
                analysis_type=analysis_type,
                response=response,
                report_file=output_filename,
            )

        # Move prompt file to processed/
        shutil.move(str(pf), str(DONE_DIR / pf.name))

        results["processed"].append({
            "ai":           ai_name,
            "day":          day,
            "file":         output_filename,
            "chars":        len(response),
            "type":         prompt_type,
            "is_training":  is_training_doc,
        })

    return results

def send_completion_notifications(results: dict):
    """Send Telegram + email after queue is processed."""
    processed = results.get("processed", [])
    errors    = results.get("errors", [])

    if not processed and not errors:
        return  # Nothing happened, don't notify

    # Split private training results (already sent via Rexxie) from curriculum
    curriculum = [r for r in processed if not r.get("is_training")]
    private_training = [r for r in processed if r.get("is_training")]

    # Build Telegram message (only for curriculum — private training already sent directly)
    if curriculum:
        lines = [f"📚 <b>REX Training — AI Responses Ready</b>\n"]
        for r in curriculum:
            emoji = {"grok": "⚡", "chatgpt": "💬", "gemini": "♊"}.get(r["ai"], "🤖")
            day_label = r["day"].title()
            lines.append(f"{emoji} <b>{r['ai'].upper()}</b> ({day_label}): {r['chars']:,} chars → saved as {r['file']}")
        lines.append(f"\n✅ Drop in <code>~/Desktop/REX/training_reports/</code> (already done)")
        if private_training:
            lines.append(f"\n🧠 {len(private_training)} training doc(s) analyzed — results sent privately via Rexxie.")
        lines.append("All 5 AM sessions are pre-loaded. Monday auto-start is on.")
    elif private_training:
        # Only training docs processed — just note it briefly
        lines = [f"🧠 <b>REX Training Docs Analyzed</b>\n{len(private_training)} document(s) processed → results sent via Rexxie."]
    else:
        lines = ["⚠️ <b>REX Queue Processor</b> — no new files were processed"]

    if errors:
        lines.append(f"\n❌ Errors ({len(errors)}): {', '.join(str(e) for e in errors[:3])}")

    send_telegram("\n".join(lines))

    # Email (only if configured + enabled)
    if processed:
        email_lines = ["REX Training — AI Responses Pre-Loaded\n"]
        for r in processed:
            email_lines.append(f"  {r['ai'].upper()} ({r['day']}): saved as {r['file']}")
        email_lines.append(f"\nAll files saved to: ~/Desktop/REX/training_reports/")
        email_lines.append("Monday 5 AM auto-processing will start automatically.")
        send_email(
            subject="📚 REX Training Ready — AI Responses Pre-Loaded",
            body="\n".join(email_lines),
        )

# ── Test mode ─────────────────────────────────────────────────────────────────

def run_test():
    print("\n" + "=" * 55)
    print("  REX QUEUE PROCESSOR — CONNECTION TEST")
    print("=" * 55)

    # Test nemobot
    print("\n1. Testing nemobot at", CFG["nemobot"]["url"])
    try:
        resp = call_nemobot("Say 'REX nemobot connection OK' and nothing else.", "test")
        print(f"   ✅ Nemobot responded: {resp[:80]}")
    except Exception as e:
        print(f"   ❌ Nemobot failed: {e}")
        print(f"   → Check that nemobot is running and that rex_queue_config.json")
        print(f"     has the correct url/prompt_key/response_key")

    # Test Telegram
    print("\n2. Testing Telegram notification...")
    ok = send_telegram("🔬 REX Queue Processor — connection test successful. System is ready.")
    if ok:
        print("   ✅ Telegram sent — check your phone")
    else:
        print("   ❌ Telegram failed — check token/chat_id in rex_queue_config.json")

    # Test Email
    em = CFG.get("email", {})
    if em.get("enabled") and em.get("app_password"):
        print("\n3. Testing email...")
        ok = send_email("REX Test Email", "This is a REX queue processor test email.")
        print(f"   {'✅' if ok else '❌'} Email {'sent' if ok else 'failed'}")
    else:
        print("\n3. Email: disabled (configure app_password in rex_queue_config.json to enable)")

    print("\n" + "=" * 55 + "\n")

def show_status():
    prompt_files = list(QUEUE_DIR.glob("*.prompt"))
    done_files   = list(DONE_DIR.glob("*.prompt"))
    report_files = list(REPORTS_DIR.glob("*.txt"))

    print("\n" + "=" * 55)
    print("  REX QUEUE STATUS")
    print("=" * 55)
    print(f"\n  Queue (pending):   {len(prompt_files)} file(s)")
    for f in prompt_files:
        try:
            d = json.loads(f.read_text())
            print(f"    → {d.get('ai','?').upper()} / {d.get('day','?')} / {d.get('topic','?')[:40]}")
        except:
            print(f"    → {f.name}")

    print(f"\n  Processed:         {len(done_files)} file(s)")
    print(f"  Training reports:  {len(report_files)} file(s)")
    for f in sorted(report_files)[-5:]:
        print(f"    → {f.name}  ({f.stat().st_size:,} bytes)")
    print(f"\n  Queue dir:   {QUEUE_DIR}")
    print(f"  Reports dir: {REPORTS_DIR}")
    print("=" * 55 + "\n")

# ── Main ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    if "--test" in sys.argv:
        run_test()
    elif "--status" in sys.argv:
        show_status()
    else:
        log.info("=" * 50)
        log.info("REX Queue Processor starting")
        results = process_queue()
        send_completion_notifications(results)

        processed = results.get("processed", [])
        errs = results.get("errors", [])
        total = len(processed) if isinstance(processed, (list, tuple)) else int(processed or 0)
        errors = len(errs) if isinstance(errs, (list, tuple)) else int(errs or 0)
        log.info(f"Done — {total} processed, {errors} errors")

        # ── Absorb new training reports into REX background knowledge ─────────
        # This is what makes REX smarter over time — like finishing a chapter
        # and adding it to everything you know. REX answers stay organic and
        # genuine; the other AIs just expand what REX has "read and absorbed."
        if total > 0:
            try:
                backend_path = Path(__file__).parent / "backend"
                if backend_path.exists():
                    import sys as _sys
                    _sys.path.insert(0, str(backend_path.parent))
                    from backend.rex_ai_enrichment import ingest_reports
                    ingest_reports(max_age_days=30)
                    log.info("✅  Background knowledge updated — REX has absorbed new perspectives")
            except Exception as e:
                log.warning(f"Background knowledge ingest skipped: {e}")
