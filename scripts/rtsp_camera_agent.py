#!/usr/bin/env python3
"""
Send camera events / heartbeats / snapshots to BauPass RTSP ingest (local NVR bridge).

Usage:
  set BAUPASS_API_URL=https://baupass-production.up.railway.app
  set BAUPASS_RTSP_BRIDGE_TOKEN=your-token
  set BAUPASS_COMPANY_ID=cmp-xxx
  python scripts/rtsp_camera_agent.py --interval 60

Heartbeat only (no AI event):
  python scripts/rtsp_camera_agent.py --once --heartbeat

Optional RTSP snapshot via ffmpeg (requires ffmpeg on PATH):
  set BAUPASS_CAMERA_RTSP_URL=rtsp://user:pass@192.168.1.50/stream1
  python scripts/rtsp_camera_agent.py --once --snapshot
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request


def _capture_rtsp_jpeg(rtsp_url: str, timeout_sec: int = 15) -> str | None:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg or not rtsp_url.strip():
        return None
    tmp = tempfile.NamedTemporaryFile(suffix=".jpg", delete=False)
    tmp.close()
    try:
        proc = subprocess.run(
            [
                ffmpeg,
                "-y",
                "-rtsp_transport",
                "tcp",
                "-i",
                rtsp_url,
                "-frames:v",
                "1",
                "-q:v",
                "4",
                tmp.name,
            ],
            capture_output=True,
            timeout=timeout_sec,
        )
        if proc.returncode != 0:
            return None
        with open(tmp.name, "rb") as fh:
            data = fh.read()
        if len(data) < 500:
            return None
        return base64.b64encode(data).decode("ascii")
    except Exception:
        return None
    finally:
        try:
            os.unlink(tmp.name)
        except Exception:
            pass


def post_payload(
    api_url: str,
    token: str,
    company_id: str,
    body: dict,
) -> dict:
    url = f"{api_url.rstrip('/')}/api/integrations/cameras/rtsp-ingest"
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={
            "Content-Type": "application/json",
            "X-BauPass-Rtsp-Token": token,
            "X-BauPass-Company-Id": company_id,
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def send_once(
    *,
    api_url: str,
    token: str,
    company_id: str,
    camera_id: str,
    event_type: str,
    worker_id: str | None,
    heartbeat: bool,
    snapshot_b64: str | None,
    camera_name: str,
    location: str,
    rtsp_url: str,
) -> dict:
    body: dict = {
        "companyId": company_id,
        "camera_id": camera_id,
        "camera_name": camera_name or camera_id,
        "location": location,
    }
    if rtsp_url:
        body["rtsp_url"] = rtsp_url
    if heartbeat:
        body["heartbeat"] = True
    else:
        body["event_type"] = event_type
    if worker_id:
        body["worker_id"] = worker_id
    if snapshot_b64:
        body["image_base64"] = snapshot_b64
    return post_payload(api_url, token, company_id, body)


def main() -> int:
    parser = argparse.ArgumentParser(description="BauPass RTSP/camera bridge agent")
    parser.add_argument("--api-url", default=os.getenv("BAUPASS_API_URL", "http://127.0.0.1:8000"))
    parser.add_argument("--token", default=os.getenv("BAUPASS_RTSP_BRIDGE_TOKEN", ""))
    parser.add_argument("--company-id", default=os.getenv("BAUPASS_COMPANY_ID", ""))
    parser.add_argument("--camera", default=os.getenv("BAUPASS_CAMERA_ID", "demo-cam-1"))
    parser.add_argument("--camera-name", default=os.getenv("BAUPASS_CAMERA_NAME", ""))
    parser.add_argument("--location", default=os.getenv("BAUPASS_CAMERA_LOCATION", ""))
    parser.add_argument("--rtsp-url", default=os.getenv("BAUPASS_CAMERA_RTSP_URL", ""))
    parser.add_argument("--worker-id", default=os.getenv("BAUPASS_WORKER_ID", ""))
    parser.add_argument("--event", default="motion", help="motion | ppe_check | unknown_person")
    parser.add_argument("--interval", type=int, default=120, help="seconds between sends (0 = once)")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--heartbeat", action="store_true", help="Send heartbeat only (no AI event row)")
    parser.add_argument("--snapshot", action="store_true", help="Capture JPEG from RTSP via ffmpeg")
    args = parser.parse_args()

    if not args.token:
        print("Missing BAUPASS_RTSP_BRIDGE_TOKEN or --token", file=sys.stderr)
        return 1
    if not args.company_id:
        print("Missing BAUPASS_COMPANY_ID or --company-id", file=sys.stderr)
        return 1

    worker_id = args.worker_id.strip() or None
    camera_name = args.camera_name.strip() or args.camera

    def tick() -> None:
        snap = None
        if args.snapshot or args.rtsp_url:
            snap = _capture_rtsp_jpeg(args.rtsp_url)
            if args.snapshot and not snap:
                print("Warning: ffmpeg snapshot failed", file=sys.stderr)
        try:
            result = send_once(
                api_url=args.api_url,
                token=args.token,
                company_id=args.company_id,
                camera_id=args.camera,
                event_type=args.event,
                worker_id=worker_id,
                heartbeat=args.heartbeat,
                snapshot_b64=snap,
                camera_name=camera_name,
                location=args.location,
                rtsp_url=args.rtsp_url,
            )
            print(json.dumps(result, indent=2))
        except urllib.error.HTTPError as exc:
            err = exc.read().decode("utf-8", errors="replace")
            print(f"HTTP {exc.code}: {err}", file=sys.stderr)
            raise

    if args.once or args.interval <= 0:
        tick()
        return 0

    print(f"Sending every {args.interval}s to {args.api_url} (camera={args.camera})")
    while True:
        tick()
        time.sleep(max(5, args.interval))


if __name__ == "__main__":
    raise SystemExit(main())
