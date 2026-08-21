# Optional SAML hardening with SignXML

When `signxml` is installed and `BAUPASS_SAML_USE_SIGNXML=1`, assertion
verification runs through SignXML after the built-in RSA-SHA256 checks.

```bash
pip install -r backend/requirements-optional.txt
# Railway / .env — only after the package is in the image
BAUPASS_SAML_USE_SIGNXML=1
```

Without the package the platform keeps the hardened stdlib verifier.
If the env flag is set but SignXML is missing, verification fails closed
(`signxml_not_installed`) so production SAML cannot silently skip the stronger path.
