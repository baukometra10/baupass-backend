"""ONVIF GetCapabilities / GetStreamUri probe (not a full ONVIF stack)."""
from __future__ import annotations

import re
import socket
import urllib.error
import urllib.request
from typing import Any
from xml.etree import ElementTree as ET

_SOAP_ENV = """<?xml version="1.0" encoding="UTF-8"?>
<s:Envelope xmlns:s="http://www.w3.org/2003/05/soap-envelope">
  <s:Body>{body}</s:Body>
</s:Envelope>"""

_GET_CAPABILITIES = """
<tds:GetCapabilities xmlns:tds="http://www.onvif.org/ver10/device/wsdl">
  <tds:Category>All</tds:Category>
</tds:GetCapabilities>
"""

_GET_STREAM_URI = """
<trt:GetStreamUri xmlns:trt="http://www.onvif.org/ver10/media/wsdl">
  <trt:StreamSetup>
    <tt:Stream xmlns:tt="http://www.onvif.org/ver10/schema">RTP-Unicast</tt:Stream>
    <tt:Transport xmlns:tt="http://www.onvif.org/ver10/schema">
      <tt:Protocol>RTSP</tt:Protocol>
    </tt:Transport>
  </trt:StreamSetup>
  <trt:ProfileToken>{token}</trt:ProfileToken>
</trt:GetStreamUri>
"""


def _local(tag: str) -> str:
    return tag.split("}", 1)[-1] if "}" in tag else tag


def _post_soap(url: str, body: str, *, username: str, password: str, timeout: float) -> bytes:
    payload = _SOAP_ENV.format(body=body).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=payload,
        method="POST",
        headers={
            "Content-Type": "application/soap+xml; charset=utf-8",
            "Content-Length": str(len(payload)),
        },
    )
    if username:
        import base64

        token = base64.b64encode(f"{username}:{password}".encode("utf-8")).decode("ascii")
        req.add_header("Authorization", f"Basic {token}")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read() or b""


def _first_text(root: ET.Element, local: str) -> str:
    for el in root.iter():
        if _local(el.tag) == local and (el.text or "").strip():
            return el.text.strip()
    return ""


def probe_onvif(
    host: str,
    *,
    port: int = 80,
    username: str = "",
    password: str = "",
    timeout: float = 6.0,
    use_https: bool = False,
) -> dict[str, Any]:
    host = str(host or "").strip()
    if not host or any(ch in host for ch in " /?#"):
        return {"ok": False, "error": "invalid_host"}
    try:
        port = int(port or 80)
    except Exception:
        port = 80
    if port < 1 or port > 65535:
        return {"ok": False, "error": "invalid_port"}
    scheme = "https" if use_https or port == 443 else "http"
    device_url = f"{scheme}://{host}:{port}/onvif/device_service"
    try:
        raw = _post_soap(device_url, _GET_CAPABILITIES, username=username, password=password, timeout=timeout)
    except socket.timeout:
        return {"ok": False, "error": "timeout", "deviceUrl": device_url}
    except urllib.error.HTTPError as exc:
        return {"ok": False, "error": f"http_{exc.code}", "deviceUrl": device_url}
    except Exception as exc:
        return {"ok": False, "error": "connect_failed", "detail": str(exc)[:180], "deviceUrl": device_url}
    try:
        root = ET.fromstring(raw)
    except ET.ParseError:
        return {"ok": False, "error": "invalid_onvif_xml", "deviceUrl": device_url}
    media_xaddr = ""
    for el in root.iter():
        if _local(el.tag) == "XAddr" and el.text and "media" in (el.text or "").lower():
            media_xaddr = el.text.strip()
            break
    if not media_xaddr:
        media_xaddr = f"{scheme}://{host}:{port}/onvif/media_service"
    rtsp = ""
    try:
        profiles_body = (
            '<trt:GetProfiles xmlns:trt="http://www.onvif.org/ver10/media/wsdl"/>'
        )
        raw_profiles = _post_soap(
            media_xaddr, profiles_body, username=username, password=password, timeout=timeout
        )
        proot = ET.fromstring(raw_profiles)
        token = ""
        for el in proot.iter():
            if _local(el.tag) in {"Profiles", "Profile"}:
                token = (el.get("token") or "").strip()
                if token:
                    break
        if token:
            raw_uri = _post_soap(
                media_xaddr,
                _GET_STREAM_URI.format(token=token),
                username=username,
                password=password,
                timeout=timeout,
            )
            uroot = ET.fromstring(raw_uri)
            uri = _first_text(uroot, "Uri")
            if uri.lower().startswith("rtsp://"):
                rtsp = uri
    except Exception:
        pass
    manufacturer = _first_text(root, "Manufacturer") or _first_text(root, "Model")
    return {
        "ok": True,
        "deviceUrl": device_url,
        "mediaUrl": media_xaddr,
        "rtspUrl": rtsp,
        "manufacturer": manufacturer,
        "note": "Probe only — no PTZ/event subscription. Credentials are not stored.",
    }


def parse_onvif_host(raw: str) -> tuple[str, int, bool]:
    text = str(raw or "").strip()
    use_https = text.lower().startswith("https://")
    text = re.sub(r"^https?://", "", text, flags=re.I)
    text = text.split("/", 1)[0]
    if ":" in text:
        host, port_s = text.rsplit(":", 1)
        try:
            return host, int(port_s), use_https
        except Exception:
            return host, 80, use_https
    return text, 443 if use_https else 80, use_https
