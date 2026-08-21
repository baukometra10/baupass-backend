"""Open transfer ZIP / JSON packages into a normalized TransferPackage."""
from __future__ import annotations

import hashlib
import io
import json
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .schema import PHASE_A_DOMAINS, SCHEMA_VERSION


@dataclass
class TransferPackage:
    schema_version: str
    manifest: dict[str, Any]
    domains: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    files: dict[str, bytes] = field(default_factory=dict)  # relative path → bytes
    checksums: dict[str, str] = field(default_factory=dict)
    source_format: str = "zip"  # zip | json


def remap_package_company_ids(package: TransferPackage, target_company_id: str) -> dict[str, Any]:
    """
    Rewrite all company references in the package to target_company_id.
    Used when an Enterprise tenant restores an old system into their own company.
    """
    target = str(target_company_id or "").strip()
    if not target:
        raise ValueError("missing_company_id")
    source_ids: set[str] = set()
    mid = str(package.manifest.get("companyId") or package.manifest.get("company_id") or "").strip()
    if mid:
        source_ids.add(mid)
    for row in package.domains.get("companies") or []:
        cid = str(row.get("id") or "").strip()
        if cid:
            source_ids.add(cid)
    for rows in package.domains.values():
        for row in rows:
            for key in ("company_id", "companyId"):
                val = str(row.get(key) or "").strip()
                if val:
                    source_ids.add(val)

    for name, rows in list(package.domains.items()):
        for row in rows:
            if name == "companies":
                row["id"] = target
            for key in ("company_id", "companyId"):
                if key in row or (name != "companies" and key == "company_id"):
                    # Always set company_id for non-company rows when present or expected
                    if name == "companies":
                        continue
                    if key in row or key == "company_id":
                        row["company_id" if key == "company_id" else key] = target
            if name != "companies":
                row["company_id"] = target
                if "companyId" in row:
                    row["companyId"] = target

    package.manifest = dict(package.manifest or {})
    package.manifest["companyId"] = target
    package.manifest["remappedFrom"] = sorted(source_ids - {target})
    package.manifest["tenantScoped"] = True
    return {
        "targetCompanyId": target,
        "remappedFrom": package.manifest["remappedFrom"],
    }


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _load_json_bytes(raw: bytes) -> Any:
    return json.loads(raw.decode("utf-8"))


def _normalize_domain_rows(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, list):
        return [row for row in value if isinstance(row, dict)]
    if isinstance(value, dict) and isinstance(value.get("rows"), list):
        return [row for row in value["rows"] if isinstance(row, dict)]
    return []


def package_from_legacy_json(data: dict[str, Any]) -> TransferPackage:
    """Adapt 2026-04-export-v2 (or flat export) into transfer package domains."""
    meta = data.get("meta") if isinstance(data.get("meta"), dict) else {}
    domains: dict[str, list[dict[str, Any]]] = {
        "companies": _normalize_domain_rows(data.get("companies")),
        "subcompanies": _normalize_domain_rows(data.get("subcompanies")),
        "workers": _normalize_domain_rows(data.get("workers")),
        "access_logs": _normalize_domain_rows(data.get("accessLogs") or data.get("access_logs")),
        "invoices": _normalize_domain_rows(data.get("invoices")),
        "contract_templates": _normalize_domain_rows(data.get("contractTemplates") or data.get("contract_templates")),
        "employment_contracts": _normalize_domain_rows(
            data.get("employmentContracts") or data.get("employment_contracts")
        ),
        "worker_documents": _normalize_domain_rows(data.get("workerDocuments") or data.get("worker_documents")),
        "deployment_days": _normalize_domain_rows(data.get("deploymentDays") or data.get("deployment_days")),
        "leave_requests": _normalize_domain_rows(data.get("leaveRequests") or data.get("leave_requests")),
    }
    # Embedded base64 files (optional in enhanced JSON).
    files: dict[str, bytes] = {}
    embedded = data.get("files") if isinstance(data.get("files"), dict) else {}
    for rel, payload in embedded.items():
        if not isinstance(payload, str) or not payload.strip():
            continue
        try:
            import base64

            raw = payload
            if "," in raw and raw.strip().lower().startswith("data:"):
                raw = raw.split(",", 1)[1]
            files[str(rel).replace("\\", "/").lstrip("/")] = base64.b64decode(raw)
        except Exception:
            continue

    counts = {name: len(rows) for name, rows in domains.items() if rows}
    manifest = {
        "schemaVersion": str(meta.get("schemaVersion") or SCHEMA_VERSION),
        "companyId": meta.get("companyId") or meta.get("company_id") or "",
        "domains": list(counts.keys()),
        "counts": counts,
        "legacy": True,
    }
    return TransferPackage(
        schema_version=str(manifest["schemaVersion"]),
        manifest=manifest,
        domains={k: v for k, v in domains.items() if v},
        files=files,
        source_format="json",
    )


def package_from_transfer_json(data: dict[str, Any]) -> TransferPackage:
    """Native transfer-v1 JSON (domains map + optional embedded files)."""
    manifest = data.get("manifest") if isinstance(data.get("manifest"), dict) else {}
    if not manifest:
        manifest = {
            "schemaVersion": data.get("schemaVersion") or SCHEMA_VERSION,
            "companyId": data.get("companyId") or data.get("company_id") or "",
        }
    domain_blob = data.get("domains") if isinstance(data.get("domains"), dict) else {}
    domains: dict[str, list[dict[str, Any]]] = {}
    for name in PHASE_A_DOMAINS:
        rows = _normalize_domain_rows(domain_blob.get(name) if domain_blob else data.get(name))
        if rows:
            domains[name] = rows
    # Also accept camelCase top-level keys via legacy adapter merge.
    if not domains:
        return package_from_legacy_json(data)

    files: dict[str, bytes] = {}
    embedded = data.get("files") if isinstance(data.get("files"), dict) else {}
    for rel, payload in embedded.items():
        if isinstance(payload, (bytes, bytearray)):
            files[str(rel).replace("\\", "/").lstrip("/")] = bytes(payload)
            continue
        if not isinstance(payload, str):
            continue
        try:
            import base64

            raw = payload
            if "," in raw and raw.strip().lower().startswith("data:"):
                raw = raw.split(",", 1)[1]
            files[str(rel).replace("\\", "/").lstrip("/")] = base64.b64decode(raw)
        except Exception:
            continue

    manifest = dict(manifest)
    manifest.setdefault("schemaVersion", SCHEMA_VERSION)
    manifest["counts"] = {k: len(v) for k, v in domains.items()}
    manifest["domains"] = list(domains.keys())
    return TransferPackage(
        schema_version=str(manifest.get("schemaVersion") or SCHEMA_VERSION),
        manifest=manifest,
        domains=domains,
        files=files,
        source_format="json",
    )


def package_from_zip(blob: bytes) -> TransferPackage:
    checksums: dict[str, str] = {}
    domains: dict[str, list[dict[str, Any]]] = {}
    files: dict[str, bytes] = {}
    manifest: dict[str, Any] = {}

    with zipfile.ZipFile(io.BytesIO(blob), "r") as zf:
        names = set(zf.namelist())
        if "checksums.sha256" in names:
            for line in zf.read("checksums.sha256").decode("utf-8", errors="replace").splitlines():
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                parts = line.split()
                if len(parts) >= 2:
                    checksums[parts[-1].lstrip("*")] = parts[0].lower()

        if "manifest.json" in names:
            manifest = _load_json_bytes(zf.read("manifest.json"))
            if not isinstance(manifest, dict):
                raise ValueError("invalid_manifest")

        for name in PHASE_A_DOMAINS:
            path = f"domains/{name}.json"
            if path not in names:
                continue
            payload = _load_json_bytes(zf.read(path))
            rows = _normalize_domain_rows(payload)
            if rows:
                domains[name] = rows

        for info in zf.infolist():
            if info.is_dir():
                continue
            rel = info.filename.replace("\\", "/")
            if not rel.startswith("files/"):
                continue
            key = rel[len("files/") :]
            if not key or key.endswith("/"):
                continue
            files[key] = zf.read(info)

        # Verify checksums when present.
        for rel, expected in checksums.items():
            if rel in {"manifest.json", "checksums.sha256"}:
                continue
            if rel.startswith("domains/"):
                data = zf.read(rel) if rel in names else b""
            elif rel.startswith("files/"):
                data = files.get(rel[len("files/") :], b"")
            else:
                data = zf.read(rel) if rel in names else b""
            if data and sha256_bytes(data) != expected.lower():
                raise ValueError(f"checksum_mismatch:{rel}")

    if not manifest:
        manifest = {
            "schemaVersion": SCHEMA_VERSION,
            "domains": list(domains.keys()),
            "counts": {k: len(v) for k, v in domains.items()},
        }
    else:
        manifest = dict(manifest)
        manifest.setdefault("counts", {k: len(v) for k, v in domains.items()})
        manifest.setdefault("domains", list(domains.keys()))

    return TransferPackage(
        schema_version=str(manifest.get("schemaVersion") or SCHEMA_VERSION),
        manifest=manifest,
        domains=domains,
        files=files,
        checksums=checksums,
        source_format="zip",
    )


def open_transfer_bytes(blob: bytes, *, filename: str = "") -> TransferPackage:
    name = (filename or "").lower()
    if name.endswith(".zip") or blob[:2] == b"PK":
        return package_from_zip(blob)
    try:
        text = blob.decode("utf-8-sig")
        data = json.loads(text)
    except Exception as exc:
        raise ValueError("invalid_package") from exc
    if not isinstance(data, dict):
        raise ValueError("invalid_package")
    schema = ""
    if isinstance(data.get("manifest"), dict):
        schema = str(data["manifest"].get("schemaVersion") or "")
    if not schema:
        schema = str(data.get("schemaVersion") or "")
    if not schema and isinstance(data.get("meta"), dict):
        schema = str(data["meta"].get("schemaVersion") or "")
    if SCHEMA_VERSION in schema or isinstance(data.get("domains"), dict):
        return package_from_transfer_json(data)
    return package_from_legacy_json(data)


def write_file_under(root: Path, rel: str, data: bytes) -> Path:
    safe = Path(str(rel).replace("\\", "/").lstrip("/"))
    if ".." in safe.parts:
        raise ValueError("unsafe_path")
    target = (root / safe).resolve()
    if not str(target).startswith(str(root.resolve())):
        raise ValueError("unsafe_path")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    return target


def build_transfer_zip(
    *,
    company_id: str,
    domains: dict[str, list[dict[str, Any]]],
    files: dict[str, bytes] | None = None,
    extra_manifest: dict[str, Any] | None = None,
) -> bytes:
    """Build a canonical 2026-08-transfer-v1 ZIP (export + round-trip)."""
    files = files or {}
    present = {k: v for k, v in domains.items() if v}
    manifest: dict[str, Any] = {
        "schemaVersion": SCHEMA_VERSION,
        "companyId": company_id,
        "createdAt": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        ),
        "domains": list(present.keys()),
        "counts": {k: len(v) for k, v in present.items()},
        "fileCount": len(files),
    }
    if extra_manifest:
        manifest.update(extra_manifest)

    checksum_lines: list[str] = []
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        manifest_bytes = json.dumps(manifest, ensure_ascii=False, indent=2).encode("utf-8")
        zf.writestr("manifest.json", manifest_bytes)
        checksum_lines.append(f"{sha256_bytes(manifest_bytes)}  manifest.json")
        for name in PHASE_A_DOMAINS:
            rows = present.get(name)
            if not rows:
                continue
            payload = json.dumps(rows, ensure_ascii=False, indent=2).encode("utf-8")
            rel = f"domains/{name}.json"
            zf.writestr(rel, payload)
            checksum_lines.append(f"{sha256_bytes(payload)}  {rel}")
        for rel, data in sorted(files.items()):
            path = f"files/{rel.replace(chr(92), '/').lstrip('/')}"
            zf.writestr(path, data)
            checksum_lines.append(f"{sha256_bytes(data)}  {path}")
        checksum_blob = ("\n".join(checksum_lines) + "\n").encode("utf-8")
        zf.writestr("checksums.sha256", checksum_blob)
    return buf.getvalue()
