#!/usr/bin/env python3
"""CC_cdp_eval.py — evaluate JS in the headless Chrome (port 9225) via CDP.
Usage: CC_cdp_eval.py '<js expression>' [--url https://...]
Drives the SEPARATE headless instance (/tmp/chrome-fresh, port 9225) so we
never compete with carecenta_change_detector.py on the shared Chrome.
"""
import asyncio, json, sys, urllib.request

import websockets

CDP = "http://localhost:9225"


def get_target():
    with urllib.request.urlopen(f"{CDP}/json") as r:
        targets = json.load(r)
    for t in targets:
        if t.get("type") == "page":
            return t
    raise SystemExit("no page target on 9225")


async def main(expr, nav_url=None, wait=4.0):
    target = get_target()
    ws_url = target["webSocketDebuggerUrl"]
    async with websockets.connect(ws_url, max_size=64 * 1024 * 1024) as ws:
        mid = 0

        async def call(method, params=None):
            nonlocal mid
            mid += 1
            await ws.send(json.dumps({"id": mid, "method": method, "params": params or {}}))
            while True:
                msg = json.loads(await ws.recv())
                if msg.get("id") == mid:
                    return msg

        if nav_url:
            await call("Page.navigate", {"url": nav_url})
            await asyncio.sleep(wait)
        # give the page a moment to settle
        await asyncio.sleep(0.5)
        res = await call("Runtime.evaluate", {
            "expression": expr,
            "returnByValue": True,
            "awaitPromise": True,
        })
        r = res.get("result", {}).get("result", {})
        if "value" in r:
            print(json.dumps(r["value"], ensure_ascii=False)[:200000])
        elif "description" in r:
            print(r["description"][:200000])
        else:
            print(json.dumps(res)[:200000])


if __name__ == "__main__":
    expr = sys.argv[1]
    nav = None
    wait = 4.0
    if "--url" in sys.argv:
        i = sys.argv.index("--url")
        nav = sys.argv[i + 1]
    if "--wait" in sys.argv:
        i = sys.argv.index("--wait")
        wait = float(sys.argv[i + 1])
    asyncio.run(main(expr, nav, wait))
