#!/usr/bin/env python3
"""Owner.com dashboard scraper via Playwright. Login → Forms tab → thread detail extraction.

Usage: python3 scripts/owner_scrape.py > /tmp/owner_scrape_output.json 2>/tmp/owner_scrape_log.txt
Output: JSON with 'new_inquiries' array of {party_name, reservation_date, reservation_time, party_size, phone, notes}
"""
import asyncio, json, re, sys
from datetime import datetime

CREDENTIALS = {"email": "olympusbbg@gmail.com", "password": "Olympus12345$"}
INBOX_URL = "https://app.owner.com/2aQ7PB6C7xTK/inbox"  # simpler URL; app auto-redirects to location-specific path
SIGNIN_URL = "https://app.owner.com/auth/sign-in-email"


async def main():
    result = {"new_inquiries": [], "raw_threads": [], "error": None}

    try:
        from playwright.async_api import async_playwright
    except ImportError:
        result["error"] = "playwright not installed; run: python3 -m playwright install chromium"
        print(json.dumps(result))
        return

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()

        try:
            # ── 1. Sign in ──────────────────────────────────────────────
            await page.goto(SIGNIN_URL, wait_until="networkidle", timeout=30000)
            await page.wait_for_timeout(3000)

            page_text = await page.evaluate("() => document.body.innerText || ''")

            # Handle phone-number login redirect
            if "Use email and password instead" in page_text:
                await page.evaluate('''() => {
                    for (let el of document.querySelectorAll('*')) {
                        if (el.textContent && el.textContent.includes('Use email and password instead')) {
                            el.click(); return;
                        }
                    }
                }''')
                await page.wait_for_timeout(3000)

            page_text = await page.evaluate("() => document.body.innerText || ''")

            if CREDENTIALS["email"] not in page_text and ("Sign in" in page_text or "Next" in page_text):
                # Fill email (try CSS selector first, fall back to JS)
                try:
                    await page.fill('input[type="email"]', CREDENTIALS["email"])
                except Exception:
                    await page.evaluate(
                        f'''() => {{ for (let inp of document.querySelectorAll('input')) {{
                            if (inp.type === 'email' || inp.name?.includes('email') || inp.placeholder?.toLowerCase().includes('email')) {{
                                inp.value = "{CREDENTIALS['email']}"; inp.dispatchEvent(new Event('input', {{bubbles: true}})); return;
                            }}
                        }}}}'''
                    )

                try:
                    await page.fill('input[type="password"]', CREDENTIALS["password"])
                except Exception:
                    await page.evaluate(
                        f'''() => {{ for (let inp of document.querySelectorAll('input')) {{
                            if (inp.type === 'password') {{ inp.value = "{CREDENTIALS['password']}"; inp.dispatchEvent(new Event('input', {{bubbles: true}})); return; }}
                        }}}}'''
                    )

                await page.wait_for_timeout(500)

                clicked = await page.evaluate('''() => {
                    for (let b of document.querySelectorAll('button')) {
                        const t = (b.textContent || '').trim().toLowerCase();
                        if (t === 'next' || t === 'sign in' || t === 'log in') { b.click(); return true; }
                    }
                    return false;
                }''')
                if not clicked:
                    await page.keyboard.press("Enter")

                await page.wait_for_timeout(8000)

            # ── 2. Navigate to inbox ────────────────────────────────────
            await page.goto(INBOX_URL, wait_until="networkidle", timeout=30000)
            await page.wait_for_timeout(5000)
            page_text = await page.evaluate("() => document.body.innerText || ''")

            # If inbox isn't showing, try clicking Inbox sidebar link
            if "Reservation for" not in page_text and "Forms" not in page_text:
                await page.evaluate('''() => {
                    for (let el of document.querySelectorAll('*')) {
                        if ((el.textContent || '').trim() === 'Inbox') { el.click(); return; }
                    }
                }''')
                await page.wait_for_timeout(5000)
                page_text = await page.evaluate("() => document.body.innerText || ''")

            # Click Forms tab
            if "Forms" in page_text and "Reservation for" not in page_text:
                await page.evaluate('''() => {
                    for (let el of document.querySelectorAll('*')) {
                        const t = (el.textContent || '').trim();
                        if (t.match(/^Forms\\d+$/) || t.match(/^Forms\\s*\\d+$/)) { el.click(); return; }
                    }
                    for (let el of document.querySelectorAll('*')) {
                        const t = (el.textContent || '').trim();
                        if (t.startsWith('Forms') && t.length < 20) { el.click(); return; }
                    }
                }''')
                await page.wait_for_timeout(8000)

            # ── 3. Find thread buttons ──────────────────────────────────
            thread_btns = json.loads(await page.evaluate('''() => {
                var results = [];
                document.querySelectorAll('button').forEach(function(btn, i) {
                    var tid = btn.getAttribute('data-testid') || '';
                    if (tid.indexOf('inbox-thread-') >= 0 && tid.indexOf('-row') >= 0) {
                        results.push({idx: i, testid: tid, text: (btn.textContent || '').substring(0, 200)});
                    }
                });
                return JSON.stringify(results);
            }'''))

            # ── 4. Click each thread and extract detail ─────────────────
            for btn_info in thread_btns[:15]:  # cap at 15 threads
                btn_idx = btn_info["idx"]

                # MouseEvent dispatch (most reliable click method)
                await page.evaluate(f'''(function() {{
                    var b = document.querySelectorAll('button')[{btn_idx}];
                    if (b) {{
                        b.dispatchEvent(new MouseEvent('mousedown', {{bubbles: true}}));
                        b.dispatchEvent(new MouseEvent('mouseup', {{bubbles: true}}));
                        b.dispatchEvent(new MouseEvent('click', {{bubbles: true}}));
                    }}
                }})()''')
                await page.wait_for_timeout(2500)

                detail_text = await page.evaluate("() => document.body.innerText || ''")

                name = find_guest_name(detail_text)
                detail = parse_detail(detail_text)

                if not detail["date"] or not detail["party_size"]:
                    continue  # skip incomplete entries

                if not name:
                    name = f"Guest (Owner.com #{len(result['new_inquiries']) + 1})"

                entry = {
                    "party_name": name,
                    "reservation_date": detail["date"],
                    "reservation_time": norm_time(detail["time"] or ""),
                    "party_size": detail["party_size"],
                    "phone": "",
                    "status": "pending",
                    "source": "owner.com",
                    "notes": detail["notes"],
                }
                result["new_inquiries"].append(entry)

            # ── 5. Deduplicate within scrape batch ─────────────────────
            # Adjacent threads can be the same reservation with different
            # placeholder names (#4 / #5 both 11pax at 3PM, identical notes).
            # Dedup on (date, time, size, notes) for placeholders,
            # (name_lower, date, time) for named entries.
            deduped = []
            seen = set()
            for e in result["new_inquiries"]:
                pn = e["party_name"]
                if pn.startswith("Guest (Owner.com"):
                    key = (e["reservation_date"], e["reservation_time"],
                           e["party_size"], e.get("notes", ""))
                else:
                    key = (pn.lower(), e["reservation_date"],
                           e["reservation_time"])
                if key not in seen:
                    seen.add(key)
                    deduped.append(e)
            result["new_inquiries"] = deduped

        except Exception as exc:
            result["error"] = str(exc)
            import traceback; traceback.print_exc(file=sys.stderr)
        finally:
            await browser.close()

    print(json.dumps(result, indent=2))


# ── Helpers ──────────────────────────────────────────────────────────────

def norm_time(t):
    """Strip leading zero from hour: '02:05 PM' → '2:05 PM'."""
    if not t:
        return ""
    return re.sub(r"^0(\d:)", r"\1", t)


def find_guest_name(text):
    """Walk backwards from 'Date and time' line to find guest name."""
    lines = text.split("\n")
    dt_idx = next((i for i, ln in enumerate(lines) if ln.strip() == "Date and time"), None)
    if dt_idx is None:
        return ""

    skip = {
        "Date and time", "Number of people", "Additional details or special instructions",
        "Customer", "Call guest", "Reservations", "Inbox", "Home", "Orders", "Menu",
        "Support", "Reviews", "Forms", "Boardwalk Beer Garden", "See Submission",
        "Coupons", "Print Shop", "More", "Customers", "Dashboard", "Marketing",
        "Online Ordering", "Website", "Settings", "Messages", "Payments", "Reports",
        "Staff", "Locations", "Brand", "Reservation", "Message", "Guest", "New message",
        "Unread", "Today", "Yesterday", "This week", "Last week", "Older",
        "Send message", "Reply", "Mark as read", "Archive", "Delete", "Assign",
        "Edit", "View", "Actions", "Details", "Called", "Reservation for",
    }

    for j in range(dt_idx - 1, max(0, dt_idx - 15), -1):
        candidate = lines[j].strip()
        if not candidate or candidate in skip or len(candidate) <= 1:
            continue
        # Skip timestamp lines (e.g. "1:48 PM", "12:54 PM")
        if re.match(r"^\d{1,2}:\d{2}\s*[AP]M$", candidate):
            continue
        # Also skip pure digits (party sizes, counts)
        if re.match(r"^\d+$", candidate):
            continue
        if re.match(r"^[A-Z][a-zA-Z\s.'\-]+$", candidate):
            return candidate
    return ""


def parse_detail(text):
    """Extract date, time, party_size, notes from detail panel body text."""
    result = {"date": "", "time": "", "party_size": 0, "notes": ""}

    dt_section = re.search(r"Date and time\n(.+)", text)
    if dt_section:
        for fmt in ("%b %d, %Y, %I:%M %p", "%B %d, %Y, %I:%M %p"):
            try:
                dt = datetime.strptime(dt_section.group(1).strip(), fmt)
                result["date"] = dt.strftime("%Y-%m-%d")
                result["time"] = dt.strftime("%I:%M %p")
                result["time"] = norm_time(result["time"])
                break
            except ValueError:
                continue

    ppl = re.search(r"Number of people\n(\d+)", text)
    if ppl:
        result["party_size"] = int(ppl.group(1))

    notes = re.search(
        r"Additional details or special instructions\n(.+?)"
        r"(?:\n\d+\nCustomer|\nSee Submission|\n---|\nCalled|\nCustomer)",
        text, re.DOTALL,
    )
    if notes:
        n = re.sub(r"\s+", " ", notes.group(1)).strip()
        if n not in ("", "-", "Customer"):
            result["notes"] = n

    return result


if __name__ == "__main__":
    asyncio.run(main())
