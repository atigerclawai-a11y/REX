#!/usr/bin/env python3
"""
BBG Masha Outbound Caller
Handles reservation confirmations, follow-ups, and outbound calls for Boardwalk Beer Garden.
Uses Masha agent with 11labs-victoria voice via Retell.

Usage:
  python3 bbg_masha_caller.py --to "+19295551234" --type reservation --name "Alex"
  python3 bbg_masha_caller.py --to "+19295551234" --type followup --name "Maria" --note "Birthday party Sat"
  python3 bbg_masha_caller.py --batch reservations.csv

Config from ~/Desktop/REX/.env
"""

import json, sys, time, logging, requests, argparse, csv
from datetime import datetime
from pathlib import Path

# ── Config ────────────────────────────────────────────────────────────────────
REX_DIR = Path.home() / "Desktop" / "REX"
LOG_PATH = REX_DIR / "logs" / "masha_caller.log"
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    filename=str(LOG_PATH), level=logging.INFO,
    format="%(asctime)s %(message)s"
)

def _load_env():
    """Load RETELL_KEY and other config from REX .env"""
    env = {}
    env_path = REX_DIR / ".env"
    if env_path.exists():
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    k, v = line.split('=', 1)
                    env[k.strip()] = v.strip().strip('"').strip("'")
    return env

ENV = _load_env()
RETELL_KEY = ENV.get("RETELL_API_KEY") or ENV.get("RETELL_KEY", "")
AGENT_ID = "agent_305ba9fdc34276c523766cd096"  # Masha-BBG
FROM_NUMBER = "+19293685460"  # Masha's dedicated Brooklyn number (929) 368-5460

HEADERS = {
    "Authorization": f"Bearer {RETELL_KEY}",
    "Content-Type": "application/json"
}

# ── Core Functions ────────────────────────────────────────────────────────────

def make_call(to_number, call_type="reservation", name="", note="", date_str=""):
    """
    Fire an outbound call via Retell.
    
    call_type:
      - "reservation": Confirms a booking
      - "followup": Follow-up from previous inquiry  
      - "event": Reminder about upcoming event/party
      - "test": Test call
    """
    # Clean phone
    phone = "".join(c for c in to_number.split()[0] if c.isdigit() or c == "+")
    if not phone.startswith("+"):
        phone = "+1" + phone.lstrip("1")
    
    # Build dynamic variables for the LLM
    dynamic_vars = {
        "client_name": name or "guest",
        "call_type": call_type,
    }
    if date_str:
        dynamic_vars["date"] = date_str
    if note:
        dynamic_vars["note"] = note
    
    payload = {
        "from_number": FROM_NUMBER,
        "to_number": phone,
        "override_agent_id": AGENT_ID,
        "retell_llm_dynamic_variables": dynamic_vars
    }
    
    try:
        r = requests.post(
            "https://api.retellai.com/v2/create-phone-call",
            headers=HEADERS,
            json=payload,
            timeout=15
        )
        if r.status_code == 201:
            data = r.json()
            call_id = data.get("call_id")
            logging.info("Call placed: %s -> %s (%s) call_id=%s", 
                        FROM_NUMBER, phone, call_type, call_id)
            return call_id, "placed"
        else:
            logging.error("Call failed for %s: %s", phone, r.text[:200])
            return None, f"error_{r.status_code}"
    except Exception as e:
        logging.error("Call exception for %s: %s", phone, e)
        return None, "exception"


def poll_call(call_id, wait_seconds=60):
    """Wait for call to complete, then fetch results."""
    time.sleep(wait_seconds)
    
    try:
        r = requests.get(
            f"https://api.retellai.com/v2/get-call/{call_id}",
            headers={"Authorization": f"Bearer {RETELL_KEY}"},
            timeout=10
        )
        if r.status_code == 200:
            cd = r.json()
            return {
                "call_id": call_id,
                "status": cd.get("call_status", "unknown"),
                "duration_sec": (cd.get("duration_ms", 0) or 0) // 1000,
                "recording_url": cd.get("recording_url", ""),
                "transcript": cd.get("transcript", ""),
                "dtmf": cd.get("user_dtmf", ""),
            }
    except Exception as e:
        logging.error("Poll failed for %s: %s", call_id, e)
    
    return {"call_id": call_id, "status": "poll_failed"}


def batch_calls(csv_path, call_type="reservation", wave_size=5, wave_gap=5, wave_break=30):
    """
    Batch process calls from a CSV file.
    CSV format: name,phone,date,note
    """
    calls = []
    with open(csv_path) as f:
        reader = csv.DictReader(f)
        for row in reader:
            calls.append({
                "name": row.get("name", ""),
                "phone": row.get("phone", ""),
                "date": row.get("date", ""),
                "note": row.get("note", ""),
            })
    
    if not calls:
        print("No calls found in CSV")
        return []
    
    print(f"📞 Batch calling {len(calls)} numbers with Masha...")
    
    results = []
    for i in range(0, len(calls), wave_size):
        wave = calls[i:i+wave_size]
        wave_num = i // wave_size + 1
        total_waves = (len(calls) + wave_size - 1) // wave_size
        
        print(f"  Wave {wave_num}/{total_waves} ({len(wave)} calls)...")
        
        for call in wave:
            call_id, status = make_call(
                call["phone"], call_type,
                name=call["name"], note=call["note"], date_str=call["date"]
            )
            result = {**call, "call_id": call_id, "init_status": status}
            results.append(result)
            
            if call_id:
                print(f"    ✅ {call['name']}: {call['phone']} → {call_id}")
            else:
                print(f"    ❌ {call['name']}: {call['phone']} → {status}")
            
            time.sleep(wave_gap)
        
        if wave_num < total_waves:
            time.sleep(wave_break)
    
    print(f"\n✅ All {len(results)} calls initiated. Poll for results after 2-3 min.")
    return results


# ── CLI ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="BBG Masha Outbound Caller")
    parser.add_argument("--to", help="Phone number to call")
    parser.add_argument("--name", default="", help="Caller/guest name")
    parser.add_argument("--type", default="reservation", 
                       choices=["reservation", "followup", "event", "test"],
                       help="Call type")
    parser.add_argument("--note", default="", help="Additional note for the call")
    parser.add_argument("--date", default="", help="Date context (e.g. 'Saturday, July 5')")
    parser.add_argument("--batch", help="CSV file for batch calls")
    parser.add_argument("--poll", help="Poll a specific call_id for results")
    parser.add_argument("--wait", type=int, default=60, help="Seconds to wait before polling")
    
    args = parser.parse_args()
    
    if args.poll:
        result = poll_call(args.poll, args.wait)
        print(json.dumps(result, indent=2))
        return
    
    if args.batch:
        results = batch_calls(args.batch, args.type)
        # Save results
        out_path = REX_DIR / "logs" / f"masha_batch_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(out_path, 'w') as f:
            json.dump(results, f, indent=2)
        print(f"\nResults saved to {out_path}")
        return
    
    if args.to:
        call_id, status = make_call(args.to, args.type, args.name, args.note, args.date)
        if call_id:
            print(f"✅ Call placed: {call_id}")
            print(f"   From: {FROM_NUMBER}")
            print(f"   To: {args.to}")
            print(f"   Agent: Masha-BBG (11labs-victoria)")
            print(f"\n   Poll for results: python3 bbg_masha_caller.py --poll {call_id} --wait 120")
        else:
            print(f"❌ Call failed: {status}")
            sys.exit(1)
        return
    
    parser.print_help()


if __name__ == "__main__":
    main()
