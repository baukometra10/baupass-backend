"""Trusted-proxy aware client IP resolution for Railway and CDN edges."""
from __future__ import annotations

import ipaddress

from flask import Request

_IP_HEADERS = (
    "CF-Connecting-IP",
    "True-Client-Ip",
    "X-Real-IP",
    "X-Forwarded-For",
    "Forwarded",
)


def _parse_forwarded_header(value: str) -> str:
    for part in value.split(","):
        segment = part.strip()
        if not segment:
            continue
        if "=" in segment:
            key, raw_ip = segment.split("=", 1)
            if key.strip().lower() != "for":
                continue
            candidate = raw_ip.strip().strip('"')
            if candidate.startswith("[") and "]" in candidate:
                candidate = candidate[1 : candidate.index("]")]
            if candidate.lower() == "unknown":
                continue
            return candidate
        return segment
    return ""


def _valid_ip(value: str) -> str | None:
    candidate = (value or "").strip()
    if not candidate or candidate.lower() == "unknown":
        return None
    try:
        ipaddress.ip_address(candidate)
    except ValueError:
        return None
    return candidate


def resolve_client_ip(req: Request | None = None) -> str:
    from flask import request

    active = req or request
    for header in _IP_HEADERS:
        raw = (active.headers.get(header) or "").strip()
        if not raw:
            continue
        if header == "Forwarded":
            candidate = _parse_forwarded_header(raw)
        else:
            candidate = raw.split(",")[0].strip()
        parsed = _valid_ip(candidate)
        if parsed:
            return parsed

    remote = _valid_ip(active.remote_addr or "")
    return remote or "local"
