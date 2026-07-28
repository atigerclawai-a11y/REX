#!/bin/bash
# CC_encrypt_auth_tracker.sh
# Encrypt auth_tracker.db with SQLCipher (AES-256)
# HIPAA compliance — top priority open item
#
# SAFETY: Makes backup first. Original preserved as .bak.
# Run: bash CC_encrypt_auth_tracker.sh

set -e

DB=~/Documents/goj\ files/dashboard/auth_tracker.db
DB_BAK="${DB}.bak.$(date +%Y%m%d_%H%M%S)"
DB_ENC=~/Documents/goj\ files/dashboard/auth_tracker_encrypted.db
KEY_FILE=~/.rex/auth_tracker.key

echo "🔐 SQLCipher Encryption — auth_tracker.db"
echo "=========================================="

# 1. Generate key if missing
if [ ! -f "$KEY_FILE" ]; then
    echo "Generating 32-byte AES key..."
    openssl rand -hex 32 > "$KEY_FILE"
    chmod 600 "$KEY_FILE"
    echo "✅ Key saved: $KEY_FILE"
else
    echo "✅ Key exists: $KEY_FILE"
fi

KEY=$(cat "$KEY_FILE")

# 2. Backup
echo ""
echo "📦 Backing up original..."
cp "$DB" "$DB_BAK"
echo "✅ Backup: $DB_BAK"

# 3. Create encrypted copy
echo ""
echo "🔐 Creating encrypted database..."
sqlcipher "$DB" <<SQLEOF
PRAGMA key = "x'$KEY'";
PRAGMA cipher_page_size = 4096;
PRAGMA kdf_iter = 256000;
PRAGMA cipher_hmac_algorithm = HMAC_SHA512;
PRAGMA cipher_kdf_algorithm = PBKDF2_HMAC_SHA512;
ATTACH DATABASE '$DB_ENC' AS encrypted KEY '';
SELECT sqlcipher_export('encrypted');
DETACH DATABASE encrypted;
SQLEOF

echo "✅ Encrypted DB: $DB_ENC"

# 4. Verify encrypted DB
echo ""
echo "🔍 Verifying encrypted DB..."
TABLE_COUNT=$(sqlcipher "$DB_ENC" <<SQLEOF
PRAGMA key = "x'$KEY'";
SELECT COUNT(*) FROM sqlite_master WHERE type='table';
SQLEOF
)
echo "Tables in encrypted DB: $TABLE_COUNT"

# 5. Verify plain DB is unreadable without key
echo ""
echo "🔍 Verifying encryption works..."
sqlite3 "$DB_ENC" ".tables" 2>&1 && echo "❌ ENCRYPTION FAILED — DB readable without key!" || echo "✅ Encryption verified — DB unreadable without key"

echo ""
echo "=========================================="
echo "✅ ENCRYPTION COMPLETE"
echo ""
echo "NEXT STEPS (manual):"
echo "1. Test: sqlcipher $DB_ENC → PRAGMA key=\"x'$KEY'\" → .tables"
echo "2. Update Hub endpoints to use encrypted DB + key"
echo "3. After testing: mv $DB_ENC $DB"
echo "4. Original preserved at: $DB_BAK"
