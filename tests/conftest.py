import os
import sys
import threading
import time

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

_real_sleep = time.sleep


@pytest.fixture(autouse=True)
def isolated_cwd_and_fast_sleep(tmp_path, monkeypatch):
    """The system writes JSON/CSV logs to the cwd and the demos sleep for seconds:
    run each test in its own temp dir with sleeps shortened to a yield."""
    monkeypatch.chdir(tmp_path)

    def fast_sleep(seconds):
        if threading.current_thread() is not threading.main_thread():
            _real_sleep(0.0005)  # let a background control loop yield

    monkeypatch.setattr(time, "sleep", fast_sleep)
    yield
