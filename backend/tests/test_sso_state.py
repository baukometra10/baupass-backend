"""SSO state store — in-memory path (no Redis in unit tests)."""
from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from backend.app.platform.auth import sso_state


class SsoStateTest(unittest.TestCase):
    def setUp(self):
        sso_state._MEM.clear()

    def test_oidc_issue_and_consume_once(self):
        state = sso_state.issue_oidc_state()
        self.assertTrue(sso_state.consume_oidc_state(state))
        self.assertFalse(sso_state.consume_oidc_state(state))

    def test_saml_relay_roundtrip(self):
        req_id = "_abc123"
        relay = sso_state.issue_saml_relay(req_id)
        self.assertEqual(sso_state.consume_saml_relay(relay), req_id)
        self.assertIsNone(sso_state.consume_saml_relay(relay))

    @patch.dict(os.environ, {"BAUPASS_SSO_STATE_REDIS": "0", "REDIS_URL": ""}, clear=False)
    def test_redis_disabled_uses_memory(self):
        state = sso_state.issue_oidc_state()
        with patch.object(sso_state, "_redis_client", return_value=None):
            self.assertTrue(sso_state.consume_oidc_state(state))


if __name__ == "__main__":
    unittest.main()
