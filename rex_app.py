"""
REX — macOS App Launcher
Starts the FastAPI backend, serves the React frontend, and opens a native
macOS window via PyWebView (WKWebView — same engine as Safari, ~0 overhead).
Also installs a system tray icon (rumps) for quick access & Secure Mode toggle.

Run with:  python rex_app.py
Or via:    ./run.sh
"""
import sys
import os
import threading
import time
import signal
import logging
import subprocess
from pathlib import Path

# Ensure we can import the backend package
ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")
logger = logging.getLogger("rex.launcher")

BACKEND_PORT = 8000
FRONTEND_PORT = 5173
FRONTEND_DIST = ROOT / "frontend" / "dist"

# ── Detect run mode ────────────────────────────────────────────────────────────
DEV_MODE = "--dev" in sys.argv  # python rex_app.py --dev  → uses Vite dev server
NO_TRAY = "--no-tray" in sys.argv


def start_backend():
    """Start uvicorn in a background thread."""
    import uvicorn
    config = uvicorn.Config(
        "backend.main:app",
        host="0.0.0.0",
        port=BACKEND_PORT,
        log_level="warning",
        reload=False,
    )
    server = uvicorn.Server(config)
    server.run()


def start_vite_dev():
    """Start Vite dev server (dev mode only)."""
    npm = subprocess.Popen(
        ["npm", "run", "dev"],
        cwd=str(ROOT / "frontend"),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return npm


def wait_for_backend(timeout=15):
    """Poll until FastAPI is ready."""
    import urllib.request
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{BACKEND_PORT}/api/health", timeout=1)
            return True
        except Exception:
            time.sleep(0.3)
    return False


# ── System Tray (rumps) ────────────────────────────────────────────────────────
def start_tray(window_ref):
    try:
        import rumps
    except ImportError:
        logger.warning("rumps not installed — system tray disabled. Install with: pip install rumps")
        return

    class REXTrayApp(rumps.App):
        def __init__(self, window_ref):
            super().__init__("🦖", quit_button=None)
            self._window = window_ref
            self._secure = False
            self.menu = [
                rumps.MenuItem("Open REX", callback=self.open_window),
                rumps.MenuItem("─────────────────"),
                rumps.MenuItem("🔓 Secure Mode: OFF", callback=self.toggle_secure),
                rumps.MenuItem("─────────────────"),
                rumps.MenuItem("Quit REX", callback=self.quit_app),
            ]

        def open_window(self, _=None):
            try:
                import webview
                for w in webview.windows:
                    w.show()
            except Exception:
                pass

        def toggle_secure(self, sender):
            import urllib.request, json
            self._secure = not self._secure
            label = "🔒 Secure Mode: ON" if self._secure else "🔓 Secure Mode: OFF"
            sender.title = label
            # Send toggle to backend
            try:
                data = json.dumps({"enabled": self._secure}).encode()
                req = urllib.request.Request(
                    f"http://127.0.0.1:{BACKEND_PORT}/api/settings/secure-mode",
                    data=data,
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                urllib.request.urlopen(req, timeout=2)
                self.title = "🔒" if self._secure else "🦖"
            except Exception as e:
                logger.warning(f"Could not toggle secure mode: {e}")

        @rumps.clicked("Quit REX")
        def quit_app(self, _):
            import webview
            for w in webview.windows:
                w.destroy()
            rumps.quit_application()

    app = REXTrayApp(window_ref)
    app.run()


# ── Main entrypoint ────────────────────────────────────────────────────────────
def main():
    logger.info("🦖 REX starting…")

    # ── API-only mode (--api flag) ─────────────────────────────────────────────
    # Used by start-all.command to run the backend as a headless server.
    # No webview, no tray — just uvicorn running forever on port 8000.
    if "--api" in sys.argv:
        logger.info("🌐 API-only mode — no UI, no tray")
        # Non-daemon thread so the process stays alive
        backend_thread = threading.Thread(target=start_backend, daemon=False)
        backend_thread.start()
        logger.info(f"✅ REX backend running on http://0.0.0.0:{BACKEND_PORT}")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            logger.info("👋 REX API server shutting down")
        return

    # 1. Start FastAPI backend in background thread
    backend_thread = threading.Thread(target=start_backend, daemon=True)
    backend_thread.start()

    # 2. Optionally start Vite dev server
    vite_proc = None
    if DEV_MODE:
        logger.info("🔧 Dev mode: starting Vite…")
        vite_proc = start_vite_dev()
        url = f"http://localhost:{FRONTEND_PORT}"
    else:
        # Production: serve built frontend via FastAPI static files
        if not FRONTEND_DIST.exists():
            logger.warning("Frontend not built. Run setup.sh first, or use --dev flag.")
        url = f"http://127.0.0.1:{BACKEND_PORT}"

    # 3. Wait for backend to be ready
    logger.info("⏳ Waiting for backend…")
    if not wait_for_backend():
        logger.error("❌ Backend failed to start. Check errors above.")
        sys.exit(1)
    logger.info("✅ Backend ready")

    # 4. Open native macOS window
    try:
        import webview
    except ImportError:
        logger.warning("pywebview not installed. Opening in default browser instead.")
        import webbrowser
        webbrowser.open(url)
        # Keep backend alive
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            pass
        return

    window = webview.create_window(
        title="REX — Privacy Proxy",
        url=url,
        width=1100,
        height=760,
        min_size=(800, 600),
        resizable=True,
        frameless=False,
        easy_drag=False,
        background_color="#0f0f0f",
    )

    # 5. Start webview in a background thread (rumps needs the main thread)
    #    If tray is disabled, webview blocks the main thread as before.
    if not NO_TRAY:
        # webview runs in a thread; rumps.App.run() takes the main thread
        webview_thread = threading.Thread(
            target=webview.start, kwargs={"debug": DEV_MODE}, daemon=True
        )
        webview_thread.start()

        # 6. Run system tray on main thread (required by macOS/rumps)
        start_tray(window)

        # Tray exited — wait for webview thread to finish too
        webview_thread.join(timeout=5)
    else:
        # 6. No tray — webview blocks main thread as normal
        webview.start(debug=DEV_MODE)

    # 7. Cleanup
    if vite_proc:
        vite_proc.terminate()
    logger.info("👋 REX closed")


if __name__ == "__main__":
    main()
