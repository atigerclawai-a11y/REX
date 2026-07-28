#!/usr/bin/env python3
"""
CC_ram_sentinel.py — RAM watchdog for Apple Silicon Mac.
Uses sysctl + memory_pressure for accurate numbers.
"""

import subprocess, sys, os, time, json, re
from datetime import datetime

# ── Config ────────────────────────────────────────────────────────
WARN_PCT  = 75
CRIT_PCT  = 85
OOM_PCT   = 95
TOP_N     = 8
LOG_FILE  = os.path.expanduser("~/Documents/goj files/logs/ram_sentinel.log")

def log(msg):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    try:
        os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
        with open(LOG_FILE, "a") as f:
            f.write(line + "\n")
    except:
        pass

def run(cmd):
    return subprocess.run(cmd, shell=True, capture_output=True, text=True)

def get_memory():
    """Accurate RAM stats using sysctl + memory_pressure."""
    # Total physical RAM
    total_bytes = int(run("sysctl -n hw.memsize").stdout.strip())
    total_gb = round(total_bytes / (1024**3), 1)
    
    # Memory pressure from macOS
    pressure_out = run("memory_pressure").stdout
    pressure = "normal"
    for line in pressure_out.splitlines():
        if "System-wide memory free percentage" in line:
            try:
                free_pct = int(re.search(r'(\d+)%', line).group(1))
                used_pct = 100 - free_pct
                break
            except:
                used_pct = 0
        if "The system has" in line and "free" in line:
            try:
                free_pct = int(line.split('%')[0].split()[-1])
                used_pct = 100 - free_pct
            except:
                pass
    
    # Fallback: use vm_stat properly
    if 'used_pct' not in dir():
        vm = run("vm_stat").stdout
        stats = {}
        for line in vm.splitlines():
            if ":" in line:
                k, v = line.split(":", 1)
                try:
                    stats[k.strip()] = int(v.strip().rstrip("."))
                except:
                    pass
        page_size = 16384  # Apple Silicon
        active = stats.get("Pages active", 0)
        wired = stats.get("Pages wired down", 0)
        compressed = stats.get("Pages occupied by compressor", 0)
        free = stats.get("Pages free", 0)
        inactive = stats.get("Pages inactive", 0)
        used_bytes = (active + wired + compressed) * page_size
        used_gb = round(used_bytes / (1024**3), 1)
        used_pct = round((used_bytes / total_bytes) * 100, 1)
    else:
        used_bytes = total_bytes * (used_pct / 100)
        used_gb = round(used_bytes / (1024**3), 1)
    
    # Swap
    swap_out = run("sysctl vm.swapusage").stdout
    swap_used = "0M"
    if "used" in swap_out:
        m = re.search(r'used = ([\d.]+[MG])', swap_out)
        if m: swap_used = m.group(1)
    
    p = "normal"
    if used_pct >= OOM_PCT: p = "OOM"
    elif used_pct >= CRIT_PCT: p = "CRITICAL"
    elif used_pct >= WARN_PCT: p = "WARNING"
    
    return {
        "used_gb": used_gb,
        "total_gb": total_gb,
        "used_pct": used_pct,
        "swap": swap_used,
        "pressure": p
    }

def get_top_procs(n=TOP_N):
    # macOS ps doesn't support --sort; use sort command
    out = run(f"ps aux | sort -nrk 4 | head -n {n+1}").stdout
    procs = []
    for line in out.splitlines()[1:]:
        cols = line.split(None, 10)  # split into max 11 parts (USER..COMMAND)
        if len(cols) >= 11:
            rss_kb = int(cols[5])
            procs.append({
                "pid": cols[1],
                "mem_pct": cols[3] + "%",
                "rss_mb": round(rss_kb / 1024, 1),
                "rss_gb": round(rss_kb / (1024**2), 2),
                "name": cols[10].split("/")[-1][:30]
            })
    return procs

def check():
    mem = get_memory()
    procs = get_top_procs()
    
    used_pct = mem["used_pct"]
    icon = "🟢"
    level = "OK"
    if used_pct >= OOM_PCT:
        icon = "🔴🔴"; level = "OOM IMMINENT"
    elif used_pct >= CRIT_PCT:
        icon = "🔴"; level = "CRITICAL"
    elif used_pct >= WARN_PCT:
        icon = "🟡"; level = "WARNING"
    
    lines = [
        f"{icon} RAM: {mem['used_gb']}GB / {mem['total_gb']}GB ({used_pct}%) — {level}",
        f"   Swap: {mem['swap']}",
        f"   Top {TOP_N}:"
    ]
    for p in procs:
        unit = "GB" if p["rss_gb"] >= 1 else "MB"
        val = p["rss_gb"] if unit == "GB" else p["rss_mb"]
        lines.append(f"     {val:>5.1f}{unit} ({p['mem_pct']:>5s}) — {p['name']}")
    
    report = "\n".join(lines)
    
    if level != "OK":
        log(report)
    
    print(report, flush=True)

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--daemon":
        interval = int(sys.argv[2]) if len(sys.argv) > 2 else 60
        log(f"RAM Sentinel started — {interval}s intervals | W:{WARN_PCT}% C:{CRIT_PCT}% O:{OOM_PCT}%")
        while True:
            check()
            time.sleep(interval)
    else:
        check()
