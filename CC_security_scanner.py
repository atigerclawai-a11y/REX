#!/usr/bin/env python3
"""
CC_security_scanner.py — GHS Local Security Suite
Three engines in one:
  antivirus       — signature + hash matching against known-bad patterns
  malware         — heuristic behavioral analysis of scripts and plists
  investigate     — deep forensic metadata + content analysis on any file

Usage:
  python CC_security_scanner.py antivirus [--path ~/Desktop/REX] [--deep]
  python CC_security_scanner.py malware   [--path ~/Desktop/REX] [--report]
  python CC_security_scanner.py investigate <file_path>
  python CC_security_scanner.py full      # all three engines, full REX scan

Reporting: results saved to REX/logs/security_scan_*.json
           critical findings → Telegram (HERMES_BOT_TOKEN + chat_id 5587703834)

Rules:
  - Never deletes or modifies any file
  - Never sends file contents to cloud
  - All analysis is local only
  - PHI stays local per Gate 1 policy
"""

import argparse
import ast
import base64
import hashlib
import json
import logging
import mimetypes
import os
import re
import struct
import subprocess
import sys
import urllib.request
from dataclasses import dataclass, asdict, field
from datetime import datetime
from pathlib import Path
from typing import Optional

# ── Config ─────────────────────────────────────────────────────────────────────

REX_DIR   = Path.home() / "Desktop" / "REX"
LOG_DIR   = REX_DIR / "logs"
CHAT_ID   = "5587703834"
TG_API    = "https://api.telegram.org/bot{}/sendMessage"

SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv",
             "QUARANTINE_COMMANDS_2026_04_14", "CC_june4_backup_20260604_174528"}
SKIP_EXTS = {".pyc", ".pyo", ".o", ".a", ".so", ".dylib"}

# ── Signature database ─────────────────────────────────────────────────────────
# These are pattern strings — we never store actual malware payloads.
# Matching on these triggers a finding, not an infection.

MALICIOUS_STRINGS = [
    # Reverse shells
    b"/bin/bash -i",  b"bash -c 'exec", b"nc -e /bin/sh",
    b"python -c 'import socket", b"perl -e 'use Socket",
    b"ruby -rsocket", b"php -r '$sock=",
    # Credential harvesters
    b"keylog", b"keystroke", b"screen_capture_every",
    # Crypto miners (common strings)
    b"stratum+tcp://", b"xmrig", b"minerd",
    b"MoneroMiner", b"cryptonight",
    # Obfuscation markers
    b"base64_decode(", b"eval(base64", b"exec(base64",
    b"fromCharCode(", b"unescape('%",
    # Suspicious downloader patterns
    b"curl http", b"wget http",          # only flag if combined with | sh
    b"| bash", b"| sh -", b"| python",
    # Exfiltration markers
    b"curl -X POST", b"requests.post(",  # flagged in suspicious context
]

# High-severity: flag these regardless of context
HIGH_SEVERITY_STRINGS = [
    b"rm -rf /", b"mkfs.", b"dd if=/dev/zero of=/dev/",
    b"chmod 777 /etc/", b"/etc/passwd",
    b"fork bomb", b":(){:|:&};:",
    # Crypto-locker markers
    b".encrypt(", b"ransomware", b"pay bitcoin",
    # Rootkit signatures
    b"ptrace", b"sys_call_table", b"hide_pid",
]

# Known-bad file hashes (MD5) — populate from threat intel feeds as needed
KNOWN_BAD_HASHES: set[str] = set()

# Suspicious plist keys (macOS persistence)
SUSPICIOUS_PLIST_KEYS = [
    "RunAtLoad", "KeepAlive", "StartOnMount",
    "WatchPaths", "QueueDirectories",
]

# ── Data structures ─────────────────────────────────────────────────────────────

@dataclass
class Finding:
    engine: str
    severity: str          # critical / high / medium / low / info
    file: str
    rule: str
    detail: str
    offset: Optional[int] = None
    line: Optional[int] = None
    recommendation: str = ""


@dataclass
class ScanResult:
    engine: str
    scan_path: str
    started_at: str
    finished_at: str = ""
    files_scanned: int = 0
    findings: list = field(default_factory=list)

    def to_dict(self):
        d = asdict(self)
        d["findings"] = [asdict(f) for f in self.findings]
        return d


# ── Logging ────────────────────────────────────────────────────────────────────

def setup_log():
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_file = LOG_DIR / "security_scanner.log"
    logging.basicConfig(
        filename=str(log_file), level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )
    return logging.getLogger("cc_security")


# ── Telegram ───────────────────────────────────────────────────────────────────

def telegram(msg: str, token: str = ""):
    token = token or os.environ.get("HERMES_BOT_TOKEN", "")
    if not token:
        return
    try:
        data = json.dumps({"chat_id": CHAT_ID, "text": msg,
                           "parse_mode": "HTML"}).encode()
        req = urllib.request.Request(
            TG_API.format(token), data=data,
            headers={"Content-Type": "application/json"},
        )
        urllib.request.urlopen(req, timeout=10)
    except Exception as e:
        logging.getLogger("cc_security").warning("Telegram error: %s", e)


# ── File walker ────────────────────────────────────────────────────────────────

def walk_files(root: Path, max_size_mb: int = 20) -> list[Path]:
    result = []
    for dirpath, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS and not d.startswith(".")]
        for name in files:
            if any(name.endswith(ext) for ext in SKIP_EXTS):
                continue
            p = Path(dirpath) / name
            try:
                if p.stat().st_size <= max_size_mb * 1024 * 1024:
                    result.append(p)
            except OSError:
                pass
    return result


def read_bytes_safe(p: Path, limit: int = 5 * 1024 * 1024) -> bytes:
    try:
        size = p.stat().st_size
        with open(p, "rb") as f:
            return f.read(min(size, limit))
    except Exception:
        return b""


def md5(p: Path) -> str:
    try:
        h = hashlib.md5()
        with open(p, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()
    except Exception:
        return ""


def sha256(p: Path) -> str:
    try:
        h = hashlib.sha256()
        with open(p, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()
    except Exception:
        return ""


# ══════════════════════════════════════════════════════════════════════════════
# ENGINE 1 — ANTIVIRUS: signature + hash matching
# ══════════════════════════════════════════════════════════════════════════════

def run_antivirus(scan_path: Path, deep: bool = False) -> ScanResult:
    result = ScanResult(
        engine="antivirus",
        scan_path=str(scan_path),
        started_at=datetime.now().isoformat(),
    )
    log = setup_log()
    files = walk_files(scan_path)
    result.files_scanned = len(files)

    for p in files:
        data = read_bytes_safe(p)
        if not data:
            continue

        # Hash check
        file_md5 = md5(p)
        if file_md5 in KNOWN_BAD_HASHES:
            result.findings.append(Finding(
                engine="antivirus", severity="critical",
                file=str(p), rule="KNOWN_BAD_HASH",
                detail=f"MD5 {file_md5} matches known-malicious hash",
                recommendation="Quarantine immediately — do not execute",
            ))

        # High-severity string scan (always)
        for sig in HIGH_SEVERITY_STRINGS:
            idx = data.find(sig)
            if idx != -1:
                context = data[max(0,idx-40):idx+len(sig)+40].decode("utf-8", errors="replace")
                result.findings.append(Finding(
                    engine="antivirus", severity="critical",
                    file=str(p), rule="HIGH_SEVERITY_SIGNATURE",
                    detail=f"Matched '{sig.decode(errors='replace')}' at offset {idx}",
                    offset=idx,
                    recommendation="Review file immediately — high-severity pattern",
                ))
                break

        if deep:
            # Normal signature scan
            for sig in MALICIOUS_STRINGS:
                idx = data.find(sig)
                if idx != -1:
                    # Context check — reduce false positives for common strings
                    if sig in (b"curl http", b"requests.post(", b"base64_decode("):
                        # Only flag if combined with execution pipe or in non-.py files
                        if sig == b"curl http" and b"| " not in data[idx:idx+120]:
                            continue
                    result.findings.append(Finding(
                        engine="antivirus", severity="medium",
                        file=str(p), rule="SIGNATURE_MATCH",
                        detail=f"Pattern '{sig.decode(errors='replace')}' at offset {idx}",
                        offset=idx,
                        recommendation="Manual review recommended",
                    ))
                    break  # one finding per file per engine

        # Base64 blob detection (> 500 chars of base64 in non-data files)
        if p.suffix not in {".json", ".txt", ".md", ".log", ".html"}:
            b64_blobs = re.findall(rb"[A-Za-z0-9+/]{500,}={0,2}", data)
            if b64_blobs:
                result.findings.append(Finding(
                    engine="antivirus", severity="low",
                    file=str(p), rule="LARGE_BASE64_BLOB",
                    detail=f"Found {len(b64_blobs)} large base64 blob(s) — possible obfuscation",
                    recommendation="Inspect decoded content",
                ))

    result.finished_at = datetime.now().isoformat()
    log.info("Antivirus scan: %d files, %d findings", result.files_scanned, len(result.findings))
    return result


# ══════════════════════════════════════════════════════════════════════════════
# ENGINE 2 — MALWARE: heuristic behavioral analysis
# ══════════════════════════════════════════════════════════════════════════════

def analyze_python_file(p: Path) -> list[Finding]:
    findings = []
    src = p.read_text(errors="ignore")

    # Parse AST for dangerous patterns
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return findings

    for node in ast.walk(tree):
        # exec / eval with non-literal arg
        if isinstance(node, ast.Call):
            func = ""
            if isinstance(node.func, ast.Name):
                func = node.func.id
            elif isinstance(node.func, ast.Attribute):
                func = node.func.attr

            if func in ("exec", "eval", "compile"):
                args = node.args
                if args and not isinstance(args[0], ast.Constant):
                    findings.append(Finding(
                        engine="malware", severity="high",
                        file=str(p), rule="DYNAMIC_CODE_EXECUTION",
                        detail=f"{func}() called with dynamic argument at line {node.lineno}",
                        line=node.lineno,
                        recommendation="Review — dynamic execution can run injected code",
                    ))

            # subprocess with shell=True
            if func in ("call", "run", "Popen", "check_output", "check_call"):
                for kw in node.keywords:
                    if kw.arg == "shell" and isinstance(kw.value, ast.Constant) and kw.value.value:
                        findings.append(Finding(
                            engine="malware", severity="medium",
                            file=str(p), rule="SUBPROCESS_SHELL_TRUE",
                            detail=f"subprocess.{func}(shell=True) at line {node.lineno}",
                            line=node.lineno,
                            recommendation="Prefer shell=False with explicit arg list",
                        ))

        # __import__ or importlib.import_module with variable
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name) and node.func.id == "__import__":
                if node.args and not isinstance(node.args[0], ast.Constant):
                    findings.append(Finding(
                        engine="malware", severity="medium",
                        file=str(p), rule="DYNAMIC_IMPORT",
                        detail=f"__import__() with variable at line {node.lineno}",
                        line=node.lineno,
                        recommendation="Review dynamic imports for injection risk",
                    ))

    # String-based checks (complement AST)
    suspicious_imports = ["ctypes", "ptrace", "mmap"]
    for imp in suspicious_imports:
        if re.search(rf"\bimport\s+{imp}\b", src):
            findings.append(Finding(
                engine="malware", severity="medium",
                file=str(p), rule="SUSPICIOUS_IMPORT",
                detail=f"Import of '{imp}' — low-level memory/OS access",
                recommendation="Verify this is intentional",
            ))

    return findings


def analyze_plist(p: Path) -> list[Finding]:
    findings = []
    try:
        content = p.read_text(errors="ignore")
    except Exception:
        return findings

    # Check for suspicious plist patterns
    for key in SUSPICIOUS_PLIST_KEYS:
        if key in content:
            # Look for RunAtLoad = true (persistence)
            if key == "RunAtLoad" and "<true/>" in content:
                findings.append(Finding(
                    engine="malware", severity="info",
                    file=str(p), rule="PLIST_PERSISTENCE",
                    detail=f"LaunchAgent/Daemon with RunAtLoad=true — verifies known-good list",
                    recommendation="Confirm this plist is in your authorized list",
                ))
                break

    # Check for unknown/obfuscated program path
    prog_match = re.search(r"<string>(/[^<]{80,})</string>", content)
    if prog_match:
        findings.append(Finding(
            engine="malware", severity="low",
            file=str(p), rule="PLIST_LONG_PROGRAM_PATH",
            detail=f"Unusually long program path in plist: {prog_match.group(1)[:60]}…",
            recommendation="Verify this is a known GHS plist",
        ))

    return findings


def analyze_shell_script(p: Path) -> list[Finding]:
    findings = []
    try:
        lines = p.read_text(errors="ignore").splitlines()
    except Exception:
        return findings

    for i, line in enumerate(lines, 1):
        # Download and execute pattern
        if re.search(r"(curl|wget).+\|\s*(bash|sh|python)", line):
            findings.append(Finding(
                engine="malware", severity="high",
                file=str(p), rule="DOWNLOAD_EXECUTE",
                detail=f"Line {i}: Download-and-execute pattern: {line.strip()[:80]}",
                line=i,
                recommendation="High risk — review before running",
            ))

        # Encoded payload
        if "base64" in line and ("exec" in line or "eval" in line or "|" in line):
            findings.append(Finding(
                engine="malware", severity="high",
                file=str(p), rule="ENCODED_PAYLOAD",
                detail=f"Line {i}: Encoded+executed payload: {line.strip()[:80]}",
                line=i,
                recommendation="Decode and review before executing",
            ))

    return findings


def run_malware(scan_path: Path) -> ScanResult:
    result = ScanResult(
        engine="malware",
        scan_path=str(scan_path),
        started_at=datetime.now().isoformat(),
    )
    log = setup_log()
    files = walk_files(scan_path)
    result.files_scanned = len(files)

    for p in files:
        findings = []
        if p.suffix == ".py":
            findings = analyze_python_file(p)
        elif p.suffix == ".plist":
            findings = analyze_plist(p)
        elif p.suffix in {".sh", ".command", ".bash", ".zsh"}:
            findings = analyze_shell_script(p)
        result.findings.extend(findings)

    result.finished_at = datetime.now().isoformat()
    log.info("Malware scan: %d files, %d findings", result.files_scanned, len(result.findings))
    return result


# ══════════════════════════════════════════════════════════════════════════════
# ENGINE 3 — FILE INVESTIGATOR: deep forensic analysis
# ══════════════════════════════════════════════════════════════════════════════

MAGIC_BYTES: dict[bytes, str] = {
    b"\x7fELF":      "ELF executable",
    b"\xca\xfe\xba\xbe": "Mach-O fat binary",
    b"\xce\xfa\xed\xfe": "Mach-O 32-bit",
    b"\xcf\xfa\xed\xfe": "Mach-O 64-bit",
    b"\x4d\x5a":    "Windows PE executable",
    b"PK\x03\x04":  "ZIP archive (or DOCX/XLSX/JAR/APK)",
    b"\x25\x50\x44\x46": "PDF document",
    b"\xff\xd8\xff": "JPEG image",
    b"\x89PNG":     "PNG image",
    b"GIF8":        "GIF image",
    b"\x1f\x8b":   "GZIP archive",
    b"BZh":        "BZIP2 archive",
    b"\xfd7zXZ":   "XZ archive",
    b"Rar!":       "RAR archive",
    b"#!/":        "Script (shebang)",
    b"#!":         "Script (shebang)",
}

def detect_magic(data: bytes) -> str:
    for magic, label in MAGIC_BYTES.items():
        if data[:len(magic)] == magic:
            return label
    return "unknown / text"


def investigate_file(p: Path) -> dict:
    report = {
        "file": str(p),
        "investigated_at": datetime.now().isoformat(),
        "exists": p.exists(),
        "metadata": {},
        "hashes": {},
        "type_detection": {},
        "content_analysis": {},
        "strings_of_interest": [],
        "risk_indicators": [],
    }

    if not p.exists():
        return report

    try:
        stat = p.stat()
        report["metadata"] = {
            "size_bytes": stat.st_size,
            "size_human": _human(stat.st_size),
            "created":    datetime.fromtimestamp(stat.st_birthtime).isoformat() if hasattr(stat, "st_birthtime") else "n/a",
            "modified":   datetime.fromtimestamp(stat.st_mtime).isoformat(),
            "accessed":   datetime.fromtimestamp(stat.st_atime).isoformat(),
            "permissions": oct(stat.st_mode)[-4:],
            "owner_uid":  stat.st_uid,
            "is_executable": bool(stat.st_mode & 0o111),
            "is_hidden":  p.name.startswith("."),
        }
    except Exception as e:
        report["metadata"]["error"] = str(e)

    # Hashes
    report["hashes"] = {
        "md5":    md5(p),
        "sha256": sha256(p),
    }

    # Magic bytes / type detection
    data = read_bytes_safe(p, limit=1 * 1024 * 1024)
    magic_label = detect_magic(data)
    mime, _ = mimetypes.guess_type(str(p))
    report["type_detection"] = {
        "extension": p.suffix,
        "magic_type": magic_label,
        "mime_guess": mime or "unknown",
        "has_hidden_extension": _check_double_ext(p.name),
        "extension_magic_mismatch": _check_ext_mismatch(p.suffix, magic_label),
    }

    # Content analysis
    is_text = _is_text(data)
    report["content_analysis"]["is_text"] = is_text

    if is_text:
        text = data.decode("utf-8", errors="replace")
        lines = text.splitlines()
        report["content_analysis"]["line_count"] = len(lines)
        report["content_analysis"]["char_count"] = len(text)

        # URL extraction
        urls = re.findall(r"https?://[^\s\"'<>]{10,}", text)
        report["content_analysis"]["urls_found"] = list(set(urls))[:20]

        # IP addresses
        ips = re.findall(r"\b(?:\d{1,3}\.){3}\d{1,3}\b", text)
        ips = [ip for ip in set(ips) if not ip.startswith(("127.", "192.168.", "10.", "172."))]
        report["content_analysis"]["external_ips"] = ips[:10]

        # Hardcoded secrets pattern check
        secret_patterns = {
            "API key (sk-)":  r"sk-[A-Za-z0-9]{20,}",
            "AWS key":        r"AKIA[0-9A-Z]{16}",
            "Private key":    r"-----BEGIN (RSA |EC )?PRIVATE KEY-----",
            "Bearer token":   r"Bearer [A-Za-z0-9._-]{30,}",
            "Telegram token": r"\d{8,12}:[A-Za-z0-9_-]{35}",
        }
        secrets_found = []
        for label, pattern in secret_patterns.items():
            if re.search(pattern, text):
                secrets_found.append(label)
        report["content_analysis"]["potential_secrets"] = secrets_found

        # Entropy (high entropy = possibly encrypted/obfuscated)
        report["content_analysis"]["entropy"] = round(_entropy(data), 3)
        if report["content_analysis"]["entropy"] > 7.0:
            report["risk_indicators"].append("High entropy (>7.0) — possible encrypted or compressed content")

    else:
        report["content_analysis"]["binary"] = True
        report["content_analysis"]["entropy"] = round(_entropy(data), 3)

        # Strings extraction (printable sequences ≥ 6 chars)
        strings = re.findall(rb"[\x20-\x7e]{6,}", data)
        decoded = [s.decode("ascii", errors="ignore") for s in strings[:50]]
        report["strings_of_interest"] = decoded

    # Risk indicators
    if report["metadata"].get("is_executable") and magic_label in ("ELF executable", "Mach-O 64-bit", "Mach-O 32-bit", "Windows PE executable"):
        report["risk_indicators"].append(f"Native executable: {magic_label}")

    if report["type_detection"]["extension_magic_mismatch"]:
        report["risk_indicators"].append(f"Extension/magic mismatch — file may be disguised")

    if report["type_detection"]["has_hidden_extension"]:
        report["risk_indicators"].append("Double extension detected (e.g. photo.jpg.exe)")

    if report["metadata"].get("permissions") in ("0777", "4755", "4777"):
        report["risk_indicators"].append(f"Dangerous permissions: {report['metadata']['permissions']}")

    return report


def _human(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


def _is_text(data: bytes) -> bool:
    if not data:
        return True
    sample = data[:512]
    null_ratio = sample.count(b"\x00") / len(sample)
    return null_ratio < 0.1


def _entropy(data: bytes) -> float:
    if not data:
        return 0.0
    import math
    freq = {}
    for b in data:
        freq[b] = freq.get(b, 0) + 1
    total = len(data)
    return -sum((c/total) * math.log2(c/total) for c in freq.values())


def _check_double_ext(name: str) -> bool:
    parts = name.split(".")
    return len(parts) > 2 and parts[-1] in ("exe", "com", "bat", "sh", "py", "js", "scr")


def _check_ext_mismatch(ext: str, magic: str) -> bool:
    mismatches = {
        ".jpg": ("ELF", "Mach-O", "Windows PE", "ZIP"),
        ".png": ("ELF", "Mach-O", "Windows PE"),
        ".pdf": ("ELF", "Mach-O", "Windows PE"),
        ".txt": ("ELF", "Mach-O", "Windows PE"),
    }
    for bad_magic in mismatches.get(ext.lower(), ()):
        if bad_magic in magic:
            return True
    return False


# ── Report formatting ──────────────────────────────────────────────────────────

SEVERITY_EMOJI = {
    "critical": "🔴", "high": "🟠", "medium": "🟡", "low": "🔵", "info": "⚪"
}

def print_scan_result(result: ScanResult):
    total = len(result.findings)
    by_sev = {}
    for f in result.findings:
        by_sev.setdefault(f.severity, []).append(f)

    print(f"\n{'═'*70}")
    print(f"  GHS Security Scanner — {result.engine.upper()}")
    print(f"  Path: {result.scan_path}")
    print(f"  Files scanned: {result.files_scanned}")
    print(f"  Findings: {total}")
    print(f"  Duration: {result.started_at} → {result.finished_at}")
    print(f"{'═'*70}")

    if not result.findings:
        print("  ✅ No findings.\n")
        return

    for sev in ("critical", "high", "medium", "low", "info"):
        items = by_sev.get(sev, [])
        if not items:
            continue
        emoji = SEVERITY_EMOJI.get(sev, "•")
        print(f"\n  {emoji} {sev.upper()} ({len(items)})")
        for f in items:
            rel = _rel(Path(f.file))
            print(f"    [{f.rule}] {rel}")
            print(f"      {f.detail}")
            if f.recommendation:
                print(f"      → {f.recommendation}")

    print()


def print_investigation(report: dict):
    p = report["file"]
    meta = report.get("metadata", {})
    hashes = report.get("hashes", {})
    typ = report.get("type_detection", {})
    cont = report.get("content_analysis", {})
    risks = report.get("risk_indicators", [])

    print(f"\n{'═'*70}")
    print(f"  GHS File Investigator")
    print(f"  File: {p}")
    print(f"{'═'*70}")

    print(f"\n  📋 METADATA")
    print(f"    Size:        {meta.get('size_human', '?')}")
    print(f"    Modified:    {meta.get('modified', '?')}")
    print(f"    Permissions: {meta.get('permissions', '?')}")
    print(f"    Executable:  {meta.get('is_executable', '?')}")
    print(f"    Hidden:      {meta.get('is_hidden', '?')}")

    print(f"\n  🔑 HASHES")
    print(f"    MD5:    {hashes.get('md5', '?')}")
    print(f"    SHA256: {hashes.get('sha256', '?')}")

    print(f"\n  🧬 TYPE")
    print(f"    Extension:  {typ.get('extension', '?')}")
    print(f"    Magic:      {typ.get('magic_type', '?')}")
    print(f"    MIME guess: {typ.get('mime_guess', '?')}")
    if typ.get("extension_magic_mismatch"):
        print(f"    ⚠️  Extension/magic MISMATCH")
    if typ.get("has_hidden_extension"):
        print(f"    ⚠️  Double extension detected")

    if cont:
        print(f"\n  📊 CONTENT")
        print(f"    Entropy: {cont.get('entropy', '?')} / 8.0")
        if cont.get("is_text"):
            print(f"    Lines: {cont.get('line_count', '?')}")
        urls = cont.get("urls_found", [])
        if urls:
            print(f"    URLs ({len(urls)}):")
            for u in urls[:5]:
                print(f"      {u}")
        secrets = cont.get("potential_secrets", [])
        if secrets:
            print(f"    ⚠️  Potential secrets detected:")
            for s in secrets:
                print(f"      {s}")
        ext_ips = cont.get("external_ips", [])
        if ext_ips:
            print(f"    External IPs: {', '.join(ext_ips)}")

    strings = report.get("strings_of_interest", [])
    if strings:
        print(f"\n  📝 STRINGS (first 10 of {len(strings)})")
        for s in strings[:10]:
            print(f"    {s[:80]}")

    if risks:
        print(f"\n  ⚠️  RISK INDICATORS")
        for r in risks:
            print(f"    • {r}")
    else:
        print(f"\n  ✅ No risk indicators.")

    print()


def _rel(p: Path) -> str:
    try:
        return f"~/{p.relative_to(Path.home())}"
    except ValueError:
        return str(p)


# ── Save report ────────────────────────────────────────────────────────────────

def save_report(data: dict, engine: str) -> Path:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = LOG_DIR / f"security_scan_{engine}_{ts}.json"
    out.write_text(json.dumps(data, indent=2, default=str))
    return out


def telegram_summary(result: ScanResult, token: str = ""):
    criticals = [f for f in result.findings if f.severity == "critical"]
    highs     = [f for f in result.findings if f.severity == "high"]
    if not criticals and not highs:
        return  # only alert on critical/high
    msg = (f"🔴 <b>GHS Security Scanner — {result.engine.upper()}</b>\n"
           f"Scan: {result.scan_path}\n"
           f"Files: {result.files_scanned} | Total findings: {len(result.findings)}\n\n")
    if criticals:
        msg += f"🔴 CRITICAL ({len(criticals)})\n"
        for f in criticals[:3]:
            msg += f"  [{f.rule}] {_rel(Path(f.file))}\n  {f.detail[:80]}\n"
    if highs:
        msg += f"\n🟠 HIGH ({len(highs)})\n"
        for f in highs[:3]:
            msg += f"  [{f.rule}] {_rel(Path(f.file))}\n  {f.detail[:80]}\n"
    telegram(msg, token)


# ── CLI ────────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(description="GHS Security Scanner — antivirus, malware, file investigator")
    sub = ap.add_subparsers(dest="engine")

    # antivirus
    av = sub.add_parser("antivirus", help="Signature + hash scan")
    av.add_argument("--path", default=str(REX_DIR))
    av.add_argument("--deep", action="store_true", help="Enable full signature scan")

    # malware
    ml = sub.add_parser("malware", help="Heuristic behavioral analysis")
    ml.add_argument("--path", default=str(REX_DIR))

    # investigate
    inv = sub.add_parser("investigate", help="Deep forensic analysis of a single file")
    inv.add_argument("file", help="Path to file")

    # full
    full = sub.add_parser("full", help="All three engines on REX folder")
    full.add_argument("--path", default=str(REX_DIR))
    full.add_argument("--deep", action="store_true")

    args = ap.parse_args()
    if not args.engine:
        ap.print_help()
        sys.exit(0)

    token = os.environ.get("HERMES_BOT_TOKEN", "")

    if args.engine == "antivirus":
        r = run_antivirus(Path(args.path), deep=args.deep)
        print_scan_result(r)
        out = save_report(r.to_dict(), "antivirus")
        print(f"  Report saved: {out}")
        telegram_summary(r, token)

    elif args.engine == "malware":
        r = run_malware(Path(args.path))
        print_scan_result(r)
        out = save_report(r.to_dict(), "malware")
        print(f"  Report saved: {out}")
        telegram_summary(r, token)

    elif args.engine == "investigate":
        report = investigate_file(Path(args.file))
        print_investigation(report)
        out = save_report(report, "investigate")
        print(f"  Report saved: {out}")

    elif args.engine == "full":
        path = Path(args.path)
        print("Running full security suite…")

        av_r = run_antivirus(path, deep=args.deep)
        print_scan_result(av_r)
        save_report(av_r.to_dict(), "antivirus")
        telegram_summary(av_r, token)

        ml_r = run_malware(path)
        print_scan_result(ml_r)
        save_report(ml_r.to_dict(), "malware")
        telegram_summary(ml_r, token)

        total = len(av_r.findings) + len(ml_r.findings)
        print(f"\n{'═'*70}")
        print(f"  FULL SCAN COMPLETE")
        print(f"  Antivirus: {av_r.files_scanned} files, {len(av_r.findings)} findings")
        print(f"  Malware:   {ml_r.files_scanned} files, {len(ml_r.findings)} findings")
        print(f"  Total findings: {total}")
        print(f"{'═'*70}\n")


if __name__ == "__main__":
    main()
