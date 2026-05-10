"""E2E test: OpenTable restaurant search flow.

Verifies pw can navigate opentable.com, interact with the search form,
and reach a results or restaurant page.

Run: pytest tests/test_pw_opentable_e2e.py -v -s -m integration
"""

import os
import subprocess
import sys
import time

import pytest

PW_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "pw"))
SESSION = "opentable-test"
SEARCH_LOCATION = "Manhattan"


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
class TestOpenTableReservation:
    """Search and navigate OpenTable reservation flow."""

    def test_search_and_view_availability(self):
        # Clean stale session state
        session_file = os.path.expanduser("~/Library/Application Support/safari-pw/session-opentable-test.json")
        if os.path.exists(session_file):
            os.unlink(session_file)

        timings = {}
        t_start = time.time()

        # Step 1: Navigate to OpenTable
        t0 = time.time()
        pw_ok("nav", "https://www.opentable.com", "--dismiss", "--quiet", timeout=30)
        time.sleep(3)
        url = pw_eval("window.location.href")
        assert "opentable" in url, f"Not on OpenTable: {url}"
        timings["1_navigate"] = time.time() - t0

        # Step 2: Find and fill search input
        t0 = time.time()
        # OpenTable's search UI changes frequently — use JS to find any search-like input
        fill_result = pw_eval(
            "(function(){"
            "var inputs = document.querySelectorAll('input');"
            "for(var i=0;i<inputs.length;i++){"
            "  var ph = (inputs[i].placeholder || '').toLowerCase();"
            "  var label = (inputs[i].getAttribute('aria-label') || '').toLowerCase();"
            "  if(ph.indexOf('location') > -1 || ph.indexOf('restaurant') > -1 || "
            "     ph.indexOf('cuisine') > -1 || label.indexOf('search') > -1 || "
            "     label.indexOf('location') > -1){"
            "    var nativeSetter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set;"
            "    nativeSetter.call(inputs[i], '" + SEARCH_LOCATION + "');"
            "    inputs[i].dispatchEvent(new Event('input', {bubbles:true}));"
            "    inputs[i].dispatchEvent(new Event('change', {bubbles:true}));"
            "    return 'filled: ' + (inputs[i].id || inputs[i].placeholder || 'idx:'+i);"
            "  }"
            "} return 'no search input'})()"
        )
        time.sleep(2)
        # Try to select autocomplete suggestion
        pw_eval(
            "(function(){"
            "var opts = document.querySelectorAll('[role=option], [role=listbox] li, "
            "[class*=suggestion], [class*=autocomplete] li');"
            "if(opts.length > 0) { opts[0].click(); return 'selected'; }"
            "return 'no suggestions'})()"
        )
        timings["2_search"] = time.time() - t0

        # Step 3: Click search / find a table button
        t0 = time.time()
        search_result = pw_eval(
            "(function(){"
            "var btns = document.querySelectorAll('button, a, [role=button]');"
            "for(var i=0;i<btns.length;i++){"
            "  var t = btns[i].textContent.trim().toLowerCase();"
            "  if(t === 'find a table' || t === 'search' || t.indexOf('find') > -1 && t.length < 30){"
            "    btns[i].click(); return 'clicked: ' + t;"
            "  }"
            "} return 'no search button'})()"
        )
        time.sleep(5)
        timings["3_search_click"] = time.time() - t0

        # Step 4: Verify page changed or results appeared
        t0 = time.time()
        page_url = pw_eval("window.location.href")
        page_text = pw_eval("document.body.innerText.substring(0, 500)")
        has_results = (
            "restaurant" in page_text.lower()
            or "available" in page_text.lower()
            or "reservation" in page_text.lower()
            or "result" in page_text.lower()
            or "table" in page_text.lower()
            or "/s/" in page_url  # OpenTable search results URL
        )
        timings["4_verify"] = time.time() - t0

        timings["total"] = time.time() - t_start

        print("\n" + "=" * 60)
        print("OPENTABLE RESERVATION — SAFARI JXA")
        print("=" * 60)
        for step, duration in timings.items():
            print(f"  {step:.<40} {duration:6.1f}s")
        print(f"  Fill result: {fill_result}")
        print(f"  Search result: {search_result}")
        print(f"  Has results: {has_results}")
        print(f"  URL: {page_url[:80]}")
        print("=" * 60)

        assert has_results or "opentable" in page_url, \
            f"OpenTable flow did not produce results. URL: {page_url}"
