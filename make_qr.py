"""
Generates a scannable QR code image for your authenticator app.
Run: python make_qr.py
Then scan ~/Desktop/rexxie_2fa_qr.png with your phone.
"""
import sys
import os
import base64
import subprocess
from pathlib import Path

# ── Step 1: Get the TOTP secret ───────────────────────────────────────────────
secret_b32 = None

# Try Keychain first
try:
    import keyring
    val = keyring.get_password("rex-sovereign", "rexxie-2fa-secret")
    if val:
        secret_b32 = val.upper()
        print("✅ Secret loaded from Keychain")
except Exception:
    pass

# Fallback: file
if not secret_b32:
    fallback = Path.home() / "Desktop" / "REX" / ".rexxie_2fa_secret"
    if fallback.exists():
        secret_b32 = fallback.read_text().strip().upper()
        print("✅ Secret loaded from file")

if not secret_b32:
    print("❌ No 2FA secret found. Run: python backend/rex_2fa.py --setup  first.")
    sys.exit(1)

# ── Step 2: Build the otpauth URI ─────────────────────────────────────────────
uri = f"otpauth://totp/REX-Sovereign:Rexxie?secret={secret_b32}&issuer=REX-Sovereign&digits=6&period=30"
print(f"\n📋 Manual entry secret (if QR doesn't work):\n   {secret_b32}\n")

# ── Step 3: Generate QR code ──────────────────────────────────────────────────
output_path = Path.home() / "Desktop" / "rexxie_2fa_qr.png"

# Try qrcode library
try:
    import qrcode
    img = qrcode.make(uri)
    img.save(str(output_path))
    print(f"✅ QR code saved to: {output_path}")
    subprocess.run(["open", str(output_path)])   # Opens in Preview automatically
    print("   Preview opened — scan the QR code with your authenticator app.")
    sys.exit(0)
except ImportError:
    pass

# Try segno library
try:
    import segno
    qr = segno.make(uri, error='m')
    qr.save(str(output_path), scale=10)
    print(f"✅ QR code saved to: {output_path}")
    subprocess.run(["open", str(output_path)])
    print("   Preview opened — scan the QR code with your authenticator app.")
    sys.exit(0)
except ImportError:
    pass

# Neither library available — install qrcode and retry
print("Installing qrcode library...")
subprocess.run([sys.executable, "-m", "pip", "install", "qrcode[pil]", "--quiet"])
try:
    import qrcode
    img = qrcode.make(uri)
    img.save(str(output_path))
    print(f"✅ QR code saved to: {output_path}")
    subprocess.run(["open", str(output_path)])
    print("   Preview opened — scan it with your authenticator app.")
except Exception as e:
    print(f"\n⚠️  Could not generate image: {e}")
    print(f"\nManual entry instead:")
    print(f"  App: Google Authenticator / Authy / Apple Passwords")
    print(f"  Account name: Rexxie")
    print(f"  Secret key:   {secret_b32}")
    print(f"  Type:         Time-based")
