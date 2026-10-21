import datetime
import math
import threading
import time

# The single timer, cycling the way pomofocus.io does: a pomodoro, then a
# short break (a long one after every long_break_interval-th pomodoro), then
# the next pomodoro. As one runs out the next is lined up, waiting at its full
# length until you start it. Lives in memory only, so a server restart drops
# the round in progress.

MODES = ('pomodoro', 'short_break', 'long_break')

# minutes per mode, and how many pomodoros come before a long break. Set from
# the settings before every request (see app.py), the way utils.scoring is.
lengths = {'pomodoro': 25, 'short_break': 5, 'long_break': 15}
long_break_interval = 4

_lock = threading.Lock()  # Flask serves requests on several threads — see check_done()
_mode = 'pomodoro'
_deadline = None     # time.monotonic() value when it's due while running; None otherwise
_left = None         # seconds left while paused; None when the round hasn't started
_started_at = None   # wall-clock start of the round, which is what gets recorded
_length = None       # the round's planned minutes, fixed when it starts
_count = 0           # pomodoros finished (or skipped) today, for spacing the long breaks
_count_day = None    # the day _count is for; it starts again from 0 each day
_version = 0         # bumped on every change, so open pages know to refresh


def start():
    """Start the round, or carry on with a paused one."""
    global _deadline, _left, _version
    with _lock:
        if _deadline is not None:
            return
        if _started_at is None:
            _begin()
        else:
            _deadline = time.monotonic() + _left
            _left = None
        _version += 1


def pause():
    global _deadline, _left, _version
    with _lock:
        if _deadline is None:
            return
        _left = max(0, _deadline - time.monotonic())
        _deadline = None
        _version += 1


def skip():
    """End the running round early and line up the next, as if it had run
    out. Returns the pomodoro it cut short, or None for a break (or when not
    running)."""
    with _lock:
        if _deadline is None:
            return None
        ended = _next_round()
    return ended if ended['mode'] == 'pomodoro' else None


def switch(mode):
    """Change mode from the tabs, or reset it by clicking the tab it's on. The
    mode's round waits at its full length to be started; a pomodoro that was
    under way is dropped and returned (None otherwise)."""
    global _mode, _deadline, _left, _started_at, _length, _version
    with _lock:
        dropped = _round() if _mode == 'pomodoro' and _started_at else None
        _mode = mode
        _deadline = _left = _started_at = _length = None
        _version += 1
        return dropped


def check_done():
    """The round that just ran out, the first time (and only the first time)
    its deadline has passed, with the next round lined up; None
    otherwise. Locked so two polls landing together can't both record it."""
    with _lock:
        if _deadline is None or time.monotonic() < _deadline:
            return None
        return _next_round()


def _next_round():
    """Move on to the next mode, waiting to be started; return the round that ended."""
    global _mode, _count, _version, _deadline, _left, _started_at, _length
    ended = _round()
    if _mode == 'pomodoro':
        _count = _today_count() + 1
        _mode = 'long_break' if _count % long_break_interval == 0 else 'short_break'
    else:
        _mode = 'pomodoro'
    _deadline = _left = _started_at = _length = None
    _version += 1
    return ended


def _begin():
    global _deadline, _left, _started_at, _length
    _length = lengths[_mode]
    _started_at = datetime.datetime.now().replace(microsecond=0)
    _deadline = time.monotonic() + _length * 60
    _left = None


def _round():
    return {'mode': _mode, 'started_at': _started_at, 'length': _length}


def _today_count():
    global _count, _count_day
    if _count_day != datetime.date.today():
        _count, _count_day = 0, datetime.date.today()
    return _count


def _remaining():
    """Seconds left, rounded up so 0.3s reads as 1. Before the round starts,
    its full length."""
    if _deadline is not None:
        return max(0, math.ceil(_deadline - time.monotonic()))
    if _left is not None:
        return math.ceil(_left)
    return lengths[_mode] * 60


def state():
    """Everything a page shows about the timer."""
    with _lock:
        minutes, seconds = divmod(_remaining(), 60)
        return {
            'mode': _mode,
            'running': _deadline is not None,
            'paused': _deadline is None and _started_at is not None,
            'remaining': f"{minutes:02d}:{seconds:02d}",
            'version': _version,
        }
