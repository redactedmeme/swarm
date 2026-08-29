"""SSRF protection — validate URLs before fetching."""

import ipaddress
import socket
import urllib.parse

BLOCKED_SCHEMES = {"file", "gopher", "data", "ftp", "sftp", "ldap", "ldaps"}

_PRIVATE_RANGES = [
    ipaddress.ip_network(r) for r in [
        "10.0.0.0/8",
        "172.16.0.0/12",
        "192.168.0.0/16",
        "127.0.0.0/8",
        "169.254.0.0/16",   # link-local
        "100.64.0.0/10",    # shared address space (Railway internal)
        "::1/128",
        "fc00::/7",
        "fe80::/10",
    ]
]


def _is_private_ip(host: str) -> bool:
    try:
        ip = ipaddress.ip_address(host)
        return any(ip in net for net in _PRIVATE_RANGES)
    except ValueError:
        pass
    # Resolve hostname and check
    try:
        resolved = socket.getaddrinfo(host, None)
        for r in resolved:
            ip = ipaddress.ip_address(r[4][0])
            if any(ip in net for net in _PRIVATE_RANGES):
                return True
    except Exception:
        pass
    return False


def validate_url(url: str) -> str:
    """
    Validate a URL is safe to fetch. Raises ValueError if blocked.
    Returns the url unchanged if safe.
    """
    parsed = urllib.parse.urlparse(url)

    if parsed.scheme.lower() in BLOCKED_SCHEMES:
        raise ValueError(f"[url_guard] blocked scheme: {parsed.scheme!r}")

    if parsed.scheme.lower() not in {"http", "https"}:
        raise ValueError(f"[url_guard] only http/https allowed, got: {parsed.scheme!r}")

    host = parsed.hostname or ""
    if not host:
        raise ValueError("[url_guard] missing hostname")

    if _is_private_ip(host):
        raise ValueError(f"[url_guard] SSRF blocked: private/internal host {host!r}")

    return url
