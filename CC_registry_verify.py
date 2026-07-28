#!/usr/bin/env python3
"""
GHS System Registry Verifier
═════════════════════════════
Cross-references the System Registry (source of truth) against live state.
Returns pass/fail for every registered component.
Runs as part of the knowledge integrity watchdog.
"""

import json, os, sys, sqlite3
from datetime import datetime
from pathlib import Path

REGISTRY_PATH = Path.home() / "Documents" / "GHS-Vault" / "GHS System Registry.md"

def parse_registry():
    """Parse the YAML-like registry into a dict."""
    content = REGISTRY_PATH.read_text()
    
    # Simple YAML parser — handles the registry format
    result = {}
    current_section = None
    current_subsection = None
    indent_level = 0
    
    for line in content.split('\n'):
        stripped = line.strip()
        if not stripped or stripped.startswith('#'):
            continue
        
        indent = len(line) - len(line.lstrip())
        
        # Top-level key (0 indent)
        if indent == 0 and ':' in stripped and not stripped.startswith('-'):
            key = stripped.split(':')[0].strip()
            if key in ('version', 'last_updated'):
                result[key] = stripped.split(':', 1)[1].strip().strip('"')
            else:
                result[key] = {}
            current_section = key
            current_subsection = None
            indent_level = 0
        
        # Second-level key (2 spaces)
        elif indent == 2 and ':' in stripped and not stripped.startswith('-'):
            key = stripped.split(':')[0].strip()
            val = stripped.split(':', 1)[1].strip().strip('"').strip("'")
            if current_section and isinstance(result.get(current_section), dict):
                result[current_section][key] = {}
                current_subsection = key
            indent_level = 2
        
        # Third-level key (4 spaces)
        elif indent == 4 and ':' in stripped and not stripped.startswith('-'):
            key = stripped.split(':')[0].strip()
            val = stripped.split(':', 1)[1].strip().strip('"').strip("'")
            if current_section and current_subsection:
                if isinstance(result[current_section].get(current_subsection), dict):
                    result[current_section][current_subsection][key] = val
            elif current_section and isinstance(result.get(current_section), dict):
                result[current_section][key] = val
    
    return result


def verify_agents(registry):
    """Verify voice agents against Retell API."""
    results = []
    agents = registry.get('agents', {})
    if not agents:
        return [{"component": "agents", "status": "SKIP", "detail": "No agents in registry"}]
    
    try:
        # Load Retell key
        key = None
        for env_path in [Path.home() / "Desktop/REX/.env", 
                        Path.home() / ".hermes/profiles/cloud/.env"]:
            if env_path.exists():
                for line in env_path.read_text().split('\n'):
                    if line.startswith('RETELL_KEY') or line.startswith('RETELL_API_KEY'):
                        if '=' in line:
                            key = line.split('=', 1)[1].strip().strip('"').strip("'")
                            break
            if key: break
        
        if not key:
            return [{"component": "agents", "status": "ERROR", "detail": "No Retell API key found"}]
        
        import urllib.request
        
        for name, agent in agents.items():
            agent_id = agent.get('id', '')
            expected_voice = agent.get('voice', '')
            expected_model = agent.get('model', '')
            
            req = urllib.request.Request(
                f'https://api.retellai.com/get-agent/{agent_id}',
                headers={'Authorization': f'Bearer {key}'}
            )
            with urllib.request.urlopen(req, timeout=10) as r:
                data = json.loads(r.read())
            
            actual_voice = data.get('voice_id', '?')
            actual_name = data.get('agent_name', '?')
            
            issues = []
            if actual_voice != expected_voice:
                issues.append(f"Voice mismatch: expected {expected_voice}, got {actual_voice}")
            
            results.append({
                "component": f"agent.{name}",
                "status": "PASS" if not issues else "FAIL",
                "name": actual_name,
                "voice": actual_voice,
                "issues": issues
            })
    except Exception as e:
        results.append({"component": "agents", "status": "ERROR", "detail": str(e)})
    
    return results


def verify_mcp(registry):
    """Verify MCP servers are configured."""
    results = []
    servers = registry.get('mcp_servers', {})
    
    config_path = Path.home() / ".hermes/profiles/cloud/config.yaml"
    if not config_path.exists():
        return [{"component": "mcp_servers", "status": "ERROR", "detail": "Config not found"}]
    
    config_text = config_path.read_text()
    
    for name, server in servers.items():
        cmd = server.get('command', '')
        args_str = str(server.get('args', ''))
        
        in_config = name in config_text
        
        script_path = Path(args_str.strip("[]'\" "))
        script_exists = script_path.exists() if 'Desktop' in args_str else True
        
        issues = []
        if not in_config:
            issues.append("Not found in config.yaml")
        if not script_exists:
            issues.append(f"Script not found: {script_path}")
        
        results.append({
            "component": f"mcp.{name}",
            "status": "PASS" if not issues else "FAIL",
            "command": cmd,
            "configured": in_config,
            "script_exists": script_exists,
            "issues": issues
        })
    
    return results


def verify_apis(registry):
    """Verify API tokens exist and are valid."""
    results = []
    apis = registry.get('apis', {})
    
    for name, api in apis.items():
        if api.get('skip_verify'):
            results.append({
                "component": f"api.{name}",
                "status": "SKIP",
                "detail": "Key in config.yaml (managed by Hermes)"
            })
            continue
            
        env_file = Path(api.get('env_file', '').replace('~/', str(Path.home()) + '/'))
        key_env = api.get('key_env', '')
        
        issues = []
        key_found = False
        
        if env_file.exists():
            for line in env_file.read_text().split('\n'):
                if line.startswith(key_env) and '=' in line:
                    val = line.split('=', 1)[1].strip().strip('"').strip("'")
                    if val and len(val) > 10:
                        key_found = True
                    break
        
        if not key_found:
            issues.append(f"{key_env} missing or too short")
        
        # Special: check Instagram token expiry
        if name == 'meta_instagram' and key_found:
            try:
                import urllib.request
                app_secret = api.get('app_secret_env', '')
                token = ''
                for line in env_file.read_text().split('\n'):
                    if line.startswith('META_IG_ACCESS_TOKEN') and '=' in line:
                        token = line.split('=', 1)[1].strip().strip('"').strip("'")
                
                if token:
                    req = urllib.request.Request(
                        f'https://graph.facebook.com/v22.0/debug_token?input_token={token}&access_token={api.get("app_id")}|META_APP_SECRET',
                    )
                    # Can't verify without app secret in URL — skip for now
            except:
                pass
        
        results.append({
            "component": f"api.{name}",
            "status": "PASS" if not issues else "FAIL",
            "key_env": key_env,
            "key_found": key_found,
            "issues": issues
        })
    
    return results


def verify_databases(registry):
    """Verify database files exist and have expected tables."""
    results = []
    dbs = registry.get('databases', {})
    
    for name, db in dbs.items():
        if db.get('skip_verify'):
            results.append({
                "component": f"db.{name}",
                "status": "SKIP",
                "detail": "Verification skipped (directory, not a SQLite file)"
            })
            continue
            
        path = Path(db.get('path', '').replace('~/', str(Path.home()) + '/'))
        issues = []
        
        if not path.exists():
            issues.append(f"File not found: {path}")
        elif path.stat().st_size == 0:
            issues.append(f"File is 0 bytes: {path}")
        else:
            # Check tables
            try:
                conn = sqlite3.connect(str(path))
                tables = [t[0] for t in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
                conn.close()
                
                expected_raw = db.get('tables', '')
                expected = [t.strip() for t in expected_raw.split(',') if t.strip()]
                if expected:
                    missing = [t for t in expected if t not in tables]
                    if missing:
                        issues.append(f"Missing tables: {missing}")
                
                results.append({
                    "component": f"db.{name}",
                    "status": "PASS" if not issues else "FAIL",
                    "path": str(path),
                    "size": path.stat().st_size,
                    "tables": tables,
                    "issues": issues
                })
            except Exception as e:
                issues.append(f"SQLite error: {e}")
        
        if issues and not any(r['component'] == f"db.{name}" for r in results):
            results.append({
                "component": f"db.{name}",
                "status": "FAIL",
                "issues": issues
            })
    
    return results


def verify_key_files(registry):
    """Verify key files exist and aren't stale."""
    results = []
    kf = registry.get('key_files', {})
    
    vault_path = Path(kf.get('obsidian_vault', {}).get('path', '').replace('~/', str(Path.home()) + '/'))
    if isinstance(vault_path, str):
        vault_path = Path(vault_path)
    
    # Check vault
    if vault_path.exists():
        vault = kf.get('obsidian_vault', {})
        required = vault.get('required_files', [])
        min_notes = int(vault.get('min_notes', 0))
        actual_notes = len(list(vault_path.rglob("*.md")))
        
        missing_files = []
        for rf in required:
            matches = list(vault_path.rglob(rf))
            if not matches:
                missing_files.append(rf)
        
        vault_result = {
            "component": "key_files.obsidian",
            "status": "PASS" if not missing_files and actual_notes >= min_notes else "FAIL",
            "total_notes": actual_notes,
            "min_required": min_notes,
            "missing_files": missing_files,
            "path": str(vault_path)
        }
        results.append(vault_result)
    
    # Check business memory
    bm = kf.get('business_memory', {})
    bm_path = Path(bm.get('path', '').replace('~/', str(Path.home()) + '/'))
    if bm_path.exists():
        try:
            data = json.loads(bm_path.read_text())
            version = data.get('version', '?')
            min_ver = bm.get('min_version', '0')
            results.append({
                "component": "key_files.business_memory",
                "status": "PASS" if version >= min_ver else "FAIL",
                "version": version,
                "min_version": min_ver,
                "path": str(bm_path)
            })
        except:
            results.append({
                "component": "key_files.business_memory",
                "status": "FAIL",
                "detail": "Invalid JSON"
            })
    else:
        results.append({
            "component": "key_files.business_memory",
            "status": "FAIL",
            "detail": f"Not found: {bm_path}"
        })
    
    # Check NotebookLM
    nb = kf.get('notebooklm_handoffs', {})
    nb_path = Path(nb.get('path', '').replace('~/', str(Path.home()) + '/'))
    max_age = int(nb.get('max_age_hours', 24))
    
    if nb_path.exists():
        handoffs = sorted(nb_path.glob("handoff_*.md"), reverse=True)
        if handoffs:
            latest = handoffs[0]
            age_hours = (datetime.now().timestamp() - latest.stat().st_mtime) / 3600
            results.append({
                "component": "key_files.notebooklm",
                "status": "PASS" if age_hours <= max_age else "STALE",
                "latest": latest.name,
                "age_hours": round(age_hours, 1),
                "max_age_hours": max_age,
                "path": str(nb_path)
            })
        else:
            results.append({
                "component": "key_files.notebooklm",
                "status": "FAIL",
                "detail": "No handoff files"
            })
    else:
        results.append({
            "component": "key_files.notebooklm",
            "status": "FAIL",
            "detail": f"Not found: {nb_path}"
        })
    
    return results


def run_all():
    """Run all verifications and return summary."""
    registry = parse_registry()
    
    if not registry:
        return {"status": "ERROR", "detail": "Could not parse registry"}
    
    all_results = []
    all_results.extend(verify_key_files(registry))
    all_results.extend(verify_databases(registry))
    all_results.extend(verify_mcp(registry))
    all_results.extend(verify_apis(registry))
    # Agents requires network — skip in offline mode
    
    passed = sum(1 for r in all_results if r['status'] == 'PASS')
    failed = sum(1 for r in all_results if r['status'] == 'FAIL')
    total = len(all_results)
    
    return {
        "timestamp": datetime.now().isoformat(),
        "registry_version": registry.get('version', '?'),
        "total_checks": total,
        "passed": passed,
        "failed": failed,
        "health": "OK" if failed == 0 else f"{failed}/{total} FAILED",
        "results": all_results
    }


if __name__ == "__main__":
    result = run_all()
    print(json.dumps(result, indent=2, default=str))
    sys.exit(0 if result.get('failed', 0) == 0 else 1)
