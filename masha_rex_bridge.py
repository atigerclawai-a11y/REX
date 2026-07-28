#!/usr/bin/env python3
"""
Masha ↔ REX Bridge — MCP Server
═════════════════════════════════
Connects Masha's voice agent to the REX Review CRM (Lead Connect replacement).
Exposes contacts, reservations, deals, campaigns, and call logging.

Wired as an MCP server in Hermes config, Masha can:
  - Look up customers by phone/name
  - Log reservations from voice calls
  - Check existing reservations
  - Record call outcomes in CRM
  - Access campaign lists for outbound
"""

import json, sys, sqlite3
from datetime import datetime
from pathlib import Path

DB_PATH = Path.home() / "Desktop/REX/CC_rex_review.db"
BBG_CONTACTS = Path.home() / "Desktop/REX/CC_bbg_contacts.db"

def _connect():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn

# ── Contact Tools ────────────────────────────────────────────────────────────

def find_contact(phone: str = "", name: str = "", email: str = "") -> dict:
    """Look up a customer by phone, name, or email. Returns best match."""
    conn = _connect()
    
    if phone:
        phone_clean = ''.join(c for c in phone if c.isdigit())
        row = conn.execute(
            "SELECT * FROM contacts WHERE REPLACE(REPLACE(REPLACE(phone,'(',''),')',''),'-','') LIKE ? LIMIT 1",
            (f"%{phone_clean[-10:]}%",)
        ).fetchone()
        if not row:
            # Try BBG contacts DB
            bbg = sqlite3.connect(str(BBG_CONTACTS))
            bbg.row_factory = sqlite3.Row
            row = bbg.execute(
                "SELECT *, 'bbg_contacts' as source_db FROM contacts WHERE REPLACE(REPLACE(REPLACE(phone,'(',''),')',''),'-','') LIKE ? LIMIT 1",
                (f"%{phone_clean[-10:]}%",)
            ).fetchone()
            bbg.close()
            if row:
                source_db = row["source_db"] if "source_db" in row.keys() else "bbg_contacts"
                return {
                    "found": True,
                    "contact": {
                        "id": row["id"],
                        "name": row["name"] or "",
                        "phone": row["phone"],
                        "email": row["email"] if "email" in row.keys() else "",
                        "status": row["status"] if "status" in row.keys() else "lead",
                        "tags": row["tags"] if "tags" in row.keys() else "",
                        "source": source_db,
                        "notes": row["notes"] if "notes" in row.keys() else "",
                    }
                }
    elif name:
        row = conn.execute(
            "SELECT * FROM contacts WHERE name LIKE ? OR first_name LIKE ? OR last_name LIKE ? LIMIT 1",
            (f"%{name}%", f"%{name}%", f"%{name}%")
        ).fetchone()
    elif email:
        row = conn.execute(
            "SELECT * FROM contacts WHERE email = ? LIMIT 1", (email,)
        ).fetchone()
    else:
        conn.close()
        return {"found": False, "error": "Provide phone, name, or email"}
    
    conn.close()
    
    if row:
        source = row["source"] if "source" in row.keys() else ""
        return {
            "found": True,
            "contact": {
                "id": row["id"],
                "name": row["name"] or f"{row['first_name']} {row['last_name']}".strip(),
                "phone": row["phone"],
                "email": row["email"],
                "status": row["status"],
                "tags": row["tags"],
                "source": source,
                "notes": row["notes"],
            }
        }
    return {"found": False, "phone": phone, "name": name}


def create_contact(name: str, phone: str = "", email: str = "", tags: str = "", source: str = "masha_voice") -> dict:
    """Create a new contact or update existing by phone."""
    conn = _connect()
    
    # Check if exists
    if phone:
        phone_clean = ''.join(c for c in phone if c.isdigit())
        existing = conn.execute(
            "SELECT id FROM contacts WHERE REPLACE(REPLACE(REPLACE(phone,'(',''),')',''),'-','') LIKE ?",
            (f"%{phone_clean[-10:]}%",)
        ).fetchone()
        if existing:
            conn.execute(
                "UPDATE contacts SET name=?, email=?, updated_at=datetime('now') WHERE id=?",
                (name, email, existing["id"])
            )
            conn.commit()
            conn.close()
            return {"created": False, "updated": True, "id": existing["id"], "name": name}
    
    # Split name
    parts = name.strip().split()
    first = parts[0] if parts else ""
    last = " ".join(parts[1:]) if len(parts) > 1 else ""
    
    conn.execute(
        "INSERT INTO contacts (first_name, last_name, name, phone, email, tags, source, status) VALUES (?,?,?,?,?,?,?,'lead')",
        (first, last, name, phone, email, tags, source)
    )
    new_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.commit()
    conn.close()
    
    return {"created": True, "id": new_id, "name": name, "phone": phone}


# ── Reservation Tools ────────────────────────────────────────────────────────

def log_reservation(name: str, phone: str = "", date: str = "", time: str = "", 
                    party_size: int = 0, notes: str = "", occasion: str = "") -> dict:
    """Log a reservation from a voice call into a deal with notes."""
    # First, find or create contact
    contact = find_contact(phone=phone, name=name)
    contact_id = contact.get("contact", {}).get("id") if contact.get("found") else None
    
    if not contact_id:
        result = create_contact(name=name, phone=phone, source="masha_reservation")
        contact_id = result["id"]
    
    conn = _connect()
    
    # Create as a deal in the pipeline
    conn.execute(
        """INSERT INTO deals (contact_id, pipeline_id, stage_id, title, value, notes, created_at)
           VALUES (?, 1, 'new', ?, 0, ?, datetime('now'))""",
        (contact_id, f"Reservation: {name} — {date} {time}", 
         f"Party: {party_size} | Date: {date} {time} | Occasion: {occasion} | Notes: {notes}")
    )
    deal_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.commit()
    conn.close()
    
    return {
        "reservation_logged": True,
        "contact_id": contact_id,
        "deal_id": deal_id,
        "name": name,
        "date": date,
        "time": time,
        "party_size": party_size
    }


def check_reservations(date: str = "", name: str = "") -> dict:
    """Look up existing reservations/deals."""
    conn = _connect()
    
    query = "SELECT d.*, c.name as contact_name, c.phone FROM deals d LEFT JOIN contacts c ON d.contact_id = c.id WHERE d.status = 'open'"
    params = []
    
    if date:
        query += " AND d.notes LIKE ?"
        params.append(f"%{date}%")
    if name:
        query += " AND c.name LIKE ?"
        params.append(f"%{name}%")
    
    query += " ORDER BY d.created_at DESC LIMIT 20"
    
    rows = conn.execute(query, params).fetchall()
    conn.close()
    
    return {
        "count": len(rows),
        "reservations": [
            {
                "id": r["id"],
                "contact": r["contact_name"],
                "phone": r["phone"],
                "title": r["title"],
                "stage": r["stage_id"],
                "notes": r["notes"][:200],
                "created": r["created_at"]
            }
            for r in rows
        ]
    }


# ── Call Logging ─────────────────────────────────────────────────────────────

def log_call(contact_name: str = "", phone: str = "", call_id: str = "",
             duration_sec: int = 0, outcome: str = "", notes: str = "",
             channel: str = "retell") -> dict:
    """Log a completed call into the conversations table."""
    contact = find_contact(phone=phone, name=contact_name) if (phone or contact_name) else {"found": False}
    contact_id = contact.get("contact", {}).get("id") if contact.get("found") else None
    
    conn = _connect()
    conn.execute(
        """INSERT INTO conversations (contact_id, channel, direction, body, duration_sec, metadata, created_at)
           VALUES (?, ?, 'outbound', ?, ?, ?, datetime('now'))""",
        (contact_id, channel, notes or outcome, duration_sec,
         json.dumps({"call_id": call_id, "outcome": outcome, "phone": phone}))
    )
    conv_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.commit()
    conn.close()
    
    return {
        "logged": True,
        "conversation_id": conv_id,
        "contact_id": contact_id,
        "call_id": call_id,
        "outcome": outcome
    }


def recent_calls(limit: int = 20) -> dict:
    """Get recent call log."""
    conn = _connect()
    rows = conn.execute(
        """SELECT c.id, c.channel, c.direction, c.body, c.duration_sec, c.created_at,
                  co.name as contact_name, co.phone
           FROM conversations c LEFT JOIN contacts co ON c.contact_id = co.id
           ORDER BY c.created_at DESC LIMIT ?""",
        (limit,)
    ).fetchall()
    conn.close()
    
    return {
        "count": len(rows),
        "calls": [
            {
                "id": r["id"],
                "contact": r["contact_name"] or "unknown",
                "phone": r["phone"] or "",
                "direction": r["direction"],
                "duration_sec": r["duration_sec"],
                "outcome": r["body"][:100] if r["body"] else "",
                "time": r["created_at"]
            }
            for r in rows
        ]
    }


# ── MCP Server ───────────────────────────────────────────────────────────────

TOOLS = {
    "find_contact": {
        "fn": find_contact,
        "description": "Look up a customer by phone, name, or email",
        "params": {
            "phone": "Phone number (any format)",
            "name": "Customer name (partial match)",
            "email": "Email address"
        }
    },
    "create_contact": {
        "fn": create_contact,
        "description": "Create or update a contact in the CRM",
        "params": {
            "name": "Full name (required)",
            "phone": "Phone number",
            "email": "Email address",
            "tags": "Comma-separated tags",
            "source": "Lead source (default: masha_voice)"
        }
    },
    "log_reservation": {
        "fn": log_reservation,
        "description": "Log a reservation from a voice call",
        "params": {
            "name": "Customer name",
            "phone": "Phone number",
            "date": "Reservation date (YYYY-MM-DD)",
            "time": "Reservation time",
            "party_size": "Number of guests",
            "notes": "Special requests",
            "occasion": "Birthday, anniversary, etc."
        }
    },
    "check_reservations": {
        "fn": check_reservations,
        "description": "Look up existing reservations",
        "params": {
            "date": "Filter by date",
            "name": "Filter by name"
        }
    },
    "log_call": {
        "fn": log_call,
        "description": "Log a completed phone call in the CRM",
        "params": {
            "contact_name": "Customer name",
            "phone": "Phone number",
            "call_id": "Retell call ID",
            "duration_sec": "Call duration in seconds",
            "outcome": "confirmed, declined, voicemail, no_answer",
            "notes": "Call notes"
        }
    },
    "recent_calls": {
        "fn": recent_calls,
        "description": "Get recent call log",
        "params": {"limit": "Number of calls (default 20)"}
    },
}

TOOL_SCHEMAS = {
    name: {
        "description": info["description"],
        "parameters": {k: {"type": "string", "description": v} for k, v in info["params"].items()}
    }
    for name, info in TOOLS.items()
}


def main():
    for line in sys.stdin:
        try:
            msg = json.loads(line.strip())
            method = msg.get("method", "")
            msg_id = msg.get("id")

            if method == "initialize":
                sys.stdout.write(json.dumps({
                    "jsonrpc": "2.0", "id": msg_id,
                    "result": {
                        "protocolVersion": "2024-11-05",
                        "capabilities": {"tools": {}},
                        "serverInfo": {"name": "masha-rex-bridge", "version": "1.0.0"}
                    }
                }) + "\n")
                sys.stdout.flush()

            elif method == "tools/list":
                tools = [{"name": n, "description": s["description"],
                          "inputSchema": {"type": "object", "properties": s["parameters"],
                                         "required": list(s["parameters"].keys())}}
                        for n, s in TOOL_SCHEMAS.items()]
                sys.stdout.write(json.dumps({
                    "jsonrpc": "2.0", "id": msg_id, "result": {"tools": tools}
                }) + "\n")
                sys.stdout.flush()

            elif method == "tools/call":
                tool_name = msg["params"]["name"]
                args = msg["params"].get("arguments", {})
                tool = TOOLS.get(tool_name)
                
                if tool:
                    try:
                        # Convert numeric args
                        for k in ["party_size", "duration_sec", "limit"]:
                            if k in args and args[k]:
                                args[k] = int(args[k])
                        
                        result = tool["fn"](**{k: v for k, v in args.items() if v})
                        sys.stdout.write(json.dumps({
                            "jsonrpc": "2.0", "id": msg_id,
                            "result": {"content": [{"type": "text", "text": json.dumps(result, indent=2, ensure_ascii=False)}]}
                        }) + "\n")
                    except Exception as e:
                        sys.stdout.write(json.dumps({
                            "jsonrpc": "2.0", "id": msg_id,
                            "error": {"code": -1, "message": str(e)}
                        }) + "\n")
                else:
                    sys.stdout.write(json.dumps({
                        "jsonrpc": "2.0", "id": msg_id,
                        "error": {"code": -2, "message": f"Unknown tool: {tool_name}"}
                    }) + "\n")
                sys.stdout.flush()

        except json.JSONDecodeError:
            continue
        except Exception as e:
            sys.stderr.write(f"MCP error: {e}\n")
            sys.stderr.flush()


if __name__ == "__main__":
    main()
