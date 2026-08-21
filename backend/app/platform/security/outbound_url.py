"""Outbound URL safety checks (SSRF hardening for integrations)."""
from __future__ import annotations

import ipaddress
import socket
from typing import Any
from urllib.parse import urlparse


_BLOCKED_HOSTS = {
    "localhost",
    "metadata.google.internal",
    "metadata",
    "instance-data",
}


def assert_safe_outbound_url(url: str, *, require_https: bool = True) -> dict[str, Any]:
    """
    Reject obviously dangerous outbound targets (SSRF).

    Allows public HTTPS hostnames. Blocks localhost, private/link-local IPs,
    and non-http(s) schemes.
    """
    raw = str(url or "").strip()
    if not raw:
        return {"ok": False, "error": "missing_url"}
    try:
        parsed = urlparse(raw)
    except Exception:
        return {"ok": False, "error": "invalid_url"}
    scheme = (parsed.scheme or "").lower()
    if require_https and scheme != "https":
        return {"ok": False, "error": "https_required"}
    if scheme not in {"https", "http"}:
        return {"ok": False, "error": "unsupported_scheme"}
    host = (parsed.hostname or "").strip().lower()
    if not host:
        return {"ok": False, "error": "missing_host"}
    if host in _BLOCKED_HOSTS or host.endswith(".localhost") or host.endswith(".local"):
        return {"ok": False, "error": "blocked_host"}
    # Literal IP in hostname
    try:
        ip = ipaddress.ip_address(host)
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_multicast
            or ip.is_reserved
            or ip.is_unspecified
        ):
            return {"ok": False, "error": "blocked_ip"}
    except ValueError:
        # Hostname — resolve and check all A/AAAA
        try:
            infos = socket.getaddrinfo(host, None)
        except socket.gaierror:
            return {"ok": False, "error": "dns_resolution_failed"}
        for info in infos:
            addr = info[4][0]
            try:
                ip = ipaddress.ip_address(addr)
            except ValueError:
                continue
            if (
                ip.is_private
                or ip.is_loopback
                or ip.is_link_local
                or ip.is_multicast
                or ip.is_reserved
                or ip.is_unspecified
            ):
                return {"ok": False, "error": "blocked_resolved_ip", "host": host}
    return {"ok": True, "url": raw, "host": host}
