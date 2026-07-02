"""WorkPass OpenAPI 3.0 document (v1 baseline for developers)."""
from __future__ import annotations

from typing import Any


def build_openapi_document(base_url: str = "") -> dict[str, Any]:
    server = (base_url or "https://example.up.railway.app").rstrip("/")
    bearer: list[dict[str, list[str]]] = [{"bearerAuth": []}]

    def op(
        tag: str,
        summary: str,
        *,
        roles: str = "",
        security: list | None = None,
        request_body: dict | None = None,
        parameters: list | None = None,
        responses: dict | None = None,
    ) -> dict[str, Any]:
        doc: dict[str, Any] = {
            "tags": [tag],
            "summary": summary,
            "responses": responses
            or {
                "200": {"description": "OK"},
                "401": {"$ref": "#/components/responses/Unauthorized"},
                "403": {"$ref": "#/components/responses/Forbidden"},
            },
        }
        if roles:
            doc["description"] = f"Roles: {roles}"
        if security is not None:
            doc["security"] = security
        elif security is not False:
            doc["security"] = bearer
        if request_body:
            doc["requestBody"] = request_body
        if parameters:
            doc["parameters"] = parameters
        return doc

    json_body = lambda schema, required=True: {
        "required": required,
        "content": {"application/json": {"schema": schema}},
    }

    return {
        "openapi": "3.0.3",
        "info": {
            "title": "WorkPass / Suppix Platform API",
            "version": "1.0.0",
            "description": (
                "Baseline OpenAPI spec for the WorkPass multi-tenant platform. "
                "Not every legacy handler in server.py is listed yet — extend this file "
                "when adding domain routes. Live document: GET /api/v1/openapi.json"
            ),
            "contact": {"name": "Suppix Technologie UG"},
        },
        "servers": [{"url": server, "description": "Current deployment"}],
        "tags": [
            {"name": "Health", "description": "Probes and platform readiness"},
            {"name": "Auth", "description": "Login, session, 2FA, password"},
            {"name": "Companies", "description": "Tenants and subcompanies"},
            {"name": "Workers", "description": "Employee records and documents"},
            {"name": "Access", "description": "Gates, geofences, access logs"},
            {"name": "Workforce", "description": "Leave, shifts, deployment"},
            {"name": "Chat", "description": "Admin ↔ worker messaging"},
            {"name": "Cameras", "description": "RTSP bridge, registry, events"},
            {"name": "Documents", "description": "Inbox and document assignment"},
            {"name": "Billing", "description": "Invoices and DATEV export"},
            {"name": "Admin", "description": "Devices, audit, platform tools"},
            {"name": "WorkerApp", "description": "Mobile worker session APIs"},
        ],
        "components": {
            "securitySchemes": {
                "bearerAuth": {
                    "type": "http",
                    "scheme": "bearer",
                    "bearerFormat": "JWT-or-session-token",
                    "description": "Authorization: Bearer <token> from POST /api/login",
                },
                "workerSession": {
                    "type": "http",
                    "scheme": "bearer",
                    "description": "Worker app session token",
                },
                "rtspBridgeToken": {
                    "type": "apiKey",
                    "in": "header",
                    "name": "X-WorkPass-Rtsp-Token",
                    "description": "Must match BAUPASS_RTSP_BRIDGE_TOKEN",
                },
                "deviceApiKey": {
                    "type": "apiKey",
                    "in": "header",
                    "name": "X-Device-API-Key",
                },
            },
            "schemas": {
                "Error": {
                    "type": "object",
                    "properties": {
                        "error": {"type": "string"},
                        "message": {"type": "string"},
                        "detail": {"type": "string"},
                    },
                },
                "LoginRequest": {
                    "type": "object",
                    "required": ["username", "password"],
                    "properties": {
                        "username": {"type": "string"},
                        "password": {"type": "string"},
                        "loginScope": {"type": "string", "enum": ["server-admin", "company", "turnstile"]},
                        "otpCode": {"type": "string"},
                    },
                },
                "LoginResponse": {
                    "type": "object",
                    "properties": {
                        "ok": {"type": "boolean"},
                        "token": {"type": "string"},
                        "user": {"type": "object"},
                        "planFeatures": {"type": "object"},
                    },
                },
                "CameraBulkLines": {
                    "type": "object",
                    "properties": {
                        "lines": {
                            "type": "string",
                            "description": "Name, location, RTSP URL per line (comma/semicolon/tab)",
                        },
                        "cameras": {
                            "type": "array",
                            "items": {"$ref": "#/components/schemas/CameraInput"},
                        },
                    },
                },
                "CameraInput": {
                    "type": "object",
                    "required": ["name"],
                    "properties": {
                        "id": {"type": "string"},
                        "name": {"type": "string"},
                        "location": {"type": "string"},
                        "rtspUrl": {"type": "string"},
                    },
                },
            },
            "responses": {
                "Unauthorized": {
                    "description": "Missing or invalid auth",
                    "content": {"application/json": {"schema": {"$ref": "#/components/schemas/Error"}}},
                },
                "Forbidden": {
                    "description": "Role or tenant mismatch",
                    "content": {"application/json": {"schema": {"$ref": "#/components/schemas/Error"}}},
                },
            },
        },
        "paths": {
            "/api/health": {
                "get": op("Health", "Full health check (DB, Redis, queues)", security=False),
            },
            "/api/health/ready": {
                "get": op("Health", "Readiness probe", security=False),
            },
            "/api/health/live": {
                "get": op("Health", "Liveness probe", security=False),
            },
            "/api/platform/setup-status": {
                "get": op("Admin", "Platform env completeness", roles="superadmin"),
            },
            "/api/platform/database-status": {
                "get": op("Admin", "Database backend and pool stats", roles="superadmin"),
            },
            "/api/login": {
                "post": {
                    **op("Auth", "Login and receive bearer token", security=False),
                    "requestBody": json_body({"$ref": "#/components/schemas/LoginRequest"}),
                    "responses": {
                        "200": {
                            "description": "Authenticated",
                            "content": {"application/json": {"schema": {"$ref": "#/components/schemas/LoginResponse"}}},
                        },
                        "401": {"$ref": "#/components/responses/Unauthorized"},
                    },
                },
            },
            "/api/logout": {"post": op("Auth", "Invalidate session", roles="any authenticated")},
            "/api/me": {"get": op("Auth", "Current user profile", roles="any authenticated")},
            "/api/session/bootstrap": {
                "get": op("Auth", "Session shell payload for SPA", roles="any authenticated"),
            },
            "/api/companies": {
                "get": op("Companies", "List companies", roles="superadmin"),
                "post": op("Companies", "Create company", roles="superadmin"),
            },
            "/api/companies/{company_id}": {
                "get": op(
                    "Companies",
                    "Get company",
                    roles="superadmin, company-admin",
                    parameters=[{"name": "company_id", "in": "path", "required": True, "schema": {"type": "string"}}],
                ),
            },
            "/api/workers": {
                "get": op("Workers", "List workers for tenant", roles="superadmin, company-admin"),
                "post": op("Workers", "Create worker", roles="superadmin, company-admin"),
            },
            "/api/workers/{worker_id}": {
                "get": op(
                    "Workers",
                    "Get worker",
                    roles="superadmin, company-admin",
                    parameters=[{"name": "worker_id", "in": "path", "required": True, "schema": {"type": "string"}}],
                ),
                "put": op("Workers", "Update worker", roles="superadmin, company-admin"),
                "delete": op("Workers", "Soft-delete worker", roles="superadmin, company-admin"),
            },
            "/api/access-logs": {
                "get": op("Access", "Access journal", roles="superadmin, company-admin, turnstile"),
            },
            "/api/access-logs/check-in": {
                "post": op("Access", "Check-in event", roles="turnstile, company-admin"),
            },
            "/api/access-logs/check-out": {
                "post": op("Access", "Check-out event", roles="turnstile, company-admin"),
            },
            "/api/leave-requests": {
                "get": op("Workforce", "List leave requests", roles="superadmin, company-admin"),
                "post": op("Workforce", "Create leave request", roles="worker session or admin"),
            },
            "/api/leave-requests/{request_id}": {
                "put": op(
                    "Workforce",
                    "Approve/reject leave (POST fallback supported)",
                    roles="superadmin, company-admin",
                    parameters=[{"name": "request_id", "in": "path", "required": True, "schema": {"type": "string"}}],
                ),
            },
            "/api/chat/threads": {
                "get": op("Chat", "List chat threads", roles="superadmin, company-admin"),
                "post": op("Chat", "Open thread with worker", roles="superadmin, company-admin"),
            },
            "/api/chat/threads/{thread_id}/messages": {
                "get": op("Chat", "Thread messages", roles="admin or worker session"),
                "post": op("Chat", "Send message", roles="admin or worker session"),
            },
            "/api/integrations/cameras": {
                "get": op("Cameras", "List site cameras + online summary", roles="superadmin, company-admin"),
                "post": op("Cameras", "Register single camera", roles="superadmin, company-admin"),
            },
            "/api/integrations/cameras/bulk": {
                "post": {
                    **op("Cameras", "Bulk import up to 100 cameras", roles="superadmin, company-admin"),
                    "requestBody": json_body({"$ref": "#/components/schemas/CameraBulkLines"}),
                },
            },
            "/api/integrations/cameras/setup": {
                "get": op("Cameras", "Bridge setup hints and agent JSON", roles="superadmin, company-admin"),
            },
            "/api/integrations/cameras/{camera_id}/snapshot": {
                "get": op(
                    "Cameras",
                    "Live JPEG snapshot",
                    roles="superadmin, company-admin",
                    parameters=[
                        {"name": "camera_id", "in": "path", "required": True, "schema": {"type": "string"}},
                        {"name": "format", "in": "query", "schema": {"type": "string", "enum": ["jpeg", "json"]}},
                    ],
                ),
            },
            "/api/integrations/cameras/rtsp-ingest": {
                "post": {
                    **op(
                        "Cameras",
                        "RTSP agent / NVR webhook ingest",
                        security=[{"rtspBridgeToken": []}, {"deviceApiKey": []}, {"bearerAuth": []}],
                    ),
                    "description": "Auth: X-WorkPass-Rtsp-Token, X-Device-API-Key, or admin session",
                },
            },
            "/api/integrations/cameras/events": {
                "get": op("Cameras", "Recent camera AI events", roles="superadmin, company-admin"),
            },
            "/api/admin/devices": {
                "get": op("Admin", "List registered devices", roles="superadmin, company-admin"),
                "post": op("Admin", "Register device + API key", roles="superadmin, company-admin"),
            },
            "/api/documents/inbox": {
                "get": op("Documents", "Email document inbox", roles="superadmin, company-admin"),
            },
            "/api/invoices": {
                "get": op("Billing", "List invoices", roles="superadmin, company-admin"),
            },
            "/api/worker-app/session": {
                "post": op("WorkerApp", "Worker mobile login", security=False),
            },
            "/api/worker-app/me": {
                "get": op("WorkerApp", "Worker profile", security=[{"workerSession": []}]),
            },
            "/api/v1/openapi.json": {
                "get": op("Admin", "This OpenAPI document", security=False),
            },
        },
    }
