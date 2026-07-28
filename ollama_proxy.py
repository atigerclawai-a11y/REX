#!/usr/bin/env python3
"""Ollama proxy — listens on all interfaces, forwards to localhost:11434.
Fixes Docker bridge connectivity. Run: python3 ollama_proxy.py &"""
import socket, threading, sys

BACKEND = ("127.0.0.1", 11434)
LISTEN = ("0.0.0.0", 11436)

def handle(client):
    backend = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        backend.connect(BACKEND)
        threading.Thread(target=forward, args=(client, backend), daemon=True).start()
        threading.Thread(target=forward, args=(backend, client), daemon=True).start()
    except Exception:
        client.close()

def forward(src, dst):
    try:
        while True:
            data = src.recv(8192)
            if not data:
                break
            dst.sendall(data)
    except Exception:
        pass
    finally:
        try: src.close()
        except: pass
        try: dst.close()
        except: pass

server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
server.bind(LISTEN)
server.listen(10)
print(f"Proxy :11436 -> localhost:11434", flush=True)
while True:
    client, addr = server.accept()
    threading.Thread(target=handle, args=(client,), daemon=True).start()