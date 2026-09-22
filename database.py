import datetime
import sqlite3

DB_PATH = "pomo.db"


def _connect():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _write(sql, params=()):
    with _connect() as conn:
        conn.execute(sql, params)


def _read(sql, params=()):
    with _connect() as conn:
        return [dict(row) for row in conn.execute(sql, params)]


def init():
    with _connect() as conn:
        conn.execute("""
            create table if not exists pomodoro (
                id integer primary key,
                timestamp text not null,
                quality integer,
                ai_usage text
            )
        """)
        # older databases predate ai_usage; create table if not exists won't add it
        columns = [c['name'] for c in conn.execute("pragma table_info(pomodoro)")]
        if 'ai_usage' not in columns:
            conn.execute("alter table pomodoro add column ai_usage text")


def insert_pomodoro(timestamp, quality):
    _write(
        "insert into pomodoro (timestamp, quality) values (?, ?)",
        (timestamp, quality),
    )


def delete_pomodoro(id):
    _write("delete from pomodoro where id = ?", (id,))


def set_quality(id, quality):
    _write("update pomodoro set quality = ? where id = ?", (quality, id))


def set_ai_usage(id, ai_usage):
    _write("update pomodoro set ai_usage = ? where id = ?", (ai_usage, id))


def get_today_pomodoros():
    today = datetime.date.today().isoformat()
    return _read(
        "select * from pomodoro where timestamp like ? order by timestamp",
        (f"{today}%",),
    )


def get_this_week_pomodoros():
    today = datetime.date.today()
    monday = today - datetime.timedelta(days=today.weekday())
    return _read(
        "select * from pomodoro where timestamp >= ? order by timestamp",
        (monday.isoformat(),),
    )


def get_all_pomodoros():
    return _read("select * from pomodoro order by timestamp")


init()
