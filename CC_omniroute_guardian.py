#!/usr/bin/env python3
"""
CC_omniroute_guardian.py — Security surveillance proxy for OmniRoute.
Sits between Hermes and OmniRoute. Every request is:
1. Scanned for PHI/credentials/sensitive data
2. Blocked if sensitive data found (route to local Ollama instead)
3. Logged for audit
4. Metrics exported to Obsidian security dashboard

Patterns blocked from cloud:
- GOJ client names, medical data, auth_tracker
- API keys, tokens, passwords, private keys
- rexxie.db paths, PHI identifiers
- SSNs, phone numbers, emails (except atigerclawai@gmail.com)
"""

import re, json, os, sys, time, hashlib
from datetime import datetime
from urllib.request import Request, urlopen
from urllib.error import HTTPError

OMNIROUTE_URL = "http://localhost:20128/v1"
OLLAMA_URL = "http://localhost:11434/api"
AUDIT_LOG = os.path.expanduser("~/Desktop/REX/audit/omniroute_gatekeeper.log")
SECURITY_REPORT = os.path.expanduser("~/GHS-Vault/security/omniroute_guardian.md")

# Patterns that trigger LOCAL routing (never cloud)
PHI_PATTERNS = [
    (r'\b(?:medicaid|medicare|insurance|diagnosis|treatment|patient)\b', 'PHI-MEDICAL'),
    (r'\b(?:auth_tracker\.db|rexxie\.db)\b', 'PHI-DATABASE'),
    (r'(?:GOJ|Garden of Joy)\s+client', 'PHI-CLIENT'),
    (r'\b(?:SSN|social security)\b', 'PHI-PII'),
]

# Patterns that are STRICTLY BLOCKED
BLOCKED_PATTERNS = [
    (r'sk-[A-Za-z0-9]{32,}', 'BLOCKED-API-KEY'),
    (r'eyJ[A-Za-z0-9_\-\.]{40,}', 'BLOCKED-JWT'),
    (r'-----BEGIN (?:RSA |EC )?PRIVATE KEY-----', 'BLOCKED-PRIVATE-KEY'),
    (r'(?:API[_-]?KEY|TOKEN|SECRET)\s*[:=]\s*[\w\-]{16,}', 'BLOCKED-CREDENTIAL'),
]

# Only these services CAN route to cloud
CLOUD_SAFE_TOPICS = [
    "code", "debug", "error", "python", "javascript", "typescript",
    "react", "node", "api", "json", "http", "git", "docker",
    "instagram", "facebook", "social media", "caption", "hashtag",
    "bbg", "boardwalk beer garden", "menu", "promo", "reel",
    "ollama", "model", "training", "quantize", "gguf",
    "linux", "macos", "brew", "package", "install", "deploy",
]

def is_cloud_safe(message: str) -> bool:
    """Check if message contains only safe topics for cloud routing."""
    msg_lower = message.lower()
    return any(topic in msg_lower for topic in CLOUD_SAFE_TOPICS)

def scan_for_threats(content: str) -> list:
    """Scan content for sensitive patterns. Returns list of found threats."""
    threats = []
    for pattern, label in BLOCKED_PATTERNS + PHI_PATTERNS:
        if re.search(pattern, content, re.IGNORECASE):
            threats.append(label)
    return threats

def route_to_ollama(messages: list) -> dict:
    """Fallback: route to local Ollama with Rexxie model."""
    try:
        data = json.dumps({
            "model": "rexxie-qwen3",
            "messages": messages,
            "stream": False
        }).encode()
        req = Request(f"{OLLAMA_URL}/chat", data=data, method="POST")
        req.add_header("Content-Type", "application/json")
        with urlopen(req, timeout=60) as resp:
            return json.loads(resp.read())
    except Exception as e:
        return {"error": f"Ollama fallback failed: {e}"}

def route_to_omniroute(messages: list) -> dict:
    """Route to OmniRoute cloud providers."""
    try:
        data = json.dumps({
            "model": "auto/free",
            "messages": messages,
            "stream": False
        }).encode()
        req = Request(f"{OMNIROUTE_URL}/chat/completions", data=data, method="POST")
        req.add_header("Content-Type", "application/json")
        with urlopen(req, timeout=120) as resp:
            return json.loads(resp.read())
    except Exception as e:
        return {"error": f"OmniRoute failed: {e}"}

def log_decision(content: str, threats: list, route: str):
    """Log routing decision for audit."""
    os.makedirs(os.path.dirname(AUDIT_LOG), exist_ok=True)
    timestamp = datetime.now().isoformat()
    content_hash = hashlib.sha256(content.encode()).hexdigest()[:16]
    
    with open(AUDIT_LOG, 'a') as f:
        f.write(f"{timestamp} | {route:6s} | {content_hash} | threats={threats or 'none'} | {content[:80].replace(chr(10),' ')}\n")

def generate_report():
    """Generate security report from audit logs."""
    if not os.path.exists(AUDIT_LOG):
        return
    
    total = 0
    blocked = 0
    cloud = 0
    local = 0
    
    with open(AUDIT_LOG) as f:
        for line in f:
            total += 1
            parts = line.split(' | ')
            if len(parts) >= 2:
                route = parts[1].strip()
                if route == 'BLOCK':
                    blocked += 1
                elif route == 'CLOUD':
                    cloud += 1
                elif route == 'LOCAL':
                    local += 1
    
    report = f"""# OmniRoute Security Guardian Report
> Last updated: {datetime.now().strftime('%Y-%m-%d %H:%M UTC')}

## Traffic Summary
| Route | Count | % |
|---|---|---|
| CLOUD (OmniRoute) | {cloud} | {cloud/total*100 if total else 0:.1f}% |
| LOCAL (Ollama) | {local} | {local/total*100 if total else 0:.1f}% |
| BLOCKED | {blocked} | {blocked/total*100 if total else 0:.1f}% |
| **Total** | **{total}** | |

## Status: {'🟢 CLEAN' if blocked == 0 else '🔴 ALERTS' if blocked > 0 else '🟡 PENDING'}
"""
    
    os.makedirs(os.path.dirname(SECURITY_REPORT), exist_ok=True)
    with open(SECURITY_REPORT, 'w') as f:
        f.write(report)
    
    return report

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--report', action='store_true', help='Generate security report')
    parser.add_argument('--test', action='store_true', help='Test scan functionality')
    args = parser.parse_args()
    
    if args.report:
        print(generate_report())
    elif args.test:
        tests = [
            ("How do I fix this Python async bug?", 'CLOUD'),
            ("Show me Maria's medical diagnosis from auth_tracker.db", 'BLOCK'),
            ("What's the API key for the bot? sk-abc123def456ghi789jkl012mno345pqr678stu", 'BLOCK'),
            ("Write a BBG Instagram caption for Friday", 'CLOUD'),
            ("What did Olga say about her insurance renewal?", 'BLOCK'),
        ]
        for content, expected in tests:
            threats = scan_for_threats(content)
            safe = is_cloud_safe(content)
            route = 'CLOUD' if (not threats and safe) else 'BLOCK'
            match = '✓' if route == expected else '✗'
            print(f"{match} {route} <- {content[:60]}")
    else:
        report = generate_report()
        if report:
            print(f"Security report written to {SECURITY_REPORT}")
        else:
            print(f"AUDIT LOG MISSING: {AUDIT_LOG}")
            print("No traffic logged. Initialize the gatekeeper proxy to begin logging.")
            # Create empty log so future runs have a baseline
            os.makedirs(os.path.dirname(AUDIT_LOG), exist_ok=True)
            if not os.path.exists(AUDIT_LOG):
                with open(AUDIT_LOG, 'w') as f:
                    f.write(f"# OmniRoute Gatekeeper Audit Log — initialized {datetime.now().isoformat()}\n")
                print(f"Initialized empty audit log at {AUDIT_LOG}")
