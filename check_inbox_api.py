#!/usr/bin/env python3
"""Check documents inbox via API"""

import urllib.request
import json

# Prüfe die aktuellen Mails im UI-Inbox
try:
    req = urllib.request.Request(
        "https://baupass-app.up.railway.app/api/documents/inbox",
        headers={
            "Authorization": "Bearer YOUR_AUTH_TOKEN_HERE"  # Need to set this
        }
    )
    
    # Ohne Token wird das 401, aber das ist OK für diesen Debug
    print("[*] Checking /api/documents/inbox endpoint...")
    print("[*] Note: Need valid auth token to see emails")
    print("[*] But we can check the IMAP poll logs instead...")
    
except Exception as e:
    print(f"[-] Error: {e}")

# Alternative: Check backend logs for IMAP debug output
print("\n[*] Check Railway logs for [IMAP DEBUG] messages")
print("[*] The debug output should show:")
print("    - IMAP connection parameters")
print("    - SEARCH results and message count")
print("    - Any errors during poll_imap_inbox()")
