import datetime
import json
import shutil
import sqlite3
from pathlib import Path

# next to this file, not wherever the server happened to be launched from
DB_PATH = Path(__file__).parent / 'pomo.db'

DEFAULTS = {'target': 10, 'pomodoro_length': 25}
DAY_FIELDS = ('target', 'project')  # the columns set_day() may change


def _connect():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _write(sql, params=()):
    with _connect() as conn:
        conn.execute(sql, params)


def _create_tables(conn):
    conn.execute("""
        create table if not exists day (
            date     text primary key,  -- YYYY-MM-DD
            target   integer not null,  -- copied from the target setting when the day starts
            project  text,              -- thesis / work
            energy   integer            -- 1-5; no longer set from the app
        )
    """)
    conn.execute("""
        create table if not exists pomodoro (
            id          integer primary key,
            day         text not null references day(date),
            started_at  text not null,
            ended_at    text not null,     -- when it finished, or when it was stopped
            length      integer not null,  -- planned minutes
            completed   integer not null,  -- 1 = ran to the end, 0 = stopped early
            quality     integer,           -- 1-5
            ai_usage    text,              -- chat / agents / none
            on_task     integer            -- 1 = on task, 0 = off task (yak shaving)
        )
    """)
    conn.execute("create table if not exists setting (key text primary key, value text not null)")


def init():
    with _connect() as conn:
        columns = [c['name'] for c in conn.execute("pragma table_info(pomodoro)")]
    if 'timestamp' in columns:
        _migrate_from_single_timestamp()
    with _connect() as conn:
        _create_tables(conn)
        columns = [c['name'] for c in conn.execute("pragma table_info(pomodoro)")]
        if 'on_task' not in columns:  # added after the day table
            conn.execute("alter table pomodoro add column on_task integer")


def _migrate_from_single_timestamp():
    """Before the day table, a pomodoro only stored the time it finished. Each
    one becomes a completed 25-minute pomodoro that ended at that time, and each
    day gets a target of 10. The old file is kept as pomo.before-migration.db."""
    shutil.copy(DB_PATH, DB_PATH.with_name('pomo.before-migration.db'))
    with _connect() as conn:
        old = [dict(row) for row in conn.execute("select * from pomodoro")]
        conn.execute("alter table pomodoro rename to pomodoro_old")
        _create_tables(conn)
        for row in old:
            ended = datetime.datetime.fromisoformat(row['timestamp']).replace(microsecond=0)
            started = ended - datetime.timedelta(minutes=25)
            day = started.date().isoformat()
            conn.execute("insert or ignore into day (date, target) values (?, 10)", (day,))
            conn.execute(
                "insert into pomodoro (id, day, started_at, ended_at, length, completed, quality, ai_usage)"
                " values (?, ?, ?, ?, 25, 1, ?, ?)",
                (row['id'], day, started.isoformat(), ended.isoformat(), row['quality'], row['ai_usage']),
            )
        conn.execute("drop table pomodoro_old")


def get_setting(key):
    with _connect() as conn:
        row = conn.execute("select value from setting where key = ?", (key,)).fetchone()
    return int(row['value']) if row else DEFAULTS[key]


def set_setting(key, value):
    _write("insert or replace into setting (key, value) values (?, ?)", (key, str(value)))


def get_scoring():
    """The saved workday vibe scoring, filled in from the defaults."""
    import utils
    with _connect() as conn:
        row = conn.execute("select value from setting where key = 'scoring'").fetchone()
    return {**utils.DEFAULT_SCORING, **(json.loads(row['value']) if row else {})}


def set_scoring(scoring):
    """Save the scoring; None goes back to the defaults."""
    if scoring is None:
        _write("delete from setting where key = 'scoring'")
    else:
        _write("insert or replace into setting (key, value) values ('scoring', ?)", (json.dumps(scoring),))


def get_day(date):
    """The day's row, created the first time the day is used, with the current target."""
    _write("insert or ignore into day (date, target) values (?, ?)", (date.isoformat(), get_setting('target')))
    with _connect() as conn:
        return dict(conn.execute("select * from day where date = ?", (date.isoformat(),)).fetchone())


def peek_day(date):
    """The day's row if it exists, or what it would start as — without saving
    it, so browsing past days in the history doesn't create empty rows."""
    with _connect() as conn:
        row = conn.execute("select * from day where date = ?", (date.isoformat(),)).fetchone()
    if row:
        return dict(row)
    return {'date': date.isoformat(), 'target': get_setting('target'), 'project': None, 'energy': None}


def set_day(date, field, value):
    if field not in DAY_FIELDS:  # a column name can't be a query parameter
        raise ValueError(field)
    get_day(date)
    _write(f"update day set {field} = ? where date = ?", (value, date.isoformat()))


def insert_pomodoro(started_at, length, ended_at, completed):
    day = get_day(started_at.date())['date']
    _write(
        "insert into pomodoro (day, started_at, ended_at, length, completed) values (?, ?, ?, ?, ?)",
        (day, started_at.isoformat(timespec='seconds'), ended_at.isoformat(timespec='seconds'), length, int(completed)),
    )


def delete_pomodoro(id):
    _write("delete from pomodoro where id = ?", (id,))


def set_quality(id, quality):
    _write("update pomodoro set quality = ? where id = ?", (quality, id))


def set_ai_usage(id, ai_usage):
    _write("update pomodoro set ai_usage = ? where id = ?", (ai_usage, id))


def set_on_task(id, on_task):
    _write("update pomodoro set on_task = ? where id = ?", (int(on_task), id))


def get_completed_pomodoros():
    """Every pomodoro that ran to the end, oldest first, with times parsed. The
    stopped ones stay in the database for later analysis but aren't shown or counted."""
    with _connect() as conn:
        rows = [dict(row) for row in conn.execute(
            "select * from pomodoro where completed = 1 order by started_at")]
    for row in rows:
        row['started_at'] = datetime.datetime.fromisoformat(row['started_at'])
        row['ended_at'] = datetime.datetime.fromisoformat(row['ended_at'])
    return rows


init()
