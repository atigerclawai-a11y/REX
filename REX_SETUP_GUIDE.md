# REX — Getting Everything Live
## Step-by-Step Guide

---

## PART 1 — See the New Dashboard (Gold Egg, Rexxie Toggle, etc.)

The code is done. The changes just need to be compiled once on your Mac.

**Do this once:**

1. Open **Terminal**
2. Type this and press Enter:
   ```
   cd ~/Desktop/REX/frontend && npm run build
   ```
3. Wait about 15 seconds until you see `dist/index.html` in the output
4. Then double-click **`rex-rebuild.command`** in your REX folder
   (or just run `begin` in Terminal)
5. Open **http://localhost:8000** — you'll see the new UI

**OR — Easiest method:**
Just double-click `rex-rebuild.command` in your REX folder on your Desktop.
It rebuilds AND restarts everything automatically. Takes 20 seconds.

---

## PART 2 — iPhone (PWA — Free, Works Today)

Your web app already has everything needed to be installed on iPhone.

1. Make sure your Mac is running REX (`begin` in Terminal)
2. In Terminal on Mac, run: `ipconfig getifaddr en0`
   — Write down that number (looks like `192.168.1.249`)
3. On your **iPhone**, open **Safari** (must be Safari, not Chrome)
4. Type: `http://[YOUR MAC IP]:8000` (e.g. `http://192.168.1.249:8000`)
5. Tap the **Share** button (box with upward arrow at bottom of screen)
6. Tap **"Add to Home Screen"**
7. Name it **REX** → tap **Add**

REX will now appear on your iPhone home screen as a proper app.
Opens full screen, no browser bar, gold egg and all.

**Limitation:** Your Mac must be on and running, and your iPhone must be
on the same WiFi. See Part 4 for remote access.

---

## PART 3 — iPhone Native App via Expo (Requires Payment)

You already have a full React Native app built at `~/Desktop/REX/rex-ios/`.
It has Face ID, haptics, gold egg animation, Rexxie toggle — everything.

### Step 1 — Install Expo Go (Free, immediate)
1. On your iPhone: App Store → search **"Expo Go"** → install (free)
2. In Terminal on Mac:
   ```
   cd ~/Desktop/REX && ./start-ios.sh
   ```
3. A QR code will appear in Terminal
4. Open your iPhone camera → point at the QR code → tap the link
5. REX opens in Expo Go on your iPhone

This gives you the full native app experience TODAY for free.

---

### 💳 WHEN YOU NEED TO PAY

**Apple Developer Account — $99/year**
Required to install the app directly on your iPhone (without Expo Go),
share it via TestFlight, or submit to the App Store.

Sign up at: https://developer.apple.com/programs/

Once you have that:
1. Install Xcode from the Mac App Store (free)
2. In Terminal:
   ```
   cd ~/Desktop/REX/rex-ios
   npm install
   npx expo run:ios
   ```
3. Xcode opens → plug in iPhone → tap your device → press Play
4. REX installs directly to your iPhone, no Expo Go needed

**EAS Build — Free tier available, ~$15/month for faster builds**
For building the `.ipa` file to send to TestFlight for family/staff.
Sign up at: https://expo.dev/eas

---

## PART 4 — Access REX Away from Home (Optional)

To use REX on your iPhone when NOT on home WiFi:

**Tailscale (Free for personal use)**
1. Download Tailscale on your Mac: https://tailscale.com
2. Download Tailscale on your iPhone (App Store)
3. Sign in to both with the same account
4. Your Mac gets a permanent address like `100.x.x.x`
5. Use `http://100.x.x.x:8000` in Safari — works anywhere

No monthly cost for personal use.

---

## PART 5 — What's Already Built vs What's Pending

| Feature | Status | Where |
|---|---|---|
| Gold egg + dino hatch (web) | ✅ Done | Rebuild frontend to see it |
| REX/Rexxie toggle (web) | ✅ Done | Rebuild frontend to see it |
| Rose/warm Rexxie palette | ✅ Done | Rebuild frontend to see it |
| Gold egg + Face ID (iOS) | ✅ Done | Run start-ios.sh |
| REX/Rexxie toggle (iOS) | ✅ Done | Run start-ios.sh |
| PWA / Add to Home Screen | ✅ Done | Safari → Share → Add to Home |
| Native install (no Expo Go) | 🔑 Needs $99 Apple Dev account |
| TestFlight for family/staff | 🔑 Needs $99 Apple Dev account |
| App Store listing | 🔑 Needs $99 + App Review |
| Remote access (off-WiFi) | Free via Tailscale |

---

## Summary of Costs

| What | Cost | When |
|---|---|---|
| PWA on your iPhone | **Free** | Now |
| Expo Go (native feel) | **Free** | Now |
| Apple Developer account | **$99/year** | When ready for TestFlight |
| EAS Build (optional) | **Free tier** or $15/mo | For faster CI builds |
| Tailscale (remote access) | **Free** personal | Whenever you want |
| App Store submission | Included in $99 | When ready to publish |
