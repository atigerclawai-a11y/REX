"""Docker container status endpoint for Command Center."""
import json
import subprocess
import os
from fastapi import APIRouter

router = APIRouter(prefix="/docker", tags=["docker"])

# Docker binary may not be in launchd's restricted PATH
_DOCKER = "/usr/local/bin/docker"
if not os.path.exists(_DOCKER):
    _DOCKER = "/opt/homebrew/bin/docker"
if not os.path.exists(_DOCKER):
    _DOCKER = "docker"  # fallback to PATH


@router.get("/status")
async def docker_status():
    """Return running container status as JSON."""
    try:
        result = subprocess.run(
            [_DOCKER, "ps", "--format", "json",
             "--filter", "status=running"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode != 0:
            return {"error": result.stderr.strip(), "containers": []}

        containers = []
        for line in result.stdout.strip().split("\n"):
            if not line:
                continue
            try:
                c = json.loads(line)
                containers.append({
                    "name": c.get("Names", ""),
                    "image": c.get("Image", ""),
                    "status": c.get("Status", ""),
                    "ports": c.get("Ports", ""),
                    "running_for": c.get("RunningFor", ""),
                    "state": "running",
                })
            except json.JSONDecodeError:
                pass

        # Also get all containers (including stopped) for full picture
        result_all = subprocess.run(
            [_DOCKER, "ps", "-a", "--format", "json",
             "--filter", "status=exited"],
            capture_output=True, text=True, timeout=5,
        )
        stopped = []
        for line in result_all.stdout.strip().split("\n"):
            if not line:
                continue
            try:
                c = json.loads(line)
                stopped.append({
                    "name": c.get("Names", ""),
                    "image": c.get("Image", ""),
                    "status": c.get("Status", ""),
                    "ports": c.get("Ports", ""),
                    "running_for": c.get("RunningFor", ""),
                    "state": "stopped",
                })
            except json.JSONDecodeError:
                pass

        return {
            "total": len(containers) + len(stopped),
            "running": len(containers),
            "stopped": len(stopped),
            "containers": containers + stopped,
        }

    except subprocess.TimeoutExpired:
        return {"error": "Docker query timed out", "containers": []}
    except FileNotFoundError:
        return {"error": "Docker CLI not found", "containers": []}
    except Exception as e:
        return {"error": str(e), "containers": []}
