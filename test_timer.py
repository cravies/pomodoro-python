import importlib

import pytest

import timer


@pytest.fixture
def clock(monkeypatch):
    """A fresh timer on a fake clock; call clock(seconds) to move time on."""
    importlib.reload(timer)
    now = [1000.0]
    monkeypatch.setattr(timer.time, 'monotonic', lambda: now[0])

    def advance(seconds):
        now[0] += seconds
    return advance


def test_idle_shows_the_modes_full_length(clock):
    state = timer.state()
    assert (state['mode'], state['remaining'], state['running'], state['paused']) == ('pomodoro', '25:00', False, False)
    assert timer.check_done() is None


def test_a_pomodoro_lines_up_a_break_and_back_but_waits_to_start_them(clock):
    timer.start()
    clock(25 * 60)
    done = timer.check_done()
    assert done['mode'] == 'pomodoro' and done['length'] == 25
    assert timer.check_done() is None  # recorded once only
    state = timer.state()
    assert (state['mode'], state['running'], state['paused'], state['remaining']) == ('short_break', False, False, '05:00')
    clock(60 * 60)
    assert timer.check_done() is None  # still waiting
    timer.start()
    clock(5 * 60)
    assert timer.check_done()['mode'] == 'short_break'
    state = timer.state()
    assert (state['mode'], state['running']) == ('pomodoro', False)


def test_every_fourth_pomodoro_is_followed_by_a_long_break(clock):
    timer.start()
    breaks = []
    for _ in range(8):
        clock(25 * 60)
        timer.check_done()
        breaks.append(timer.state()['mode'])
        timer.start()
        clock(timer.lengths[breaks[-1]] * 60)
        timer.check_done()
        timer.start()
    assert breaks == ['short_break'] * 3 + ['long_break'] + ['short_break'] * 3 + ['long_break']


def test_pause_keeps_the_time_left(clock):
    timer.start()
    clock(60)
    timer.pause()
    clock(600)
    assert timer.state()['remaining'] == '24:00' and timer.state()['paused']
    assert timer.check_done() is None
    timer.start()
    clock(24 * 60)
    assert timer.check_done()['mode'] == 'pomodoro'


def test_skip_ends_a_pomodoro_early_and_counts_it(clock):
    timer.start()
    clock(60)
    cut = timer.skip()
    assert cut['mode'] == 'pomodoro'
    state = timer.state()
    assert (state['mode'], state['running']) == ('short_break', False)
    timer.start()
    assert timer.skip() is None  # skipping a break records nothing
    assert timer.state()['mode'] == 'pomodoro'


def test_skip_does_nothing_unless_running(clock):
    assert timer.skip() is None
    assert timer.state()['mode'] == 'pomodoro'


def test_switching_mode_drops_the_round_and_waits(clock):
    timer.start()
    clock(60)
    dropped = timer.switch('long_break')
    assert dropped['mode'] == 'pomodoro'
    state = timer.state()
    assert (state['mode'], state['running'], state['paused'], state['remaining']) == ('long_break', False, False, '15:00')
    assert timer.switch('pomodoro') is None  # no pomodoro was under way


def test_the_current_tab_resets_it(clock):
    timer.start()
    clock(2)
    timer.pause()
    assert timer.state()['remaining'] == '24:58'
    assert timer.switch('pomodoro')['mode'] == 'pomodoro'
    state = timer.state()
    assert (state['mode'], state['remaining'], state['running'], state['paused']) == ('pomodoro', '25:00', False, False)


def test_every_change_bumps_the_version(clock):
    versions = [timer.state()['version']]
    for change in (timer.start, timer.pause, timer.start, timer.skip, lambda: timer.switch('pomodoro')):
        change()
        versions.append(timer.state()['version'])
    assert versions == sorted(set(versions))
