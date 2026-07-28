"""
REX — TLS Certificate Management
Generates a self-signed certificate for HTTPS on first run.
Stored in ~/.rex/certs/ — survives app restarts.
iOS companion uses certificate pinning to validate this exact cert.
"""
import ssl
import socket
import logging
from pathlib import Path
from datetime import datetime, timedelta, timezone

logger = logging.getLogger(__name__)

CERT_DIR = Path.home() / ".rex" / "certs"
CERT_FILE = CERT_DIR / "rex.crt"
KEY_FILE  = CERT_DIR / "rex.key"
CERT_FINGERPRINT_FILE = CERT_DIR / "fingerprint.txt"


def _get_local_ips() -> list:
    """Get all local IP addresses including Tailscale if available."""
    ips = ["127.0.0.1", "localhost"]
    try:
        hostname = socket.gethostname()
        ips.append(socket.gethostbyname(hostname))
    except Exception:
        pass

    # Enumerate all network interfaces
    try:
        import netifaces
        for iface in netifaces.interfaces():
            addrs = netifaces.ifaddresses(iface)
            for addr in addrs.get(netifaces.AF_INET, []):
                ip = addr.get("addr", "")
                if ip and not ip.startswith("127."):
                    ips.append(ip)
    except ImportError:
        # Fallback: use socket
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ips.append(s.getsockname()[0])
            s.close()
        except Exception:
            pass

    return list(dict.fromkeys(ips))  # deduplicate, preserve order


def get_or_create_cert() -> tuple:
    """
    Return (cert_path, key_path), generating self-signed cert if needed.
    The cert covers all local IPs + Tailscale IPs (100.x.x.x range).
    """
    CERT_DIR.mkdir(parents=True, exist_ok=True)

    if CERT_FILE.exists() and KEY_FILE.exists():
        logger.info(f"🔐 Using existing TLS cert: {CERT_FILE}")
        return str(CERT_FILE), str(KEY_FILE)

    logger.info("🔐 Generating new TLS certificate for REX…")
    try:
        from cryptography import x509
        from cryptography.x509.oid import NameOID
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import rsa
        import ipaddress

        # Generate RSA key
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

        # Build subject
        subject = issuer = x509.Name([
            x509.NameAttribute(NameOID.COMMON_NAME, "REX Privacy Proxy"),
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, "REX Local"),
        ])

        # SANs: all local IPs + DNS names
        local_ips = _get_local_ips()
        san_entries = [x509.DNSName("localhost"), x509.DNSName("rex.local")]
        for ip in local_ips:
            try:
                san_entries.append(x509.IPAddress(ipaddress.ip_address(ip)))
            except Exception:
                pass
        # Include full Tailscale subnet just in case
        for i in range(1, 5):
            try:
                san_entries.append(x509.IPAddress(ipaddress.ip_address(f"100.64.0.{i}")))
            except Exception:
                pass

        cert = (
            x509.CertificateBuilder()
            .subject_name(subject)
            .issuer_name(issuer)
            .public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(datetime.now(timezone.utc))
            .not_valid_after(datetime.now(timezone.utc) + timedelta(days=3650))  # 10 years
            .add_extension(x509.SubjectAlternativeName(san_entries), critical=False)
            .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
            .sign(key, hashes.SHA256())
        )

        # Write cert and key
        CERT_FILE.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
        KEY_FILE.write_bytes(key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.TraditionalOpenSSL,
            serialization.NoEncryption(),
        ))
        KEY_FILE.chmod(0o600)

        # Write fingerprint for iOS pinning
        fp = cert.fingerprint(hashes.SHA256()).hex()
        fingerprint = ":".join(fp[i:i+2].upper() for i in range(0, len(fp), 2))
        CERT_FINGERPRINT_FILE.write_text(fingerprint)

        logger.info(f"✅ TLS cert generated | Fingerprint: {fingerprint[:23]}…")
        return str(CERT_FILE), str(KEY_FILE)

    except ImportError:
        logger.warning("cryptography library needed for TLS cert generation")
        return None, None


def get_cert_fingerprint() -> str:
    if CERT_FINGERPRINT_FILE.exists():
        return CERT_FINGERPRINT_FILE.read_text().strip()
    return ""


def get_ssl_context() -> ssl.SSLContext:
    cert_path, key_path = get_or_create_cert()
    if not cert_path:
        return None
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.load_cert_chain(cert_path, key_path)
    ctx.minimum_version = ssl.TLSVersion.TLSv1_2
    return ctx
