# OpenAPI — WorkPass API v1

## Live document

```
GET /api/v1/openapi.json
```

Returns OpenAPI **3.0.3** JSON with the baseline routes (auth, workers, cameras, chat, leave, health, …).

## Source of truth

- Python builder: [`backend/app/api/openapi_spec.py`](../backend/app/api/openapi_spec.py)
- Route: [`backend/app/api/openapi_routes.py`](../backend/app/api/openapi_routes.py)

When adding a **new public API**, extend `build_openapi_document()` in the same PR.

## Tools

- [Swagger Editor](https://editor.swagger.io/) — paste JSON from `/api/v1/openapi.json`
- Postman — Import → Link → `{PUBLIC_BASE_URL}/api/v1/openapi.json`

## Tests

```bash
pytest backend/tests/test_openapi_spec.py
```
