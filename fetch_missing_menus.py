import json, base64, os, sys
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
TOKEN_PATH = os.path.join(SCRIPT_DIR, 'gmail_token.json')
DEST = os.path.join(SCRIPT_DIR, 'signins')

token = json.load(open(TOKEN_PATH))
creds = Credentials(
    token=token['token'],
    refresh_token=token['refresh_token'],
    token_uri=token['token_uri'],
    client_id=token['client_id'],
    client_secret=token['client_secret'],
    scopes=token['scopes']
)
if creds.expired:
    creds.refresh(Request())
    token['token'] = creds.token
    json.dump(token, open(TOKEN_PATH, 'w'))
    print("Token refreshed.")

service = build('gmail', 'v1', credentials=creds)

downloads = [
    ('19de6671e6a1f4a5', 'ANGjdJ-l1lal9huWeqkmsCPd7XfavM60YbwhtN6QcBoQvGUqeW0a1huGrgT7jrVJZXxNoZnBQTl0UPc7SFoE-fy3Wf7w0kC_B7eNPcBWg6PF96JPOiHdcuNdw9eH03RiAJdjKwPev9rcl5a6yvkvjm8J-sZ6j6OXpytF0XkPuVsWjyAuim1NdS_XibyggSY_RxMjhgc8cGVnTJqdRXDqdyUqQPsoEib8K_WnUcv0SHWylhs-nUEyqO4XcQPmPS4bglAEICOsuFKx2XBXyq8saELQjuVt0kcjIMC66ooUCGHzTR4pdX4wllq6KvubU9JTI6b3a9C9-aTMJCH1CTZ0A9zRHL6UQ3RYjhy585PBGhbnvWsVJ4GSqO9_GDZNrr9ut1Esq9umBPMMc7kw_cctO9RgyGem3uf5oIQcWoMObw', 'scan_20260429_1051.pdf'),
    ('19de663d6150d19c', 'ANGjdJ-duFclJUz5I130HQNAjnSFf3RuZg8iLO9VHssuaMvTjINq93E24Eu4Bfm1eq3ECm6jmxFQtQD83yxJYVUMEw-QZjpu65oOWdzXYH3O7_UY5W2bQUVFbx08WxwrJXax2H5ZaC6JMGTMCEnFSdBRXMnCt4GQAY1gNXp-Fhu7zmt4x17PTbzOHD-jpGG0F1jMiteSaGnQCgATVv6sNe2CPFY7ArJ73etCoz47AWGN_wqsndQeuhb0JlolyvFyXb3Gw2PxHYEMZqGNlT1Hu70Dq_TTFl-wb69qJeoGpbImzKHgyUvU7grceQrM9H-GzbIIBwudnhufFKK7hOSIrReldo84RQURBG9MdbggN8UH9uqiWOsN0zSHsiiWPVG1a0AldogCXQPJU6jVdA2hFlj_NFCBaTjIqwq5_Os-Ng', 'scan_20260430_1041.pdf'),
    ('19de669e98ec3af6', 'ANGjdJ9GVBpk3pa9voslQPboiAAzVZLJ8cEJyRIcMwrbIklMqm4yYeJMYVR-GG72kAQX1a7CIsBxLoimtA52x-NPK3Q7RGPLAVGXQCF5Xw3403p7be_dvS-UdmyEhREXUWrHtr-VShDYqFj4jU6mkFjSTrnckLjEVcRplDEdo-wzGcgd-A6vXBNwCGHokwyXZc6ve38VO-Hf3FzbuYIDtGJtFIcj6vBqGQ8Q4O_Fc0_WqZDgSCKGGgK3N-M0-00CndvG_khOFaADwVNZXmQf-Oo_WF9Tt4Qr4F1LnXGTl6mSN1bxMVnUsgg2PsdrHXHodh38m-B3RAcmgaToqM4Tx6Q5lMnehHG5a8Mlch6UPRcTrflAGuH3e7ZTI1xLr4Lsxek2FoZnWXvUAcT5t7Ggjf5BpJ4WdcVq4sTX6qxgsQ', 'scan_20260430_1516.pdf'),
]

for msg_id, att_id, filename in downloads:
    path = os.path.join(DEST, filename)
    if os.path.exists(path):
        print(f"Already exists: {filename}")
        continue
    att = service.users().messages().attachments().get(userId='me', messageId=msg_id, id=att_id).execute()
    data = base64.urlsafe_b64decode(att['data'])
    with open(path, 'wb') as f:
        f.write(data)
    print(f"Saved {filename} ({len(data):,} bytes)")

print("Done.")
