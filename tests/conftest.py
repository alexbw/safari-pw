"""Shared pytest fixtures for safari-pw.

Auto-cleanup: any test module that defines a module-level `SESSION = "..."`
constant gets its named pw session torn down after each test (closes the
managed Safari tab, removes the state file). Modules without a SESSION
constant are unaffected.
"""

import os
import subprocess
import sys

import pytest

PW_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "pw"))


@pytest.fixture(autouse=True)
def _pw_session_cleanup(request):
    session = getattr(request.module, "SESSION", None)
    yield
    if not session:
        return
    subprocess.run(
        [sys.executable, PW_PATH, "--name", session, "close"],
        capture_output=True, text=True, timeout=15,
    )
