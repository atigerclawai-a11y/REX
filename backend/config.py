"""
REX — Configuration & API Key Management
Stores API keys in macOS Keychain via `keyring`.
Falls back to environment variables if keychain entry not found.
"""
import os
import json
import keyring
from pathlib import Path
from typing import Optional


APP_NAME = "REX-PrivacyProxy"
CONFIG_DIR = Path.home() / ".rex"
CONFIG_FILE = CONFIG_DIR / "config.json"
DB_FILE = CONFIG_DIR / "journeys.db"
AUDIT_DB_FILE = CONFIG_DIR / "audit.db"


# Ensure config directory exists
CONFIG_DIR.mkdir(exist_ok=True)


class Settings:
    """
    Central settings object.
    API keys are persisted in macOS Keychain.
    Other settings are persisted in ~/.rex/config.json.
    """

    PROVIDERS = {
        "anthropic": {
            "env_key": "ANTHROPIC_API_KEY",
            "keychain_key": "rex_anthropic_api_key",
            "display": "Anthropic (Claude)",
        },
        "openai": {
            "env_key": "OPENAI_API_KEY",
            "keychain_key": "rex_openai_api_key",
            "display": "OpenAI (ChatGPT)",
        },
        "google": {
            "env_key": "GEMINI_API_KEY",
            "keychain_key": "rex_gemini_api_key",
            "display": "Google (Gemini)",
        },
        "xai": {
            "env_key": "XAI_API_KEY",
            "keychain_key": "rex_xai_api_key",
            "display": "xAI (Grok)",
        },
        "perplexity": {
            "env_key": "PERPLEXITY_API_KEY",
            "keychain_key": "rex_perplexity_api_key",
            "display": "Perplexity (Sonar)",
        },
        # LibreChat runs locally — no API key needed, but store the base URL here
        # We use "librechat" as a virtual provider; availability checked by pinging port 3080
        "librechat": {
            "env_key": "LIBRECHAT_API_KEY",        # optional auth token if LibreChat needs it
            "keychain_key": "rex_librechat_api_key",
            "display": "LibreChat (Local)",
        },
    }

    def __init__(self):
        self._data = self._load()

    def _load(self) -> dict:
        if CONFIG_FILE.exists():
            try:
                return json.loads(CONFIG_FILE.read_text())
            except Exception:
                pass
        return {
            "secure_mode": True,           # ← SOVEREIGN DEFAULT: Secure Mode ON always
            "default_model": "ollama/mistral-hermie:latest",  # ← SOVEREIGN DEFAULT: local AI first
            "local_first_model": "ollama/mistral-hermie:latest",  # Primary local model (matches Ollama running instance)
            "ollama_base_url": "http://localhost:11434",
            "ollama_secure_model": "mistral-hermie:latest",
            "auto_ollama_on_phi": True,    # auto-route to Ollama when PHI detected
            "theme": "dark",
        }

    def _save(self):
        CONFIG_FILE.write_text(json.dumps(self._data, indent=2))

    # ── Secure Mode ──────────────────────────────────────────────────────────

    @property
    def secure_mode(self) -> bool:
        return self._data.get("secure_mode", False)

    @secure_mode.setter
    def secure_mode(self, value: bool):
        self._data["secure_mode"] = value
        self._save()

    # ── Model selection ───────────────────────────────────────────────────────

    @property
    def default_model(self) -> str:
        return self._data.get("default_model", "ollama/mistral-hermie:latest")  # LOCKED LUCY: never fall back to cloud

    @property
    def ollama_base_url(self) -> str:
        return self._data.get("ollama_base_url", "http://localhost:11434")

    @property
    def ollama_secure_model(self) -> str:
        return self._data.get("ollama_secure_model", "mistral-hermie:latest")

    @property
    def auto_ollama_on_phi(self) -> bool:
        return self._data.get("auto_ollama_on_phi", True)

    # ── API Keys (Keychain-first) ─────────────────────────────────────────────

    def get_api_key(self, provider: str) -> Optional[str]:
        """Retrieve API key: keychain → env var → None"""
        info = self.PROVIDERS.get(provider)
        if not info:
            return None

        # 1. Try OS keychain
        try:
            val = keyring.get_password(APP_NAME, info["keychain_key"])
            if val:
                return val
        except Exception:
            pass

        # 2. Fall back to environment variable
        return os.environ.get(info["env_key"])

    def set_api_key(self, provider: str, api_key: str):
        """Store API key in macOS Keychain"""
        info = self.PROVIDERS.get(provider)
        if not info:
            raise ValueError(f"Unknown provider: {provider}")
        keyring.set_password(APP_NAME, info["keychain_key"], api_key)
        # Also set in env for LiteLLM (which reads env vars)
        os.environ[info["env_key"]] = api_key

    def load_all_keys_to_env(self):
        """Load all stored keys into env at startup (LiteLLM reads from env)"""
        for provider, info in self.PROVIDERS.items():
            key = self.get_api_key(provider)
            if key:
                os.environ[info["env_key"]] = key

    def has_any_api_key(self) -> bool:
        return any(self.get_api_key(p) for p in self.PROVIDERS)

    def provider_status(self) -> dict:
        return {p: bool(self.get_api_key(p)) for p in self.PROVIDERS}

    def update(self, **kwargs):
        self._data.update(kwargs)
        self._save()
