"""
Optional Sentry error tracking (set SENTRY_DSN).
"""
from __future__ import annotations

import logging
import os

from flask import Flask

logger = logging.getLogger("baupass.sentry")


def init_sentry(flask_app: Flask) -> None:
    dsn = os.getenv("SENTRY_DSN", "").strip()
    if not dsn:
        return
    try:
        import sentry_sdk
        from sentry_sdk.integrations.flask import FlaskIntegration

        sentry_sdk.init(
            dsn=dsn,
            integrations=[FlaskIntegration()],
            environment=os.getenv("SENTRY_ENVIRONMENT", os.getenv("BAUPASS_ENV", "production")),
            traces_sample_rate=float(os.getenv("SENTRY_TRACES_SAMPLE_RATE", "0.1")),
            send_default_pii=False,
        )
        logger.info("Sentry initialized")
    except ImportError:
        logger.warning("sentry-sdk not installed; pip install sentry-sdk")
