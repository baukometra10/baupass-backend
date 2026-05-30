#!/usr/bin/env python3
"""
Send demo camera events to BauPass RTSP ingest (local NVR bridge stub).

Usage:
  set BAUPASS_API_URL=https://baupass-production.up.railway.app
  set BAUPASS_RTSP_BRIDGE_TOKEN=your-token
  set BAUPASS_COMPANY_ID=cmp-xxx
  python scripts/rtsp_camera_agent.py --interval 60

Optional one-shot:
  python scripts/rtsp_camera_agent.py --once --event motion --camera gate-north
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request


def post_event(
    api_url: str,
    token: str,
    company_id: str,
    camera_id: str,
    event_type: str,
    worker_id: str | None,
) -> dict:
    url = f"{api_url.rstrip('/')}/api/integrations/cameras/rtsp-ingest"
    body = {
        "companyId": company_id,
        "camera_id": camera_id,
        "event_type": event_type,
    }
    if worker_id:
        body["worker_id"] = worker_id
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


def main() -> int:
    parser = argparse.ArgumentParser(description="BauPass RTSP/camera demo agent")
    parser.add_argument("--api-url", default=os.getenv("BAUPASS_API_URL", "http://127.0.0.1:8000"))
    parser.add_argument("--token", default=os.getenv("BAUPASS_RTSP_BRIDGE_TOKEN", ""))
    parser.add_argument("--company-id", default=os.getenv("BAUPASS_COMPANY_ID", ""))
    parser.add_argument("--camera", default=os.getenv("BAUPASS_CAMERA_ID", "demo-cam-1"))
    parser.add_argument("--worker-id", default=os.getenv("BAUPASS_WORKER_ID", ""))
    parser.add_argument("--event", default="motion", help="motion | ppe_check | unknown_person")
    parser.add_argument("--interval", type=int, default=120, help="seconds between events (0 = once)")
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()

    if not args.token:
        print("Missing BAUPASS_RTSP_BRIDGE_TOKEN or --token", file=sys.stderr)
        return 1
    if not args.company_id:
        print("Missing BAUPASS_COMPANY_ID or --company-id", file=sys.stderr)
        return 1

    worker_id = args.worker_id.strip() or None

    def send_once() -> None:
        try:
            result = post_event(
                args.api_url,
                args.token,
                args.company_id,
                args.camera,
                args.event,
                worker_id,
            )
            print(json.dumps(result, indent=2))
        except urllib.error.HTTPError as exc:
            err = exc.read().decode("utf-8", errors="replace")
            print(f"HTTP {exc.code}: {err}", file=sys.stderr)
            raise

    if args.once or args.interval <= 0:
        send_once()
        return 0

    print(f"Sending every {args.interval}s to {args.api_url} (camera={args.camera})")
    while True:
        send_once()
        time.sleep(max(5, args.interval))


if __name__ == "__main__":
    raise SystemExit(main())
