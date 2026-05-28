"""Native push delivery (FCM legacy HTTP API)."""

from .fcm import send_fcm_notification

__all__ = ["send_fcm_notification"]
