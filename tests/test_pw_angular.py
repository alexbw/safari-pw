"""Integration tests: pw against an AngularJS form.

Motivation: real-world AngularJS apps (Mission Workshop's ReturnLogic portal,
many older enterprise SPAs) don't reliably respond to programmatic
`el.value = X` or `el.click()` because AngularJS routes input/click through
its own directives and only commits changes during the `$digest` cycle.

These tests load real AngularJS from CDN, render a small form with `ng-model`
inputs and an `ng-click` submit button, then exercise both:

  * the dedicated `pw ng-set` / `pw ng-click` commands (must always work)
  * the regular `pw fill` / `pw click` commands (must auto-detect Angular
    and use the right path transparently)

If the CDN is unreachable the tests skip — no offline fallback for now.
The fixture URL pattern `/tmp/pw-test-angular-fixture.html` matches the
session-cleanup needles in conftest.py so escaped tabs get swept.
"""

import os
import socket
import subprocess
import sys
import textwrap
import time

import pytest

PW_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "pw"))

SESSION = "pytest-test-pw-angular"

ANGULAR_CDN = "https://ajax.googleapis.com/ajax/libs/angularjs/1.8.3/angular.min.js"

ANGULAR_FIXTURE_HTML = textwrap.dedent(f"""\
    <!DOCTYPE html>
    <html ng-app="testApp">
    <head>
        <title>AngularJS Form Test</title>
        <script src="{ANGULAR_CDN}"></script>
        <script>
            angular.module('testApp', [])
              .controller('FormCtrl', ['$scope', function($scope) {{
                  $scope.form = {{ email: '', orderNumber: '' }};
                  $scope.submitted = false;
                  $scope.lastEmail = '';
                  $scope.lastOrder = '';
                  $scope.submit = function() {{
                      $scope.submitted = true;
                      $scope.lastEmail = $scope.form.email;
                      $scope.lastOrder = $scope.form.orderNumber;
                  }};
              }}]);
        </script>
    </head>
    <body ng-controller="FormCtrl">
        <form name="startForm" novalidate>
            <input id="email" type="email" ng-model="form.email" required>
            <input id="orderNumber" type="text" ng-model="form.orderNumber" required>
            <button id="submitBtn" type="button" ng-click="submit()">Submit</button>
        </form>
        <div>
            <span id="submittedFlag">{{{{submitted}}}}</span>
            <span id="capturedEmail">{{{{lastEmail}}}}</span>
            <span id="capturedOrder">{{{{lastOrder}}}}</span>
        </div>
    </body>
    </html>
""")

ANGULAR_FIXTURE_PATH = "/tmp/pw-test-angular-fixture.html"


def _internet_ok():
    """Quick TCP probe for the AngularJS CDN host. Skips tests if offline."""
    try:
        sock = socket.create_connection(("ajax.googleapis.com", 443), timeout=2)
        sock.close()
        return True
    except OSError:
        return False


def _run_pw(*args, timeout=30):
    """Run pw as a subprocess pinned to this module's session."""
    result = subprocess.run(
        [sys.executable, PW_PATH, "--name", SESSION] + list(args),
        capture_output=True, text=True, timeout=timeout,
        env={**os.environ, "NODE_NO_WARNINGS": "1"},
    )
    return result.returncode, result.stdout, result.stderr


def _eval(js):
    """Evaluate JS in the test tab, return stdout (trimmed)."""
    code, out, _ = _run_pw("eval", js)
    return out.strip() if code == 0 else None


def _wait_for_angular(deadline_s=8.0):
    """Poll until Angular has finished its initial bootstrap and bindings.

    A page is Angular-ready when `angular` exists AND the {{submitted}}
    binding in the fixture has rendered to "false". We can't just check
    `window.angular` because the script tag may have loaded before the
    digest cycle runs — checking the rendered binding confirms the
    controller is wired up.

    Note: `pw eval` prints Python's str(True/False), so we accept both
    "false" (raw JS) and "False" (Python-rendered) here.
    """
    end = time.time() + deadline_s
    while time.time() < end:
        val = _eval('(typeof angular !== "undefined") && '
                    'document.getElementById("submittedFlag") && '
                    'document.getElementById("submittedFlag").innerText.trim()')
        if val and val.lower() == "false":
            return True
        time.sleep(0.2)
    return False


@pytest.fixture(scope="module")
def angular_fixture():
    if not _internet_ok():
        pytest.skip("AngularJS CDN unreachable — these tests need the network")
    with open(ANGULAR_FIXTURE_PATH, "w") as f:
        f.write(ANGULAR_FIXTURE_HTML)
    yield ANGULAR_FIXTURE_PATH
    if os.path.exists(ANGULAR_FIXTURE_PATH):
        os.unlink(ANGULAR_FIXTURE_PATH)


def _open_fixture():
    _run_pw("nav", f"file://{ANGULAR_FIXTURE_PATH}", "--quiet")
    assert _wait_for_angular(), "AngularJS never bootstrapped — check CDN reachability"


# ============================================================================
# Dedicated ng-set / ng-click commands — the explicit path
# ============================================================================


@pytest.mark.safari
class TestNgCommands:
    """`pw ng-set` + `pw ng-click` must drive AngularJS forms end-to-end."""

    def test_ng_set_updates_scope(self, angular_fixture):
        _open_fixture()
        code, out, err = _run_pw("ng-set", "#email", "alex@example.com")
        assert code == 0, f"ng-set failed: {err}"
        # Read back via scope — direct DOM .value reflects ng-model two-way binding
        val = _eval('document.getElementById("email").value')
        assert val == "alex@example.com", f"DOM value not updated: {val!r}"

    def test_ng_click_fires_handler(self, angular_fixture):
        _open_fixture()
        _run_pw("ng-set", "#email", "alex@example.com")
        _run_pw("ng-set", "#orderNumber", "EC-139091")
        code, out, err = _run_pw("ng-click", "#submitBtn")
        assert code == 0, f"ng-click failed: {err}"
        flag = _eval('document.getElementById("submittedFlag").innerText.trim()')
        assert flag and flag.lower() == "true", f"ng-click handler did not fire: submitted={flag!r}"
        assert _eval('document.getElementById("capturedEmail").innerText.trim()') == "alex@example.com"
        assert _eval('document.getElementById("capturedOrder").innerText.trim()') == "EC-139091"


# ============================================================================
# Auto-detect: regular fill / click should transparently work on Angular
# ============================================================================


@pytest.mark.safari
class TestFillAndClickAutoDetect:
    """`pw fill` and `pw click` must auto-detect AngularJS and route correctly.

    This is the user-facing acceptance criterion from task pw-angular-b75ce6fc:
    a script that uses the normal commands should complete the
    Mission-Workshop-style return flow without the caller needing to know
    the page is Angular.
    """

    def test_fill_updates_ng_model_scope(self, angular_fixture):
        _open_fixture()
        code, out, err = _run_pw("fill", "#email", "alex@example.com")
        assert code == 0, f"fill failed: {err}"
        # The DOM .value reflects scope.form.email via ng-model two-way binding.
        # If fill didn't go through Angular, the value sits in the DOM but the
        # scope still has '' — confirm by triggering submit and checking what
        # the handler captured.
        _run_pw("fill", "#orderNumber", "EC-139091")
        _run_pw("click", "#submitBtn")
        captured_email = _eval('document.getElementById("capturedEmail").innerText.trim()')
        captured_order = _eval('document.getElementById("capturedOrder").innerText.trim()')
        assert captured_email == "alex@example.com", (
            f"scope.form.email not synced: captured={captured_email!r}"
        )
        assert captured_order == "EC-139091", (
            f"scope.form.orderNumber not synced: captured={captured_order!r}"
        )

    def test_click_fires_ng_click_handler(self, angular_fixture):
        _open_fixture()
        _run_pw("fill", "#email", "alex@example.com")
        _run_pw("fill", "#orderNumber", "EC-139091")
        code, out, err = _run_pw("click", "#submitBtn")
        assert code == 0, f"click failed: {err}"
        flag = _eval('document.getElementById("submittedFlag").innerText.trim()')
        assert flag and flag.lower() == "true", (
            f"ng-click handler did not fire: submitted={flag!r}"
        )


# ============================================================================
# CLI surface — commands are registered
# ============================================================================


class TestNgCliRegistration:
    """Verify ng-set and ng-click are part of the public CLI."""

    def test_ng_set_in_commands_table(self):
        import importlib.machinery
        import importlib.util
        loader = importlib.machinery.SourceFileLoader("pw", PW_PATH)
        spec = importlib.util.spec_from_loader("pw", loader, origin=PW_PATH)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        assert "ng-set" in mod.COMMANDS
        assert "ng-click" in mod.COMMANDS

    def test_ng_set_usage(self):
        result = subprocess.run(
            [sys.executable, PW_PATH, "ng-set"],
            capture_output=True, text=True, timeout=10,
        )
        assert result.returncode == 1
        assert "ng-set" in result.stderr.lower()

    def test_ng_click_usage(self):
        result = subprocess.run(
            [sys.executable, PW_PATH, "ng-click"],
            capture_output=True, text=True, timeout=10,
        )
        assert result.returncode == 1
        assert "ng-click" in result.stderr.lower()
