#!/usr/bin/env python3
"""
GOJ Victoria Webhook
Receives Retell call results → writes to goj_proprietary.db
Keeps 2-week call log with recording URLs
Port 8089
"""
import sqlite3, json, logging
from http.server import HTTPServer, BaseHTTPRequestHandler
from datetime import datetime, timedelta
from pathlib import Path

DB  = str(Path.home() / "Documents/goj files/proprietary/goj_proprietary.db")
LOG = str(Path.home() / "Desktop/REX/logs/victoria_webhook.log")

Path(LOG).parent.mkdir(parents=True, exist_ok=True)
logging.basicConfig(filename=LOG, level=logging.INFO,
                    format="%(asctime)s %(message)s")

def init_db():
    conn = sqlite3.connect(DB)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS victoria_calls (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            call_id       TEXT UNIQUE,
            client_name   TEXT,
            phone         TEXT,
            call_date     TEXT,
            call_time     TEXT,
            duration_sec  INTEGER DEFAULT 0,
            dtmf_pressed  TEXT,
            status        TEXT,
            att_status    TEXT,
            recording_url TEXT,
            transcript    TEXT,
            created_at    TEXT DEFAULT (datetime('now'))
        )
    """)
    conn.commit()
    conn.close()

def purge_old():
    cutoff = (datetime.now() - timedelta(days=14)).strftime("%Y-%m-%d")
    conn = sqlite3.connect(DB)
    conn.execute("DELETE FROM victoria_calls WHERE call_date < ?", (cutoff,))
    conn.commit()
    conn.close()

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        """Health check endpoint — responds 200 so monitors stop flagging 501."""
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Victoria webhook alive\n")

    def do_POST(self):
        try:
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length))

            # Retell webhook envelope: {"event": "...", "call": {...}}
            # All call fields are nested under "call" — top-level reads return None.
            call      = body.get("call", {}) or {}
            call_id   = call.get("call_id", "") or ""
            status    = call.get("call_status", "") or ""
            variables = call.get("retell_llm_dynamic_variables", {}) or {}
            client    = variables.get("client_name", "") or ""
            phone     = call.get("to_number", "") or ""
            dtmf      = call.get("user_dtmf", "") or ""
            duration  = (call.get("duration_ms", 0) or 0) // 1000
            recording = call.get("recording_url", "") or ""
            transcript= call.get("transcript", "") or ""
            now       = datetime.now()

            if not call_id:
                logging.warning("Webhook event without call_id: %s", json.dumps(body)[:200])
                self.send_response(200); self.end_headers(); self.wfile.write(b"SKIP")
                return

            logging.info("Received %s for %s → status=%s dtmf=%s",
                         body.get("event", ""), client, status, dtmf)

            if dtmf == "1":    att = "confirmed"
            elif dtmf == "2":  att = "declined"
            elif dtmf == "3":  att = "requested_staff"
            elif dtmf == "0":  att = "repeated_options"
            elif not dtmf:     att = "no_answer"
            else:              att = "voicemail"

            conn = sqlite3.connect(DB)
            conn.execute("""
                INSERT OR REPLACE INTO victoria_calls
                (call_id,client_name,phone,call_date,call_time,
                 duration_sec,dtmf_pressed,status,att_status,recording_url,transcript)
                VALUES (?,?,?,?,?,?,?,?,?,?,?)
            """, (call_id, client, phone,
                  now.strftime("%Y-%m-%d"), now.strftime("%H:%M:%S"),
                  duration, dtmf, status, att, recording, transcript))

            conn.execute("""
                INSERT OR IGNORE INTO attendance
                (client_name,att_date,shift,status,reported_by,reason)
                VALUES (?,?,'',(?),'victoria',?)
            """, (client, now.strftime("%Y-%m-%d"), att, f"call:{call_id}"))
            conn.commit()
            conn.close()

            purge_old()
            logging.info("Logged: %s → %s", client, att)

        except Exception as e:
            logging.error("Error: %s", e)

        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK")

    def log_message(self, *args):
        pass

if __name__ == "__main__":
    init_db()
    print("Victoria webhook on port 8089...")
    HTTPServer(("127.0.0.1", 8089), Handler).serve_forever()
