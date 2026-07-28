# Alienware Aurora R8 — Integration Plan
# IRONWALL Node — June 7, 2026

## Hardware
- **Model:** Alienware Aurora R8
- **RAM:** 32GB DDR4
- **GPU:** NVIDIA RTX 2070 (8GB VRAM) — can run 7B-13B models
- **OS:** Pop!_OS (Linux)
- **Role:** IRONWALL — Security/GPU worker node

## Tonight's Integration

### Step 1: Tailscale Mesh
```bash
# On Aurora (Pop!_OS):
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up --authkey=<KEY_FROM_ADMIN_CONSOLE> --hostname=aurora-r8
# Verify: tailscale status → should see mac-mini + office-mac
```

### Step 2: SSH Key Exchange
```bash
# On Mac Mini:
ssh-copy-id aurora-r8  # via Tailscale IP
# Test: ssh aurora-r8 'nvidia-smi'
```

### Step 3: Ollama Install (GPU-Accelerated)
```bash
# On Aurora:
curl -fsSL https://ollama.com/install.sh | sh
ollama pull mistral:7b        # Quick test model
ollama pull qwen2.5-coder:7b  # Coding
ollama pull nomic-embed-text  # Embeddings
# Test GPU: nvidia-smi should show ollama process
```

### Step 4: Hermes Worker Setup
```bash
# On Aurora:
python3 -m venv ~/hermes-worker
source ~/hermes-worker/bin/activate
pip install httpx websockets
# Clone worker config from Mac Mini
scp mac-mini:~/.hermes/profiles/cloud/config.yaml ~/hermes-worker-config.yaml
```

### Step 5: Roles
| Role | GPU | RAM | Purpose |
|------|-----|-----|---------|
| **Sentinel (IRONWALL)** | RTX 2070 | 32GB | Egress firewall, security scanning |
| **Ollama Worker** | RTX 2070 | 8GB VRAM | 7B model inference (offload from Mac Mini) |
| **Backup Hermes Gateway** | CPU | 32GB | Fallback when Mac Mini is under load |

### Step 6: First Task After Connection
1. Run `nvidia-smi` → confirm GPU detected
2. Run `ollama run mistral:7b "Hello"` → confirm GPU inference
3. Clone security scanning tools from Mac Mini
4. Set up Sentinel (red team / blue team) to run on Aurora
5. Configure as secondary Ollama endpoint for Hermes

### Network Topology (Tailscale)
```
Mac Mini M4 (24GB) ←→ Aurora R8 (32GB + RTX 2070) ←→ Office Mac (16GB)
   :9000 Hub              :11434 Ollama                  Clock in/out
   :8000 REX              :8081 Sentinel
   :3002 Cloud GW
```

## Files to Transfer
- `~/Desktop/REX/rex_red_team.py` → Aurora
- `~/Desktop/REX/rex_blue_team.py` → Aurora
- `~/Desktop/REX/CC_transition_drive_watcher.py` → Aurora (can run there too)
- `~/.hermes/config.yaml` → Aurora (adapted for worker role)
