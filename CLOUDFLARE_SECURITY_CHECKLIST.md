# Cloudflare Security Checklist — goldhealthsys.com
### Complete these steps in the Cloudflare dashboard BEFORE going live

Go to: **dash.cloudflare.com → goldhealthsys.com**

---

## ✅ LAYER 1 — Zero Trust Access (Most Important)
> This is a login wall that blocks EVERYONE before they even reach REX.
> Even if someone finds the URL, they hit a Cloudflare auth screen first.

1. Go to **Zero Trust** (left sidebar) → **Access** → **Applications** → **Add an application**
2. Choose **Self-hosted**
3. Fill in:
   - App name: `REX Dashboard`
   - Subdomain: `goldhealthsys.com` (or use `*` to cover www too)
4. Under **Policies**, click **Add a policy**:
   - Policy name: `GOJ Authorized Users`
   - Action: `Allow`
   - Rule: `Emails` → add:
     - `atigerclawai@gmail.com` (Kato / Chairman)
     - Add any other authorized email (Vlad, etc.)
5. Click **Save**

**What this does:** Anyone visiting goldhealthsys.com first sees a Cloudflare login page asking for their email. Cloudflare sends them a one-time code. Only the emails you listed can get through. REX never sees unauthorized traffic at all.

---

## ✅ LAYER 2 — SSL/TLS Settings

1. Go to **SSL/TLS** → **Overview**
2. Set mode to: **Full (strict)**
   - This ensures end-to-end encryption — browser → Cloudflare → tunnel → REX
3. Go to **SSL/TLS** → **Edge Certificates**
4. Enable:
   - ✅ **Always Use HTTPS** — redirects all HTTP to HTTPS automatically
   - ✅ **HSTS** → Enable → Max Age: **12 months** → Include subdomains: ✅ → Preload: ✅
   - ✅ **Minimum TLS Version**: TLS 1.2 (blocks old, vulnerable versions)
   - ✅ **Opportunistic Encryption**: On

---

## ✅ LAYER 3 — WAF (Web Application Firewall)

1. Go to **Security** → **WAF** → **Managed rules**
2. Enable: **Cloudflare Managed Ruleset** (free tier includes this)
3. Enable: **Cloudflare OWASP Core Ruleset** — blocks SQL injection, XSS, etc.
4. Go to **Security** → **WAF** → **Custom rules** → **Create rule**:

**Rule 1 — Block non-US traffic (optional but recommended for GOJ):**
- Name: `Block non-US`
- Expression: `(ip.geoip.country ne "US")`
- Action: Block
- *(Only do this if all authorized users are in the US)*

**Rule 2 — Block known bad bots:**
- Name: `Block bad user agents`
- Expression: `(http.user_agent contains "sqlmap") or (http.user_agent contains "nikto") or (http.user_agent contains "masscan") or (http.user_agent eq "")`
- Action: Block

**Rule 3 — Rate limit login-style endpoints:**
- Name: `Rate limit auth`
- Expression: `(http.request.uri.path contains "/api/auth")`
- Action: Block (rate limit: 10 requests per minute per IP)

---

## ✅ LAYER 4 — Bot Protection

1. Go to **Security** → **Bots**
2. Enable: **Bot Fight Mode** ✅
   - This blocks automated scanners, credential stuffers, and scrapers
3. If on Pro plan: enable **Super Bot Fight Mode** (more aggressive)

---

## ✅ LAYER 5 — DDoS Protection

1. Go to **Security** → **DDoS**
2. Set **HTTP DDoS attack protection** to: **High**
3. This is automatic on all Cloudflare plans

---

## ✅ LAYER 6 — Security Level & Challenge Settings

1. Go to **Security** → **Settings**
2. Set **Security Level**: `High`
   - Challenges suspicious IPs automatically (CAPTCHA/JS challenge)
3. Enable: **Browser Integrity Check** ✅
   - Rejects requests from browsers with suspicious headers
4. **Challenge Passage**: 30 minutes
   - Once a user passes a challenge, they're trusted for 30 min

---

## ✅ LAYER 7 — Privacy & Scrape Shield

1. Go to **Scrape Shield**
2. Enable: **Email Address Obfuscation** ✅ (hides email addresses from bots)
3. Enable: **Server-side Excludes** ✅

---

## ✅ LAYER 8 — Notifications & Alerts

1. Go to **Notifications** (top right → bell icon)
2. Add alerts for:
   - **Security** → **DDoS Attack** — email Kato when an attack is detected
   - **Security** → **WAF Attack** — email when WAF blocks a spike of requests
   - **Health Checks** — alert if goldhealthsys.com goes down

---

## Launch Order

Run these in order on your Mac terminal:

```bash
# 1. Run security hardening (firewall, env, secrets check)
bash ~/Desktop/REX/setup_security_hardening.sh

# 2. Start REX backend (must be running before tunnel)
bash ~/Desktop/REX/run.sh

# 3. Set up Cloudflare tunnel (run once, auto-starts after)
bash ~/Desktop/REX/setup_cloudflare_tunnel.sh
```

Then complete the Cloudflare dashboard steps above.

---

## Security Architecture Summary

```
Internet
   │
   ▼
Cloudflare Edge (Layer 2–7 above)
   │  ✅ HTTPS enforced
   │  ✅ Zero Trust Access (email auth wall)
   │  ✅ WAF (OWASP + managed rules)
   │  ✅ Bot Fight Mode
   │  ✅ DDoS protection
   │  ✅ Geo-blocking (optional)
   │
   ▼
Cloudflare Tunnel (encrypted, no open ports)
   │  ✅ No port forwarding on your router
   │  ✅ Mac firewall blocks port 8000 from internet
   │  ✅ Only Cloudflare IPs can reach REX
   │
   ▼
REX FastAPI (localhost:8000)
   │  ✅ CORS locked to goldhealthsys.com
   │  ✅ Security headers on every response
   │  ✅ Rate limiting (20 req/min on chat)
   │  ✅ /docs and /redoc disabled
   │  ✅ Role-based auth (Chairman / Vlad / Staff)
   │  ✅ Device manager (iPhone pairing JWT)
   │  ✅ Audit logger on every action
   │  ✅ Encrypted storage (AES)
   │  ✅ De-identification engine (PHI protection)
   │
   ▼
Data (encrypted at rest)
   ✅ Encrypted SQLite (AES-256)
   ✅ Chairman-only vault (separate key)
   ✅ Triple-encrypted Rexxie DB
   ✅ Paperless-NGX (document archive)
```

**6 layers between the internet and any GOJ data.** Even if Cloudflare is compromised, an attacker still hits REX's own auth. Even if REX's auth is bypassed, the data is encrypted at rest.
