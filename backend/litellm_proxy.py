"""
REX — LiteLLM Multi-Provider Proxy
Supports: Anthropic (Claude), OpenAI (GPT), Google (Gemini), xAI (Grok), Ollama (local).
Handles streaming, Ollama health-check, and auto-fallback routing.
"""
import asyncio
import logging
import httpx
from typing import AsyncGenerator, List, Dict, Optional
from .config import Settings
from .models import ProviderModel

logger = logging.getLogger(__name__)


# ── Model registry ─────────────────────────────────────────────────────────────
# Define all supported models — availability is checked at runtime vs stored keys.

LIBRECHAT_BASE_URL = "http://localhost:3080/api"

ALL_MODELS: List[ProviderModel] = [
    # Anthropic — Claude family
    ProviderModel(id="anthropic/claude-opus-4-5",     name="Claude Opus 4.5",      provider="anthropic"),
    ProviderModel(id="anthropic/claude-sonnet-4-5",   name="Claude Sonnet 4.5",    provider="anthropic"),
    ProviderModel(id="anthropic/claude-haiku-4-5",    name="Claude Haiku 4.5",     provider="anthropic"),
    # OpenAI — ChatGPT family
    ProviderModel(id="openai/gpt-4o",                 name="ChatGPT-4o",           provider="openai"),
    ProviderModel(id="openai/gpt-4o-mini",            name="ChatGPT-4o Mini",      provider="openai"),
    ProviderModel(id="openai/o1",                     name="OpenAI o1",            provider="openai"),
    ProviderModel(id="openai/o3-mini",                name="OpenAI o3-mini",       provider="openai"),
    # Google — Gemini family
    ProviderModel(id="gemini/gemini-2.0-flash",       name="Gemini 2.0 Flash",     provider="google"),
    ProviderModel(id="gemini/gemini-2.5-pro",         name="Gemini 2.5 Pro",       provider="google"),
    ProviderModel(id="gemini/gemini-1.5-pro",         name="Gemini 1.5 Pro",       provider="google"),
    # xAI — Grok family
    ProviderModel(id="xai/grok-3",                    name="Grok 3",               provider="xai"),
    ProviderModel(id="xai/grok-3-fast",               name="Grok 3 Fast",          provider="xai"),
    ProviderModel(id="xai/grok-beta",                 name="Grok Beta",            provider="xai"),
    # Perplexity — Sonar (web-search-grounded AI)
    ProviderModel(id="perplexity/sonar",              name="Perplexity Sonar",     provider="perplexity"),
    ProviderModel(id="perplexity/sonar-pro",          name="Perplexity Sonar Pro", provider="perplexity"),
    ProviderModel(id="perplexity/sonar-reasoning",    name="Perplexity Reasoning", provider="perplexity"),
    # LibreChat — local router (port 3080); proxies to whatever LibreChat is configured with
    ProviderModel(id="librechat/gpt-4o",              name="LibreChat → GPT-4o",   provider="librechat", local=True),
    ProviderModel(id="librechat/claude-3-5-sonnet",   name="LibreChat → Claude",   provider="librechat", local=True),
    ProviderModel(id="librechat/gemini-pro",          name="LibreChat → Gemini",   provider="librechat", local=True),
    # Ollama — fully local / air-gapped
    ProviderModel(id="ollama/llama3",                 name="Llama 3 (Local)",      provider="ollama", local=True),
    ProviderModel(id="ollama/llama3.1",               name="Llama 3.1 (Local)",    provider="ollama", local=True),
    ProviderModel(id="ollama/mistral",                name="Mistral (Local)",      provider="ollama", local=True),
    ProviderModel(id="ollama/phi3",                   name="Phi-3 (Local)",        provider="ollama", local=True),
    ProviderModel(id="ollama/medllama3",              name="MedLlama 3 (Local)",   provider="ollama", local=True),
]


class LiteLLMProxy:
    """
    Thin wrapper around LiteLLM that adds:
    - Model availability filtering based on stored API keys
    - Ollama health checking
    - Streaming support (async generator)
    - Auto-fallback to Ollama when PHI detected in Secure Mode
    """

    def __init__(self, settings: Settings):
        self._settings = settings
        self._ollama_available: Optional[bool] = None

    def get_available_models(self) -> List[Dict]:
        """Return models available given the currently configured API keys."""
        status = self._settings.provider_status()
        models = []
        for m in ALL_MODELS:
            if m.provider == "ollama":
                models.append({**m.dict(), "available": True})  # checked at call-time
            elif m.provider == "librechat":
                # LibreChat is local — mark available if port 3080 is reachable (checked async elsewhere)
                models.append({**m.dict(), "available": True, "local": True})
            else:
                models.append({
                    **m.dict(),
                    "available": status.get(m.provider, False),
                })
        return models

    async def check_librechat(self) -> bool:
        """Ping LibreChat to see if it's running on port 3080."""
        try:
            async with httpx.AsyncClient(timeout=2.0) as client:
                r = await client.get("http://localhost:3080/api/health")
                return r.status_code < 500
        except Exception:
            return False

    async def check_ollama(self) -> bool:
        """Ping Ollama to check if it's running."""
        try:
            async with httpx.AsyncClient(timeout=2.0) as client:
                r = await client.get(f"{self._settings.ollama_base_url}/api/tags")
                self._ollama_available = r.status_code == 200
        except Exception:
            self._ollama_available = False
        return self._ollama_available

    async def get_ollama_models(self) -> List[str]:
        """Fetch actual list of pulled Ollama models."""
        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                r = await client.get(f"{self._settings.ollama_base_url}/api/tags")
                if r.status_code == 200:
                    data = r.json()
                    return [m["name"] for m in data.get("models", [])]
        except Exception:
            pass
        return []

    @staticmethod
    def _is_cloud_provider(model: str) -> bool:
        """Returns True if this model routes to an external cloud provider."""
        _local = ("ollama/", "librechat/")
        return not any(model.startswith(p) for p in _local)

    async def stream(
        self,
        model: str,
        messages: List[Dict],
        phi_detected: bool = False,
        cloud_approved: bool = False,
    ) -> AsyncGenerator[str, None]:
        """
        Stream completion tokens.

        Cloud providers are hard-locked by default.
        Pass cloud_approved=True only when Kato has explicitly approved this
        specific request. When approved, messages are stripped to the current
        message only — no history, no GOJ context is ever sent to the cloud.

        If Secure Mode + PHI detected + auto_ollama_on_phi is enabled,
        routes to local Ollama instead of the cloud provider.

        Yields text chunks as they arrive.
        """
        actual_model = model

        # ── Cloud provider gate ───────────────────────────────────────────────
        if self._is_cloud_provider(actual_model) and not cloud_approved:
            logger.warning(f"[cloud_gate] Blocked unapproved cloud call → {actual_model}")
            yield (
                "⛔ Cloud providers are locked by default to protect your data.\n\n"
                "To use a cloud AI for one message only, say:\n"
                "  **use claude for this:** [your question]\n"
                "  **ask gpt:** [your question]\n\n"
                "Only your exact question is sent — no history, no GOJ data. "
                "Approval resets after one use."
            )
            return

        # ── PHI auto-route to Ollama ──────────────────────────────────────────
        if (
            phi_detected
            and self._settings.auto_ollama_on_phi
            and not actual_model.startswith("ollama/")
        ):
            ollama_ok = await self.check_ollama()
            if ollama_ok:
                actual_model = f"ollama/{self._settings.ollama_secure_model}"
                logger.info(f"🔒 PHI detected → auto-routing to local {actual_model}")

        # ── Cloud isolation: strip everything except the current message ──────
        if self._is_cloud_provider(actual_model) and cloud_approved:
            # Only send the last user message — no history, no system context
            isolated = [m for m in messages if m.get("role") == "user"][-1:]
            logger.info(f"☁️  Cloud call approved — sending {len(isolated)} msg(s) to {actual_model} (history stripped)")
            messages = isolated

        if actual_model.startswith("ollama/"):
            async for chunk in self._stream_ollama(actual_model, messages):
                yield chunk
        elif actual_model.startswith("librechat/"):
            async for chunk in self._stream_librechat(actual_model, messages):
                yield chunk
        else:
            async for chunk in self._stream_litellm(actual_model, messages):
                yield chunk

    def _provider_from_model(self, model: str) -> str:
        """Extract provider name from model string like 'anthropic/claude-...'"""
        if "/" in model:
            return model.split("/")[0]
        return model

    async def _stream_litellm(
        self, model: str, messages: List[Dict]
    ) -> AsyncGenerator[str, None]:
        """Stream via LiteLLM (handles Anthropic, OpenAI/ChatGPT, Gemini, Grok, Perplexity)."""

        provider_names = {
            "anthropic":  "Anthropic (Claude)",
            "openai":     "OpenAI (ChatGPT)",
            "google":     "Google (Gemini)",
            "xai":        "xAI (Grok)",
            "perplexity": "Perplexity",
        }
        portals = {
            "anthropic":  "https://console.anthropic.com",
            "openai":     "https://platform.openai.com/api-keys",
            "google":     "https://aistudio.google.com/app/apikey",
            "xai":        "https://console.x.ai",
            "perplexity": "https://www.perplexity.ai/settings/api",
        }

        # ── Pre-flight: check API key before hitting the provider ──────────────
        provider = self._provider_from_model(model)
        status = self._settings.provider_status()
        if not status.get(provider, False):
            nice_name = provider_names.get(provider, provider.capitalize())
            yield (
                f"**No API key configured for {nice_name}.**\n\n"
                f"To fix this:\n"
                f"1. Click the **⚙ Settings** button (top-right corner)\n"
                f"2. Go to the **API Keys** tab\n"
                f"3. Paste your {nice_name} API key and save\n\n"
                f"Get a key at: {portals.get(provider, provider + ' developer portal')}"
            )
            return

        try:
            import litellm
            litellm.set_verbose = False

            # Perplexity needs its own API key injected
            extra_kwargs: Dict = {}
            if provider == "perplexity":
                pplx_key = self._settings.get_api_key("perplexity")
                if pplx_key:
                    extra_kwargs["api_key"] = pplx_key

            response = await litellm.acompletion(
                model=model,
                messages=messages,
                stream=True,
                temperature=0.7,
                max_tokens=4096,
                **extra_kwargs,
            )
            async for chunk in response:
                delta = chunk.choices[0].delta
                if hasattr(delta, "content") and delta.content:
                    yield delta.content
        except ImportError:
            yield "**Error:** LiteLLM not installed. Run: `pip install litellm`"
        except Exception as e:
            err = str(e)
            logger.error(f"LiteLLM stream error for model {model}: {err}")
            nice = provider_names.get(provider, provider.capitalize())
            if "auth" in err.lower() or "401" in err or "api_key" in err.lower():
                yield (
                    f"**API key rejected by {nice}.** The key may be invalid or expired.\n\n"
                    f"Go to ⚙ Settings → API Keys to update it."
                )
            elif "rate" in err.lower() or "429" in err:
                yield "**Rate limit reached.** Wait a moment or switch to a different model."
            elif "timeout" in err.lower():
                yield "**Request timed out.** Check your internet connection or try a faster model."
            else:
                yield f"**{nice} error:** {err[:200]}"

    async def _stream_librechat(
        self, model: str, messages: List[Dict]
    ) -> AsyncGenerator[str, None]:
        """
        Stream from a local LibreChat instance (http://localhost:3080).
        LibreChat exposes an OpenAI-compatible /api/ask endpoint.
        Model format: 'librechat/gpt-4o' → strips prefix and sends to LibreChat.
        """
        model_name = model.replace("librechat/", "")
        url = f"{LIBRECHAT_BASE_URL}/ask/openAI"
        headers = {"Content-Type": "application/json"}

        # If user saved a LibreChat token in settings, send it
        lc_key = self._settings.get_api_key("librechat")
        if lc_key:
            headers["Authorization"] = f"Bearer {lc_key}"

        # LibreChat expects a slightly different body format
        payload = {
            "text":          messages[-1]["content"] if messages else "",
            "model":         model_name,
            "messages":      messages[:-1],   # history without the latest
            "stream":        True,
        }

        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                # Try OpenAI-compatible endpoint first (LibreChat 0.7+)
                try:
                    response = await client.post(
                        f"http://localhost:3080/api/chat/completions",
                        json={
                            "model":    model_name,
                            "messages": messages,
                            "stream":   True,
                        },
                        headers=headers,
                    )
                    if response.status_code == 200:
                        import json as _json
                        async for line in response.aiter_lines():
                            if line.startswith("data: "):
                                data_str = line[6:]
                                if data_str.strip() == "[DONE]":
                                    break
                                try:
                                    data = _json.loads(data_str)
                                    content = data.get("choices", [{}])[0].get("delta", {}).get("content", "")
                                    if content:
                                        yield content
                                except Exception:
                                    pass
                        return
                except Exception:
                    pass

                # Fallback: non-streaming via LibreChat's /api/ask endpoint
                r = await client.post(url, json=payload, headers=headers, timeout=30.0)
                if r.status_code == 200:
                    data = r.json()
                    reply = data.get("response") or data.get("text") or data.get("message", "")
                    if reply:
                        yield reply
                        return
                yield f"[LibreChat returned HTTP {r.status_code}. Make sure LibreChat is running at localhost:3080]"

        except httpx.ConnectError:
            yield (
                "**LibreChat is not running.**\n\n"
                "Start it with the `begin` command or from Docker Desktop,\n"
                "then try again. LibreChat runs on port 3080."
            )
        except Exception as e:
            logger.error(f"LibreChat stream error: {e}")
            yield f"**LibreChat error:** {str(e)[:200]}"

    async def _stream_ollama(
        self, model: str, messages: List[Dict]
    ) -> AsyncGenerator[str, None]:
        """
        Stream directly from Ollama's /api/chat endpoint.
        Model ID format: "ollama/modelname" — strip prefix.
        """
        model_name = model.replace("ollama/", "")
        url = f"{self._settings.ollama_base_url}/api/chat"
        payload = {
            "model": model_name,
            "messages": messages,
            "stream": True,
        }
        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                async with client.stream("POST", url, json=payload) as response:
                    if response.status_code != 200:
                        yield f"[Ollama error: HTTP {response.status_code}]"
                        return
                    import json
                    async for line in response.aiter_lines():
                        if line.strip():
                            try:
                                data = json.loads(line)
                                content = data.get("message", {}).get("content", "")
                                if content:
                                    yield content
                                if data.get("done", False):
                                    break
                            except json.JSONDecodeError:
                                continue
        except httpx.ConnectError:
            yield "\n[Ollama is not running. Start it with: `ollama serve`]"
        except Exception as e:
            logger.error(f"Ollama stream error: {e}")
            yield f"\n[Ollama error: {str(e)[:100]}]"

    async def complete(
        self, model: str, messages: List[Dict], phi_detected: bool = False
    ) -> str:
        """Non-streaming completion. Collects full stream and returns."""
        chunks = []
        async for chunk in self.stream(model, messages, phi_detected=phi_detected):
            chunks.append(chunk)
        return "".join(chunks)
