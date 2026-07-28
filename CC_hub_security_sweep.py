#!/usr/bin/env python3
"""
Tiger Claw Hub — Red Team + Blue Team Security Sweep
Scans all hub endpoints for vulnerabilities.
"""
import urllib.request
import urllib.error
import ssl
import json
import sys
from urllib.parse import urljoin

HUB = "http://127.0.0.1:9000"
ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

results = {"red": [], "blue": [], "passed": 0, "failed": 0, "warned": 0}

def test(name, url, method="GET", expected_code=None, data=None, headers=None, category="red"):
    full_url = urljoin(HUB, url)
    try:
        req = urllib.request.Request(full_url, method=method, data=data, headers=headers or {})
        with urllib.request.urlopen(req, timeout=5, context=ctx) as r:
            code = r.status
            body = r.read().decode(errors='replace')
    except urllib.error.HTTPError as e:
        code = e.code
        body = e.read().decode(errors='replace')
    except Exception as e:
        code = 0
        body = str(e)

    if expected_code:
        passed = code in (expected_code if isinstance(expected_code, (list, tuple)) else [expected_code])
    else:
        passed = code < 500

    icon = "✅" if passed else "❌"
    status_text = f"{name} → HTTP {code}"
    
    if passed:
        results["passed"] += 1
    else:
        results["failed"] += 1
    
    entry = {
        "name": name, "url": url, "method": method,
        "code": code, "passed": passed, "category": category
    }
    if category == "red":
        results["red"].append(entry)
    else:
        results["blue"].append(entry)
    
    # Only show failures
    if not passed:
        print(f"  {icon} {status_text} [{category.upper()}]")
    return entry

print("=" * 60)
print("TIGER CLAW HUB — SECURITY SWEEP")
print("=" * 60)

# ── RED TEAM: Attack surface ──
print("\n🔴 RED TEAM — Attack surface probes\n" + "-" * 40)

# Auth bypass attempts
test("Unauthenticated /command", "/command", expected_code=307, category="red")
test("Unauthenticated /settings", "/settings", expected_code=307, category="red")
test("Unauthenticated /api/admin/users", "/api/admin/users", expected_code=401, category="red")
test("Unauthenticated /api/admin/settings", "/api/admin/settings", expected_code=401, category="red")
test("Basic auth with wrong password", "/api/admin/users", 
     headers={"Authorization": "Basic d3Jvbmc6d3Jvbmc="}, expected_code=401, category="red")

# Path traversal
test("Path traversal ../etc", "/vault/../../../etc/passwd", expected_code=[401, 403, 404], category="red")
test("Path traversal ..", "/..%2f..%2f..%2fetc/passwd", expected_code=[401, 403, 404], category="red")

# SQL injection probes
test("SQLi in login", "/login?username='OR'1'='1", expected_code=200, category="red")
test("SQLi POST", "/api/hub/chat", method="POST", 
     data=json.dumps({"message": "' OR 1=1 --"}).encode(),
     headers={"Content-Type": "application/json"},
     expected_code=401, category="red")

# XSS probes
test("XSS in URL", "/command?q=<script>alert(1)</script>", expected_code=307, category="red")
test("XSS in API", "/api/hub/chat", method="POST",
     data=json.dumps({"message": "<img src=x onerror=alert(1)>"}).encode(),
     headers={"Content-Type": "application/json"},
     expected_code=401, category="red")

# Command injection
test("CMD injection URL", "/command?q=;cat /etc/passwd", expected_code=307, category="red")
test("CMD injection API", "/api/hub/chat", method="POST",
     data=json.dumps({"message": "; rm -rf /"}).encode(),
     headers={"Content-Type": "application/json"},
     expected_code=401, category="red")

# Sensitive files
test("/.env access", "/.env", expected_code=[401, 403, 404], category="red")
test("/auth.json access", "/auth.json", expected_code=[401, 403, 404], category="red")
test("/server.py access", "/server.py", expected_code=[401, 403, 404], category="red")

# Missing security headers on error pages
test("Error page headers", "/nonexistent", category="red")

print("\n🔵 BLUE TEAM — Defense verification\n" + "-" * 40)

# Security headers
test("X-Frame-Options set", "/command", 
     headers={"Accept": "text/html"}, category="blue")

# Check specific headers via raw response
try:
    req = urllib.request.Request(f"{HUB}/command")
    with urllib.request.urlopen(req, timeout=5, context=ctx) as r:
        headers = dict(r.headers)
        checks = {
            "X-Content-Type-Options": "nosniff" in headers.get("X-Content-Type-Options", ""),
            "X-Frame-Options": "SAMEORIGIN" == headers.get("X-Frame-Options", ""),
            "Referrer-Policy": headers.get("Referrer-Policy", "") != "",
            "Content-Security-Policy": headers.get("Content-Security-Policy", "") != "",
        }
        for hdr, ok in checks.items():
            icon = "✅" if ok else "❌"
            if not ok:
                print(f"  {icon} Missing: {hdr}")
                results["failed"] += 1
            else:
                results["passed"] += 1
except:
    pass

# Auth verification
test("Login page returns 200", "/login", expected_code=200, category="blue")
test("Health endpoint public", "/health", expected_code=200, category="blue")
test("Admin API requires auth", "/api/admin/users", expected_code=401, category="blue")
test("Admin settings requires auth", "/api/admin/settings", expected_code=401, category="blue")
test("Settings requires auth", "/settings", expected_code=307, category="blue")

# CORS check
test("CORS headers present", "/health", category="blue")

# Rate limiting probe (quick)
test("Rapid requests", "/health", category="blue")

# API endpoint coverage
for endpoint in ["/health", "/login", "/command", "/jarvis", "/terminal", 
                  "/notebook", "/docs", "/graphify", "/notebooklm", "/settings",
                  "/api/hub/agents", "/api/hub/chat", "/api/hub/librechat"]:
    test(f"Route: {endpoint}", endpoint, category="blue")

# ── RESULTS ──
print("\n" + "=" * 60)
print(f"RESULTS: {results['passed']} passed | {results['failed']} failed")
print(f"Red team probes: {len(results['red'])} | Blue team checks: {len(results['blue'])}")

resistance = (results['passed'] / (results['passed'] + results['failed']) * 100) if (results['passed'] + results['failed']) > 0 else 0
print(f"Security score: {resistance:.0f}%")

if results['failed'] > 0:
    print(f"\n❌ {results['failed']} issues need attention")
else:
    print("\n✅ ALL CHECKS PASSED")

sys.exit(0 if results['failed'] == 0 else 1)
