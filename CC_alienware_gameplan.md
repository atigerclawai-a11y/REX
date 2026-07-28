# CC_alienware_gameplan.md
# Alienware Windows PC — GHS Integration Game Plan
# Prepared: June 4, 2026 | Architect: Hermes / Claude

---

## Overview

The Alienware PC is a GPU-capable Windows machine that can be a significant compute node in the GHS stack. The goal is to integrate it as a first-class citizen: Hermes agent running natively, Ollama/LM Studio leveraging the NVIDIA GPU for local inference, shared file access with mainsobhelper, and Task Scheduler jobs as the Windows equivalent of macOS launchd plists.

**Architecture principle:** Tailscale is the backbone. Every cross-machine service call routes through the private Tailscale IP, never exposed to the public internet.

---

## Phase 1: Network Foundation (Tailscale)

**Goal:** The Alienware and mainsobhelper are on the same private tailnet. Every subsequent step depends on this.

### Steps

1. **Install Tailscale on Alienware**
   - Download: https://tailscale.com/download/windows
   - Install and run the client
   - Log in with the same Tailscale account as mainsobhelper

2. **Verify both machines appear in tailnet**
   - Open: https://login.tailscale.com/admin/machines
   - Both `mainsobhelper` and the Alienware (note its Tailscale IP, format 100.x.x.x) should appear
   - Note the Alienware's Tailscale IP — used in all configs below

3. **Set a stable Tailscale hostname for the Alienware**
   - In Tailscale admin console → rename machine to something like `alienware-ghs`
   - This lets mainsobhelper reach it by name: `alienware-ghs` instead of raw IP

4. **Test connectivity both directions**
   ```bash
   # From mainsobhelper:
   tailscale ping alienware-ghs
   curl http://100.x.x.x:8000/health   # (once Alienware runs any service)

   # From Alienware PowerShell:
   tailscale ping mainsobhelper
   curl http://100.x.x.x:8000/api/health  # ping REX on mainsobhelper
   ```

**Success criteria:** `tailscale ping` returns <20ms latency both directions.

---

## Phase 2: GPU Inference Node (Ollama + LM Studio)

**Goal:** Alienware's NVIDIA GPU runs local models that mainsobhelper can call via Hermes model routing.

### 2A: Install Ollama on Windows

1. Download Ollama Windows installer: https://ollama.com/download/windows
2. Install and verify:
   ```powershell
   ollama --version
   ollama run mistral    # test pull
   ```
3. Configure Ollama to listen on Tailscale interface (not just localhost):
   - Set environment variable: `OLLAMA_HOST=0.0.0.0:11434`
   - In Windows: System Properties → Environment Variables → System → add `OLLAMA_HOST`
   - Or in Task Scheduler job (see Phase 4)

4. **Expose via Tailscale only** — Windows Firewall rule:
   ```powershell
   # Allow Ollama only on Tailscale interface (100.x.x.x subnet)
   netsh advfirewall firewall add rule name="Ollama-Tailscale" `
     dir=in action=allow protocol=TCP localport=11434 `
     remoteip=100.64.0.0/10
   ```

5. Verify from mainsobhelper:
   ```bash
   curl http://alienware-ghs:11434/api/version
   ```

### 2B: Wire into Hermes Model Routing

Add Alienware GPU as a model provider in Hermes config (`~/.hermes/profiles/cloud/config.yaml`):

```yaml
# In models section, add:
- name: "alienware-gpu"
  provider: "ollama"
  base_url: "http://alienware-ghs:11434"
  models:
    - "mistral"
    - "llama3"
    - "qwen2.5-coder:7b"
    # Add any GPU-capable model pulled on Alienware
```

Then in routing rules, direct heavy inference tasks to Alienware:
```yaml
routing:
  - pattern: "code/*"
    model: "alienware-gpu/qwen2.5-coder:7b"
  - pattern: "local/heavy"
    model: "alienware-gpu/llama3"
```

### 2C: Recommended Models for GPU (prioritize by VRAM)

| Model | Size | Use Case |
|-------|------|----------|
| mistral | 7B | General ops, Hermie replacement |
| llama3:8b | 8B | High-quality reasoning |
| qwen2.5-coder:14b | 14B | Code (upgrade from 7b on mainsobhelper) |
| deepseek-r1:14b | 14B | Complex analysis (local fallback) |
| nomic-embed-text | 137M | Embeddings for memory search |

Pull commands (run on Alienware):
```powershell
ollama pull mistral
ollama pull llama3:8b
ollama pull qwen2.5-coder:14b
ollama pull nomic-embed-text
```

---

## Phase 3: Hermes Agent on Windows

**Goal:** A Hermes agent instance runs on Alienware, participates in swarm tasks, handles Windows-specific operations.

### 3A: Install Hermes on Windows

1. Install Node.js (LTS): https://nodejs.org/en/download
2. Install Python 3.11+: https://python.org/downloads
3. Clone/copy Hermes from mainsobhelper:
   ```powershell
   # Option A: Copy from mainsobhelper via Tailscale (scp or shared folder)
   # Option B: Install fresh from Hermes distribution
   ```
4. Install Hermes CLI:
   ```powershell
   pip install hermes-agent   # or npm install -g @hermes/cli
   ```
5. Configure profile pointing to mainsobhelper's Hermes cloud gateway:
   ```yaml
   # ~/.hermes/profiles/windows/config.yaml
   gateway:
     url: "http://mainsobhelper:3002"   # Tailscale hostname
   identity:
     name: "Alienware-Agent"
     role: "compute_node"
   ```

### 3B: Windows-Specific Hermes Skills

The Alienware agent handles tasks mainsobhelper can't:
- GPU-accelerated image/video generation (Stable Diffusion, etc.)
- Windows application automation via Python win32api
- File format conversions using Windows-native apps
- GPU benchmark and health monitoring

---

## Phase 4: Task Scheduler (launchd Equivalent)

**Goal:** All automated jobs that run on mainsobhelper via LaunchAgent plists have Windows equivalents running on Alienware.

### Windows Task Scheduler vs macOS LaunchAgent

| macOS (plist) | Windows (Task Scheduler) |
|--------------|--------------------------|
| LaunchInterval (seconds) | Trigger: Repeat every N minutes |
| StartCalendarInterval | Trigger: Daily at time |
| RunAtLoad | Trigger: At startup + At logon |
| `launchctl load` | `schtasks /Create` |
| `launchctl list` | `schtasks /Query` |
| `launchctl unload` | `schtasks /Delete` |

### Creating Task Scheduler Jobs (PowerShell)

Template for a recurring job:
```powershell
# Example: Run Ollama health check every 5 minutes
$action = New-ScheduledTaskAction `
  -Execute "python.exe" `
  -Argument "C:\GHS\scripts\health_check.py" `
  -WorkingDirectory "C:\GHS\scripts"

$trigger = New-ScheduledTaskTrigger `
  -RepetitionInterval (New-TimeSpan -Minutes 5) `
  -Once -At (Get-Date)

$settings = New-ScheduledTaskSettingsSet `
  -ExecutionTimeLimit (New-TimeSpan -Minutes 2) `
  -RestartCount 3 `
  -RestartInterval (New-TimeSpan -Minutes 1)

Register-ScheduledTask `
  -TaskName "GHS-OllamaHealthCheck" `
  -Action $action `
  -Trigger $trigger `
  -Settings $settings `
  -RunLevel Highest `
  -Force
```

### Recommended GHS Jobs for Alienware

| Job Name | Schedule | Script | Purpose |
|----------|----------|--------|---------|
| GHS-OllamaWatchdog | Every 2 min | ollama_watchdog.py | Restart Ollama if crashed |
| GHS-ModelSync | Daily 2am | model_sync.py | Pull latest models |
| GHS-HermesAgent | At startup | hermes_agent.py | Keep agent running |
| GHS-GPUHealthCheck | Every 10 min | gpu_health.py | Monitor VRAM + temp |
| GHS-BackupToMainsob | Daily 3am | backup_sync.py | Sync work files to mainsobhelper |

### Install Script: `CC_install_alienware_tasks.ps1`

```powershell
# Run as Administrator on Alienware
# Installs all GHS Task Scheduler jobs

$GHS_DIR = "C:\GHS"
$PYTHON = "python.exe"

function Install-GHSTask {
    param($Name, $Script, $Minutes)
    $action = New-ScheduledTaskAction -Execute $PYTHON -Argument "$GHS_DIR\$Script" -WorkingDirectory $GHS_DIR
    $trigger = New-ScheduledTaskTrigger -RepetitionInterval (New-TimeSpan -Minutes $Minutes) -Once -At (Get-Date)
    Register-ScheduledTask -TaskName "GHS-$Name" -Action $action -Trigger $trigger -RunLevel Highest -Force
    Write-Host "✅ Installed: GHS-$Name"
}

Install-GHSTask "OllamaWatchdog"  "ollama_watchdog.py"  2
Install-GHSTask "GPUHealthCheck"  "gpu_health.py"       10
Install-GHSTask "ModelSync"       "model_sync.py"       1440   # daily
```

---

## Phase 5: Shared File Access

**Goal:** mainsobhelper and Alienware can read/write shared files (menus, reports, exports).

### Option A: SMB Share over Tailscale (Recommended)

On Alienware, share a folder via Windows Explorer:
1. Right-click folder (e.g., `C:\GHS\shared`) → Properties → Sharing → Advanced Sharing
2. Share name: `ghs-shared`
3. Permissions: add a dedicated GHS user account with read/write

Mount on mainsobhelper:
```bash
# Mount permanently via /etc/fstab entry or launchd job
sudo mkdir -p /Volumes/alienware-shared
mount -t smbfs //ghs:password@alienware-ghs/ghs-shared /Volumes/alienware-shared

# Or one-liner:
open smb://alienware-ghs/ghs-shared
```

### Option B: rsync over Tailscale (One-way sync)

```bash
# From mainsobhelper → Alienware (push exports)
rsync -avz ~/Desktop/REX/exports/ ghs@alienware-ghs:/c/GHS/imports/

# From Alienware → mainsobhelper (pull GPU outputs)
rsync -avz ghs@alienware-ghs:/c/GHS/outputs/ ~/Desktop/REX/gpu-outputs/
```

---

## Phase 6: Security & Monitoring

### Firewall Rules (Windows Defender Firewall)

```powershell
# Allow only Tailscale subnet (100.64.0.0/10) for all GHS ports
$tailnet = "100.64.0.0/10"

# Ollama
netsh advfirewall firewall add rule name="GHS-Ollama" dir=in action=allow protocol=TCP localport=11434 remoteip=$tailnet

# Hermes agent
netsh advfirewall firewall add rule name="GHS-Hermes" dir=in action=allow protocol=TCP localport=3002 remoteip=$tailnet

# Block all else on those ports
netsh advfirewall firewall add rule name="GHS-Block-Public-Ollama" dir=in action=block protocol=TCP localport=11434
```

### GPU Monitoring Script (`gpu_health.py`)

```python
import subprocess, json, requests

def get_gpu_stats():
    result = subprocess.run(
        ["nvidia-smi", "--query-gpu=utilization.gpu,memory.used,memory.free,temperature.gpu",
         "--format=csv,noheader,nounits"],
        capture_output=True, text=True
    )
    util, vram_used, vram_free, temp = result.stdout.strip().split(", ")
    return {
        "gpu_util_pct": int(util),
        "vram_used_mb": int(vram_used),
        "vram_free_mb": int(vram_free),
        "temp_c": int(temp)
    }

if __name__ == "__main__":
    stats = get_gpu_stats()
    # Post to REX on mainsobhelper
    requests.post("http://mainsobhelper:8000/api/alienware/gpu", json=stats, timeout=5)
    print(stats)
```

---

## Integration Checklist

### Phase 1 — Network ✅ / ❌
- [ ] Tailscale installed on Alienware
- [ ] Alienware appears in tailnet as `alienware-ghs`
- [ ] `tailscale ping` passes both directions
- [ ] mainsobhelper can curl Alienware services

### Phase 2 — GPU Inference
- [ ] Ollama installed on Windows
- [ ] OLLAMA_HOST set to 0.0.0.0:11434
- [ ] Firewall allows Tailscale subnet only
- [ ] At least 3 models pulled (mistral, llama3, qwen2.5-coder)
- [ ] mainsobhelper can query Alienware Ollama

### Phase 3 — Hermes Agent
- [ ] Node.js + Python installed
- [ ] Hermes agent configured with mainsobhelper gateway URL
- [ ] Agent connects to swarm

### Phase 4 — Task Scheduler
- [ ] `CC_install_alienware_tasks.ps1` created
- [ ] OllamaWatchdog job installed and running
- [ ] GPUHealthCheck job installed and running

### Phase 5 — Shared Files
- [ ] SMB share created on Alienware (`ghs-shared`)
- [ ] Mounted on mainsobhelper at `/Volumes/alienware-shared`

### Phase 6 — Security
- [ ] Firewall rules applied (Tailscale subnet only)
- [ ] `gpu_health.py` posting stats to REX

---

## PAE Items (need Kato approval before executing)

| ID | Item | Reason |
|----|------|--------|
| PAE-10 | Enroll Alienware in Tailscale tailnet | Requires Tailscale account credentials |
| PAE-11 | Add Alienware Ollama to Hermes config.yaml | Modifies production routing config |
| PAE-12 | Create ghs-shared SMB share on Alienware | File access policy decision |

---

## Quick Start (Once Kato approves PAE-10)

```
1. On Alienware: Install Tailscale → Log in → Verify in admin console
2. On Alienware: Install Ollama → Set OLLAMA_HOST=0.0.0.0:11434 → Pull mistral
3. From mainsobhelper: curl http://alienware-ghs:11434/api/tags
4. Add alienware-ghs to Hermes config.yaml model routing
5. Run CC_gateway_audit.command on mainsobhelper — Alienware should appear in services
```

---

*Prepared by Hermes — June 4, 2026*
*PAE required for all production steps. Propose → Approve → Execute.*
