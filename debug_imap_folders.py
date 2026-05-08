#!/usr/bin/env python3
"""Debug script to list IMAP folders"""

import imaplib

# GMX IMAP settings
host = "imap.gmx.net"
port = 993
username = "baupass-docs@gmx.de"
password = input(f"Enter IMAP password for {username}: ").strip()

print(f"\n[*] Connecting to {host}:{port}...")
try:
    conn = imaplib.IMAP4_SSL(host, port, timeout=15)
    print("[+] Connected!")
    
    print(f"[*] Logging in as {username}...")
    conn.login(username, password)
    print("[+] Logged in!")
    
    print("\n[*] Listing all folders...")
    status, mailboxes = conn.list()
    
    if status == "OK":
        print(f"[+] Found {len(mailboxes)} folders:")
        for i, mailbox_info in enumerate(mailboxes):
            print(f"  {i+1}. {mailbox_info}")
    else:
        print(f"[-] LIST failed: {status}")
    
    # Try to search in INBOX
    print("\n[*] Searching for ALL messages in INBOX...")
    status, data = conn.select("INBOX", readonly=True)
    if status != "OK":
        print(f"[-] SELECT INBOX failed: {status}")
    else:
        print("[+] INBOX selected")
        status, search_result = conn.search(None, "ALL")
        if status == "OK":
            msg_count = len((search_result[0] or b"").split())
            print(f"[+] Found {msg_count} messages in INBOX")
            if msg_count > 0:
                print(f"    Message IDs: {search_result[0][:100]}..." if len(search_result[0]) > 100 else f"    Message IDs: {search_result[0]}")
        else:
            print(f"[-] SEARCH failed: {status}")
    
    conn.logout()
    print("\n[+] Done!")
    
except Exception as e:
    print(f"[-] Error: {e}")
    import traceback
    traceback.print_exc()
