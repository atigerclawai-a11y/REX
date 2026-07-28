"""
CC_auth_db.py — Encrypted auth_tracker.db access via sqlcipher CLI
====================================================================
Since pysqlcipher3 won't build on this system, we use the sqlcipher
CLI binary as a subprocess wrapper. All consumers get transparent
encrypted DB access.

Key at ~/.rex/auth_tracker.key (chmod 600).

Usage:
    from CC_auth_db import AuthDB
    db = AuthDB()
    rows = db.query("SELECT client_name FROM client_menus WHERE day='M'")
    db.execute("INSERT INTO client_menus (...) VALUES (...)", params)
    db.close()
"""

import json
import os
import subprocess
import sys
from pathlib import Path

HOME = Path(os.path.expanduser("~"))
KEY_FILE = HOME / ".rex" / "auth_tracker.key"
DB_ENCRYPTED = HOME / "Documents" / "goj files" / "dashboard" / "auth_tracker_encrypted.db"
DB_ORIGINAL  = HOME / "Documents" / "goj files" / "dashboard" / "auth_tracker.db"

SQLCIPHER_BIN = "/opt/homebrew/bin/sqlcipher"

class AuthDB:
    """Encrypted auth_tracker.db connection via sqlcipher CLI."""
    
    def __init__(self, use_encrypted: bool = True):
        self._key = None
        self._db_path = DB_ENCRYPTED if use_encrypted else DB_ORIGINAL
        
        if use_encrypted:
            if not DB_ENCRYPTED.exists():
                if DB_ORIGINAL.exists():
                    print("⚠️  Encrypted DB not found, using plaintext fallback", file=sys.stderr)
                    self._db_path = DB_ORIGINAL
                    self._encrypted = False
                    return
                raise FileNotFoundError(f"DB not found: {DB_ENCRYPTED}")
            
            if not KEY_FILE.exists():
                raise FileNotFoundError(f"Key file missing: {KEY_FILE}")
            
            self._key = KEY_FILE.read_text().strip()
            self._encrypted = True
        else:
            self._encrypted = False
    
    def _run(self, sql: str) -> str:
        """Execute SQL via sqlcipher CLI and return stdout."""
        if self._encrypted:
            full_sql = f"PRAGMA key = \"x'{self._key}'\";\n{sql}"
        else:
            full_sql = sql
        
        result = subprocess.run(
            [SQLCIPHER_BIN, str(self._db_path)],
            input=full_sql,
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0 and "Error" in result.stderr:
            raise RuntimeError(f"SQLCipher error: {result.stderr.strip()}")
        return result.stdout.strip()
    
    def query(self, sql: str) -> list[dict]:
        """Run SELECT and return list of dicts."""
        output = self._run(f".mode json\n{sql};")
        if not output:
            return []
        # sqlcipher outputs "ok" for PRAGMA, then JSON on subsequent lines
        lines = output.strip().split("\n")
        json_line = None
        for line in lines:
            line = line.strip()
            if line.startswith("[") or line.startswith("{"):
                json_line = line
                break
        if not json_line:
            return []
        try:
            data = json.loads(json_line)
            return data if isinstance(data, list) else [data]
        except json.JSONDecodeError:
            return [{"result": output}]
    
    def query_one(self, sql: str):
        """Return single value from first row, first column."""
        rows = self.query(sql)
        if rows:
            return list(rows[0].values())[0] if rows[0] else None
        return None
    
    def execute(self, sql: str) -> int:
        """Execute INSERT/UPDATE/DELETE. Returns rowcount."""
        self._run(sql)
        # Get changes
        output = self._run("SELECT changes();")
        try:
            return int(output.strip())
        except ValueError:
            return -1
    
    def close(self):
        """No-op for CLI-based access."""
        pass

# Singleton convenience
_auth_db = None

def get_db(use_encrypted: bool = True) -> AuthDB:
    global _auth_db
    if _auth_db is None:
        _auth_db = AuthDB(use_encrypted=use_encrypted)
    return _auth_db

if __name__ == "__main__":
    db = AuthDB()
    count = db.query_one("SELECT COUNT(*) FROM client_menus")
    print(f"✅ {count} rows in client_menus")
    
    # Quick coverage check
    cov = db.query_one(
        "SELECT ROUND(100.0*SUM(CASE WHEN main IS NOT NULL THEN 1 ELSE 0 END)/COUNT(*),1) "
        "FROM client_menus WHERE week_start='2026-06-01'"
    )
    print(f"📊 Week 2026-06-01 coverage: {cov}%")
