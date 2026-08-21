# Optional SAML hardening with SignXML

When `signxml` is installed and `BAUPASS_SAML_USE_SIGNXML=1`, assertion
verification runs through SignXML after the built-in RSA-SHA256 checks.

```bash
pip install "signxml>=4.0.3"
# Railway / .env
BAUPASS_SAML_USE_SIGNXML=1
```

Without the package the platform keeps the hardened stdlib verifier.
