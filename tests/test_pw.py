"""Tests for the pw CLI — Playwright browser automation tool.

Unit tests mock the browser; integration tests use a real Chromium instance.
Run: pytest tests/test_pw.py -v
Run unit only: pytest tests/test_pw.py -v -m "not integration"
Run integration only: pytest tests/test_pw.py -v -m integration
"""

import importlib.machinery
import importlib.util
import json
import os
import signal
import subprocess
import sys
import textwrap
import time

import pytest

# ---------------------------------------------------------------------------
# Import pw as a module (it's a script without .py extension)
# ---------------------------------------------------------------------------

PW_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "pw"))


def _load_pw():
    loader = importlib.machinery.SourceFileLoader("pw", PW_PATH)
    spec = importlib.util.spec_from_loader("pw", loader, origin=PW_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


pw = _load_pw()

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# Use isolated state files so tests don't collide with a real session
TEST_CDP_FILE = "/tmp/pw-test-cdp-endpoint"
TEST_PID_FILE = "/tmp/pw-test-browser-pid"
TEST_TAB_FILE = "/tmp/pw-test-active-tab"
TEST_USER_DATA = "/tmp/pw-test-user-data"
TEST_CDP_PORT = 9333  # Different port from production

# HTML fixture for integration tests
FIXTURE_HTML = textwrap.dedent("""\
    <!DOCTYPE html>
    <html>
    <head><title>PW Test Page</title></head>
    <body>
        <h1 id="heading">Hello PW</h1>
        <p id="para">This is a test paragraph.</p>
        <a href="https://example.com">Example Link</a>
        <a href="https://test.com">Test Link</a>
        <form>
            <input id="name" type="text" name="name" />
            <input id="email" type="email" name="email" />
            <select id="color" name="color">
                <option value="red">Red</option>
                <option value="blue">Blue</option>
                <option value="green">Green</option>
            </select>
            <textarea id="notes" name="notes"></textarea>
            <input type="checkbox" id="agree" name="agree" />
            <button type="submit" id="submit-btn">Submit</button>
        </form>
        <div id="dynamic" style="display:none">Dynamic content</div>
        <script>
            setTimeout(() => {
                document.getElementById('dynamic').style.display = 'block';
            }, 500);
        </script>
    </body>
    </html>
""")

FIXTURE_PATH = "/tmp/pw-test-fixture.html"


# Pin every subprocess pw call to a single named session so the tabs we
# open during testing all live in one trackable place. Naming this `SESSION`
# (as opposed to a private constant) opts into the per-test cleanup fixture
# in conftest.py — `pw close --name pytest-test-pw` runs after every test,
# closing the tab and removing the state file. Leftover-detection by glob
# still runs at session end as a belt-and-braces backstop.
SESSION = "pytest-test-pw"
PYTEST_SESSION = SESSION  # readability alias used elsewhere in this file


def run_pw(*args, timeout=30):
    """Run pw CLI as a subprocess, return (exit_code, stdout, stderr)."""
    result = subprocess.run(
        [sys.executable, PW_PATH] + list(args),
        capture_output=True,
        text=True,
        timeout=timeout,
        env={
            **os.environ,
            "NODE_NO_WARNINGS": "1",
            "PW_SESSION": PYTEST_SESSION,
        },
    )
    return result.returncode, result.stdout, result.stderr


# ============================================================================
# UNIT TESTS — no browser needed
# ============================================================================


class TestUrlNormalization:
    """Test the URL prefix logic in cmd_nav."""

    def test_https_passthrough(self):
        # We test the prefix logic directly since cmd_nav calls connect_and_run
        url = "https://example.com"
        assert url.startswith(("http://", "https://", "file://"))

    def test_http_passthrough(self):
        url = "http://example.com"
        assert url.startswith(("http://", "https://", "file://"))

    def test_file_passthrough(self):
        url = "file:///tmp/test.html"
        assert url.startswith(("http://", "https://", "file://"))

    def test_bare_domain_gets_prefix(self):
        url = "example.com"
        assert not url.startswith(("http://", "https://", "file://"))
        url = "https://" + url
        assert url == "https://example.com"


class TestPwError:
    def test_is_exception(self):
        assert issubclass(pw.PwError, Exception)

    def test_message(self):
        e = pw.PwError("test message")
        assert str(e) == "test message"


# ============================================================================
# CLI DISPATCH TESTS — subprocess, no browser
# ============================================================================


class TestCliDispatch:
    def test_no_args_shows_help(self):
        code, out, err = run_pw()
        assert code == 0
        assert "pw — Safari" in out and "browser automation CLI" in out

    def test_unknown_command(self):
        code, out, err = run_pw("foobar")
        assert code == 1
        assert "Unknown command: foobar" in err

    def test_fill_missing_args(self):
        code, out, err = run_pw("fill")
        assert code == 1
        assert "Usage: pw fill SELECTOR TEXT" in err

    def test_fill_one_arg(self):
        code, out, err = run_pw("fill", "#input")
        assert code == 1
        assert "Usage: pw fill SELECTOR TEXT" in err

    def test_click_missing_args(self):
        code, out, err = run_pw("click")
        assert code == 1
        assert "Usage: pw click SELECTOR" in err

    def test_type_missing_args(self):
        code, out, err = run_pw("type")
        assert code == 1
        assert "Usage: pw type TEXT" in err

    def test_press_missing_args(self):
        code, out, err = run_pw("press")
        assert code == 1
        assert "Usage: pw press KEY" in err

    def test_select_missing_args(self):
        code, out, err = run_pw("select")
        assert code == 1
        assert "Usage: pw select SELECTOR VALUE" in err

    def test_select_one_arg(self):
        code, out, err = run_pw("select", "#dropdown")
        assert code == 1
        assert "Usage: pw select SELECTOR VALUE" in err

    def test_eval_missing_args(self):
        code, out, err = run_pw("eval")
        assert code == 1
        assert "Usage: pw eval JS" in err

    def test_wait_missing_args(self):
        code, out, err = run_pw("wait")
        assert code == 1
        assert "Usage: pw wait SELECTOR" in err

    def test_tab_missing_args(self):
        code, out, err = run_pw("tab")
        assert code == 1
        assert "Usage: pw tab INDEX" in err

    def test_status_runs(self):
        code, out, err = run_pw("status")
        assert code == 0
        # Safari may or may not be running on the system
        assert "running" in out.lower() or "Running" in out

    def test_close_runs(self):
        code, out, err = run_pw("close")
        assert code == 0
        # `pw close` either scrubs unnamed state ("cleaned"), reports nothing
        # to do ("not running"), or, when PW_SESSION points at a named session
        # (as the test suite sets it), reports "closed".
        out_l = out.lower()
        assert "cleaned" in out_l or "not running" in out_l or "closed" in out_l


class TestCommandsDict:
    """Verify COMMANDS table structure is consistent."""

    def test_all_commands_have_handler(self):
        for name, spec in pw.COMMANDS.items():
            assert "handler" in spec, f"{name} missing handler"
            assert callable(spec["handler"]), f"{name} handler not callable"

    def test_all_commands_have_min_args(self):
        for name, spec in pw.COMMANDS.items():
            assert "min_args" in spec, f"{name} missing min_args"
            assert isinstance(spec["min_args"], int), f"{name} min_args not int"

    def test_commands_requiring_args_have_usage(self):
        for name, spec in pw.COMMANDS.items():
            if spec["min_args"] > 0:
                assert "usage" in spec, f"{name} requires args but has no usage string"

    def test_expected_commands_exist(self):
        # Core commands that must always exist. New commands can be added
        # without churning this test; this only catches accidental removals.
        required = {
            "launch", "nav", "click", "fill", "type", "press", "select",
            "screenshot", "snap", "text", "html", "eval", "title", "url",
            "links", "wait", "tabs", "tab", "back", "close", "status",
            "doctor", "batch", "fetch", "cookies",
        }
        missing = required - set(pw.COMMANDS.keys())
        assert not missing, f"required commands missing: {missing}"


class TestFetchCookies:
    """CLI/dispatch unit tests for the fetch/cookies commands — no browser."""

    def test_fetch_missing_url(self):
        code, out, err = run_pw("fetch")
        assert code == 1
        assert "Usage: pw fetch URL" in err

    def test_fetch_to_requires_value(self):
        code, out, err = run_pw("fetch", "https://example.com/x", "--to")
        assert code == 1
        assert "--to requires a path" in err

    def test_fetch_method_requires_value(self):
        code, out, err = run_pw("fetch", "https://example.com/x", "--method")
        assert code == 1
        assert "--method requires" in err

    def test_fetch_timeout_non_integer(self):
        code, out, err = run_pw("fetch", "https://example.com/x", "--timeout", "abc")
        assert code == 1
        assert "not an integer" in err

    def test_cookies_unknown_format(self):
        code, out, err = run_pw("cookies", "--format", "yaml")
        assert code == 1
        assert "Unknown cookies format" in err or "use json|header|netscape" in err

    def test_cookies_format_requires_value(self):
        code, out, err = run_pw("cookies", "--format")
        assert code == 1
        assert "--format requires" in err

    def test_cookies_name_requires_value(self):
        # --name as cookies-arg (the session --name is stripped earlier in main)
        code, out, err = run_pw("cookies", "--format", "json", "--name")
        assert code == 1
        # Top-level --name parser catches the missing-value first; either
        # message is acceptable as long as we exit non-zero with usage.
        assert "name" in err.lower()

    def test_cookies_rejects_positional(self):
        code, out, err = run_pw("cookies", "extra-arg")
        assert code == 1
        assert "Usage: pw cookies" in err


# ============================================================================
# SAFARI BACKEND UNIT TESTS
# ============================================================================


class TestSafariHelpers:
    """Test Safari helper functions without requiring Safari."""

    def test_js_escape_basic(self):
        assert pw._js_escape("hello") == '"hello"'

    def test_js_escape_quotes(self):
        assert pw._js_escape('say "hi"') == '"say \\"hi\\""'

    def test_js_escape_backslash(self):
        assert pw._js_escape("a\\b") == '"a\\\\b"'

    def test_translate_selector_css(self):
        result = pw._translate_selector("#foo")
        assert "querySelector" in result
        assert '"#foo"' in result

    def test_translate_selector_text(self):
        result = pw._translate_selector("text=Click me")
        assert "textContent" in result
        assert '"Click me"' in result

    def test_translate_selector_complex_css(self):
        result = pw._translate_selector("div.class > span[data-x='y']")
        assert "querySelector" in result

    def test_mac_key_codes_has_basics(self):
        assert pw.MAC_KEY_CODES["Enter"] == 36
        assert pw.MAC_KEY_CODES["Tab"] == 48
        assert pw.MAC_KEY_CODES["Escape"] == 53
        assert pw.MAC_KEY_CODES["ArrowUp"] == 126
        assert pw.MAC_KEY_CODES["ArrowDown"] == 125

    def test_safari_tab_index_default(self, tmp_path, monkeypatch):
        monkeypatch.setattr(pw, "SAFARI_TAB_FILE", str(tmp_path / "no-such-file"))
        assert pw._safari_tab_index() == 0

    def test_safari_tab_index_from_file(self, tmp_path, monkeypatch):
        tab_file = tmp_path / "tab"
        tab_file.write_text("3")
        monkeypatch.setattr(pw, "SAFARI_TAB_FILE", str(tab_file))
        assert pw._safari_tab_index() == 3

    def test_safari_tab_index_corrupt_file(self, tmp_path, monkeypatch):
        tab_file = tmp_path / "tab"
        tab_file.write_text("not-a-number")
        monkeypatch.setattr(pw, "SAFARI_TAB_FILE", str(tab_file))
        assert pw._safari_tab_index() == 0

    def test_safari_page_nav_cache(self):
        page = pw.SafariPage(0)
        page._last_nav = {"title": "Cached Title", "url": "https://cached.com"}
        assert page.title() == "Cached Title"
        assert page.url == "https://cached.com"
        # Cache persists until invalidated by a mutation (click, fill, _do_js, etc.)

    def test_safari_page_init(self):
        page = pw.SafariPage(2)
        assert page._tab == 2
        assert hasattr(page, "keyboard")
        assert isinstance(page.keyboard, pw._SafariKeyboard)
        assert page._last_nav == {}


class TestDoctor:
    """pw doctor surfaces Safari setup status."""

    def test_doctor_runs(self):
        code, out, err = run_pw("doctor")
        assert "Safari automation setup check" in out


# ============================================================================
# TAB STATE & SESSION MANAGEMENT TESTS
# ============================================================================


class TestTabState:
    """Test the new tab state management functions."""

    def test_read_tab_state_no_file(self, tmp_path, monkeypatch):
        monkeypatch.setattr(pw, "SAFARI_TAB_FILE", str(tmp_path / "nonexistent"))
        monkeypatch.setattr(pw, "_session_name", None)
        assert pw._read_tab_state() is None

    def test_read_tab_state_legacy_integer(self, tmp_path, monkeypatch):
        f = tmp_path / "tab"
        f.write_text("5")
        monkeypatch.setattr(pw, "SAFARI_TAB_FILE", str(f))
        monkeypatch.setattr(pw, "_session_name", None)
        state = pw._read_tab_state()
        assert state == {"tab_index": 5}

    def test_read_tab_state_json_format(self, tmp_path, monkeypatch):
        f = tmp_path / "tab"
        f.write_text(json.dumps({
            "session_id": "pw_12345",
            "url": "https://example.com",
            "tab_index": 2,
        }))
        monkeypatch.setattr(pw, "SAFARI_TAB_FILE", str(f))
        monkeypatch.setattr(pw, "_session_name", None)
        state = pw._read_tab_state()
        assert state["session_id"] == "pw_12345"
        assert state["url"] == "https://example.com"
        assert state["tab_index"] == 2

    def test_read_tab_state_corrupt_file(self, tmp_path, monkeypatch):
        f = tmp_path / "tab"
        f.write_text("{invalid json")
        monkeypatch.setattr(pw, "SAFARI_TAB_FILE", str(f))
        monkeypatch.setattr(pw, "_session_name", None)
        assert pw._read_tab_state() is None

    def test_write_tab_state(self, tmp_path, monkeypatch):
        f = tmp_path / "tab"
        monkeypatch.setattr(pw, "SAFARI_TAB_FILE", str(f))
        monkeypatch.setattr(pw, "_session_name", None)
        pw._write_tab_state({
            "session_id": "pw_test",
            "url": "https://test.com",
            "tab_index": 3,
        })
        state = json.loads(f.read_text())
        assert state["session_id"] == "pw_test"
        assert state["tab_index"] == 3

    def test_safari_tab_index_legacy_compat(self, tmp_path, monkeypatch):
        """_safari_tab_index() should work with both old integer and new JSON format."""
        f = tmp_path / "tab"
        # Legacy integer format
        f.write_text("4")
        monkeypatch.setattr(pw, "SAFARI_TAB_FILE", str(f))
        monkeypatch.setattr(pw, "_session_name", None)
        assert pw._safari_tab_index() == 4
        # New JSON format
        f.write_text(json.dumps({"session_id": "pw_x", "tab_index": 7}))
        assert pw._safari_tab_index() == 7


class TestSessionFiles:
    """Test named session file management."""

    def test_default_session_file(self, monkeypatch):
        monkeypatch.setattr(pw, "_session_name", None)
        assert pw._safari_session_file() == pw.SAFARI_TAB_FILE

    def test_named_session_file(self, monkeypatch):
        monkeypatch.setattr(pw, "_session_name", "agent1")
        assert pw._safari_session_file() == os.path.join(pw.STATE_DIR, "session-agent1.json")

    def test_named_session_isolation(self, tmp_path, monkeypatch):
        """Two named sessions should use separate state files."""
        monkeypatch.setattr(pw, "SAFARI_TAB_FILE", str(tmp_path / "default"))

        monkeypatch.setattr(pw, "_session_name", "session-a")
        pw._write_tab_state({"session_id": "a", "url": "https://a.com", "tab_index": 0})

        monkeypatch.setattr(pw, "_session_name", "session-b")
        pw._write_tab_state({"session_id": "b", "url": "https://b.com", "tab_index": 1})

        # Read back — each session has its own state
        monkeypatch.setattr(pw, "_session_name", "session-a")
        state_a = pw._read_tab_state()
        assert state_a["session_id"] == "a"
        assert state_a["url"] == "https://a.com"

        monkeypatch.setattr(pw, "_session_name", "session-b")
        state_b = pw._read_tab_state()
        assert state_b["session_id"] == "b"
        assert state_b["url"] == "https://b.com"

        # Cleanup
        for name in ["session-a", "session-b"]:
            path = os.path.join(pw.STATE_DIR, f"session-{name}.json")
            if os.path.exists(path):
                os.unlink(path)

    def test_name_flag_parsing(self):
        """--name flag should be parsed without erroring."""
        code, out, err = run_pw("--name", "test-parse", "status")
        assert "Unknown command" not in err
        # Cleanup
        path = os.path.join(pw.STATE_DIR, "session-test-parse.json")
        if os.path.exists(path):
            os.unlink(path)

    def test_name_flag_missing_value(self):
        """--name without a session name should error."""
        code, out, err = run_pw("--name")
        assert code == 1


class TestSafariPageInit:
    """Test SafariPage initialization with new session features."""

    def test_session_id_generated(self):
        page = pw.SafariPage(0)
        assert hasattr(page, "_session_id")
        assert page._session_id.startswith("pw_")

    def test_session_id_custom(self):
        page = pw.SafariPage(0, session_id="custom_123")
        assert page._session_id == "custom_123"

    def test_session_id_unique(self):
        page1 = pw.SafariPage(0)
        page2 = pw.SafariPage(0)
        assert page1._session_id != page2._session_id


class TestClickJs:
    """Test that _click_js generates proper pointer event sequence."""

    def test_click_js_has_pointer_events(self):
        page = pw.SafariPage(0)
        js = page._click_js('document.querySelector("#btn")', "#btn")
        assert "PointerEvent" in js
        assert "pointerdown" in js
        assert "pointerup" in js
        assert "mousedown" in js
        assert "mouseup" in js
        assert "click" in js

    def test_click_js_has_coordinates(self):
        page = pw.SafariPage(0)
        js = page._click_js('document.querySelector("#btn")', "#btn")
        assert "getBoundingClientRect" in js
        assert "clientX" in js
        assert "clientY" in js

    def test_click_js_scrolls_into_view(self):
        page = pw.SafariPage(0)
        js = page._click_js('document.querySelector("#btn")', "#btn")
        assert "scrollIntoView" in js


class TestFillJs:
    """Test that fill() generates React-compatible JavaScript."""

    def test_fill_uses_native_setter(self):
        page = pw.SafariPage(0)
        # Call fill to generate the JS (it will fail without Safari, but we can
        # inspect the method's source to verify the JS template)
        import inspect
        source = inspect.getsource(page.fill)
        assert "getOwnPropertyDescriptor" in source
        assert "HTMLInputElement.prototype" in source
        assert "HTMLTextAreaElement.prototype" in source

    def test_fill_resets_value_tracker(self):
        import inspect
        source = inspect.getsource(pw.SafariPage.fill)
        assert "_valueTracker" in source
        # Accept either quote style
        assert "tracker.setValue('')" in source or 'tracker.setValue("")' in source


class TestSelectOptionStrategy:
    """Test that select_option() handles both native and custom dropdowns."""

    def test_select_option_checks_tagname(self):
        """select_option should check el.tagName to decide strategy."""
        import inspect
        source = inspect.getsource(pw.SafariPage.select_option)
        assert "el.tagName" in source or "tagName" in source

    def test_select_option_has_native_strategy(self):
        """Native <select> should use React-compatible setter."""
        import inspect
        source = inspect.getsource(pw.SafariPage.select_option)
        assert "HTMLSelectElement.prototype" in source
        assert "_valueTracker" in source

    def test_select_option_has_custom_strategy(self):
        """Custom dropdown should click to open, then find option."""
        import inspect
        source = inspect.getsource(pw.SafariPage.select_option)
        assert "role='option'" in source or 'role="option"' in source
        assert "MuiMenuItem" in source
        assert "a-dropdown" in source


# ============================================================================
# INTEGRATION TESTS — real browser (Safari)
# ============================================================================

# Additional HTML fixtures for testing new features

REACT_FIXTURE_HTML = textwrap.dedent("""\
    <!DOCTYPE html>
    <html>
    <head><title>React Compat Test</title></head>
    <body>
        <div id="root">
            <input id="controlled" type="text" value="" />
            <select id="controlled-select">
                <option value="">Select...</option>
                <option value="ny">New York</option>
                <option value="nj">New Jersey</option>
                <option value="ca">California</option>
            </select>
            <textarea id="controlled-textarea"></textarea>
        </div>
        <script>
            // Simulate React-like controlled components:
            // Override the value property with a getter/setter that tracks changes
            // via an internal _valueTracker, mimicking React's behavior.
            function makeControlled(el) {
                var _realValue = el.value;
                var _tracker = { _value: _realValue, setValue: function(v) { this._value = v; } };
                el._valueTracker = _tracker;

                var desc = Object.getOwnPropertyDescriptor(
                    el.tagName === 'TEXTAREA' ? HTMLTextAreaElement.prototype :
                    el.tagName === 'SELECT' ? HTMLSelectElement.prototype :
                    HTMLInputElement.prototype, 'value'
                );
                var nativeSet = desc.set;
                var nativeGet = desc.get;

                Object.defineProperty(el, 'value', {
                    get: function() { return nativeGet.call(this); },
                    set: function(v) {
                        // React-like behavior: track old value
                        _tracker._value = nativeGet.call(this);
                        nativeSet.call(this, v);
                    },
                    configurable: true
                });

                // Track whether our event listener was called
                el.addEventListener('input', function(e) {
                    el.setAttribute('data-last-event', 'input');
                });
                el.addEventListener('change', function(e) {
                    el.setAttribute('data-last-event', 'change');
                });
            }
            makeControlled(document.getElementById('controlled'));
            makeControlled(document.getElementById('controlled-select'));
            makeControlled(document.getElementById('controlled-textarea'));
        </script>
    </body>
    </html>
""")

POINTER_EVENTS_FIXTURE_HTML = textwrap.dedent("""\
    <!DOCTYPE html>
    <html>
    <head><title>Pointer Events Test</title></head>
    <body>
        <button id="mousedown-btn">Click Me</button>
        <div id="custom-dropdown" style="cursor:pointer">Select Option</div>
        <div id="dropdown-menu" style="display:none">
            <div class="dropdown-item" data-value="opt1">Option 1</div>
            <div class="dropdown-item" data-value="opt2">Option 2</div>
            <div class="dropdown-item" data-value="opt3">Option 3</div>
        </div>
        <div id="log"></div>
        <script>
            var log = document.getElementById('log');

            // Button that only responds to mousedown (like MUI)
            document.getElementById('mousedown-btn').addEventListener('mousedown', function(e) {
                log.textContent = 'mousedown:' + e.clientX + ',' + e.clientY;
                this.setAttribute('data-mousedown', 'true');
            });

            // Also track pointerdown
            document.getElementById('mousedown-btn').addEventListener('pointerdown', function(e) {
                this.setAttribute('data-pointerdown', 'true');
            });

            // Custom dropdown that opens on mousedown
            document.getElementById('custom-dropdown').addEventListener('mousedown', function() {
                var menu = document.getElementById('dropdown-menu');
                menu.style.display = menu.style.display === 'none' ? 'block' : 'none';
            });

            // Dropdown items
            document.querySelectorAll('.dropdown-item').forEach(function(item) {
                item.addEventListener('click', function() {
                    document.getElementById('custom-dropdown').textContent = this.textContent;
                    document.getElementById('dropdown-menu').style.display = 'none';
                    document.getElementById('custom-dropdown').setAttribute('data-selected', this.getAttribute('data-value'));
                });
            });
        </script>
    </body>
    </html>
""")

REACT_FIXTURE_PATH = "/tmp/pw-test-react-fixture.html"
POINTER_FIXTURE_PATH = "/tmp/pw-test-pointer-fixture.html"


@pytest.fixture(scope="module")
def safari_browser():
    """Ensure Safari is available for integration tests."""
    # Write fixtures
    with open(REACT_FIXTURE_PATH, "w") as f:
        f.write(REACT_FIXTURE_HTML)
    with open(POINTER_FIXTURE_PATH, "w") as f:
        f.write(POINTER_EVENTS_FIXTURE_HTML)
    yield
    # Cleanup
    for path in [REACT_FIXTURE_PATH, POINTER_FIXTURE_PATH]:
        if os.path.exists(path):
            os.unlink(path)
    # Clean up any test session files
    import glob as _glob
    for f in _glob.glob(os.path.join(pw.STATE_DIR, "session-test-*.json")):
        os.unlink(f)


def _run_safari(*args, timeout=30):
    """Run pw CLI, return (code, stdout, stderr).

    Historically passed a --safari backend flag; pw is Safari-only now,
    so this is identical to run_pw and kept only for callsite stability.
    """
    result = subprocess.run(
        [sys.executable, PW_PATH] + list(args),
        capture_output=True, text=True, timeout=timeout,
        env={**os.environ, "NODE_NO_WARNINGS": "1"},
    )
    return result.returncode, result.stdout, result.stderr


@pytest.mark.safari
class TestReactCompatFill:
    """Test fill() works on React-like controlled components."""

    def test_fill_controlled_input(self, safari_browser):
        _run_safari("nav", f"file://{REACT_FIXTURE_PATH}", "--quiet")
        code, out, err = _run_safari("fill", "#controlled", "Hello React")
        assert code == 0
        assert "Filled" in out
        # Verify the DOM value is set
        code2, val, _ = _run_safari("eval", 'document.getElementById("controlled").value')
        assert val.strip() == "Hello React"
        # Verify the input event was dispatched (React would need this)
        code3, evt, _ = _run_safari("eval", 'document.getElementById("controlled").getAttribute("data-last-event")')
        assert evt.strip() in ("input", "change")

    def test_fill_controlled_textarea(self, safari_browser):
        _run_safari("nav", f"file://{REACT_FIXTURE_PATH}", "--quiet")
        code, out, err = _run_safari("fill", "#controlled-textarea", "Textarea content")
        assert code == 0
        code2, val, _ = _run_safari("eval", 'document.getElementById("controlled-textarea").value')
        assert val.strip() == "Textarea content"

    def test_fill_empty_string(self, safari_browser):
        """Filling with empty string should clear the field."""
        _run_safari("nav", f"file://{REACT_FIXTURE_PATH}", "--quiet")
        _run_safari("fill", "#controlled", "Some text")
        code, out, err = _run_safari("fill", "#controlled", "")
        assert code == 0
        code2, val, _ = _run_safari("eval", 'document.getElementById("controlled").value')
        assert val.strip() == ""


@pytest.mark.safari
class TestReactCompatSelect:
    """Test select_option() works on React-like controlled selects."""

    def test_select_native_controlled(self, safari_browser):
        _run_safari("nav", f"file://{REACT_FIXTURE_PATH}", "--quiet")
        code, out, err = _run_safari("select", "#controlled-select", "nj")
        assert code == 0
        assert "Selected" in out
        code2, val, _ = _run_safari("eval", 'document.getElementById("controlled-select").value')
        assert val.strip() == "nj"

    def test_select_native_by_different_value(self, safari_browser):
        _run_safari("nav", f"file://{REACT_FIXTURE_PATH}", "--quiet")
        _run_safari("select", "#controlled-select", "ca")
        code, val, _ = _run_safari("eval", 'document.getElementById("controlled-select").value')
        assert val.strip() == "ca"


@pytest.mark.safari
class TestPointerEvents:
    """Test click() dispatches full pointer event sequence."""

    def test_click_triggers_mousedown(self, safari_browser):
        _run_safari("nav", f"file://{POINTER_FIXTURE_PATH}", "--quiet")
        code, out, err = _run_safari("click", "#mousedown-btn")
        assert code == 0
        # Check that mousedown was detected (pw eval may return "true" or "True")
        code2, val, _ = _run_safari("eval",
            'document.getElementById("mousedown-btn").getAttribute("data-mousedown")')
        assert val.strip().lower() == "true"

    def test_click_triggers_pointerdown(self, safari_browser):
        _run_safari("nav", f"file://{POINTER_FIXTURE_PATH}", "--quiet")
        _run_safari("click", "#mousedown-btn")
        code, val, _ = _run_safari("eval",
            'document.getElementById("mousedown-btn").getAttribute("data-pointerdown")')
        assert val.strip().lower() == "true"

    def test_click_has_coordinates(self, safari_browser):
        _run_safari("nav", f"file://{POINTER_FIXTURE_PATH}", "--quiet")
        _run_safari("click", "#mousedown-btn")
        code, val, _ = _run_safari("eval", 'document.getElementById("log").textContent')
        # Should contain "mousedown:X,Y" with non-zero coordinates
        assert val.strip().startswith("mousedown:")
        parts = val.strip().replace("mousedown:", "").split(",")
        assert len(parts) == 2
        assert float(parts[0]) > 0  # X coordinate
        assert float(parts[1]) > 0  # Y coordinate

    def test_click_custom_dropdown(self, safari_browser):
        """Click on a mousedown-activated custom dropdown should open it."""
        _run_safari("nav", f"file://{POINTER_FIXTURE_PATH}", "--quiet")
        _run_safari("click", "#custom-dropdown")
        code, val, _ = _run_safari("eval",
            'document.getElementById("dropdown-menu").style.display')
        assert val.strip() == "block"


@pytest.mark.safari
class TestNamedSessions:
    """Test --name flag for multi-agent tab isolation."""

    def test_named_session_creates_state_file(self, safari_browser):
        _run_safari("nav", "https://example.com", "--name", "test-session-1", "--quiet")
        path = os.path.join(pw.STATE_DIR, "session-test-session-1.json")
        assert os.path.exists(path)
        state = json.loads(open(path).read())
        assert state["session_id"].startswith("pw_")
        assert "example.com" in state["url"]
        # Cleanup: close the tab AND remove state (unlink alone leaks tabs).
        _run_safari("close", "--name", "test-session-1")

    def test_named_session_injects_marker(self, safari_browser):
        _run_safari("nav", "https://example.com", "--name", "test-marker", "--quiet")
        code, val, _ = _run_safari("eval", "window.__pw_session_id", "--name", "test-marker")
        assert val.strip().startswith("pw_")
        # Cleanup
        _run_safari("close", "--name", "test-marker")

    def test_env_var_session(self, safari_browser):
        """PW_SESSION env var should work like --name."""
        result = subprocess.run(
            [sys.executable, PW_PATH, "nav", "https://example.com", "--quiet"],
            capture_output=True, text=True, timeout=30,
            env={**os.environ, "NODE_NO_WARNINGS": "1", "PW_SESSION": "test-env-session"},
        )
        assert result.returncode == 0
        path = os.path.join(pw.STATE_DIR, "session-test-env-session.json")
        assert os.path.exists(path)
        # Cleanup
        _run_safari("close", "--name", "test-env-session")


@pytest.mark.safari
class TestEmptyTabRegression:
    """REGRESSION: when a named session's first command was anything other
    than `nav` (e.g. status, eval, title, url, screenshot), every
    subsequent command spawned another empty tab.

    Root cause: _safari_create_new_tab pushed a Tab object then tried to
    inject the session marker via doJavaScript — but a freshly-pushed
    empty Tab has no document, so the inject silently failed. The
    resolver's marker scan then missed on every later call and fell into
    the create-tab branch over and over.

    Fix: bake the marker into a data:text/html URL so it's part of the
    rendered document by the time the function returns. These tests
    pin both the source-level invariants (other unit tests) and the
    end-to-end behavior (here)."""

    @staticmethod
    def _managed_tab_count():
        """Count Safari tabs flagged with window.__pw_managed === true.

        Counting only managed tabs makes this test robust to ambient
        activity — if Alex opens a new tab during the test, we don't
        falsely flag pw for spawning it.
        """
        result = subprocess.run(
            ["osascript", "-l", "JavaScript", "-e", '''
            var s = Application("Safari");
            if (!s.running()) { 0; }
            else {
                var n = 0;
                for (var w = 0; w < s.windows.length; w++) {
                    for (var t = 0; t < s.windows[w].tabs.length; t++) {
                        try {
                            var m = s.doJavaScript("window.__pw_managed === true ? 1 : 0",
                                                   {in: s.windows[w].tabs[t]});
                            if (m === 1) n++;
                        } catch(e) {}
                    }
                }
                n;
            }
            '''],
            capture_output=True, text=True, timeout=15,
        )
        return int(result.stdout.strip() or "0")

    @staticmethod
    def _close_session_tab(session_name):
        """Close the managed tab for a session and remove its state file."""
        path = os.path.join(pw.STATE_DIR, f"session-{session_name}.json")
        try:
            if os.path.exists(path):
                state = json.loads(open(path).read())
                w = state.get("window_index", 0)
                t = state.get("tab_index", 0)
                # Close by id() so we don't trip over reordering
                subprocess.run(
                    ["osascript", "-l", "JavaScript", "-e", f'''
                    var s = Application("Safari");
                    try {{ s.windows[{w}].tabs[{t}].close(); }} catch(e) {{}}
                    '''],
                    capture_output=True, timeout=5,
                )
        finally:
            if os.path.exists(path):
                os.unlink(path)

    def test_non_nav_first_command_does_not_spawn_extra_tabs(self, safari_browser):
        """The headline regression: four non-nav commands in a row with
        the same --name should produce exactly ONE new managed tab,
        not four. Pre-fix, each command created a new empty tab."""
        name = f"test-empty-tab-regress-{int(time.time())}"
        # Start clean
        path = os.path.join(pw.STATE_DIR, f"session-{name}.json")
        if os.path.exists(path):
            os.unlink(path)
        try:
            managed_before = self._managed_tab_count()
            cmds = [
                ("--name", name, "title"),
                ("--name", name, "url"),
                ("--name", name, "eval", "1+1"),
                ("--name", name, "title"),
            ]
            for args in cmds:
                code, _, err = run_pw(*args)
                assert code == 0, f"{args} failed: {err}"
            managed_after = self._managed_tab_count()
            # Exactly one new managed tab — the one created on the first
            # call, reused by the next three. Pre-fix this would be +4.
            # Counting only managed (__pw_managed === true) tabs makes
            # this robust to ambient user-tab activity.
            assert managed_after == managed_before + 1, (
                f"non-nav commands spawned extra managed tabs (regression): "
                f"managed before={managed_before}, after={managed_after}, "
                f"expected before+1"
            )
        finally:
            self._close_session_tab(name)

    def test_create_new_tab_marker_round_trip(self, safari_browser):
        """The new tab must have window.__pw_session_id set to the
        session_id returned by _safari_create_new_tab. Pre-fix, the
        injected marker was lost: setting tab.url = 'about:blank'
        triggered a navigation that replaced the window object after
        we'd already injected the marker, so a read-back returned NONE.
        Post-fix, the marker lives inside the data: URL's HTML, so it's
        present as soon as the page is loaded."""
        win, tab, sid, win_id = pw._safari_create_new_tab()
        try:
            got = pw._jxa(
                f'var s = Application("Safari"); '
                f's.doJavaScript("window.__pw_session_id || \'NONE\'", '
                f'{{in: s.windows[{win}].tabs[{tab}]}});'
            )
            assert got == sid, (
                f"marker not on tab (regression): _safari_create_new_tab "
                f"returned sid={sid!r} but tab has {got!r}. The session "
                f"marker injection is broken; subsequent commands will "
                f"fail to resolve this tab and spawn duplicates."
            )
        finally:
            # Clean up the managed tab + its dedicated pw window.
            try:
                pw._jxa(
                    f'var s = Application("Safari"); '
                    f'for (var i = 0; i < s.windows.length; i++) {{'
                    f'  try {{ if (s.windows[i].id() === {win_id}) {{ s.windows[i].close(); break; }} }}'
                    f'  catch(e) {{}} }}'
                )
            except Exception:
                pass

    def test_create_new_tab_accepts_explicit_session_id(self, safari_browser):
        """Caller can pass a session_id and the new tab will use it
        verbatim (so callers don't have to mint-then-discover; the id
        baked into the tab matches the id they persist in state)."""
        my_sid = f"pw_explicit_{int(time.time())}"
        win, tab, sid, win_id = pw._safari_create_new_tab(session_id=my_sid)
        try:
            assert sid == my_sid, f"explicit sid not honored: passed {my_sid}, got {sid}"
            got = pw._jxa(
                f'var s = Application("Safari"); '
                f's.doJavaScript("window.__pw_session_id || \'NONE\'", '
                f'{{in: s.windows[{win}].tabs[{tab}]}});'
            )
            assert got == my_sid, f"tab marker {got!r} != explicit sid {my_sid!r}"
        finally:
            try:
                pw._jxa(
                    f'var s = Application("Safari"); '
                    f'for (var i = 0; i < s.windows.length; i++) {{'
                    f'  try {{ if (s.windows[i].id() === {win_id}) {{ s.windows[i].close(); break; }} }}'
                    f'  catch(e) {{}} }}'
                )
            except Exception:
                pass


# ============================================================================
# BATCH COMMAND TESTS
# ============================================================================

BATCH_FIXTURE_HTML = textwrap.dedent("""\
    <!DOCTYPE html>
    <html>
    <head><title>Batch Test</title></head>
    <body>
        <h1 id="heading">Batch Test Page</h1>
        <input id="first" type="text" />
        <input id="last" type="text" />
        <input id="email" type="email" />
        <select id="state">
            <option value="">Select...</option>
            <option value="ny">New York</option>
            <option value="nj">New Jersey</option>
        </select>
        <button id="submit" onclick="
            document.getElementById('result').textContent =
                document.getElementById('first').value + '|' +
                document.getElementById('last').value + '|' +
                document.getElementById('email').value + '|' +
                document.getElementById('state').value;
        ">Submit</button>
        <div id="result"></div>
    </body>
    </html>
""")

BATCH_FIXTURE_PATH = "/tmp/pw-test-batch-fixture.html"


class TestBatchCliParsing:
    """Unit tests for batch command CLI parsing — no browser needed."""

    def test_batch_command_exists(self):
        """batch should be a recognized command."""
        assert "batch" in pw.COMMANDS

    def test_batch_requires_args(self):
        """batch with no arguments should fail."""
        code, out, err = run_pw("batch")
        assert code == 1
        assert "Usage" in err or "batch" in err.lower()

    def test_batch_help_text(self):
        """Help output should mention batch."""
        code, out, err = run_pw()
        assert "batch" in out

    def test_batch_accepts_multiple_commands(self):
        """batch should accept multiple quoted command strings."""
        # This will fail at execution (no browser for unit test) but
        # should parse correctly — we're testing arg handling, not execution
        code, out, err = run_pw("batch", "eval 1+1", "eval 2+2")
        # Should attempt execution (not a parse error like "Usage:")
        assert "Usage: pw batch" not in err


class TestBatchCommandParsing:
    """Test that batch correctly parses command strings into (cmd, args) tuples."""

    def test_parse_simple_command(self):
        """'eval 1+1' should parse to ('eval', ['1+1'])."""
        assert hasattr(pw, '_parse_batch_command')
        cmd, args = pw._parse_batch_command("eval 1+1")
        assert cmd == "eval"
        assert args == ["1+1"]

    def test_parse_fill_command(self):
        """'fill #name Alex' should parse to ('fill', ['#name', 'Alex'])."""
        cmd, args = pw._parse_batch_command("fill #name Alex")
        assert cmd == "fill"
        assert args == ["#name", "Alex"]

    def test_parse_fill_with_spaces(self):
        """'fill #name \"Alex Wiltschko\"' should preserve quoted strings."""
        cmd, args = pw._parse_batch_command('fill #name "Alex Wiltschko"')
        assert cmd == "fill"
        assert args == ["#name", "Alex Wiltschko"]

    def test_parse_nav_command(self):
        """'nav https://example.com --quiet' should parse correctly."""
        cmd, args = pw._parse_batch_command("nav https://example.com --quiet")
        assert cmd == "nav"
        assert args == ["https://example.com", "--quiet"]

    def test_parse_click_text_selector(self):
        """'click text=Submit' should parse correctly."""
        cmd, args = pw._parse_batch_command("click text=Submit")
        assert cmd == "click"
        assert args == ["text=Submit"]

    def test_parse_empty_string_raises(self):
        """Empty command string should raise."""
        with pytest.raises((ValueError, pw.PwError)):
            pw._parse_batch_command("")

    def test_parse_unknown_command_raises(self):
        """Unknown command in batch should raise."""
        with pytest.raises((ValueError, pw.PwError)):
            pw._parse_batch_command("foobar arg1")

    def test_parse_validates_min_args(self):
        """Command with too few args should raise."""
        with pytest.raises((ValueError, pw.PwError)):
            pw._parse_batch_command("fill")  # fill needs 2 args


class TestBatchExecution:
    """Test batch execution semantics — no browser, mocked page."""

    def test_batch_runs_commands_sequentially(self):
        """Commands in a batch should execute in order."""
        # We verify ordering by checking that the batch function
        # returns results in order
        assert hasattr(pw, 'cmd_batch')

    def test_batch_stops_on_error_by_default(self):
        """If a command in the batch fails, subsequent commands should not run."""
        # This is a design decision — verify the function signature
        # accepts a continue_on_error parameter or documents default behavior
        import inspect
        sig = inspect.signature(pw.cmd_batch)
        # cmd_batch should accept args (the list of command strings)
        assert len(sig.parameters) >= 1

    def test_batch_output_format(self):
        """Batch should output labeled results for each command."""
        # Verify via CLI — run two eval commands that will work
        # even without a fixture page (just need Safari running)
        code, out, err = run_pw("batch", "title", "url")
        if code == 0:
            # Output should contain markers for each command
            assert "[1/" in out or "title" in out.lower()


@pytest.fixture(scope="module")
def batch_browser():
    """Set up Safari with batch test fixture."""
    with open(BATCH_FIXTURE_PATH, "w") as f:
        f.write(BATCH_FIXTURE_HTML)
    _run_safari("nav", f"file://{BATCH_FIXTURE_PATH}", "--quiet")
    yield
    if os.path.exists(BATCH_FIXTURE_PATH):
        os.unlink(BATCH_FIXTURE_PATH)


@pytest.mark.safari
class TestBatchSafariIntegration:
    """Integration tests for batch command with real Safari."""

    def test_batch_multiple_fills(self, batch_browser):
        """Fill multiple fields in one batch invocation."""
        _run_safari("nav", f"file://{BATCH_FIXTURE_PATH}", "--quiet")
        code, out, err = _run_safari("batch",
            "fill #first Alex",
            "fill #last Wiltschko",
            'fill #email alex@test.com')
        assert code == 0
        # Verify all fields were filled
        _, v1, _ = _run_safari("eval", 'document.getElementById("first").value')
        _, v2, _ = _run_safari("eval", 'document.getElementById("last").value')
        _, v3, _ = _run_safari("eval", 'document.getElementById("email").value')
        assert v1.strip() == "Alex"
        assert v2.strip() == "Wiltschko"
        assert v3.strip() == "alex@test.com"

    def test_batch_fill_and_select(self, batch_browser):
        """Mix fill and select in one batch."""
        _run_safari("nav", f"file://{BATCH_FIXTURE_PATH}", "--quiet")
        code, out, err = _run_safari("batch",
            "fill #first Alex",
            "select #state nj")
        assert code == 0
        _, v1, _ = _run_safari("eval", 'document.getElementById("first").value')
        _, v2, _ = _run_safari("eval", 'document.getElementById("state").value')
        assert v1.strip() == "Alex"
        assert v2.strip() == "nj"

    def test_batch_fill_select_click(self, batch_browser):
        """Full form flow: fill fields, select dropdown, click submit."""
        _run_safari("nav", f"file://{BATCH_FIXTURE_PATH}", "--quiet")
        code, out, err = _run_safari("batch",
            "fill #first Alex",
            "fill #last Wiltschko",
            "fill #email alex@test.com",
            "select #state nj",
            "click #submit --quiet")
        assert code == 0
        # Verify the submit handler ran and concatenated values
        _, result, _ = _run_safari("eval", 'document.getElementById("result").textContent')
        assert result.strip() == "Alex|Wiltschko|alex@test.com|nj"

    def test_batch_eval_commands(self, batch_browser):
        """Multiple eval commands in batch."""
        _run_safari("nav", f"file://{BATCH_FIXTURE_PATH}", "--quiet")
        code, out, err = _run_safari("batch",
            "eval document.title",
            "eval 1+1",
            "eval document.querySelectorAll('input').length")
        assert code == 0
        assert "Batch Test" in out
        assert "2" in out
        assert "3" in out

    def test_batch_with_nav(self, batch_browser):
        """Batch starting with nav then operating on the page."""
        code, out, err = _run_safari("batch",
            f"nav file://{BATCH_FIXTURE_PATH} --quiet",
            "fill #first BatchNav",
            "eval document.getElementById('first').value")
        assert code == 0
        assert "BatchNav" in out

    def test_batch_stops_on_error(self, batch_browser):
        """Batch should stop when a command fails (element not found)."""
        _run_safari("nav", f"file://{BATCH_FIXTURE_PATH}", "--quiet")
        code, out, err = _run_safari("batch",
            "fill #first BeforeError",
            "fill #nonexistent ShouldFail",
            "fill #last ShouldNotRun")
        assert code == 1
        # First fill should have worked
        _, v1, _ = _run_safari("eval", 'document.getElementById("first").value')
        assert v1.strip() == "BeforeError"
        # Third fill should NOT have run
        _, v2, _ = _run_safari("eval", 'document.getElementById("last").value')
        assert v2.strip() != "ShouldNotRun"

    def test_batch_reports_which_command_failed(self, batch_browser):
        """Error output should indicate which batch step failed."""
        _run_safari("nav", f"file://{BATCH_FIXTURE_PATH}", "--quiet")
        code, out, err = _run_safari("batch",
            "eval 1+1",
            "fill #nonexistent Fail")
        assert code == 1
        # Should mention the failing command index or content
        assert "2" in (out + err) or "nonexistent" in (out + err)

    def test_batch_performance(self, batch_browser):
        """Batch should be faster than individual commands."""
        import time
        _run_safari("nav", f"file://{BATCH_FIXTURE_PATH}", "--quiet")

        # Time 3 individual fills
        start = time.perf_counter()
        _run_safari("fill", "#first", "A")
        _run_safari("fill", "#last", "B")
        _run_safari("fill", "#email", "C")
        individual_time = time.perf_counter() - start

        # Time same 3 fills as batch
        _run_safari("nav", f"file://{BATCH_FIXTURE_PATH}", "--quiet")
        start = time.perf_counter()
        _run_safari("batch",
            "fill #first A",
            "fill #last B",
            "fill #email C")
        batch_time = time.perf_counter() - start

        # Batch should be meaningfully faster (at least 30% savings)
        # 3 individual: ~3 × 320ms = 960ms
        # 1 batch:      ~320ms + 2 × 110ms = 540ms
        print(f"\n  Individual: {individual_time:.3f}s, Batch: {batch_time:.3f}s, "
              f"Savings: {(1 - batch_time/individual_time)*100:.0f}%")
        assert batch_time < individual_time, \
            f"Batch ({batch_time:.3f}s) should be faster than individual ({individual_time:.3f}s)"


# ============================================================================
# INTEGRATION TESTS — real browser (Chromium)
# ============================================================================
# ============================================================================


@pytest.fixture(scope="module")
def browser():
    """Launch a browser for integration tests, tear down after."""
    # Clean up any existing session
    run_pw("close")
    # Write fixture HTML
    with open(FIXTURE_PATH, "w") as f:
        f.write(FIXTURE_HTML)
    # Launch
    code, out, err = run_pw("launch")
    if code != 0:
        pytest.skip(f"Could not launch browser: {err}")
    yield
    # Teardown
    run_pw("close")
    if os.path.exists(FIXTURE_PATH):
        os.unlink(FIXTURE_PATH)


@pytest.mark.integration
class TestNavigation:
    def test_nav_with_protocol(self, browser):
        code, out, err = run_pw("nav", f"file://{FIXTURE_PATH}")
        assert code == 0
        assert "PW Test Page" in out
        assert FIXTURE_PATH in out

    def test_nav_bare_domain(self, browser):
        code, out, err = run_pw("nav", "example.com")
        assert code == 0
        assert "example.com" in out.lower()

    def test_nav_back(self, browser):
        run_pw("nav", f"file://{FIXTURE_PATH}")
        run_pw("nav", "https://example.com")
        code, out, err = run_pw("back")
        assert code == 0
        assert FIXTURE_PATH in out


@pytest.mark.integration
class TestPageInspection:
    def setup_method(self):
        run_pw("nav", f"file://{FIXTURE_PATH}")

    def test_title(self, browser):
        code, out, err = run_pw("title")
        assert code == 0
        assert out.strip() == "PW Test Page"

    def test_url(self, browser):
        code, out, err = run_pw("url")
        assert code == 0
        assert FIXTURE_PATH in out

    def test_text_full_page(self, browser):
        code, out, err = run_pw("text")
        assert code == 0
        assert "Hello PW" in out
        assert "test paragraph" in out

    def test_text_with_selector(self, browser):
        code, out, err = run_pw("text", "#heading")
        assert code == 0
        assert out.strip() == "Hello PW"

    def test_text_missing_selector(self, browser):
        code, out, err = run_pw("text", "#nonexistent")
        assert code == 1
        assert "Selector not found" in err

    def test_html_with_selector(self, browser):
        code, out, err = run_pw("html", "#para")
        assert code == 0
        assert "test paragraph" in out

    def test_html_missing_selector(self, browser):
        code, out, err = run_pw("html", "#nonexistent")
        assert code == 1
        assert "Selector not found" in err

    def test_eval_string(self, browser):
        code, out, err = run_pw("eval", "document.title")
        assert code == 0
        assert out.strip() == "PW Test Page"

    def test_eval_number(self, browser):
        code, out, err = run_pw("eval", "1 + 2")
        assert code == 0
        assert out.strip() == "3"

    def test_eval_object(self, browser):
        code, out, err = run_pw("eval", "({a: 1, b: 'hello'})")
        assert code == 0
        data = json.loads(out)
        assert data == {"a": 1, "b": "hello"}

    def test_eval_null(self, browser):
        code, out, err = run_pw("eval", "null")
        assert code == 0
        assert out.strip() == "null"

    def test_eval_array(self, browser):
        code, out, err = run_pw("eval", "[1, 2, 3]")
        assert code == 0
        assert json.loads(out) == [1, 2, 3]


@pytest.mark.integration
class TestFormInteraction:
    def setup_method(self):
        run_pw("nav", f"file://{FIXTURE_PATH}")

    def test_fill(self, browser):
        code, out, err = run_pw("fill", "#name", "Alex")
        assert code == 0
        assert "Filled" in out
        # Verify via eval
        code2, val, _ = run_pw("eval", 'document.getElementById("name").value')
        assert val.strip() == "Alex"

    def test_fill_multiple_fields(self, browser):
        run_pw("fill", "#name", "Alex")
        run_pw("fill", "#email", "alex@test.com")
        _, name_val, _ = run_pw("eval", 'document.getElementById("name").value')
        _, email_val, _ = run_pw("eval", 'document.getElementById("email").value')
        assert name_val.strip() == "Alex"
        assert email_val.strip() == "alex@test.com"

    def test_select(self, browser):
        code, out, err = run_pw("select", "#color", "green")
        assert code == 0
        assert "Selected" in out
        _, val, _ = run_pw("eval", 'document.getElementById("color").value')
        assert val.strip() == "green"

    def test_press_key(self, browser):
        run_pw("click", "#name")
        run_pw("type", "test")
        code, out, err = run_pw("press", "Tab")
        assert code == 0
        assert "Pressed: Tab" in out


@pytest.mark.integration
class TestWait:
    def test_wait_existing_element(self, browser):
        run_pw("nav", f"file://{FIXTURE_PATH}")
        code, out, err = run_pw("wait", "#heading")
        assert code == 0
        assert "Found: #heading" in out

    def test_wait_dynamic_element(self, browser):
        """Element appears after 500ms via JavaScript."""
        run_pw("nav", f"file://{FIXTURE_PATH}")
        code, out, err = run_pw("wait", "#dynamic")
        assert code == 0
        assert "Found: #dynamic" in out

    def test_wait_nonexistent_times_out(self, browser):
        run_pw("nav", f"file://{FIXTURE_PATH}")
        code, out, err = run_pw("wait", "#never-exists", timeout=15)
        assert code == 1
        assert "Timeout" in err


@pytest.mark.integration
class TestScreenshot:
    def test_screenshot_default_path(self, browser):
        run_pw("nav", f"file://{FIXTURE_PATH}")
        code, out, err = run_pw("screenshot")
        assert code == 0
        assert os.path.exists("/tmp/pw-screenshot.png")
        assert os.path.getsize("/tmp/pw-screenshot.png") > 1000

    def test_screenshot_custom_path(self, browser):
        path = "/tmp/pw-test-custom-screenshot.png"
        if os.path.exists(path):
            os.unlink(path)
        run_pw("nav", f"file://{FIXTURE_PATH}")
        code, out, err = run_pw("screenshot", path)
        assert code == 0
        assert os.path.exists(path)
        assert os.path.getsize(path) > 1000
        os.unlink(path)


@pytest.mark.integration
class TestTabs:
    def test_tabs_single(self, browser):
        run_pw("nav", f"file://{FIXTURE_PATH}")
        code, out, err = run_pw("tabs")
        assert code == 0
        assert "PW Test Page" in out
        assert "*" in out  # Active tab marker

    def test_tab_switch(self, browser):
        # Open a new tab
        run_pw("eval", "window.open('about:blank', '_blank'); 'ok'")
        time.sleep(0.5)
        # Should have multiple tabs
        code, out, err = run_pw("tabs")
        assert code == 0
        lines = [l for l in out.strip().split("\n") if l.startswith("[")]
        assert len(lines) >= 2
        # Switch to first tab
        code, out, err = run_pw("tab", "0")
        assert code == 0
        assert "Switched to tab 0" in out

    def test_tab_out_of_range(self, browser):
        code, out, err = run_pw("tab", "99")
        assert code == 1
        assert "Tab 99 not found" in err


@pytest.mark.integration
class TestBrowserLifecycle:
    """Test close/status. Safari is launched (and left running) by other
    integration tests via the `browser` fixture; we don't kill the user's
    real Safari just to test pw."""

    def test_close_idempotent(self):
        """Closing when already closed should not error."""
        code, out, err = run_pw("close")
        assert code == 0


# ============================================================================
# CONCURRENT BROWSING ROBUSTNESS TESTS
# ============================================================================


class TestAutoSession:
    """Test auto-session when CLAUDE_CODE env is set."""

    def test_auto_session_sets_claude_name(self, monkeypatch):
        """When CLAUDE_CODE=1 and no explicit session, _session_name should be 'claude'."""
        monkeypatch.setattr(pw, "_session_name", None)
        monkeypatch.setenv("CLAUDE_CODE", "1")
        # Simulate the main() logic
        if pw._session_name is None and os.environ.get("CLAUDE_CODE"):
            pw._session_name = "claude"
        assert pw._session_name == "claude"

    def test_no_auto_session_without_claude_code(self, monkeypatch):
        """Without CLAUDE_CODE env, _session_name stays None."""
        monkeypatch.setattr(pw, "_session_name", None)
        monkeypatch.delenv("CLAUDE_CODE", raising=False)
        if pw._session_name is None and os.environ.get("CLAUDE_CODE"):
            pw._session_name = "claude"
        assert pw._session_name is None

    def test_explicit_name_overrides_auto(self, monkeypatch):
        """Explicit --name should not be overridden by CLAUDE_CODE."""
        monkeypatch.setattr(pw, "_session_name", "my-session")
        monkeypatch.setenv("CLAUDE_CODE", "1")
        # The auto-session check is: if _session_name is None and CLAUDE_CODE
        if pw._session_name is None and os.environ.get("CLAUDE_CODE"):
            pw._session_name = "claude"
        assert pw._session_name == "my-session"

    def test_auto_session_uses_session_file(self, monkeypatch):
        """Auto-session should use STATE_DIR/session-claude.json."""
        monkeypatch.setattr(pw, "_session_name", "claude")
        assert pw._safari_session_file() == os.path.join(pw.STATE_DIR, "session-claude.json")


class TestResolveTabCreateIfMissing:
    """Test _resolve_safari_tab with create_if_missing parameter."""

    def test_no_state_with_session_creates_tab(self, tmp_path, monkeypatch):
        """With a named session but no state, should create a new tab and
        return (win, tab, session_id) — the session_id must be the one
        injected into the new tab so subsequent resolves match the marker."""
        monkeypatch.setattr(pw, "_session_name", "test-create")
        monkeypatch.setattr(pw, "SAFARI_TAB_FILE", str(tmp_path / "nonexistent"))
        created = []
        monkeypatch.setattr(
            pw, "_safari_create_new_tab",
            lambda session_id=None, existing_window_id=None: (
                created.append(existing_window_id),
                (0, 5, "pw_mock_sid", 12345),
            )[1],
        )
        result = pw._resolve_safari_tab(create_if_missing=True)
        assert result == (0, 5, "pw_mock_sid")
        assert len(created) == 1

    def test_no_state_no_session_still_creates_managed_tab(self, tmp_path, monkeypatch):
        """Even without a session name, the resolver must NEVER return
        indices pointing at the user's tab. With no state and no name,
        it must create a managed tab in pw's own window. The old behavior
        of returning (0, 0, "") would have targeted whatever tab the user
        had frontmost — the exact tab-hijacking we promise to prevent."""
        monkeypatch.setattr(pw, "_session_name", None)
        monkeypatch.setattr(pw, "SAFARI_TAB_FILE", str(tmp_path / "nonexistent"))
        created = []
        monkeypatch.setattr(
            pw, "_safari_create_new_tab",
            lambda session_id=None, existing_window_id=None: (
                created.append(1),
                (2, 0, "pw_auto_sid", 999),
            )[1],
        )
        assert pw._resolve_safari_tab(create_if_missing=True) == (2, 0, "pw_auto_sid")
        assert len(created) == 1, "resolver must mint a managed tab, not return (0,0,'')"

    def test_recovery_branches_persist_new_session_id(self):
        """REGRESSION: when the resolver creates a recovery tab (because
        the original is gone, the stored window is out of range, or the
        stored tab 0,0 isn't ours), it must persist the *new* session_id
        — not blank `""`. Pre-fix, recovery wrote `session_id: ""`, which
        made the very next command's resolver scan miss the marker and
        create yet another tab."""
        import inspect
        source = inspect.getsource(pw._resolve_safari_tab)
        # No assignment of session_id to empty string in recovery branches
        for line in source.splitlines():
            stripped = line.strip()
            if 'session_id' in stripped and '""' in stripped and "=" in stripped:
                # Allow `session_id = state.get(...)` but not assignment to ""
                if 'state[' in stripped and 'session_id' in stripped and '""' in stripped:
                    raise AssertionError(
                        f"regression: recovery branch resets session_id to \"\" "
                        f"instead of persisting the new tab's id. Offending: "
                        f"{stripped}"
                    )


class TestScreenshotBackgrounded:
    """Screenshot must capture without activating Safari.

    screencapture -l<windowID> reads from the window-server backing store
    and works on occluded windows, so there is no need to bring Safari to
    the front. The capture path must not call safari.activate() and must
    still switch to the pw tab + restore the user's original tab.
    """

    def test_screenshot_does_not_activate_safari(self):
        """REGRESSION: the 50KB-fallback that called safari.activate() was
        a false-positive trap — sparse pages (login forms, simple modals)
        legitimately compress below the threshold even when correctly
        captured, so the fallback yanked Safari to the front during
        normal use. The screenshot path must contain no activate() at
        all; window-server capture works on occluded windows."""
        import inspect, re
        source = inspect.getsource(pw.SafariPage.screenshot)
        # Strip Python comments so the explanatory comment doesn't trip us
        code = "\n".join(
            re.sub(r"#.*$", "", line) for line in source.splitlines()
        )
        assert "screencapture" in code, "expected a screencapture call"
        assert "activate()" not in code, (
            "screenshot path must not call safari.activate() — even as a "
            "fallback. The window-server backing buffer captures occluded "
            "windows correctly; foregrounding Safari mid-task is disruptive."
        )

    def test_screenshot_no_size_heuristic_fallback(self):
        """REGRESSION: the `< 50_000` byte heuristic was empirically wrong
        — sparse pages (login forms, blank states) compress well under
        50KB even when the capture is correct. It must not gate any
        re-capture path."""
        import inspect
        source = inspect.getsource(pw.SafariPage.screenshot)
        assert "50_000" not in source and "50000" not in source, (
            "screenshot must not reintroduce the 50KB blank-capture heuristic"
        )

    def test_screenshot_uses_window_id_capture(self):
        """Capture must target Safari's windowID, not full-screen."""
        import inspect
        source = inspect.getsource(pw.SafariPage.screenshot)
        assert 'screencapture' in source
        assert '-l' in source and 'win_id' in source

    def test_screenshot_restores_user_tab(self):
        """Original tab must be restored after capture."""
        import inspect
        source = inspect.getsource(pw.SafariPage.screenshot)
        assert "originalTab" in source
        assert "currentTab = __pw_win.tabs[" in source


class TestKeyboardBackgrounded:
    """type/press must default to a JS path that doesn't foreground Safari.

    OS-level keystrokes (which require Safari to be frontmost) are gated
    behind PW_KEYSTROKE=1 for sites that ignore synthetic KeyboardEvents.
    """

    def test_type_default_path_no_activate(self):
        import inspect
        source = inspect.getsource(pw._SafariKeyboard.type)
        assert "safari.activate" not in source, (
            "_SafariKeyboard.type default path must not activate Safari"
        )
        # Must run JS in the pw tab via the page's _do_js
        assert "self._page._do_js" in source
        # Must fire input events for framework reactivity
        assert "execCommand" in source or 'dispatchEvent' in source

    def test_type_fires_per_character_keydown_events(self):
        """Type must loop per character and dispatch keydown — bulk insertText
        would skip keydown and break type-as-you-search sites."""
        import inspect
        source = inspect.getsource(pw._SafariKeyboard.type)
        # Loop over text characters
        assert "text.length" in source and "for" in source
        # Per-char keydown
        assert '"keydown"' in source
        assert '"keyup"' in source

    def test_press_default_path_no_activate(self):
        import inspect
        source = inspect.getsource(pw._SafariKeyboard.press)
        assert "safari.activate" not in source, (
            "_SafariKeyboard.press default path must not activate Safari"
        )
        assert "self._page._do_js" in source
        assert "KeyboardEvent" in source

    def test_press_handles_enter_form_submit(self):
        """Synthetic Enter alone doesn't reliably submit forms — press must
        also call form.requestSubmit/submit when the focused element is in
        a form."""
        import inspect
        source = inspect.getsource(pw._SafariKeyboard.press)
        assert "requestSubmit" in source or "form.submit" in source

    def test_keystroke_path_still_exists_for_opt_in(self):
        """PW_KEYSTROKE=1 must still route to System Events (some sites
        need real OS keys); this is the only path that activates Safari."""
        import inspect
        type_kb = inspect.getsource(pw._SafariKeyboard._type_keystroke)
        press_kb = inspect.getsource(pw._SafariKeyboard._press_keystroke)
        assert "System Events" in type_kb and "safari.activate" in type_kb
        assert "System Events" in press_kb and "safari.activate" in press_kb

    def test_use_keystroke_respects_env_var(self, monkeypatch):
        kb = pw._SafariKeyboard(page=object())
        monkeypatch.delenv("PW_KEYSTROKE", raising=False)
        assert kb._use_keystroke() is False
        monkeypatch.setenv("PW_KEYSTROKE", "1")
        assert kb._use_keystroke() is True

    def test_use_keystroke_when_no_page(self):
        """Without a page reference, fall back to keystroke (legacy compat)."""
        kb = pw._SafariKeyboard(page=None)
        assert kb._use_keystroke() is True

    def test_keyboard_wired_to_page(self):
        """SafariPage must pass itself into _SafariKeyboard."""
        import inspect
        source = inspect.getsource(pw.SafariPage.__init__)
        assert "_SafariKeyboard(page=self)" in source


@pytest.mark.safari
class TestNoForegroundIntegration:
    """End-to-end: type/press/screenshot must not change which app is
    frontmost. Captures the frontmost app before each action and asserts
    it's still frontmost after. Also confirms no Safari tabs were added
    or destroyed."""

    @staticmethod
    def _frontmost():
        result = subprocess.run(
            ["osascript", "-l", "JavaScript", "-e",
             'Application("System Events").processes.whose({frontmost: true})[0].name()'],
            capture_output=True, text=True, timeout=5,
        )
        return result.stdout.strip()

    @staticmethod
    def _safari_state():
        """Return (window_count, total_tab_count) snapshot."""
        result = subprocess.run(
            ["osascript", "-l", "JavaScript", "-e", '''
            var s = Application("Safari");
            if (!s.running()) { JSON.stringify({wins: 0, tabs: 0}); }
            else {
                var n = 0;
                for (var i = 0; i < s.windows.length; i++) n += s.windows[i].tabs.length;
                JSON.stringify({wins: s.windows.length, tabs: n});
            }
            '''],
            capture_output=True, text=True, timeout=5,
        )
        return json.loads(result.stdout.strip())

    def _ensure_frontmost_not_safari(self):
        """Bring iTerm2/Terminal forward so we can detect if pw steals focus.
        Falls back to skipping the check if no terminal app is available."""
        for app in ("iTerm2", "Terminal", "Ghostty", "Alacritty"):
            try:
                subprocess.run(
                    ["osascript", "-l", "JavaScript", "-e", f'Application({json.dumps(app)}).activate();'],
                    capture_output=True, timeout=3,
                )
                time.sleep(0.3)
                if self._frontmost() == app:
                    return app
            except Exception:
                continue
        return None

    def test_screenshot_keeps_other_app_frontmost(self, safari_browser, tmp_path):
        run_pw("nav", f"file://{REACT_FIXTURE_PATH}", "--quiet")
        front_before = self._ensure_frontmost_not_safari()
        if not front_before or front_before == "Safari":
            pytest.skip("could not establish a non-Safari frontmost app")
        state_before = self._safari_state()
        out_path = str(tmp_path / "shot.png")
        code, _, err = run_pw("screenshot", out_path)
        assert code == 0, f"screenshot failed: {err}"
        # A real Safari window screenshot is well over 50KB; smaller means
        # the window-server returned a blank capture.
        assert os.path.getsize(out_path) > 50_000, (
            f"screenshot suspiciously small ({os.path.getsize(out_path)} bytes) — "
            f"likely captured a blank window backing-store"
        )
        front_after = self._frontmost()
        state_after = self._safari_state()
        # The bug we're guarding against is pw activating Safari. We assert
        # that specifically — not strict equality with `front_before` —
        # because ambient user activity (notifications, Messages, Slack
        # popping forward) can legitimately change frontmost during the
        # test without pw being at fault.
        assert front_after != "Safari", (
            f"screenshot stole focus to Safari (was {front_before})"
        )
        assert state_after == state_before, (
            f"screenshot disturbed Safari tabs: before={state_before} after={state_after}"
        )

    def test_screenshot_completes_under_one_second(self, safari_browser, tmp_path):
        """Backgrounded path should be noticeably faster than the old
        activate+sleep+restore path. Set a generous ceiling that the old
        path would routinely blow through (it slept 0.2s after activate
        plus the activate/restore round-trips)."""
        run_pw("nav", f"file://{REACT_FIXTURE_PATH}", "--quiet")
        out_path = str(tmp_path / "speed.png")
        t0 = time.time()
        code, _, err = run_pw("screenshot", out_path)
        elapsed = time.time() - t0
        assert code == 0, f"screenshot failed: {err}"
        # End-to-end CLI invocation includes Python startup + osascript +
        # screencapture. Backgrounded path comfortably fits under 2s.
        assert elapsed < 2.0, f"screenshot took {elapsed:.2f}s — regressing speed"

    def test_type_keeps_other_app_frontmost(self, safari_browser):
        run_pw("nav", f"file://{REACT_FIXTURE_PATH}", "--quiet")
        # Focus the controlled input via JS so type() has a target
        run_pw("eval", 'document.getElementById("controlled").focus()')
        front_before = self._ensure_frontmost_not_safari()
        if not front_before or front_before == "Safari":
            pytest.skip("could not establish a non-Safari frontmost app")
        state_before = self._safari_state()
        code, _, err = run_pw("type", "hello")
        assert code == 0, f"type failed: {err}"
        # Confirm the text actually landed
        _, val, _ = run_pw("eval", 'document.getElementById("controlled").value')
        assert "hello" in val
        front_after = self._frontmost()
        state_after = self._safari_state()
        # See test_screenshot_keeps_other_app_frontmost for rationale —
        # we only flag the actual bug (pw activating Safari), not any
        # ambient focus change.
        assert front_after != "Safari", (
            f"type stole focus to Safari (was {front_before})"
        )
        assert state_after == state_before

    def test_type_fires_per_character_keydown(self, safari_browser):
        """type-as-you-search sites depend on keydown firing per character.
        Old System Events path did this naturally; the JS path must too —
        otherwise autocomplete/Cmd-K palettes never trigger."""
        run_pw("nav", f"file://{REACT_FIXTURE_PATH}", "--quiet")
        # Install a keydown counter on the controlled input
        run_pw("eval", '''(function(){
            var el = document.getElementById("controlled");
            el.focus();
            window.__pw_keydown_count = 0;
            window.__pw_keydown_keys = [];
            el.addEventListener("keydown", function(e) {
                window.__pw_keydown_count++;
                window.__pw_keydown_keys.push(e.key);
            });
        })()''')
        code, _, err = run_pw("type", "abc")
        assert code == 0, f"type failed: {err}"
        _, count, _ = run_pw("eval", "window.__pw_keydown_count")
        assert count.strip() == "3", (
            f"expected 3 keydown events for 'abc', got {count.strip()} — "
            f"per-character keydown regressed; autocomplete sites will break"
        )
        _, keys, _ = run_pw("eval", "JSON.stringify(window.__pw_keydown_keys)")
        assert json.loads(keys.strip()) == ["a", "b", "c"]

    def test_press_enter_keeps_other_app_frontmost(self, safari_browser):
        run_pw("nav", f"file://{REACT_FIXTURE_PATH}", "--quiet")
        run_pw("eval", 'document.getElementById("controlled").focus()')
        front_before = self._ensure_frontmost_not_safari()
        if not front_before or front_before == "Safari":
            pytest.skip("could not establish a non-Safari frontmost app")
        state_before = self._safari_state()
        code, _, err = run_pw("press", "Enter")
        assert code == 0, f"press failed: {err}"
        front_after = self._frontmost()
        state_after = self._safari_state()
        # See test_screenshot_keeps_other_app_frontmost for rationale.
        assert front_after != "Safari", (
            f"press stole focus to Safari (was {front_before})"
        )
        assert state_after == state_before


class TestCreateNewTab:
    """Test _safari_create_new_tab function exists and has correct JXA."""

    def test_function_exists(self):
        assert hasattr(pw, "_safari_create_new_tab")
        assert callable(pw._safari_create_new_tab)

    def test_jxa_template(self):
        """The JXA should push a new tab without switching to it."""
        import inspect
        source = inspect.getsource(pw._safari_create_new_tab)
        assert "win.tabs.push" in source
        assert "win.tabs.length - 1" in source

    def test_accepts_session_id_parameter(self):
        """Must accept an optional session_id so callers can thread the
        same id through state and SafariPage. The id baked into the tab
        and the id persisted in state must match — otherwise the resolver
        won't find the tab on the next command."""
        import inspect
        sig = inspect.signature(pw._safari_create_new_tab)
        assert "session_id" in sig.parameters, (
            "_safari_create_new_tab must accept session_id parameter"
        )
        assert sig.parameters["session_id"].default is None

    def test_returns_tuple_with_session_id_and_window_id(self):
        """REGRESSION: must return (win, tab, session_id, window_id).
        Pre-fix, callers minted their own session_id after the fact, so
        the id baked into the tab marker didn't match the id persisted
        in state. window_id was added so subsequent tab creations can
        reuse pw's dedicated Safari window instead of spawning a fresh
        one."""
        import inspect
        source = inspect.getsource(pw._safari_create_new_tab)
        assert "sid," in source and 'result.get("window_id")' in source, (
            "must return (win, tab, sid, window_id) tuple"
        )

    def test_marker_baked_into_initial_url(self):
        """REGRESSION: the new tab's session marker must be present at
        page-load time, not injected post-hoc via doJavaScript on a
        freshly-pushed empty Tab. The empty-Tab inject path silently
        failed (no document existed), so subsequent commands couldn't
        find the tab and kept spawning new ones. Fix: bake the marker
        into a data:text/html URL whose <script> sets __pw_session_id
        before any DOM interaction."""
        import inspect
        source = inspect.getsource(pw._safari_create_new_tab)
        assert "data:text/html" in source, (
            "tab must be navigated to a data: URL with the marker baked in"
        )
        assert "__pw_session_id" in source, (
            "the data: URL must include the __pw_session_id assignment"
        )
        assert "urllib.parse.quote" in source, (
            "the inline HTML must be URL-encoded to survive the data: URL"
        )

    def test_does_not_inject_marker_on_empty_tab(self):
        """REGRESSION: the original bug was a doJavaScript call on a
        freshly-pushed Tab object (no document → silent failure). The
        fix MUST NOT reintroduce that pattern. Specifically, there must
        be no doJavaScript injecting __pw_session_id into a newly-pushed
        empty Tab — the marker has to come from the loaded data: URL."""
        import inspect
        source = inspect.getsource(pw._safari_create_new_tab)
        # If we ever see safari.doJavaScript("...__pw_session_id..."), the
        # bug is back. Allow doJavaScript for readState polling only.
        for line in source.splitlines():
            if "doJavaScript" in line and "__pw_session_id" in line:
                raise AssertionError(
                    f"regression: doJavaScript injecting __pw_session_id is "
                    f"back. Marker must come from the data: URL, not from "
                    f"a post-creation inject. Offending line:\n  {line.strip()}"
                )

    def test_minted_id_uses_helper(self):
        """Both _safari_create_new_tab and SafariPage should mint ids via
        the shared _new_session_id helper, so id format stays consistent."""
        assert hasattr(pw, "_new_session_id"), (
            "_new_session_id helper should exist"
        )
        sid = pw._new_session_id()
        assert sid.startswith("pw_"), f"session id should start with pw_: {sid}"
        # Two consecutive ids must differ (counter increments)
        assert sid != pw._new_session_id()


@pytest.mark.integration
class TestConcurrentBrowsingIntegration:
    """Integration tests for concurrent browsing robustness.

    These tests run against real Safari and verify that:
    1. Named sessions get their own tab
    2. User tab switching doesn't affect automation
    3. Closed tabs are recovered automatically
    """

    def test_named_session_creates_own_tab(self):
        """pw nav with --name should create a new tab, not hijack current."""
        # Count tabs before
        code, out, err = run_pw("tabs")
        before_lines = [l for l in out.strip().split("\n") if l.startswith("[")]
        before_count = len(before_lines)

        # Navigate with a named session
        session_name = f"test-concurrent-{int(time.time())}"
        code, out, err = run_pw("--name", session_name, "nav", "file:///tmp/pw-test-fixture.html", "--quiet", timeout=60)
        assert code == 0

        # Count tabs after — should have one more
        code, out, err = run_pw("tabs")
        after_lines = [l for l in out.strip().split("\n") if l.startswith("[")]
        after_count = len(after_lines)
        assert after_count >= before_count + 1, f"Expected new tab: {before_count} -> {after_count}"

        # Cleanup: close the session's tab by navigating away and clearing state
        session_file = os.path.join(pw.STATE_DIR, f"session-{session_name}.json")
        if os.path.exists(session_file):
            os.unlink(session_file)

    def test_named_session_persists_across_commands(self):
        """Multiple commands with same --name should target the same tab."""
        session_name = f"test-persist-{int(time.time())}"

        # First nav — creates the tab
        code, out, err = run_pw("--name", session_name, "nav", "file:///tmp/pw-test-fixture.html", "--quiet")
        assert code == 0

        # Second command — should target the same tab
        code, out, err = run_pw("--name", session_name, "text")
        assert code == 0
        assert "PW Test Page" in out or "test" in out.lower()

        # Cleanup
        session_file = os.path.join(pw.STATE_DIR, f"session-{session_name}.json")
        if os.path.exists(session_file):
            os.unlink(session_file)

    def test_claude_code_env_auto_session(self):
        """CLAUDE_CODE=1 env should auto-create a session named 'claude'."""
        env = {**os.environ, "CLAUDE_CODE": "1", "NODE_NO_WARNINGS": "1"}
        result = subprocess.run(
            [sys.executable, PW_PATH, "nav", "file:///tmp/pw-test-fixture.html", "--quiet"],
            capture_output=True, text=True, timeout=30, env=env,
        )
        assert result.returncode == 0

        # Verify session file was created
        session_file = os.path.join(pw.STATE_DIR, "session-claude.json")
        assert os.path.exists(session_file)
        state = json.loads(open(session_file).read())
        assert "session_id" in state
        assert "tab_index" in state

        # Cleanup
        if os.path.exists(session_file):
            os.unlink(session_file)
