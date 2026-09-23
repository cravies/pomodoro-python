import datetime as dt
import sqlite3

import pytest

import timer
import utils


@pytest.fixture
def db(tmp_path, monkeypatch):
    """A fresh database file, never the real one."""
    import database
    monkeypatch.setattr(database, 'DB_PATH', tmp_path / 'test.db')
    database.init()
    return database


@pytest.fixture
def client(db):
    import app
    return app.app.test_client()


def fake_clock(monkeypatch, start=1000.0):
    now = [start]
    monkeypatch.setattr(timer.time, 'monotonic', lambda: now[0])
    return now


def today_at(hour, minute=0):
    return dt.datetime.combine(dt.date.today(), dt.time(hour, minute))


def add(db, started, completed=True, length=25):
    db.insert_pomodoro(started, length, started + dt.timedelta(minutes=length), completed)


# ---- timer ----

def test_check_done_fires_exactly_once(monkeypatch):
    now = fake_clock(monkeypatch)
    timer.start(1)
    assert timer.check_done() is None
    now[0] += 60
    assert timer.check_done()['length'] == 1
    assert timer.check_done() is None  # the next poll must not record it again


def test_remaining_rounds_up_and_idle_shows_next_length(monkeypatch):
    now = fake_clock(monkeypatch)
    timer.start(1)
    now[0] += 59.7
    assert timer.remaining(25) == 1  # 0.3s left reads as 1, not 0
    timer.stop()
    assert timer.remaining_str(25) == '25:00'


# ---- stats ----

def pomodoro(day, quality=None, ai=None, on_task=None):
    return {'started_at': dt.datetime.combine(day, dt.time(10)), 'quality': quality, 'ai_usage': ai, 'on_task': on_task}


def test_usual_ignores_this_week():
    monday = dt.date(2026, 9, 21)
    last, before = monday - dt.timedelta(days=7), monday - dt.timedelta(days=14)
    rows = [pomodoro(last), pomodoro(last), pomodoro(before)] + [pomodoro(monday)] * 3
    counts, _, _, _ = utils.usual_weekday_averages(rows, monday)
    assert counts[0] == 1.5  # (2 + 1) / 2 past Mondays; this Monday's 3 left out


def test_on_task_counts_per_weekday():
    monday = dt.date(2026, 9, 21)
    last = monday - dt.timedelta(days=7)
    rows = [pomodoro(last, on_task=1), pomodoro(last, on_task=0), pomodoro(monday, on_task=1), pomodoro(monday)]
    week_counts, week_on, _, _ = utils.weekday_totals([r for r in rows if r['started_at'].date() >= monday])
    assert (week_counts[0], week_on[0]) == (2, 2)  # unmarked counts as on task
    _, usual_on, _, _ = utils.usual_weekday_averages(rows, monday)
    assert usual_on[0] == 1


def test_compare_rows_dashes_and_upcoming():
    wednesday = dt.date(2026, 9, 23)
    rows = utils.compare_rows([0] * 7, [0] * 7, 5, wednesday, zero_means_no_data=True)
    assert rows[0]['value'] == '–' and rows[0]['usual'] == '–'  # nothing rated, no history
    assert rows[3]['upcoming'] and rows[3]['value'] == ''       # Thursday hasn't happened


def test_ai_totals_and_quality_by_ai():
    day = dt.date(2026, 9, 23)
    rows = [pomodoro(day, 4, 'chat'), pomodoro(day, 2, 'chat'), pomodoro(day, 5, 'agents'), pomodoro(day)]
    assert utils.ai_totals(rows) == [2, 1, 0, 1]
    assert utils.quality_by_ai(rows) == [3, 5, 0, 0]
    rows += [pomodoro(day, ai='chat', on_task=0), pomodoro(day, ai='chat', on_task=1)]
    assert utils.off_task_by_ai(rows) == [1, 0, 0, 0]


def test_daily_quality_stars():
    day = dt.date(2026, 9, 23)
    assert utils.daily_quality([pomodoro(day, 4), pomodoro(day, 3), pomodoro(day)]) == '⭐⭐⭐⭐☆'  # 3.5 rounds up
    assert utils.daily_quality([pomodoro(day, 3), pomodoro(day, 2)]) == '⭐⭐⭐☆☆'  # 2.5 rounds up too
    assert utils.daily_quality([pomodoro(day)]) == '–'  # nothing rated yet


# ---- database ----

def test_migration_from_single_timestamp(tmp_path, monkeypatch):
    import database
    path = tmp_path / 'old.db'
    old = sqlite3.connect(path)
    old.execute('create table pomodoro (id integer primary key, timestamp text not null, quality integer, ai_usage text)')
    old.execute("insert into pomodoro values (7, '2026-09-22T15:34:49.446718', 4, 'agents')")
    old.commit()
    old.close()

    monkeypatch.setattr(database, 'DB_PATH', path)
    database.init()
    [row] = database.get_completed_pomodoros()
    assert (row['id'], row['day'], row['quality'], row['ai_usage']) == (7, '2026-09-22', 4, 'agents')
    assert row['ended_at'] == dt.datetime(2026, 9, 22, 15, 34, 49)
    assert row['started_at'] == dt.datetime(2026, 9, 22, 15, 9, 49)  # 25 minutes earlier
    assert database.get_day(dt.date(2026, 9, 22))['target'] == 10
    assert (tmp_path / 'pomo.before-migration.db').exists()


def test_day_keeps_its_own_target(db):
    db.get_day(dt.date(2026, 9, 21))  # a day that started with the default of 10
    db.set_setting('target', 6)
    assert db.get_day(dt.date(2026, 9, 21))['target'] == 10  # not re-judged against the new one
    assert db.get_day(dt.date(2026, 9, 22))['target'] == 6


# ---- routes ----

def test_routes_reject_bad_input(client):
    assert client.get('/').status_code == 200
    assert client.get('/stats').status_code == 200
    assert client.post('/rate', data={'id': '1'}).status_code == 400
    assert client.post('/rate', data={'id': '1', 'quality': '9'}).status_code == 400
    assert client.post('/ai', data={'id': '1', 'ai_usage': 'lots'}).status_code == 400
    assert client.post('/day', data={'project': 'hobby'}).status_code == 400
    assert client.post('/length', data={'minutes': '0'}).status_code == 400


def test_stopped_pomodoro_is_kept_but_not_counted(client, db):
    client.post('/start', data={'minutes': '25'})
    client.post('/stop')
    with sqlite3.connect(db.DB_PATH) as conn:
        assert conn.execute('select completed from pomodoro').fetchall() == [(0,)]
    assert db.get_completed_pomodoros() == []
    assert '10 to go' in client.get('/').get_data(as_text=True)


def test_finished_pomodoro_is_recorded_once(client, db, monkeypatch):
    now = fake_clock(monkeypatch)
    client.post('/start', data={'minutes': '30'})
    now[0] += 30 * 60
    assert client.get('/state').get_json()['finished'] is True
    assert client.get('/state').get_json()['finished'] is False
    [row] = db.get_completed_pomodoros()
    assert row['length'] == 30 and row['ended_at'] - row['started_at'] == dt.timedelta(minutes=30)
    assert db.get_setting('pomodoro_length') == 30  # remembered for next time


def test_add_and_refuse_other_sites(client, db):
    assert client.post('/add', data={'time': '00:00'}).status_code == 302  # earlier today
    soon = dt.datetime.now() + dt.timedelta(minutes=2)
    if soon.date() == dt.date.today():  # skip right before midnight, when "soon" is tomorrow
        assert client.post('/add', data={'time': soon.strftime('%H:%M')}).status_code == 400
    assert client.post('/add', data={'time': 'soon'}).status_code == 400
    assert db.get_completed_pomodoros()[0]['started_at'] == today_at(0)

    evil = {'Origin': 'https://evil.example'}
    assert client.post('/delete', data={'id': '1'}, headers=evil).status_code == 403
    response = client.post('/stop', headers={'Referer': 'https://evil.example/phish?x=1'})
    assert response.headers['Location'] == '/phish?x=1'  # the redirect never leaves this app


def test_numbers_count_today_only_oldest_first(client, db):
    add(db, dt.datetime.combine(dt.date.today() - dt.timedelta(days=1), dt.time(9)))
    add(db, today_at(1))
    add(db, today_at(2))
    import re
    html = client.get('/').get_data(as_text=True)
    assert re.findall(r'<td>(\d+:\d+ [AP]M)</td>', html) == ['1:00 AM', '2:00 AM']  # yesterday's left out


def test_target_and_day_settings(client, db):
    add(db, today_at(0))
    assert '9 to go' in client.get('/').get_data(as_text=True)
    assert client.post('/target', data={'target': '1'}).status_code == 302
    assert 'Target reached' in client.get('/').get_data(as_text=True)
    assert client.post('/target', data={'target': '0'}).status_code == 400

    client.post('/day', data={'project': 'thesis'})
    client.post('/length', data={'minutes': '40'})
    day = db.get_day(dt.date.today())
    assert (day['project'], day['target']) == ('thesis', 1)
    assert db.get_setting('pomodoro_length') == 40


def test_on_task(client, db):
    add(db, today_at(0))
    [p] = db.get_completed_pomodoros()
    assert p['on_task'] is None  # blank until you say
    assert '9 to go' in client.get('/').get_data(as_text=True)
    assert client.post('/task', data={'id': p['id'], 'on_task': 'no'}).status_code == 302
    assert db.get_completed_pomodoros()[0]['on_task'] == 0
    assert '10 to go' in client.get('/').get_data(as_text=True)  # off task doesn't count toward the target
    assert client.post('/task', data={'id': p['id'], 'on_task': 'maybe'}).status_code == 400


def test_history_picks_a_past_day(client, db):
    yesterday = dt.date.today() - dt.timedelta(days=1)
    add(db, dt.datetime.combine(yesterday, dt.time(9)))
    assert client.get('/history').status_code == 200
    assert client.get('/history?month=2026-02').status_code == 200
    assert client.get('/history?month=soon').status_code == 400

    html = client.get(f'/?date={yesterday}').get_data(as_text=True)
    assert 'Back to today' in html and '9:00 AM' in html
    assert client.get(f'/?date={dt.date.today() + dt.timedelta(days=1)}').status_code == 400
    assert db.peek_day(yesterday - dt.timedelta(days=5))['target'] == 10  # looking doesn't create it

    client.post('/add', data={'date': yesterday, 'time': '23:00'})  # later that day is fine
    assert len([p for p in db.get_completed_pomodoros() if p['day'] == str(yesterday)]) == 2
    client.post('/target', data={'date': yesterday, 'target': '3'})
    assert db.get_day(yesterday)['target'] == 3
    assert db.get_setting('target') == 10  # a past day's target doesn't change future days


def test_locked_in_and_on_task_percent():
    day = dt.date(2026, 9, 23)
    assert utils.locked_in(pomodoro(day, 5, 'none', on_task=1)) == 1
    assert round(utils.locked_in(pomodoro(day, 1, 'agents', on_task=0)), 2) == 0.3  # the worst mix
    assert utils.locked_in(pomodoro(day, 4, 'none', 1)) == utils.locked_in(pomodoro(day, 4, 'none', None))  # unmarked is on
    assert utils.locked_in(pomodoro(day, 3, 'chat', 1)) > utils.locked_in(pomodoro(day, 2, 'chat', 1))  # rating counts
    rows = [pomodoro(day, on_task=0), pomodoro(day), pomodoro(day, on_task=1)]
    assert utils.on_task_percent(rows) == 67 and utils.on_task_percent([]) is None


def test_day_locked_in_label():
    day = dt.date(2026, 9, 23)
    assert utils.day_locked_in([pomodoro(day, 5, 'none', 1)])['label'] == 'heroic'
    assert utils.day_locked_in([pomodoro(day, 1, 'agents', 0)]) == {'score': '0.00', 'label': 'cooked', 'emoji': '🍳'}
    assert utils.day_locked_in([]) is None


def test_vibe_scoring_popup(client, db):
    form = {**utils.DEFAULT_SCORING, 'weight_ai': 2}
    assert client.post('/vibe', data=form).status_code == 302
    assert db.get_scoring()['weight_ai'] == 2
    assert client.post('/vibe', data={**form, 'ai_chat': 3}).status_code == 400   # scores are out of 1
    assert client.post('/vibe', data={**form, 'weight_quality': 0, 'weight_ai': 0, 'weight_task': 0}).status_code == 400
    assert client.post('/vibe', data={**form, 'cut_2': 0.1}).status_code == 400  # cut-offs must rise
    client.post('/vibe', data={'reset': '1'})
    assert db.get_scoring() == utils.DEFAULT_SCORING
