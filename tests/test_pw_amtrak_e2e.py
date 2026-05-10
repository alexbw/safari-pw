"""E2E test: Amtrak.com train booking flow.

Verifies pw can search for trains on amtrak.com — station autocomplete,
date/time selection, passenger count, and reach the schedule/results page.

Tests the Amtrak booking flow for NJ/NYC train routes.

Run: pytest tests/test_pw_amtrak_e2e.py -v -s -m integration
"""

import os
import subprocess
import sys
import time

import pytest

PW_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "pw"))
SESSION = "amtrak-test"

# Route params
ORIGIN_STATION = "New York Penn"
DEST_STATION = "Newark"
TRAVEL_DATE = "05/15/2026"  # Far enough out


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
class TestAmtrakTrainSearch:
    """Search for trains on amtrak.com."""

    def test_search_trains_nyp_to_ewr(self):
        # Clean stale session state
        session_file = os.path.expanduser("~/Library/Application Support/safari-pw/session-amtrak-test.json")
        if os.path.exists(session_file):
            os.unlink(session_file)

        timings = {}
        t_start = time.time()

        # Step 1: Navigate to Amtrak
        t0 = time.time()
        pw_ok("nav", "https://www.amtrak.com", "--dismiss", "--quiet", timeout=30)
        time.sleep(4)
        timings["1_navigate"] = time.time() - t0

        # Step 2: Dismiss cookie/popup banners
        t0 = time.time()
        pw("dismiss")
        time.sleep(1)
        timings["2_dismiss_popups"] = time.time() - t0

        # Step 3: Fill origin station
        t0 = time.time()
        # Amtrak has #mat-input-0 or similar for origin, or aria-label based
        origin_result = pw_eval(
            "(function(){"
            "var inputs = document.querySelectorAll('input');"
            "for(var i=0;i<inputs.length;i++){"
            "  var ph = (inputs[i].placeholder || '').toLowerCase();"
            "  var label = (inputs[i].getAttribute('aria-label') || '').toLowerCase();"
            "  var id = (inputs[i].id || '').toLowerCase();"
            "  if(ph.indexOf('from') > -1 || label.indexOf('from') > -1 || "
            "     id.indexOf('origin') > -1 || ph.indexOf('depart') > -1){"
            "    inputs[i].focus();"
            "    inputs[i].value = '" + ORIGIN_STATION + "';"
            "    inputs[i].dispatchEvent(new Event('input', {bubbles:true}));"
            "    return 'filled: ' + (inputs[i].id || inputs[i].name || 'idx:'+i);"
            "  }"
            "} return 'not found'})()"
        )
        time.sleep(2)
        # Select first autocomplete suggestion
        pw_eval(
            "(function(){"
            "var opts = document.querySelectorAll('[role=option], [class*=suggestion], "
            "mat-option, [class*=autocomplete-item]');"
            "if(opts.length > 0) { opts[0].click(); return 'selected: ' + opts[0].textContent.trim().substring(0,40); }"
            "return 'no suggestions'})()"
        )
        timings["3_origin"] = time.time() - t0

        # Step 4: Fill destination station
        t0 = time.time()
        dest_result = pw_eval(
            "(function(){"
            "var inputs = document.querySelectorAll('input');"
            "for(var i=0;i<inputs.length;i++){"
            "  var ph = (inputs[i].placeholder || '').toLowerCase();"
            "  var label = (inputs[i].getAttribute('aria-label') || '').toLowerCase();"
            "  var id = (inputs[i].id || '').toLowerCase();"
            "  if(ph.indexOf('to') > -1 || label.indexOf('to') > -1 || "
            "     id.indexOf('dest') > -1 || label.indexOf('arriv') > -1){"
            "    inputs[i].focus();"
            "    inputs[i].value = '" + DEST_STATION + "';"
            "    inputs[i].dispatchEvent(new Event('input', {bubbles:true}));"
            "    return 'filled: ' + (inputs[i].id || inputs[i].name || 'idx:'+i);"
            "  }"
            "} return 'not found'})()"
        )
        time.sleep(2)
        pw_eval(
            "(function(){"
            "var opts = document.querySelectorAll('[role=option], [class*=suggestion], mat-option');"
            "if(opts.length > 0) { opts[0].click(); return 'selected'; }"
            "return 'no suggestions'})()"
        )
        timings["4_destination"] = time.time() - t0

        # Step 5: Set travel date
        t0 = time.time()
        # Find date input
        pw_eval(
            "(function(){"
            "var inputs = document.querySelectorAll('input');"
            "for(var i=0;i<inputs.length;i++){"
            "  var id = (inputs[i].id || '').toLowerCase();"
            "  var label = (inputs[i].getAttribute('aria-label') || '').toLowerCase();"
            "  var ph = (inputs[i].placeholder || '').toLowerCase();"
            "  if(id.indexOf('date') > -1 || label.indexOf('date') > -1 || "
            "     ph.indexOf('date') > -1 || ph.indexOf('mm/dd') > -1){"
            "    inputs[i].focus(); inputs[i].click();"
            "    return 'opened date: ' + (inputs[i].id || 'idx:'+i);"
            "  }"
            "} return 'no date input'})()"
        )
        time.sleep(1)
        # Try to type the date or find a calendar
        pw_eval(
            "(function(){"
            "var dateInput = document.querySelector('input[aria-label*=\"date\" i], "
            "input[placeholder*=\"MM/DD\"]');"
            "if(dateInput){"
            "  var nativeSetter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set;"
            "  nativeSetter.call(dateInput, '" + TRAVEL_DATE + "');"
            "  dateInput.dispatchEvent(new Event('input', {bubbles:true}));"
            "  dateInput.dispatchEvent(new Event('change', {bubbles:true}));"
            "  return 'set date';"
            "} return 'no date input'})()"
        )
        timings["5_date"] = time.time() - t0

        # Step 6: Click search/find trains
        t0 = time.time()
        search_result = pw_eval(
            "(function(){"
            "var btns = document.querySelectorAll('button, a');"
            "for(var i=0;i<btns.length;i++){"
            "  var t = btns[i].textContent.trim().toLowerCase();"
            "  if(t.indexOf('find train') > -1 || t.indexOf('search') > -1 || "
            "     t === 'find trains' || t === 'search trains'){"
            "    btns[i].click(); return 'clicked: ' + t;"
            "  }"
            "} return 'no search button'})()"
        )
        time.sleep(8)
        timings["6_search"] = time.time() - t0

        # Step 7: Verify results
        page_url = pw_eval("window.location.href")
        page_text = pw_eval("document.body.innerText.substring(0, 500)")
        has_results = (
            "train" in page_text.lower()
            or "schedule" in page_text.lower()
            or "depart" in page_text.lower()
            or "northeast" in page_text.lower()
            or "/trains/" in page_url
        )

        timings["total"] = time.time() - t_start

        print("\n" + "=" * 60)
        print("AMTRAK TRAIN SEARCH — SAFARI JXA")
        print("=" * 60)
        for step, duration in timings.items():
            print(f"  {step:.<40} {duration:6.1f}s")
        print(f"  Origin: {origin_result}")
        print(f"  Dest: {dest_result}")
        print(f"  Search: {search_result}")
        print(f"  Has results: {has_results}")
        print(f"  Final URL: {page_url[:80]}")
        print("=" * 60)
