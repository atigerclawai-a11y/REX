"""Quick config diagnostic"""
import json
from pathlib import Path

# Test both config paths
rex_path = Path.home() / "Desktop" / "REX" / "rex_telegram_config.json"
rexxie_path = Path.home() / "Desktop" / "REX" / "rex_rexxie_telegram_config.json"

print(f"Path.home() = {Path.home()}")
print(f"REX config:    {rex_path}  exists={rex_path.exists()}")
print(f"Rexxie config: {rexxie_path}  exists={rexxie_path.exists()}")

for name, path in [("REX", rex_path), ("Rexxie", rexxie_path)]:
    if path.exists():
        try:
            cfg = json.loads(path.read_text())
            token = cfg.get("bot_token", "MISSING")
            print(f"{name}: token={'PRESENT' if token else 'MISSING'}  keys={list(cfg.keys())}")
        except Exception as e:
            print(f"{name}: ERROR: {e}")
    else:
        print(f"{name}: FILE NOT FOUND")
