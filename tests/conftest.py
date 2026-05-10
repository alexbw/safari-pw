"""Shared pytest fixtures for safari-pw.

Two cleanup layers, so the suite never leaves Safari tabs open:

1. Per-test (`_pw_session_cleanup`): any test module that defines a
   module-level `SESSION = "..."` constant gets that named pw session torn
   down after each test (closes the managed Safari tab, removes the state
   file). Used by the e2e test modules — each test wants a fresh tab.

2. Session-end (`_pw_pytest_session_finalizer`): after the entire pytest
   run finishes, scan the pw state directory for any leftover sessions
   matching `session-pytest-*.json` and close them. Catches anything that
   tests created via `PW_SESSION=pytest-...` env (e.g. `test_pw.py`'s
   `run_pw` helper, which pins everything to `pytest-test-pw`).
"""

import glob
import os
import subprocess
import sys

import pytest

PW_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "pw"))
STATE_DIR = os.path.expanduser("~/Library/Application Support/safari-pw")


def _close_pw_session(name):
    subprocess.run(
        [sys.executable, PW_PATH, "--name", name, "close"],
        capture_output=True, text=True, timeout=15,
    )


@pytest.fixture(autouse=True)
def _pw_session_cleanup(request):
    session = getattr(request.module, "SESSION", None)
    yield
    if not session:
        return
    _close_pw_session(session)


# URL patterns that identify a tab as belonging to the test suite. Any
# Safari tab whose URL contains one of these substrings is fair game for
# the cleanup sweep. Whitelist-only — never match against generic patterns
# like "about:blank" or "example.com" (could be the user's real tab).
#
# - "/tmp/pw-test-": HTML fixtures the suite writes to /tmp
# - "/tmp/pw-screenshot": pw screenshot output (sometimes navigated to)
# - "__pw_session_id": pw bakes its session marker into a `data:text/html`
#   URL when it spawns a managed tab. The substring is unique to pw, so any
#   tab whose URL contains it is pw-spawned (and therefore safe to close).
_TEST_TAB_URL_NEEDLES = (
    "/tmp/pw-test-",
    "/tmp/pw-screenshot",
    "__pw_session_id",
)


def _close_test_tabs_by_url():
    """Close every Safari tab whose URL matches a test-fixture pattern.

    Catches tabs that escaped pw's session tracking — e.g. a test that opened
    a fixture URL and then crashed before cleanup, or one of the spawn-time
    `data:text/html` marker tabs that wasn't replaced by a real navigation.
    """
    needles_js = "[" + ", ".join(repr(n) for n in _TEST_TAB_URL_NEEDLES) + "]"
    script = f"""
    var s = Application("Safari");
    var needles = {needles_js};
    var closed = 0;
    for (var w = s.windows.length - 1; w >= 0; w--) {{
        var win = s.windows[w];
        for (var t = win.tabs.length - 1; t >= 0; t--) {{
            try {{
                var url = win.tabs[t].url() || "";
                for (var i = 0; i < needles.length; i++) {{
                    if (url.indexOf(needles[i]) >= 0) {{
                        win.tabs[t].close();
                        closed++;
                        break;
                    }}
                }}
            }} catch(e) {{}}
        }}
    }}
    String(closed);
    """
    subprocess.run(
        ["osascript", "-l", "JavaScript", "-e", script],
        capture_output=True, text=True, timeout=15,
    )


# Glob patterns for state files that the suite may have created. Matches
# both `pytest-*` (used by test_pw.py via PW_SESSION) and `test-*` (used by
# legacy named-session tests like test_named_session_creates_state_file).
# Anything outside these patterns is the user's real session — leave it.
_PYTEST_SESSION_GLOBS = (
    "session-pytest-*.json",
    "session-test-*.json",
)


@pytest.fixture(scope="session", autouse=True)
def _pw_pytest_session_finalizer():
    yield
    # First, close any pw sessions we created (by state file).
    for pattern in _PYTEST_SESSION_GLOBS:
        for path in glob.glob(os.path.join(STATE_DIR, pattern)):
            name = os.path.basename(path)[len("session-"):-len(".json")]
            _close_pw_session(name)
    # Then sweep up any test-fixture tabs that escaped session tracking.
    _close_test_tabs_by_url()
