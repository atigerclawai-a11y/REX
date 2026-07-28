#!/usr/bin/env python3
"""Model Selector — switch between Rexxie models per task.
Usage: python3 CC_model_selector.py [model_name]
Models: rexxie | coder | hermes4 | gemma | list"""

import json, subprocess, sys, os

MODELS = {
    "rexxie": {
        "ollama_model": "rexxie-qwen3:latest",
        "description": "Personal assistant — chat, strategy, daily ops",
        "best_for": "Conversation, GOJ operations, planning, personal questions",
    },
    "coder": {
        "ollama_model": "ghs-coder:latest",
        "description": "Dedicated coding agent — write, debug, refactor",
        "best_for": "Code generation, bug fixing, architecture, scripts",
    },
    "hermes4": {
        "ollama_model": "rexxie-hermes4:latest",
        "description": "Uncensored assistant — answers what others refuse",
        "best_for": "Unfiltered research, edge cases, absolute honesty",
    },
    "gemma": {
        "ollama_model": "gemma4:12b-heretic",
        "description": "Gemma 4 Heretic — uncensored, local, fast",
        "best_for": "Unfiltered conversation, anything-goes chat, raw honesty"
    },
}

CONFIG_PATH = os.path.expanduser("~/Desktop/REX/.model_selector.json")

def load_config():
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH) as f:
            return json.load(f)
    return {"active": "rexxie", "history": []}

def save_config(config):
    with open(CONFIG_PATH, "w") as f:
        json.dump(config, f, indent=2)

def switch_model(name):
    if name not in MODELS:
        print(f"Unknown model: {name}")
        print(f"Available: {', '.join(MODELS.keys())}")
        return False
    
    config = load_config()
    old = config["active"]
    config["active"] = name
    config["history"].append({"from": old, "to": name, "timestamp": str(subprocess.check_output(["date", "+%Y-%m-%d %H:%M:%S"]).decode().strip())})
    # Keep last 50 switches
    config["history"] = config["history"][-50:]
    save_config(config)
    
    print(f"🔄 Switched: {old} → {name}")
    print(f"   Model: {MODELS[name]['ollama_model']}")
    print(f"   Best for: {MODELS[name]['best_for']}")
    return True

def list_models():
    config = load_config()
    print("\n📋 Available Models:\n")
    for name, info in MODELS.items():
        active = " ★ ACTIVE" if config["active"] == name else ""
        print(f"  {name:<10} {info['ollama_model']:<30} {info['description']}{active}")
    print(f"\n  Switch: python3 CC_model_selector.py [name]")
    print(f"  History: {len(config['history'])} switches")

def get_active():
    config = load_config()
    active = config["active"]
    return MODELS[active]["ollama_model"]

if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] == "list":
        list_models()
    elif sys.argv[1] in MODELS:
        switch_model(sys.argv[1])
    else:
        print(f"Usage: python3 CC_model_selector.py [{'|'.join(MODELS.keys())}|list]")
        print(f"Unknown model: {sys.argv[1]}")
