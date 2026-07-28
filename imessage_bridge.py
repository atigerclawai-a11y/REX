#!/usr/bin/env python3
"""Rexxie iMessage Bridge — forwards iMessages to local chat API and responds."""
import subprocess, json, time, os, requests

LOCAL_API = "http://localhost:8420/chat"
CHAT_ID = "5587703834"
POLL_INTERVAL = 3  # seconds
STATE_FILE = os.path.expanduser("~/Desktop/REX/.imessage_bridge_state.json")

def load_state():
    try: return json.load(open(STATE_FILE))
    except: return {"last_id": 0}

def save_state(state):
    json.dump(state, open(STATE_FILE, "w"))

def get_new_messages(last_id):
    """Poll Messages.app via AppleScript for new messages from Kato."""
    script = '''
    tell application "Messages"
        set output to ""
        repeat with msg in (get every message)
            set mId to id of msg
            if mId > %d then
                set senderName to ""
                try
                    set senderHandle to get handle of buddy of msg
                    if senderHandle is "5587703834" or (text of senderHandle contains "atigerclawai") then
                        set output to output & mId & "|||" & (content of msg as string) & "\\n"
                    end if
                end try
            end if
        end repeat
        return output
    end tell
    ''' % last_id
    try:
        result = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=10)
        return result.stdout.strip()
    except:
        return ""

def send_imessage(number, text):
    """Send an iMessage via AppleScript."""
    text_escaped = text.replace('"', '\\"').replace('\n', '\\n')
    script = f'''
    tell application "Messages"
        set targetBuddy to buddy "{number}"
        send "{text_escaped}" to targetBuddy
    end tell
    '''
    try:
        subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=10)
        return True
    except:
        return False

def chat_via_api(text):
    """Send to local Rexxie API."""
    try:
        r = requests.post(LOCAL_API, json={"text": text, "history": []}, timeout=60)
        return r.json().get("reply", "")
    except:
        return ""

def main():
    print("Rexxie iMessage Bridge — forwarding messages to local API")
    state = load_state()
    print(f"Starting from message ID: {state['last_id']}")
    
    while True:
        new = get_new_messages(state["last_id"])
        for line in new.strip().split("\n"):
            if "|||" not in line:
                continue
            parts = line.split("|||", 1)
            msg_id = int(parts[0])
            text = parts[1]
            
            print(f"[{msg_id}] Received: {text[:80]}")
            reply = chat_via_api(text)
            if reply:
                # Send via iMessage back — but only to known numbers
                # For now, we print the reply and could send via API
                print(f"[{msg_id}] Reply: {reply[:80]}")
                # Uncomment to actually send via iMessage:
                # send_imessage("+15587703834", reply)
            
            if msg_id > state["last_id"]:
                state["last_id"] = msg_id
        
        save_state(state)
        time.sleep(POLL_INTERVAL)

if __name__ == "__main__":
    print("NOTE: iMessage bridge requires Messages.app to be open.")
    print("This polls via AppleScript every 3 seconds.")
    print("To send responses: uncomment the send_imessage line in the code.")
    main()
