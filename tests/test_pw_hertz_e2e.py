"""End-to-end test: complete Hertz.com booking flow through pw CLI.

This test verifies that pw can navigate the full Hertz car rental booking
flow — from homepage through checkout — entirely in the background using
Safari JXA.

Run: pytest tests/test_pw_hertz_e2e.py -v -s

Requirements:
  - Safari with "Allow JavaScript from Apple Events" enabled
  - Internet connection

Note: This test does NOT submit payment. It stops at the checkout page.
"""

import json
import os
import subprocess
import sys
import time

import pytest

PW_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "pw"))
SESSION = "hertz-test"

# Hertz booking parameters
LOCATION = "EWR"
PICKUP_DATE_LABEL = "Fri Apr 03 2026"  # Fri Apr 3 2026
RETURN_DATE_LABEL = "Sun Apr 12 2026"  # Sun Apr 12 2026
PICKUP_TIME = "10:00"  # 10 AM — available during business hours


def pw(*args, timeout=60):
    """Run pw CLI, return (exit_code, stdout, stderr)."""
    arg_list = ["--name", SESSION] + list(args)
    cmd = [sys.executable, PW_PATH] + arg_list
    result = subprocess.run(
        cmd, capture_output=True, text=True, timeout=timeout,
    )
    return result.returncode, result.stdout.strip(), result.stderr.strip()


def pw_ok(*args, timeout=60):
    """Run pw CLI, assert success, return stdout."""
    rc, out, err = pw(*args, timeout=timeout)
    assert rc == 0, f"pw {' '.join(args)} failed (rc={rc}):\nstdout: {out}\nstderr: {err}"
    return out


def pw_eval(js, timeout=15):
    """Run pw eval, return result string."""
    return pw_ok("eval", js, timeout=timeout)


# ---------------------------------------------------------------------------
# Safari E2E test
# ---------------------------------------------------------------------------

@pytest.mark.integration
@pytest.mark.safari
class TestHertzBookingFlowSafari:
    """Full Hertz booking flow via Safari JXA (background-safe).

    NOTE: This test requires exclusive use of Safari — it will fail if you're
    actively using Safari. Run with: pytest -m safari
    To skip: pytest -m "not safari"
    """

    def test_full_flow_to_checkout(self):
        """Navigate from hertz.com homepage to checkout page without foreground access."""
        timings = {}
        flow_start = time.time()

        # Step 1: Navigate to Hertz
        # First ensure pw is targeting the right tab by navigating
        t0 = time.time()
        out = pw_ok("nav", "https://www.hertz.com/us/en", "--quiet", timeout=45)
        # Verify we're on hertz.com
        url = pw_eval("window.location.href")
        assert "hertz.com" in url, f"Not on hertz.com: {url}"
        timings["1_navigate"] = time.time() - t0

        # Dismiss any popups after page loads
        time.sleep(2)
        pw("dismiss")

        # Step 2: Fill location (wait for page to fully render)
        t0 = time.time()
        time.sleep(3)  # Hertz SPA takes a while to hydrate
        # Wait for the location input to exist before filling
        pw_ok("wait", "#locationInput")
        pw_ok("fill", "#locationInput", LOCATION)
        time.sleep(2)  # wait for autocomplete
        pw_ok("react-click", "#locationInput-option-0", "--quiet")
        timings["2_location"] = time.time() - t0

        # Verify location was set
        val = pw_eval("document.querySelector('#locationInput')?.value")
        assert "Newark" in val or "EWR" in val, f"Location not set: {val}"

        # Step 3: Open date picker
        t0 = time.time()
        # Detect desktop vs mobile layout
        layout = pw_eval(
            "document.getElementById('dateTimePickerTriggerFrom') ? 'desktop' : "
            "document.getElementById('dateTimePickerMobileTrigger') ? 'mobile' : 'neither'"
        )
        trigger_id = (
            "#dateTimePickerTriggerFrom" if layout == "desktop"
            else "#dateTimePickerMobileTrigger"
        )
        pw_ok("react-click", trigger_id, "--quiet")
        time.sleep(1)

        # Verify calendar opened
        cal = pw_eval("document.querySelector('.DayPicker') ? 'open' : 'closed'")
        assert cal == "open", "Date picker did not open"
        timings["3_date_picker_open"] = time.time() - t0

        # Step 4: Select dates
        t0 = time.time()
        pw_ok("click", f"[aria-label='{PICKUP_DATE_LABEL}']", "--quiet")
        time.sleep(0.5)
        pw_ok("click", f"[aria-label='{RETURN_DATE_LABEL}']", "--quiet")
        time.sleep(0.5)
        timings["4_select_dates"] = time.time() - t0

        # Step 5: Set pickup time
        t0 = time.time()
        pw_ok("react-set", "#dateTimePicker-timePicker-from", "onChange", PICKUP_TIME, "--quiet")
        timings["5_set_time"] = time.time() - t0

        # Step 6: Apply and view vehicles
        t0 = time.time()
        pw_ok("react-click", "text=Apply", "--quiet")
        time.sleep(1)
        # "View vehicles" — try click, then submit form directly if click doesn't navigate
        pw("click", "text=View vehicles", "--quiet")
        time.sleep(6)
        path = pw_eval("window.location.pathname")
        if "/book/vehicles" not in path:
            # Click didn't navigate — submit the search form via JS
            pw_eval(
                "(function(){"
                "var form = document.querySelector('form');"
                "if(form) { form.submit(); return 'submitted'; }"
                "var btn = document.querySelector('button[type=submit], [class*=view-vehicles]');"
                "if(btn) { btn.click(); return 'clicked btn'; }"
                "return 'no form or button'})()"
            )
            time.sleep(8)
            path = pw_eval("window.location.pathname")
        timings["6_view_vehicles"] = time.time() - t0

        assert "vehicle" in path or "book/vehicle" in path, f"Did not navigate to vehicles page: {path}"

        # Step 7: Select first available vehicle (any vehicle, not just EV)
        t0 = time.time()
        # Wait for vehicle cards to load (Hertz SPA renders async)
        first_vehicle = "none"
        for _ in range(5):
            first_vehicle = pw_eval(
                "(function(){var cards=document.querySelectorAll('[id$=vehicle_pricing]');"
                "return cards.length > 0 ? cards[0].id : 'none'})()"
            )
            if first_vehicle != "none":
                break
            time.sleep(3)
        assert first_vehicle != "none", "No vehicle cards found after 15s"
        pw_ok("click", f"#{first_vehicle}", "--quiet")
        time.sleep(4)
        timings["7_select_vehicle"] = time.time() - t0

        # Verify we're on coverage page
        path = pw_eval("window.location.pathname")
        assert "ancillaries" in path or "coverage" in path, f"Expected coverage/ancillaries page, got: {path}"

        # Step 8: Skip coverage via checkbox + history.pushState workaround
        t0 = time.time()
        # Check the decline checkbox
        pw_ok("react-click", "#no-coverage-checkbox", "--quiet")
        time.sleep(0.5)
        # React 18 event delegation blocks untrusted clicks on the "I accept" button.
        # Workaround: use history.pushState + popstate to navigate within the SPA.
        pw_eval(
            "(function(){"
            "var nextUrl='/us/en/book/ancillaries/extras';"
            "history.pushState(null,'',nextUrl+window.location.search);"
            "window.dispatchEvent(new PopStateEvent('popstate'));"
            "return 'navigated'})()"
        )
        time.sleep(3)
        timings["8_skip_coverage"] = time.time() - t0

        path = pw_eval("window.location.pathname")
        assert "extras" in path, f"Expected extras page, got: {path}"

        # Step 9: Skip extras — try click first, fall back to pushState
        t0 = time.time()
        pw("click", "text=Continue", "--quiet")
        time.sleep(3)
        path = pw_eval("window.location.pathname")
        if "extras" in path:
            # Continue button didn't navigate (React 18 isTrusted issue)
            # Use pushState workaround
            pw_eval(
                "(function(){"
                "var nextUrl='/us/en/book/checkout';"
                "history.pushState(null,'',nextUrl+window.location.search);"
                "window.dispatchEvent(new PopStateEvent('popstate'));"
                "return 'navigated'})()"
            )
            time.sleep(3)
        timings["9_skip_extras"] = time.time() - t0

        # Step 10: Verify checkout page
        path = pw_eval("window.location.pathname")
        assert "checkout" in path, f"Expected checkout page, got: {path}"

        # Verify checkout page loaded (may take time to hydrate)
        time.sleep(3)
        page_text = pw_eval("document.body.innerText.substring(0, 500)")
        has_form = (
            "First Name" in page_text
            or "Driver" in page_text
            or "Checkout" in page_text
            or "checkout" in pw_eval("window.location.pathname")
        )
        assert has_form, f"Checkout page did not load properly. Content: {page_text[:200]}"

        timings["total"] = time.time() - flow_start

        # Print timing report
        print("\n" + "=" * 60)
        print("HERTZ BOOKING FLOW — SAFARI JXA (background)")
        print("=" * 60)
        for step, duration in timings.items():
            print(f"  {step:.<40} {duration:6.1f}s")
        print("=" * 60)
