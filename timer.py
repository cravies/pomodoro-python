import math
import time

_deadline = None      # time.monotonic() value when the pomodoro is due; None if idle
_duration_s = 25 * 60  # remembers the last chosen duration, for display while idle


def start(minutes):
    global _deadline, _duration_s
    _duration_s = minutes * 60
    _deadline = time.monotonic() + _duration_s


def stop():
    global _deadline
    _deadline = None


def running():
    return _deadline is not None


def remaining():
    if _deadline is None:
        return _duration_s
    return max(0, math.ceil(_deadline - time.monotonic()))


def remaining_str():
    minutes, seconds = divmod(remaining(), 60)
    return f"{minutes:02d}:{seconds:02d}"


def check_done():
    global _deadline
    if _deadline is not None and time.monotonic() >= _deadline:
        _deadline = None
        return True
    return False
