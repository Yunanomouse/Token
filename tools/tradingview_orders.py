"""Walk through the $40 bot's orders in TradingView, one at a time.

Run on your own computer (Windows, macOS or Linux) with Playwright installed:

    python tradingview_orders.py

What it does
------------
1. Downloads the bot's latest ``live/real/orders.json`` from GitHub.
2. Refuses to go on unless the bot is in ``"mode": "live"`` and the orders
   are from the latest trading day (a missed day is never traded late).
3. Opens TradingView in Chrome for Testing (the same signed-in profile as
   ``open_tradingview.py``) on each order's stock, with a banner saying
   exactly what to do: side, shares, limit price.
4. When you press "Fill shares & price" on the banner, it types the shares
   and the limit price into the order panel and reads them back to check.

What it never does
------------------
It never clicks Buy, Sell or any button of TradingView's, and never presses
Enter.  Choosing the side and pressing the final Buy/Sell is always yours.
It never sees or stores your passwords.
"""

from __future__ import annotations

import csv
import json
import sys
import urllib.request
from datetime import date, datetime
from pathlib import Path

from playwright.sync_api import TimeoutError as PlaywrightTimeout
from playwright.sync_api import sync_playwright

REPO = "Yunanomouse/Token"
BRANCHES = ["claude/canada-tax-system-data-e7jmyx", "claude/day-trading-quantum-programs-7iy790"]
ORDERS_PATH = "live/real/orders.json"
PROFILE = Path.home() / "tradingview-browser-profile"
LOG = Path.home() / "tradingview_orders_log.csv"
MAX_AGE_DAYS = 4

BANNER_JS = """
([title, lines, status]) => {
  let b = document.getElementById('qt-banner');
  if (!b) {
    b = document.createElement('div');
    b.id = 'qt-banner';
    b.style.cssText = 'position:fixed;top:0;left:50%;transform:translateX(-50%);z-index:2147483647;'
      + 'background:#111;color:#fff;font:15px/1.4 system-ui,sans-serif;padding:12px 16px;'
      + 'border:3px solid #f5a623;border-radius:0 0 10px 10px;max-width:640px;box-shadow:0 4px 16px #0008';
    document.documentElement.appendChild(b);
  }
  b.innerHTML = '';
  const h = document.createElement('div'); h.style.cssText = 'font-weight:700;font-size:17px;margin-bottom:6px';
  h.textContent = title; b.appendChild(h);
  for (const l of lines) { const p = document.createElement('div'); p.textContent = l; b.appendChild(p); }
  if (status) { const s = document.createElement('div'); s.style.cssText = 'margin-top:6px;color:#ffd479';
    s.textContent = status; b.appendChild(s); }
  const row = document.createElement('div'); row.style.cssText = 'margin-top:10px;display:flex;gap:8px';
  for (const [label, act] of [['Fill shares & price', 'fill'], ['Next order', 'next'], ['Stop', 'stop']]) {
    const k = document.createElement('button'); k.textContent = label;
    k.style.cssText = 'font:inherit;padding:4px 10px;border-radius:6px;border:0;cursor:pointer;'
      + (act === 'fill' ? 'background:#f5a623;color:#111' : 'background:#444;color:#fff');
    k.onclick = () => { window.__qtAction = act; };
    row.appendChild(k);
  }
  b.appendChild(row);
  window.__qtAction = null;
}
"""


def fetch_orders() -> dict:
    """The newest orders.json across the default and working branches."""
    best = None
    for branch in BRANCHES:
        url = f"https://raw.githubusercontent.com/{REPO}/{branch}/{ORDERS_PATH}"
        try:
            with urllib.request.urlopen(url, timeout=30) as r:
                doc = json.loads(r.read())
        except Exception:
            continue
        if best is None or (doc.get("date") or "") > (best.get("date") or ""):
            best = doc
    if best is None:
        sys.exit("Could not download the bot's orders from GitHub. Has the $40 bot run yet?")
    return best


def check(doc: dict) -> None:
    if doc.get("schema") != 1:
        sys.exit("orders.json is not in a format this helper understands; nothing done.")
    print(f"Bot mode: {doc['mode']}   orders for: {doc['date']}   budget: ${doc['budget']:.2f}")
    for o in doc["orders"]:
        print(f"  {o['side'].upper():4} {o['shares']:g} x {o['ticker']}  limit ${o['limit']:.2f}")
    if doc["mode"] != "live":
        sys.exit("The bot is in PAPER mode: these are for information only. Nothing to place.\n"
                 "To go live, change \"mode\": \"paper\" to \"mode\": \"live\" in live/real/config.json.")
    age = (date.today() - date.fromisoformat(doc["date"])).days
    if age > MAX_AGE_DAYS:
        sys.exit(f"These orders are {age} days old. A missed day is not traded late; nothing done.")
    if not doc["orders"]:
        sys.exit("No orders today. Nothing to place.")


def fill_ticket(page, shares: float, limit: float) -> str:
    """Type shares and limit price into TradingView's order panel; read them back."""
    results = []
    for label, value in (("Shares", f"{shares:g}"), ("Price", f"{limit:.2f}")):
        try:
            box = page.get_by_text(label, exact=True).first.locator("xpath=following::input[1]")
            box.fill(value, timeout=5000)
            got = box.input_value(timeout=2000).replace(",", "")
            ok = abs(float(got) - float(value)) < 1e-9
            results.append(f"{label} {got} {'OK' if ok else 'DIFFERENT, type ' + value + ' by hand'}")
        except Exception:
            results.append(f"{label}: box not found, type {value} by hand")
    return "; ".join(results)


def wait_for_click(page, banner: list) -> str:
    """Wait for a banner button; put the banner back if the page redrew itself."""
    while True:
        try:
            # Waiting through Playwright (not input()) keeps pop-ups and the page working.
            page.wait_for_function("window.__qtAction", timeout=2000)
            return page.evaluate("window.__qtAction")
        except PlaywrightTimeout:
            if not page.evaluate("!!document.getElementById('qt-banner')"):
                page.evaluate(BANNER_JS, banner)


def log(row: list) -> None:
    new = not LOG.exists()
    with LOG.open("a", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        if new:
            w.writerow(["time", "orders_date", "ticker", "side", "shares", "limit", "event"])
        w.writerow([datetime.now().isoformat(timespec="seconds"), *row])


def main() -> None:
    doc = fetch_orders()
    check(doc)
    orders = doc["orders"]
    with sync_playwright() as p:
        browser = p.chromium.launch_persistent_context(
            str(PROFILE), headless=False, no_viewport=True, chromium_sandbox=True,
            ignore_default_args=["--enable-automation"],
            args=["--disable-blink-features=AutomationControlled"])
        page = browser.pages[0] if browser.pages else browser.new_page()
        for n, o in enumerate(orders, 1):
            side = o["side"].upper()
            title = f"Order {n} of {len(orders)}:  {side} {o['shares']:g} share(s) of {o['ticker']}"
            lines = [
                f"1. In the order panel (click Trade if it is closed), check it shows {o['ticker']}.",
                f"2. Choose the {side} side and the Limit tab.",
                f"3. Press 'Fill shares & price' below: {o['shares']:g} share(s) at ${o['limit']:.2f}.",
                f"4. Check everything, then click TradingView's {side} button yourself.",
            ]
            page.goto(f"https://www.tradingview.com/chart/?symbol={o['ticker']}",
                      wait_until="domcontentloaded", timeout=60_000)
            status = ""
            log([doc["date"], o["ticker"], o["side"], o["shares"], o["limit"], "shown"])
            while True:
                page.evaluate(BANNER_JS, [title, lines, status])
                action = wait_for_click(page, [title, lines, status])
                if action == "fill":
                    status = fill_ticket(page, o["shares"], o["limit"])
                    log([doc["date"], o["ticker"], o["side"], o["shares"], o["limit"], "filled: " + status])
                    continue
                break
            if action == "stop":
                break
        page.evaluate(BANNER_JS, ["Done", [f"Your log is in {LOG}", "Close this window when finished."], ""])
        browser.wait_for_event("close", timeout=0)


if __name__ == "__main__":
    main()
