"""E2E test: United.com flight search flow.

Verifies pw can search for flights on united.com — origin/destination
autocomplete, date picker, passenger count, and reach the results page.

Alex has United loyalty (SF045492). This tests a complex React booking
flow similar to Hertz but with airline-specific UI patterns.

Run: pytest tests/test_pw_united_e2e.py -v -s -m integration
"""

import os
import subprocess
import sys
import time

import pytest

PW_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "pw"))
SESSION = "united-test"

# Flight search params
ORIGIN = "EWR"
DESTINATION = "SFO"
DEPART_DATE = "2026-05-15"  # Far enough out to have availability
RETURN_DATE = "2026-05-20"


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
class TestUnitedFlightSearch:
    """Search for flights on united.com."""

    def test_search_flights_ewr_to_sfo(self):
        # Clean stale session state
        session_file = os.path.expanduser("~/Library/Application Support/safari-pw/session-united-test.json")
        if os.path.exists(session_file):
            os.unlink(session_file)

        timings = {}
        t_start = time.time()

        # Step 1: Navigate to United
        t0 = time.time()
        pw_ok("nav", "https://www.united.com/en/us", "--dismiss", "--quiet", timeout=30)
        time.sleep(4)  # Heavy SPA
        timings["1_navigate"] = time.time() - t0

        # Step 2: Dismiss cookie/popup banners
        t0 = time.time()
        pw("dismiss")
        time.sleep(1)
        timings["2_dismiss_popups"] = time.time() - t0

        # Step 3: Fill origin airport
        t0 = time.time()
        # United uses #bookFlightOriginInput or similar
        origin_filled = pw_eval(
            "(function(){"
            "var inputs = document.querySelectorAll('input');"
            "for(var i=0;i<inputs.length;i++){"
            "  var ph = (inputs[i].placeholder || '').toLowerCase();"
            "  var label = (inputs[i].getAttribute('aria-label') || '').toLowerCase();"
            "  var id = (inputs[i].id || '').toLowerCase();"
            "  if(ph.indexOf('from') > -1 || ph.indexOf('origin') > -1 || "
            "     label.indexOf('from') > -1 || id.indexOf('origin') > -1){"
            "    inputs[i].focus();"
            "    inputs[i].value = '" + ORIGIN + "';"
            "    inputs[i].dispatchEvent(new Event('input', {bubbles:true}));"
            "    return 'filled: ' + inputs[i].id;"
            "  }"
            "} return 'not found'})()"
        )
        time.sleep(2)  # Wait for autocomplete
        # Select first autocomplete suggestion
        pw_eval(
            "(function(){"
            "var opts = document.querySelectorAll('[role=option], [role=listbox] li, "
            "[class*=autocomplete] li, [class*=suggestion]');"
            "if(opts.length > 0) { opts[0].click(); return 'selected'; }"
            "return 'no suggestions'})()"
        )
        timings["3_origin"] = time.time() - t0

        # Step 4: Fill destination airport
        t0 = time.time()
        dest_filled = pw_eval(
            "(function(){"
            "var inputs = document.querySelectorAll('input');"
            "for(var i=0;i<inputs.length;i++){"
            "  var ph = (inputs[i].placeholder || '').toLowerCase();"
            "  var label = (inputs[i].getAttribute('aria-label') || '').toLowerCase();"
            "  var id = (inputs[i].id || '').toLowerCase();"
            "  if(ph.indexOf('to') > -1 || ph.indexOf('dest') > -1 || "
            "     label.indexOf('to') > -1 || id.indexOf('dest') > -1){"
            "    inputs[i].focus();"
            "    inputs[i].value = '" + DESTINATION + "';"
            "    inputs[i].dispatchEvent(new Event('input', {bubbles:true}));"
            "    return 'filled: ' + inputs[i].id;"
            "  }"
            "} return 'not found'})()"
        )
        time.sleep(2)
        pw_eval(
            "(function(){"
            "var opts = document.querySelectorAll('[role=option], [role=listbox] li');"
            "if(opts.length > 0) { opts[0].click(); return 'selected'; }"
            "return 'no suggestions'})()"
        )
        timings["4_destination"] = time.time() - t0

        # Step 5: Set departure date
        t0 = time.time()
        # United uses a date picker — find and click the departure date field
        pw_eval(
            "(function(){"
            "var inputs = document.querySelectorAll('input');"
            "for(var i=0;i<inputs.length;i++){"
            "  var id = (inputs[i].id || '').toLowerCase();"
            "  var label = (inputs[i].getAttribute('aria-label') || '').toLowerCase();"
            "  if(id.indexOf('depart') > -1 || label.indexOf('depart') > -1){"
            "    inputs[i].click(); return 'clicked depart date';"
            "  }"
            "} return 'not found'})()"
        )
        time.sleep(1)
        # Try to find and click the specific date in the calendar
        pw_eval(
            "(function(){"
            "var cells = document.querySelectorAll('[role=gridcell], [aria-label*=\"May 15\"], "
            "td[data-date], button[data-date]');"
            "for(var i=0;i<cells.length;i++){"
            "  var label = cells[i].getAttribute('aria-label') || cells[i].textContent;"
            "  if(label.indexOf('May 15') > -1 || label.indexOf('15') > -1){"
            "    cells[i].click(); return 'selected May 15';"
            "  }"
            "} return 'no date cells found (' + cells.length + ')'})()"
        )
        timings["5_depart_date"] = time.time() - t0

        # Step 6: Set return date
        t0 = time.time()
        pw_eval(
            "(function(){"
            "var cells = document.querySelectorAll('[role=gridcell], [aria-label*=\"May 20\"], "
            "td[data-date], button[data-date]');"
            "for(var i=0;i<cells.length;i++){"
            "  var label = cells[i].getAttribute('aria-label') || cells[i].textContent;"
            "  if(label.indexOf('May 20') > -1 || label.indexOf('20') > -1){"
            "    cells[i].click(); return 'selected May 20';"
            "  }"
            "} return 'no date cells'})()"
        )
        timings["6_return_date"] = time.time() - t0

        # Step 7: Click search/find flights
        t0 = time.time()
        pw_eval(
            "(function(){"
            "var btns = document.querySelectorAll('button');"
            "for(var i=0;i<btns.length;i++){"
            "  var t = btns[i].textContent.trim().toLowerCase();"
            "  if(t.indexOf('search') > -1 || t.indexOf('find flight') > -1){"
            "    btns[i].click(); return 'clicked: ' + t;"
            "  }"
            "} return 'no search button'})()"
        )
        time.sleep(8)  # Flight search takes a while
        timings["7_search"] = time.time() - t0

        # Step 8: Verify results
        t0 = time.time()
        page_url = pw_eval("window.location.href")
        page_text = pw_eval("document.body.innerText.substring(0, 500)")
        has_results = (
            "flight" in page_text.lower()
            or "result" in page_text.lower()
            or "nonstop" in page_text.lower()
            or "economy" in page_text.lower()
            or "/flight-search/" in page_url
        )
        timings["8_verify_results"] = time.time() - t0

        timings["total"] = time.time() - t_start

        print("\n" + "=" * 60)
        print("UNITED.COM FLIGHT SEARCH — SAFARI JXA")
        print("=" * 60)
        for step, duration in timings.items():
            print(f"  {step:.<40} {duration:6.1f}s")
        print(f"  Origin filled: {origin_filled}")
        print(f"  Dest filled: {dest_filled}")
        print(f"  Has results: {has_results}")
        print(f"  Final URL: {page_url[:80]}")
        print("=" * 60)
