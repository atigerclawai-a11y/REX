#!/usr/bin/env python3
"""Quick check: fetch the 3 Owner.com emails via IMAP and see their UIDs."""
import imaplib, email, ssl, json

# Try both passwords
for pw in ["uxemapqvhkndgmsv", "ijpu cgfi tufj mqhf"]:
    try:
        ctx = ssl.create_default_context()
        mail = imaplib.IMAP4_SSL("imap.gmail.com", 993, ssl_context=ctx, timeout=15)
        mail.login("atigerclawai@gmail.com", pw)
        mail.select("INBOX")
        
        # Search for owner.com related emails
        for query in ['SUBJECT "Reservations"', 'FROM "mg.owner.com"', 'FROM "olympusbbg"']:
            status, messages = mail.search(None, query)
            if status == "OK" and messages[0]:
                ids = messages[0].split()
                print(f"PW: {pw[:8]}... QUERY: {query} -> {len(ids)} messages, last 3: {ids[-3:]}")
                
                # Fetch last 3
                for mid in ids[-3:]:
                    status, data = mail.fetch(mid, "(BODY.PEEK[HEADER.FIELDS (From Subject Date UID)])")
                    if status == "OK" and data[0]:
                        raw = data[0][1]
                        print(f"  UID {mid.decode()}: {raw[:200]}")
        mail.logout()
        break
    except Exception as e:
        print(f"PW {pw[:8]}... failed: {e}")
