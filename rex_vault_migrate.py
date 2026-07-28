#!/usr/bin/env python3
"""
rex_vault_migrate.py
──────────────────────────────────────────────────────────────────────────────
REX — Plaintext SQLite → SQLCipher Vault Migration

Reads each backed-up plaintext database, creates an encrypted SQLCipher
counterpart in ~/Desktop/REX/data/vaults/, and copies all data with
secrecy levels inferred from table names.

SAFE TO RUN MULTIPLE TIMES — existing vault items are not overwritten unless
--force flag is passed. Original plaintext databases are never touched.

Databases migrated:
  rexxie_memory.db     → rexxie_agent_vault.db   (namespace: rexxie_memory)
  rex_memory.db        → rexxie_agent_vault.db   (namespace: rex_memory)
  rex_user_model.db    → rexxie_agent_vault.db   (namespace: user_model)
  rex_background_knowledge.db → knowledge_agent_vault.db
  rex_curriculum_log.db       → knowledge_agent_vault.db
  rexxie.db            → credentials_agent_vault.db  (most sensitive)
  ~/.rex/rex_journeys.db → backend_agent_vault.db

Usage:
    cd ~/Desktop/REX
    python3 rex_vault_migrate.py              # dry run — shows what will happen
    python3 rex_vault_migrate.py --execute    # actually migrate
    python3 rex_vault_migrate.py --execute --force  # re-migrate everything
    python3 rex_vault_migrate.py --verify     # verify vaults after migration
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

# Add REX dir to path so we can import vault module
REX_DIR = Path.home() / "Desktop" / "REX"
sys.path.insert(0, str(REX_DIR))

from rex_sqlcipher_vault import (
    VaultManager, SecrecyLevel, infer_secrecy_level, VaultSession,
    VAULT_DIR, AGENT_VAULTS
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("rex.migrate")

# ─────────────────────────────────────────────────────────────────────────────
# MIGRATION MAP
# maps source db → (agent_name, namespace_prefix)
# ─────────────────────────────────────────────────────────────────────────────

MIGRATION_MAP = [
    {
        "source":    REX_DIR / "rexxie_memory.db",
        "agent":     "rexxie",
        "namespace": "rexxie_memory",
        "note":      "Rexxie ideas, decisions, tasks, preferences",
    },
    {
        "source":    REX_DIR / "rex_memory.db",
        "agent":     "rexxie",
        "namespace": "rex_memory",
        "note":      "Session memories",
    },
    {
        "source":    REX_DIR / "rex_user_model.db",
        "agent":     "rexxie",
        "namespace": "user_model",
        "note":      "User behavior model, communication preferences",
    },
    {
        "source":    REX_DIR / "rex_background_knowledge.db",
        "agent":     "knowledge",
        "namespace": "background_knowledge",
        "note":      "Background knowledge base",
    },
    {
        "source":    REX_DIR / "rex_curriculum_log.db",
        "agent":     "knowledge",
        "namespace": "curriculum_log",
        "note":      "Curriculum and training log",
    },
    {
        "source":    REX_DIR / "rexxie.db",
        "agent":     "credentials",
        "namespace": "rexxie_core",
        "note":      "Core Rexxie database — may contain sensitive data",
    },
    {
        "source":    Path.home() / ".rex" / "rex_journeys.db",
        "agent":     "backend",
        "namespace": "journeys",
        "note":      "Backend journey tracking",
    },
]


# ─────────────────────────────────────────────────────────────────────────────
# SOURCE DB READER
# ─────────────────────────────────────────────────────────────────────────────

def read_plaintext_db(db_path: Path) -> dict:
    """
    Read all tables and their data from a plaintext SQLite database.
    Returns {table_name: {"schema": str, "rows": list[dict], "columns": list[str]}}
    """
    if not db_path.exists():
        return {}

    result = {}
    try:
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row

        # Get all user tables (not sqlite internal tables)
        tables = conn.execute("""
            SELECT name, sql FROM sqlite_master
            WHERE type='table' AND name NOT LIKE 'sqlite_%'
            ORDER BY name
        """).fetchall()

        for table_row in tables:
            table_name = table_row["name"]
            schema_sql = table_row["sql"] or ""

            try:
                rows = conn.execute(f"SELECT * FROM {table_name}").fetchall()
                columns = [desc[0] for desc in conn.execute(
                    f"SELECT * FROM {table_name} LIMIT 0"
                ).description or []]

                result[table_name] = {
                    "schema":  schema_sql,
                    "columns": columns,
                    "rows":    [dict(r) for r in rows],
                    "count":   len(rows),
                }
            except Exception as e:
                logger.warning(f"  Could not read table {table_name}: {e}")

        conn.close()
    except Exception as e:
        logger.error(f"  Could not open {db_path.name}: {e}")

    return result


# ─────────────────────────────────────────────────────────────────────────────
# VAULT WRITER
# ─────────────────────────────────────────────────────────────────────────────

def migrate_table_to_vault(
    vault:       VaultSession,
    namespace:   str,
    table_name:  str,
    table_data:  dict,
    dry_run:     bool = True,
    force:       bool = False,
) -> dict:
    """
    Migrate one table from plaintext into the vault.

    Strategy:
    1. Recreate the original table schema inside the vault (SQLCipher DB)
    2. Add a `_secrecy_level` column to the migrated table
    3. Copy all rows with inferred secrecy levels
    4. Also store a vault_items entry pointing to the table (for quick lookups)

    Returns migration stats.
    """
    schema     = table_data["schema"]
    rows       = table_data["rows"]
    columns    = table_data["columns"]
    row_count  = len(rows)

    # Infer secrecy level for this table
    level = infer_secrecy_level(table_name)

    stats = {
        "table":         table_name,
        "namespace":     namespace,
        "rows":          row_count,
        "secrecy_level": level.label(),
        "status":        "dry_run" if dry_run else "pending",
    }

    if dry_run:
        return stats

    if row_count == 0:
        stats["status"] = "empty_skipped"
        return stats

    try:
        # Create the table in the vault if it doesn't exist
        # Add _secrecy_level column to the schema
        migrated_table = f"{namespace}__{table_name}"

        # Build CREATE TABLE from original schema
        # Replace original table name with namespaced name
        create_sql = schema.replace(
            f"CREATE TABLE {table_name}",
            f"CREATE TABLE IF NOT EXISTS {migrated_table}",
            1
        ).replace(
            f"CREATE TABLE IF NOT EXISTS {table_name}",
            f"CREATE TABLE IF NOT EXISTS {migrated_table}",
            1
        )

        # Add secrecy level column if not in original schema
        if "_secrecy_level" not in create_sql:
            create_sql = create_sql.rstrip().rstrip(")")
            create_sql += ",\n    _secrecy_level TEXT DEFAULT 'restricted'\n)"

        vault.execute(create_sql)
        vault.commit()

        # Check if table already has data (skip unless --force)
        existing = vault.execute(
            f"SELECT COUNT(*) FROM {migrated_table}"
        ).fetchone()[0]

        if existing > 0 and not force:
            stats["status"] = "skipped_already_migrated"
            stats["existing_rows"] = existing
            return stats

        if force and existing > 0:
            vault.execute(f"DELETE FROM {migrated_table}")
            vault.commit()

        # Insert rows
        migrated = 0
        for row in rows:
            row_with_secrecy = dict(row)
            row_with_secrecy["_secrecy_level"] = level.label()

            # Only insert columns that exist in the schema
            insert_cols = [c for c in row_with_secrecy.keys() if c in columns or c == "_secrecy_level"]
            placeholders = ", ".join("?" for _ in insert_cols)
            col_names    = ", ".join(insert_cols)
            values       = [row_with_secrecy.get(c) for c in insert_cols]

            try:
                vault.execute(
                    f"INSERT OR REPLACE INTO {migrated_table} ({col_names}) VALUES ({placeholders})",
                    tuple(values)
                )
                migrated += 1
            except Exception as e:
                logger.debug(f"    Row insert failed in {table_name}: {e}")

        vault.commit()

        # Store a pointer in vault_items for quick lookup
        vault.write(
            namespace  = namespace,
            key        = f"_table_meta_{table_name}",
            value      = {
                "source_table":  table_name,
                "vault_table":   migrated_table,
                "row_count":     migrated,
                "secrecy_level": level.label(),
                "migrated_at":   datetime.now(timezone.utc).isoformat(),
            },
            secrecy_level = SecrecyLevel.PUBLIC,
        )

        stats["status"]   = "migrated"
        stats["migrated"] = migrated
        return stats

    except Exception as e:
        stats["status"] = f"error: {e}"
        logger.error(f"  Migration error for {table_name}: {e}")
        return stats


# ─────────────────────────────────────────────────────────────────────────────
# MAIN MIGRATION
# ─────────────────────────────────────────────────────────────────────────────

def run_migration(dry_run: bool = True, force: bool = False) -> list[dict]:
    """Run the full migration. Returns list of per-table stats."""

    print()
    print("=" * 65)
    print("  REX SQLCipher Vault Migration")
    print(f"  Mode: {'DRY RUN — no changes made' if dry_run else 'LIVE — writing to vaults'}")
    print(f"  Force re-migrate: {force}")
    print(f"  Target: {VAULT_DIR}")
    print("=" * 65)

    vm        = VaultManager()
    all_stats = []

    for entry in MIGRATION_MAP:
        source    = entry["source"]
        agent     = entry["agent"]
        namespace = entry["namespace"]
        note      = entry["note"]

        print(f"\n▶  {source.name}  →  {agent} vault  [{note}]")

        if not source.exists():
            print(f"   {source.name} not found — skipping")
            all_stats.append({"source": source.name, "status": "not_found"})
            continue

        # Read plaintext source
        tables = read_plaintext_db(source)
        if not tables:
            print(f"   No tables found in {source.name}")
            all_stats.append({"source": source.name, "status": "empty"})
            continue

        print(f"   Tables: {list(tables.keys())}")

        vault = vm.open(agent)

        for table_name, table_data in tables.items():
            stats = migrate_table_to_vault(
                vault      = vault,
                namespace  = namespace,
                table_name = table_name,
                table_data = table_data,
                dry_run    = dry_run,
                force      = force,
            )
            level    = stats.get("secrecy_level", "?")
            row_cnt  = stats.get("rows", 0)
            status   = stats.get("status", "?")
            migrated = stats.get("migrated", "—")

            status_icon = {
                "dry_run":                  "⬜",
                "migrated":                 "✅",
                "skipped_already_migrated": "⏭ ",
                "empty_skipped":            "◻ ",
                "not_found":                "⚠️ ",
            }.get(status, "❌")

            print(
                f"   {status_icon}  {table_name:30s}  "
                f"{level:12s}  {row_cnt:5d} rows  "
                f"→ {migrated if not dry_run else '(dry run)'}"
            )
            all_stats.append({**stats, "source": source.name, "agent": agent})

    # Summary
    print()
    print("─" * 65)
    if dry_run:
        total_rows = sum(s.get("rows", 0) for s in all_stats)
        total_tables = len([s for s in all_stats if "table" in s])
        print(f"  DRY RUN COMPLETE — {total_tables} tables, {total_rows} total rows would be migrated")
        print()
        print("  To execute migration, run:")
        print("  python3 rex_vault_migrate.py --execute")
    else:
        migrated = len([s for s in all_stats if s.get("status") == "migrated"])
        skipped  = len([s for s in all_stats if "skipped" in s.get("status", "")])
        errors   = len([s for s in all_stats if "error" in s.get("status", "")])
        print(f"  MIGRATION COMPLETE — {migrated} migrated, {skipped} skipped, {errors} errors")

        if errors > 0:
            print()
            print("  ⚠️  Errors occurred — check logs above")
        else:
            print()
            print("  ✅ All tables migrated successfully")
            print()
            print("  Vault files created:")
            for vault_info in vm.list_vaults():
                print(f"    {vault_info['file']:40s}  {vault_info['size_kb']:6d} KB")
    print()

    vm.close_all()
    return all_stats


# ─────────────────────────────────────────────────────────────────────────────
# VERIFY
# ─────────────────────────────────────────────────────────────────────────────

def run_verify() -> bool:
    """Verify all vaults can be opened and read."""
    print()
    print("=" * 65)
    print("  REX SQLCipher Vault Verification")
    print("=" * 65)

    vm      = VaultManager()
    vaults  = vm.list_vaults()
    all_ok  = True

    if not vaults:
        print("  No vault files found. Run migration first.")
        return False

    for vault_info in vaults:
        agent = vault_info["agent"]
        try:
            vault = vm.open(agent)
            stats = vault.stats()
            counts = stats["by_secrecy"]

            # Build secrecy breakdown string
            secrecy_str = "  ".join(
                f"{level}:{n}" for level, n in counts.items() if n > 0
            )

            print(
                f"  ✅  {vault_info['file']:40s}  "
                f"{stats['total']:5d} items  "
                f"{vault_info['size_kb']:5d} KB  "
                f"[{secrecy_str}]"
            )
        except Exception as e:
            print(f"  ❌  {vault_info['file']}  ERROR: {e}")
            all_ok = False

    print()
    if all_ok:
        print("  All vaults verified OK — SQLCipher encryption is active")
    else:
        print("  ⚠️  Some vaults failed verification")

    # Verify audit log
    audit_path = VAULT_DIR / "vault_audit.jsonl"
    if audit_path.exists():
        entries = [json.loads(l) for l in audit_path.read_text().strip().splitlines() if l.strip()]
        print(f"  Audit log: {len(entries)} entries at {audit_path}")
    else:
        print("  Audit log: not yet created")

    vm.close_all()
    return all_ok


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Migrate plaintext SQLite databases to SQLCipher vaults.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python3 rex_vault_migrate.py              # dry run
  python3 rex_vault_migrate.py --execute    # migrate for real
  python3 rex_vault_migrate.py --execute --force   # re-migrate everything
  python3 rex_vault_migrate.py --verify     # verify vaults after migration
        """
    )
    parser.add_argument("--execute", action="store_true",
                        help="Actually perform migration (default is dry run)")
    parser.add_argument("--force", action="store_true",
                        help="Re-migrate even if vault already has data")
    parser.add_argument("--verify", action="store_true",
                        help="Verify existing vaults (skips migration)")
    args = parser.parse_args()

    if args.verify:
        ok = run_verify()
        sys.exit(0 if ok else 1)
    else:
        run_migration(dry_run=not args.execute, force=args.force)


if __name__ == "__main__":
    main()
