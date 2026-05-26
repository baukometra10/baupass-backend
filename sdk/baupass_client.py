"""
BauPass Enterprise SDK (minimal HTTP client).
"""
from __future__ import annotations

import json
from urllib import request as urlrequest


class BauPassClient:
    def __init__(self, base_url: str, api_key: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key

    def _get(self, path: str) -> dict:
        req = urlrequest.Request(
            f"{self.base_url}{path}",
            headers={"X-Api-Key": self.api_key},
            method="GET",
        )
        with urlrequest.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode())

    def list_workers(self) -> dict:
        return self._get("/api/v1/workers")

    def company(self) -> dict:
        return self._get("/api/v1/company")

    def health(self) -> dict:
        return self._get("/api/v1/public/health")
