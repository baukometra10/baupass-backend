"""Tests for optional field encryption."""
from __future__ import annotations

import os
import unittest

from backend.app.platform.security import field_encryption as fe


class FieldEncryptionTests(unittest.TestCase):
    def setUp(self):
        self._prev = os.environ.get("BAUPASS_FIELD_ENCRYPTION_KEY")
        fe._fernet = False

    def tearDown(self):
        fe._fernet = False
        if self._prev is None:
            os.environ.pop("BAUPASS_FIELD_ENCRYPTION_KEY", None)
        else:
            os.environ["BAUPASS_FIELD_ENCRYPTION_KEY"] = self._prev

    def test_plaintext_when_key_missing(self):
        os.environ.pop("BAUPASS_FIELD_ENCRYPTION_KEY", None)
        self.assertEqual(fe.maybe_encrypt_field("hello"), "hello")
        self.assertEqual(fe.maybe_decrypt_field("hello"), "hello")

    def test_roundtrip_with_key(self):
        os.environ["BAUPASS_FIELD_ENCRYPTION_KEY"] = "unit-test-secret-key"
        encrypted = fe.maybe_encrypt_field("Geheime Nachricht")
        self.assertTrue(encrypted.startswith("enc:v1:"))
        self.assertEqual(fe.maybe_decrypt_field(encrypted), "Geheime Nachricht")


if __name__ == "__main__":
    unittest.main()
