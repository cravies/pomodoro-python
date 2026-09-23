import datetime
import math
import threading
import time

# The single running-or-idle pomodoro timer. Lives in memory only, so a server
# restart drops one in progress.

_lock = threading.Lock()  # Flask serves requests on several threads — see check_done()
_deadline = None          # time.monotonic() value when it's due; None when idle
_started_at = None        # wall-clock start, which is what gets recorded
_length = None            # planned minutes


def start(minutes):
    global _deadline, _started_at, _length
    with _lock:
        _length = minutes
        _started_at = datetime.datetime.now().replace(microsecond=0)
        _deadline = time.monotonic() + minutes * 60


def running():
    return _deadline is not None


def stop():
    """End the running pomodoro, and return what it was (or None when idle)."""
    with _lock:
        return _clear()


def check_done():
    """The pomodoro that just finished, the first time (and only the first time)
    its deadline has passed; None otherwise. Locked so two polls landing
    together can't both record the same pomodoro."""
    with _lock:
        if _deadline is None or time.monotonic() < _deadline:
            return None
        return _clear()


def _clear():
    global _deadline
    if _deadline is None:
        return None
    _deadline = None
    return {'started_at': _started_at, 'length': _length}


def remaining(idle_minutes):
    """Seconds left, rounded up so 0.3s reads as 1. When idle, the next pomodoro's length."""
    with _lock:
        if _deadline is None:
            return idle_minutes * 60
        return max(0, math.ceil(_deadline - time.monotonic()))


def remaining_str(idle_minutes):
    minutes, seconds = divmod(remaining(idle_minutes), 60)
    return f"{minutes:02d}:{seconds:02d}"
