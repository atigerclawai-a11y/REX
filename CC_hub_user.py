#!/usr/bin/env python3
"""
CC_hub_user.py — manage Tiger Claw Hub accounts (for onboarding a partner)
==========================================================================
Thin admin client for the Hub's built-in RBAC API. YOU run it, YOU set the
password and role — nothing is granted automatically.

    python3 CC_hub_user.py list                 # list users
    python3 CC_hub_user.py roles                # show roles + permissions
    python3 CC_hub_user.py add                  # interactively add a user
    python3 CC_hub_user.py demo [--hours N]     # add an N-hour demo account (default 24h, auto-expires)
    python3 CC_hub_user.py passwd <username>    # reset a user's password

Talks to the LOCAL hub (127.0.0.1:9000). You authenticate as an admin
(kato) first; the partner's credentials are whatever you type.
"""

import getpass
import json
import sys
import urllib.request

HUB = "http://127.0.0.1:9000"
VALID_ROLES_HINT = "admin (full) · operator (dashboard+attendance+reports) · viewer (dashboard only)"


def _req(method, path, cookie=None, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(f"{HUB}{path}", data=data, method=method,
                                 headers={"Content-Type": "application/json"})
    if cookie:
        req.add_header("Cookie", cookie)
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.getcode(), json.loads(r.read().decode() or "{}"), r.headers.get("Set-Cookie", "")
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode() or "{}"), ""
        except Exception:
            return e.code, {"detail": f"HTTP {e.code}"}, ""
    except Exception as e:
        return 0, {"detail": str(e)}, ""


def admin_login():
    user = input("Admin username [kato]: ").strip() or "kato"
    pw = getpass.getpass("Admin password: ")
    code, body, setcookie = _req("POST", "/api/hub/auth/login",
                                 body={"username": user, "password": pw})
    if code != 200 or not body.get("ok"):
        print(f"❌ login failed: {body.get('detail', body)}")
        sys.exit(1)
    cookie = setcookie.split(";")[0] if setcookie else ""
    if not cookie:
        print("❌ no session cookie returned"); sys.exit(1)
    print(f"✅ authenticated as {user}")
    return cookie


def cmd_list():
    cookie = admin_login()
    code, body, _ = _req("GET", "/api/admin/users", cookie=cookie)
    if code != 200:
        print(f"❌ {body.get('detail')}"); return
    print(f"\n{body.get('count', 0)} user(s):")
    for u in body.get("users", []):
        print(f"  • {u['username']:16} role={u['role']:10} perms={u.get('permissions')}")


def cmd_roles():
    cookie = admin_login()
    code, body, _ = _req("GET", "/api/admin/roles", cookie=cookie)
    if code != 200:
        print(f"❌ {body.get('detail')}"); return
    print("\nroles:")
    for r, v in (body.get("roles") or body).items() if isinstance(body, dict) else []:
        print(f"  • {r}: {v.get('permissions') if isinstance(v, dict) else v}")


def cmd_add():
    print(f"Add a Hub account.  Roles: {VALID_ROLES_HINT}")
    cookie = admin_login()
    username = input("New username: ").strip()
    role = input("Role [viewer]: ").strip() or "viewer"
    pw = getpass.getpass(f"Password for {username}: ")
    pw2 = getpass.getpass("Confirm password: ")
    if pw != pw2:
        print("❌ passwords do not match"); return
    code, body, _ = _req("POST", "/api/admin/users", cookie=cookie,
                         body={"username": username, "password": pw, "role": role})
    if code == 200 and body.get("ok"):
        print(f"✅ created '{username}' as {body.get('role')}.")
        print(f"   They log in at https://jarvis.hermestigerclaw.com  (username + the password you set)")
    else:
        print(f"❌ {body.get('detail', body)}")


def cmd_demo(hours=24):
    print(f"Create a {hours:g}-HOUR FULL-ACCESS demo account (auto-expires, shows maintenance banner).")
    cookie = admin_login()
    username = input("Demo username (for your partner): ").strip()
    pw = getpass.getpass(f"Password for {username}: ")
    pw2 = getpass.getpass("Confirm password: ")
    if pw != pw2:
        print("❌ passwords do not match"); return
    # role=viewer (non-admin) → read-only + blocked from personal/sensitive namespaces
    # by the Hub's demo_guard. They still SEE all business dashboards.
    code, body, _ = _req("POST", "/api/admin/users", cookie=cookie,
                         body={"username": username, "password": pw, "role": "viewer", "demo_hours": hours})
    if code == 200 and body.get("ok"):
        print(f"\n✅ {hours:g}h demo account '{username}' created (read-only preview, no personal data).")
        print(f"   Expires: {body.get('expires_at')}")
        print(f"   Send your partner:")
        print(f"     URL:      https://jarvis.hermestigerclaw.com")
        print(f"     Username: {username}")
        print(f"     Password: (the one you just set)")
        print(f"   He'll see a maintenance banner + live countdown. Access auto-revokes at expiry.")
    else:
        print(f"❌ {body.get('detail', body)}")


def cmd_passwd(username):
    cookie = admin_login()
    pw = getpass.getpass(f"New password for {username}: ")
    code, body, _ = _req("PUT", f"/api/admin/users/{username}", cookie=cookie,
                         body={"password": pw})
    print(f"{'✅ updated' if code == 200 else '❌ ' + str(body.get('detail'))}")


def main():
    if len(sys.argv) < 2:
        print(__doc__); return
    cmd = sys.argv[1]
    if cmd == "list":
        cmd_list()
    elif cmd == "roles":
        cmd_roles()
    elif cmd == "add":
        cmd_add()
    elif cmd == "demo":
        hours = 24
        if "--hours" in sys.argv:
            try:
                hours = float(sys.argv[sys.argv.index("--hours") + 1])
            except (IndexError, ValueError):
                print("❌ --hours needs a number, e.g. --hours 6"); return
        cmd_demo(hours)
    elif cmd == "passwd" and len(sys.argv) > 2:
        cmd_passwd(sys.argv[2])
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
