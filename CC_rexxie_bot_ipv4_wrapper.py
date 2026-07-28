#!/usr/bin/env python3.11
"""Wrapper to force IPv4 for api.telegram.org before running Rexxie bot."""
import socket
import sys
import os

# Save original getaddrinfo
_original_getaddrinfo = socket.getaddrinfo

def _ipv4_getaddrinfo(host, port, family=0, type=0, proto=0, flags=0):
    """Force IPv4 for api.telegram.org."""
    if host == 'api.telegram.org':
        return _original_getaddrinfo(host, port, socket.AF_INET, type, proto, flags)
    return _original_getaddrinfo(host, port, family, type, proto, flags)

socket.getaddrinfo = _ipv4_getaddrinfo

# Also patch create_connection
_original_create_connection = socket.create_connection
def _ipv4_create_connection(address, timeout=None, source_address=None):
    """Force IPv4 for api.telegram.org connections."""
    host, port = address if isinstance(address, tuple) else (address[0], address[1])
    if host == 'api.telegram.org':
        # Resolve IPv4 only
        for res in socket.getaddrinfo(host, port, socket.AF_INET, socket.SOCK_STREAM):
            af, socktype, proto, canonname, sa = res
            try:
                sock = socket.socket(af, socktype, proto)
                if timeout is not None:
                    sock.settimeout(timeout)
                if source_address:
                    sock.bind(source_address)
                sock.connect(sa)
                return sock
            except Exception:
                sock.close()
        raise socket.error("getaddrinfo returns an empty list")
    return _original_create_connection(address, timeout, source_address)

socket.create_connection = _ipv4_create_connection

# Now run the actual bot
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from rex_rexxie_telegram_bot import RexxieTelegramBot
bot = RexxieTelegramBot()
bot.run()
