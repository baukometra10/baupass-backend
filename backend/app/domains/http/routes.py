"""
HTTP surface — HTML entrypoints and static assets.

Registered without /api prefix. Catch-all static route must remain last.
"""
from __future__ import annotations

from flask import Blueprint, Flask

from .._routes import mount_rules_once, register_blueprint_once

http_bp = Blueprint("http_static", __name__)


def _register_http_routes() -> None:
    from backend.server import (
        admin_v2_entry,
        enterprise_hub_entry,
        favicon_ico,
        phone_test_page,
        review_page,
        root,
        static_proxy,
        worker_entry_redirect,
        worker_icon_png,
        worker_icon_svg,
        worker_join_config_public,
        android_assetlinks_json,
        apple_app_site_association,
    )

    mount_rules_once(
        "http_static",
        http_bp,
        (
            ("/", root, ("GET",)),
            ("/favicon.ico", favicon_ico, ("GET",)),
            ("/enterprise", enterprise_hub_entry, ("GET",)),
            ("/enterprise/", enterprise_hub_entry, ("GET",)),
            ("/admin", admin_v2_entry, ("GET",)),
            ("/admin/", admin_v2_entry, ("GET",)),
            ("/worker.html", worker_entry_redirect, ("GET",)),
            ("/review.html", review_page, ("GET",)),
            ("/worker-join-config.json", worker_join_config_public, ("GET",)),
            ("/.well-known/assetlinks.json", android_assetlinks_json, ("GET",)),
            ("/.well-known/apple-app-site-association", apple_app_site_association, ("GET",)),
            ("/apple-app-site-association", apple_app_site_association, ("GET",)),
            ("/phone-test", phone_test_page, ("GET",)),
            ("/worker-icon-<int:icon_size>.svg", worker_icon_svg, ("GET",)),
            ("/worker-icon-<int:icon_size>.png", worker_icon_png, ("GET",)),
            ("/<path:path>", static_proxy, ("GET",)),
        ),
    )


def register_http_blueprint(flask_app: Flask) -> None:
    _register_http_routes()
    register_blueprint_once(flask_app, http_bp)
    print("[baupass] domain/http: SPA + static (registered last)", flush=True)
