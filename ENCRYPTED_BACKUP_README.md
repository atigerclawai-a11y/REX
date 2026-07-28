# REX — Encrypted Backup System

## What gets backed up (every night at 2 AM)

| Source | Contents | HIPAA |
|--------|----------|-------|
| `~/Desktop/REX/` | Training data, configs, logs, queue files, AI responses, audit trail | — |
| `~/Documents/goj files/` | Client auth DB, menus, sign-in sheets, GOJ data | ✅ Encrypted |
| All `.log` files | Sunday prep, training status, queue processor, security audit | — |
| Generated PDFs | Sign-in sheets, distribution sheets, driver lists | ✅ Encrypted |

## Encryption

- **Algorithm:** AES-256-CBC
- **Key derivation:** PBKDF2, 310,000 iterations, random salt
- **Passphrase:** Stored in macOS Keychain — never written to disk or this file
- **Output:** Single `.enc` file per backup, plus a `.manifest` (plain text index)

## One-time install (Terminal, run once)

```bash
bash ~/Desktop/REX/install_encrypted_backup_agent.sh
```

This will:
1. Ask you to create a backup passphrase (write it down — store it separately!)
2. Store the passphrase in macOS Keychain (auto-retrieved from then on)
3. Install the launchd agent (runs every night at 2:00 AM automatically)
4. Optionally run your first backup immediately

## Manual commands

```bash
# Run a backup right now
bash ~/Desktop/REX/rex_encrypted_backup.sh

# List all backups on the drive
bash ~/Desktop/REX/rex_decrypt_backup.sh --list

# Restore the latest backup
bash ~/Desktop/REX/rex_decrypt_backup.sh

# Restore a specific backup
bash ~/Desktop/REX/rex_decrypt_backup.sh --file /Volumes/cartoons/REX_Backups/REX_2026-03-29_02-00.enc

# If Keychain is unavailable (e.g. different Mac), type passphrase manually
bash ~/Desktop/REX/rex_decrypt_backup.sh --passphrase
```

## What a restore does

Decrypts the `.enc` file into `~/Desktop/REX_Restored_YYYY-MM-DD/` — a **copy** of everything at the time of backup. Your current files are never touched. Manually copy what you need from the restored folder.

## Backup location on drive

```
/Volumes/cartoons/REX_Backups/
  REX_2026-03-29_02-00.enc       ← encrypted archive
  REX_2026-03-29_02-00.manifest  ← plain-text file index (not sensitive)
  REX_2026-03-30_02-00.enc
  REX_2026-03-30_02-00.manifest
  ...
```

Keeps the **30 most recent** snapshots. Older ones are automatically pruned.

## If the drive isn't connected at 2 AM

The backup fails silently and logs the error. You'll get a Telegram alert. Connect the drive and run manually:
```bash
bash ~/Desktop/REX/rex_encrypted_backup.sh
```

## Telegram notification

After every backup (success or failure), you get a Telegram message via the Rexxie bot showing file size, drive free space, and snapshot count.
