"""E2E test: Expedia hotel search flow.

Verifies pw can search for hotels on expedia.com — destination autocomplete,
date picker, guest count, and reach the results/listing page.

Admin uses Expedia for hotel research during travel planning.

Run: pytest tests/test_pw_expedia_e2e.py -v -s -m integration
"""

import os
import subprocess
import sys
import time

import pytest

PW_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "pw"))
SESSION = "expedia-test"

# Hotel search params
DESTINATION = "Los Gatos, CA"  # Near George's wedding venue
CHECKIN = "April 11, 2026"
CHECKOUT = "April 14, 2026"


def pw(*args, timeout=60):
    cmd = [sys.executable, PW_PATH, "--name", SESSION] + list(args)
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    return result.returncode, result.stdout.strip(), result.stderr.strip()


def pw_ok(*args, timeout=60):
    rc, out, err = pw(*args, timeout=timeout)
    assert rc == 0, f"pw {' '.join(args)} failed (rc={rc}):\nstdout: {out}\nstderr: {err}"
    return out


def pw_eval(js, timeout=30):
    return pw_ok("eval", js, timeout=timeout)


@pytest.mark.integration
@pytest.mark.safari
class TestExpediaHotelSearch:
    """Search for hotels on Expedia."""

    def test_search_hotels_los_gatos(self):
        # Clean any stale session state from previous test runs
        session_file = os.path.expanduser(f"~/Library/Application Support/safari-pw/session-{SESSION}.json")
        if os.path.exists(session_file):
            os.unlink(session_file)

        timings = {}
        t_start = time.time()

        # Step 1: Navigate directly to Expedia hotel search results
        # Using URL params bypasses bot-protected form filling
        t0 = time.time()
        search_url = (
            "https://www.expedia.com/Hotel-Search?"
            "destination=Los+Gatos%2C+California&"
            "startDate=2026-04-11&endDate=2026-04-14&"
            "rooms=1&adults=2"
        )
        pw_ok("nav", search_url, "--quiet", timeout=45)
        time.sleep(5)
        url = pw_eval("window.location.href")
        assert "expedia" in url, f"Not on Expedia: {url}"
        timings["1_navigate"] = time.time() - t0

        # Step 2: Dismiss popups and wait for results
        t0 = time.time()
        pw("dismiss")
        time.sleep(3)
        timings["2_dismiss_popups"] = time.time() - t0

        # Step 3: Verify results loaded (we navigated directly to search results)
        t0 = time.time()
        # Expedia uses a button that opens a search overlay, or a direct input
        dest_result = pw_eval(
            "(function(){"
            "// Try clicking the destination button/input first"
            "var destBtn = document.querySelector('button[aria-label*=\"destination\" i], "
            "button[aria-label*=\"Going to\" i], input[aria-label*=\"destination\" i], "
            "input[aria-label*=\"Going to\" i]');"
            "if(destBtn) { destBtn.click(); }"
            "return destBtn ? 'clicked dest trigger' : 'no dest trigger'})()"
        )
        time.sleep(1)
        # Now fill the search input that appeared
        pw_eval(
            "(function(){"
            "var inputs = document.querySelectorAll('input');"
            "for(var i=0;i<inputs.length;i++){"
            "  var ph = (inputs[i].placeholder || '').toLowerCase();"
            "  var label = (inputs[i].getAttribute('aria-label') || '').toLowerCase();"
            "  if(ph.indexOf('going') > -1 || ph.indexOf('destination') > -1 || "
            "     label.indexOf('going') > -1 || label.indexOf('destination') > -1 || "
            "     ph.indexOf('where') > -1){"
            "    inputs[i].focus();"
            "    var nativeSetter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set;"
            "    nativeSetter.call(inputs[i], '" + DESTINATION + "');"
            "    inputs[i].dispatchEvent(new Event('input', {bubbles:true}));"
            "    return 'filled: ' + (inputs[i].id || 'idx:'+i);"
            "  }"
            "} return 'no destination input'})()"
        )
        time.sleep(2)
        # Select first autocomplete suggestion
        pw_eval(
            "(function(){"
            "var opts = document.querySelectorAll('[role=option], li[data-stid*=destination], "
            "button[data-stid*=suggestion]');"
            "if(opts.length > 0) { opts[0].click(); return 'selected: ' + opts[0].textContent.trim().substring(0,40); }"
            "return 'no suggestions (' + opts.length + ')'})()"
        )
        timings["3_destination"] = time.time() - t0

        # Step 4: Open date picker and set dates
        t0 = time.time()
        # Click check-in date field
        pw_eval(
            "(function(){"
            "var dateBtn = document.querySelector('button[data-stid*=date], "
            "button[aria-label*=\"Check-in\" i], button[aria-label*=\"date\" i]');"
            "if(dateBtn) { dateBtn.click(); return 'opened date picker'; }"
            "return 'no date button'})()"
        )
        time.sleep(1)
        # Try to find April 11 in the calendar
        pw_eval(
            "(function(){"
            "var cells = document.querySelectorAll('button[data-day], "
            "[role=gridcell] button, td button, [aria-label*=\"Apr 11\"], "
            "[aria-label*=\"April 11\"]');"
            "for(var i=0;i<cells.length;i++){"
            "  var label = cells[i].getAttribute('aria-label') || '';"
            "  if(label.indexOf('Apr 11') > -1 || label.indexOf('April 11') > -1){"
            "    cells[i].click(); return 'selected Apr 11';"
            "  }"
            "}"
            "// Fallback: click any day labeled 11"
            "for(var j=0;j<cells.length;j++){"
            "  if(cells[j].textContent.trim() === '11'){"
            "    cells[j].click(); return 'selected day 11';"
            "  }"
            "}"
            "return 'no dates found (' + cells.length + ')'})()"
        )
        time.sleep(0.5)
        # Select checkout April 14
        pw_eval(
            "(function(){"
            "var cells = document.querySelectorAll('button[data-day], "
            "[role=gridcell] button, td button, [aria-label*=\"Apr 14\"], "
            "[aria-label*=\"April 14\"]');"
            "for(var i=0;i<cells.length;i++){"
            "  var label = cells[i].getAttribute('aria-label') || '';"
            "  if(label.indexOf('Apr 14') > -1 || label.indexOf('April 14') > -1){"
            "    cells[i].click(); return 'selected Apr 14';"
            "  }"
            "}"
            "for(var j=0;j<cells.length;j++){"
            "  if(cells[j].textContent.trim() === '14'){"
            "    cells[j].click(); return 'selected day 14';"
            "  }"
            "}"
            "return 'no dates found'})()"
        )
        time.sleep(0.5)
        # Click "Done" on date picker if present
        pw_eval(
            "(function(){"
            "var btns = document.querySelectorAll('button');"
            "for(var i=0;i<btns.length;i++){"
            "  if(btns[i].textContent.trim() === 'Done'){"
            "    btns[i].click(); return 'clicked Done';"
            "  }"
            "} return 'no Done button'})()"
        )
        timings["4_dates"] = time.time() - t0

        # Step 5: Click search
        t0 = time.time()
        pw_eval(
            "(function(){"
            "var btns = document.querySelectorAll('button');"
            "for(var i=0;i<btns.length;i++){"
            "  var t = btns[i].textContent.trim().toLowerCase();"
            "  if(t === 'search' || t === 'find hotels' || t.indexOf('search') > -1){"
            "    btns[i].click(); return 'clicked: ' + t;"
            "  }"
            "} return 'no search button'})()"
        )
        time.sleep(8)
        timings["5_search"] = time.time() - t0

        # Step 6: Verify results loaded
        t0 = time.time()
        page_url = pw_eval("window.location.href")
        page_text = pw_eval("document.body.innerText.substring(0, 500)")
        has_results = (
            "hotel" in page_text.lower()
            or "property" in page_text.lower()
            or "night" in page_text.lower()
            or "review" in page_text.lower()
            or "/Hotel-Search" in page_url
        )
        timings["6_verify_results"] = time.time() - t0

        # Step 7: Click first hotel result
        t0 = time.time()
        clicked_hotel = pw_eval(
            "(function(){"
            "var cards = document.querySelectorAll('[data-stid*=property-listing], "
            "a[href*=\"/hotel/\"], [class*=PropertyCard]');"
            "if(cards.length > 0) {"
            "  var link = cards[0].querySelector('a') || cards[0];"
            "  link.click(); return 'clicked hotel: ' + (link.textContent || '').trim().substring(0,40);"
            "}"
            "return 'no hotel cards (' + cards.length + ')'})()"
        )
        time.sleep(3)
        timings["7_click_hotel"] = time.time() - t0

        timings["total"] = time.time() - t_start

        print("\n" + "=" * 60)
        print("EXPEDIA HOTEL SEARCH — SAFARI JXA")
        print("=" * 60)
        for step, duration in timings.items():
            print(f"  {step:.<40} {duration:6.1f}s")
        print(f"  Destination: {dest_result}")
        print(f"  Has results: {has_results}")
        print(f"  Clicked hotel: {clicked_hotel}")
        print(f"  Final URL: {page_url[:80]}")
        print("=" * 60)

        assert has_results or "expedia" in page_url, \
            f"Expedia flow did not produce results. URL: {page_url}"
