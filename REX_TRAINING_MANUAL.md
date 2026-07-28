# REX — Chairman's Training Manual
**Version 3.0 · Last Updated: March 2026**
**Classified: Chairman Eyes Only**

---

## What REX Is

REX is your sovereign AI workspace running entirely on your Mac Mini. It is not a cloud service — every message is encrypted locally before anything leaves your machine. REX has three jobs: protect your information, remember what matters, and handle GOJ operations intelligently.

REX runs at `http://localhost:8000` (or whatever IP your Mac Mini has on your local network). The frontend is the web app you interact with. The backend is a FastAPI server handling AI routing, memory, encryption, and the phone unlock server.

---

## Starting and Stopping REX

**Start REX:**
```bash
cd ~/Desktop/REX && ./run.sh
```
Or double-click `rex-rebuild.command` on your Desktop if you've just updated the code.

**Restart after a code change:**
```bash
cd ~/Desktop/REX && ./rex-rebuild.command
```

**Stop REX:**
Press `Ctrl+C` in the terminal running REX, or close that terminal window.

**Check if REX is running:**
Open your browser to `http://localhost:8000` — if REX loads, it's up.

---

## The Dashboard — What Everything Does

### Rexts (formerly Journeys)
Each conversation is called a **Rext**. Rexts are saved to the encrypted database automatically. You can:
- Create a **New Rext** with the `+` button in the sidebar
- **Rename** a Rext by clicking its title (if this feature is available in your version)
- **Organize** Rexts into folders by clicking `+ folder` in the sidebar, then dragging Rexts or using the folder dropdown on any active Rext
- **Double-click** a folder name to rename it

### REX ↔ Rexxie Toggle
The toggle at the top of the sidebar switches between:
- **🦖 REX** — standard mode: full GOJ operations, business memory, all staff-accessible features
- **🐢 Rexxie** — private mode: completely isolated, triple-encrypted, Chairman only (see Rexxie manual)

### Quick Task (⚡)
The lightning bolt button in the top bar (or floating button, bottom-right) opens the **Quick Task panel** — a separate mini-chat for things you need to do quickly without creating a Rext. Nothing in the Quick Task panel is saved to the database.

**Good for:** quick calculations, drafting a sentence, looking something up, brainstorming a name.

### HIPAA Secure Mode (🛡)
Toggle the **HIPAA** button in the top bar to enable de-identification. In Secure Mode:
- All PHI (names, dates, locations, medical identifiers) is automatically stripped before messages leave your machine
- Replaced with placeholders that are re-inserted on the response
- The audit log captures every detection event

**Always use Secure Mode when discussing real patient data, real staff names, or real locations with the AI.**

### Model Selector
The dropdown in the top bar selects which AI you're routing through. Options include:
- **Anthropic (Claude)** — best for complex reasoning, writing, analysis
- **OpenAI (GPT)** — solid general-purpose fallback
- **Google (Gemini)** — strong for document work
- **Local (Ollama)** — runs 100% offline on your Mac Mini, no data leaves at all. Requires Ollama to be open.

### Settings (⚙)
- **Appearance** — themes (Light, Dark, Midnight, Warm, Ocean, Forest, Sunset, Custom), accent color picker, font size, message spacing
- **Custom Theme** — choose your own background, card, accent, and text colors using the color pickers
- **API Keys** — add/update provider API keys (stored in macOS Keychain, never on disk)
- **System** — encryption status, key fingerprint, database path

---

## Memory and What REX Remembers

REX has persistent memory — it remembers key facts across sessions automatically. Memory is stored in `rex_memory.db`, encrypted with AES-256-GCM.

**Memory is role-filtered:** Staff see only staff-level memory. Only the Chairman sees Chairman-level memory.

**Adding memories:**
REX captures important information automatically from conversations. You can also explicitly say:
- `"remember this: [fact]"` — stores with emphasis
- `"this is important: [fact]"` — same effect

**Memory is separate from Rexts.** Rexts are conversation threads. Memory is the persistent knowledge layer that loads at the start of every new conversation.

---

## Vault Mode

The Chairman Vault provides an additional encryption layer for the most sensitive operations. When Vault Mode is active:
- REX uses AES-256-GCM + additional key hardening
- The vault key is stored in macOS Keychain under `rex-sovereign`
- Vault Mode is shown in the health status at `http://localhost:8000/api/health`

---

## Encrypted Transcripts

Every conversation is now automatically saved as a **triple-encrypted transcript** (AES-256-GCM → ChaCha20-Poly1305 → AES-256-GCM) to `~/Desktop/REX/transcripts/`.

**To view your transcripts:**
```bash
cd ~/Desktop/REX
python backend/rex_encrypted_transcript.py --list
python backend/rex_encrypted_transcript.py --read <filename.rext>
```

**To export as plain text (for printing — delete after):**
```bash
python backend/rex_encrypted_transcript.py --export <filename.rext>
```

---

## Phone Unlock

Your iPhone can unlock your Mac Mini remotely via a Shortcut.

**If it stops working (usually after a network change):**
```bash
cd ~/Desktop/REX && python3 rex_phone_unlock.py --setup
```
This prints updated Shortcut URLs using your Mac's `.local` hostname so IP changes never break it again.

---

## Session Resume

REX remembers the last 30 minutes of your conversation if the connection drops. When you reconnect, it picks up where you left off automatically. The session cache is now **encrypted** (`.rex_session_cache.enc`) — the old plaintext version was automatically migrated.

---

## Audit Log

Every sensitive action is logged to `~/Desktop/REX/rex_audit.log`. This includes: app start/stop, PHI detection events, Vault mode toggles, API key changes, journey creation. The log is in plaintext for easy review but contains no sensitive content.

---

## Common Commands (run from `~/Desktop/REX`)

| Task | Command |
|------|---------|
| Start REX | `./run.sh` |
| Rebuild frontend | `./rex-rebuild.command` |
| View health | `curl http://localhost:8000/api/health` |
| List transcripts | `python backend/rex_encrypted_transcript.py --list` |
| Reset REX (emergency) | `python rex_reset.py` |
| Check backup status | `python rex_backup.py --status` |
| Run security audit | `python rex_security_audit.py` |
| Phone unlock setup | `python3 rex_phone_unlock.py --setup` |

---

## Security Architecture (Summary)

| Layer | What It Does |
|-------|-------------|
| TLS (HTTPS/WSS) | Encrypts data in transit between your devices |
| AES-256-GCM | Encrypts conversation storage and session cache |
| Triple-layer (AES→ChaCha→AES) | Encrypts Rexxie memories and transcripts |
| macOS Keychain | Stores all master keys — never written to disk |
| HKDF key derivation | Each encryption purpose gets a unique derived key |
| Shamir's Secret Sharing | 3-part vault recovery (print and store separately) |
| TOTP 2FA | Time-based one-time password via authenticator app |
| De-identification | PHI stripped before any external AI call in Secure Mode |

---

## Troubleshooting

**REX won't start:**
Check that Python dependencies are installed: `cd ~/Desktop/REX && pip install -r requirements.txt --break-system-packages`

**"No API key" warning on startup:**
Go to Settings → API Keys and add your Anthropic key.

**Ollama models not showing:**
Make sure the Ollama app is open and running on your Mac.

**Phone unlock not working:**
Run `--setup` again (see above). Your router may have changed your Mac's IP.

**WebSocket keeps disconnecting:**
REX now sends a keepalive ping every 25 seconds. If you still see disconnects, check that your Mac's Power Nap settings aren't cutting the local network.

---

*This document is encrypted if stored inside the REX transcripts folder. If printed, treat as confidential.*
