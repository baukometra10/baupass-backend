"""
WorkPass Enterprise SDK (minimal HTTP client).
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

    def enterprise_layers(self, company_id: int | None = None) -> dict:
        path = "/api/enterprise/layers"
        if company_id is not None:
            path += f"?company_id={company_id}"
        return self._get(path)

    def intelligence_layer(self) -> dict:
        return self._get("/api/enterprise/layers/intelligence")

    def list_webhooks(self) -> dict:
        return self._get("/api/developer/webhooks")

    def ops_os_overview(self, company_id: int | None = None) -> dict:
        path = "/api/ops-os/overview"
        if company_id is not None:
            path += f"?company_id={company_id}"
        return self._get(path)

    def digital_twin(self) -> dict:
        return self._get("/api/ops-os/digital-twin")

    def command_center(self) -> dict:
        return self._get("/api/ops-os/command-center")

    def ops_copilot(self, question: str, company_id: int | None = None) -> dict:
        body: dict = {"question": question}
        if company_id is not None:
            body["company_id"] = company_id
        return self._post("/api/ops-os/copilot", body)


WorkPassClient = BauPassClient
