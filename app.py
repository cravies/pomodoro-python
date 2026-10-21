import calendar
import collections
import datetime
from urllib.parse import urlsplit

from flask import Flask, abort, redirect, render_template, request

import backgrounds
import database
import timer
import utils

app = Flask(__name__)
app.config['TEMPLATES_AUTO_RELOAD'] = True

PROJECTS = ['thesis', 'work']


@app.before_request
def same_site_posts_only():
    """Refuse form posts sent from any other site. The server only listens on
    localhost, but a page open in your browser could still post to it."""
    if request.method == 'POST' and request.origin not in (None, request.host_url.rstrip('/')):
        abort(403)


@app.before_request
def load_scoring():
    utils.scoring = database.get_scoring()
    timer.lengths = {mode: database.get_setting(f'{mode}_length') for mode in timer.MODES}
    timer.long_break_interval = database.get_setting('long_break_interval')


# what each mode is called on its tab, what the browser tab says, and its tab
# icon, which like pomofocus's turns grey (a pause sign) while paused
MODE_NAMES = {'pomodoro': 'Pomodoro', 'short_break': 'Short Break', 'long_break': 'Long Break'}
MODE_EMOJI = {'pomodoro': '🍅', 'short_break': '☕', 'long_break': '🌴', 'paused': '⏸️'}


def clock_state():
    clock = timer.state()
    clock['message'] = 'Time to focus!' if clock['mode'] == 'pomodoro' else 'Time for a break!'
    clock['title'] = f"{clock['remaining']} - {clock['message']}"
    clock['emoji'] = MODE_EMOJI['paused' if clock['paused'] else clock['mode']]
    return clock


@app.context_processor
def shared():
    # every page draws the current background, and takes its colours and tab
    # title from the timer
    return {'background': backgrounds.current(), 'clock': clock_state()}


@app.route('/')
def home():
    """The timer, with one day's pomodoros under it: today, or a past day
    picked in the history (?date=YYYY-MM-DD)."""
    today = datetime.date.today()
    date = chosen_date(request.args)
    day = database.get_day(today) if date == today else database.peek_day(date)
    # oldest at the top, newest at the bottom, just above the add row
    shown = [p for p in database.get_completed_pomodoros() if p['started_at'].date() == date]
    for p in shown:
        p['time'] = utils.format_time(p['started_at'])
        p['task'] = {1: 'yes', 0: 'no'}.get(p['on_task'])
        p['hue'] = round(29 + utils.locked_in_scaled(p) * (145 - 29))  # oklch hue: 29 red .. 145 green

    return render_template(
        'home.html',
        active='timer',
        date=date,
        is_today=date == today,
        date_label=date.strftime('%A %d %B').replace(' 0', ' '),
        day=day,
        projects=PROJECTS,
        to_go=max(0, day['target'] - sum(1 for p in shown if p['on_task'] != 0)),  # off task doesn't count
        day_quality=utils.daily_quality(shown),
        completed=len(shown),
        on_task_count=sum(1 for p in shown if p['on_task'] != 0),
        on_task_percent=utils.on_task_percent(shown),
        locked_in=utils.day_locked_in(shown),
        scoring=utils.scoring,
        levels=utils.levels(),
        modes=MODE_NAMES,
        mode_length=timer.lengths[timer.state()['mode']],
        now=datetime.datetime.now().strftime('%H:%M'),
        pomodoros=shown,
        ai_options={option: utils.AI_LABELS[option] for option in utils.AI_OPTIONS},
    )


@app.route('/stats')
def stats():
    today = datetime.date.today()
    monday = today - datetime.timedelta(days=today.weekday())
    all_rows = database.get_completed_pomodoros()
    week_counts, week_on, week_quality, week_vibe = utils.weekday_totals(
        [p for p in all_rows if p['started_at'].date() >= monday]
    )
    usual_counts, usual_on, usual_quality, usual_vibe = utils.usual_weekday_averages(all_rows, monday)

    # this week and the usual share a scale so the bar and its marker line are
    # comparable, and on task uses the pomodoro count's scale so the two charts
    # line up; quality is out of the fixed 5. the two ai charts each get
    # their own scale — today is single digits against an all-time total.
    max_count = max(week_counts + usual_counts)
    todays = [p for p in all_rows if p['started_at'].date() == today]

    return render_template(
        'stats.html',
        active='stats',
        week_total=sum(week_counts),
        count_rows=utils.compare_rows(week_counts, usual_counts, max_count, today, zero_means_no_data=False),
        quality_rows=utils.compare_rows(week_quality, usual_quality, 5, today, zero_means_no_data=True),
        on_task_rows=utils.compare_rows(week_on, usual_on, max_count, today, zero_means_no_data=False),
        vibe_rows=utils.add_vibe_emoji(
            utils.compare_rows(week_vibe, usual_vibe, 1, today, zero_means_no_data=True), week_vibe, usual_vibe),
        today_ai_rows=utils.category_rows(utils.ai_totals(todays)),
        all_time_ai_rows=utils.category_rows(utils.ai_totals(all_rows)),
        off_task_ai_rows=utils.category_rows(utils.off_task_by_ai(all_rows)),
        quality_ai_rows=utils.category_rows(utils.quality_by_ai(all_rows), scale=5, zero_means_no_data=True),
    )


@app.route('/history')
def history():
    """A month calendar; each past day links to the timer page showing that day."""
    today = datetime.date.today()
    try:
        first = datetime.date.fromisoformat(request.args.get('month', today.strftime('%Y-%m')) + '-01')
    except ValueError:
        abort(400)
    counts = collections.Counter(p['started_at'].date() for p in database.get_completed_pomodoros())
    previous = (first - datetime.timedelta(days=1)).replace(day=1)
    following = (first + datetime.timedelta(days=31)).replace(day=1)
    return render_template(
        'history.html',
        active='history',
        month_label=first.strftime('%B %Y'),
        month=first.month,
        weeks=calendar.Calendar().monthdatescalendar(first.year, first.month),  # Monday first
        counts=counts,
        today=today,
        day_labels=utils.DAY_LABELS,
        previous=previous.strftime('%Y-%m'),
        following=following.strftime('%Y-%m') if following <= today else None,  # no future months
    )


# called with the round that just ran out; the desktop app sets it to show
# its popup
on_round_end = None


def advance():
    """Notice a round that ran out, start the next, and write a finished
    pomodoro. Returns the round that ended, or None. Called by every /state
    poll, and every second by the desktop app, whose page may be minimized."""
    done = timer.check_done()
    if done and done['mode'] == 'pomodoro':
        ended = done['started_at'] + datetime.timedelta(minutes=done['length'])
        database.insert_pomodoro(done['started_at'], done['length'], ended, completed=True)
        backgrounds.next_background()
    if done and on_round_end:
        on_round_end(done)
    return done


@app.route('/state')
def state():
    """Polled once a second by every page."""
    done = advance()
    clock = clock_state()
    # a new version tells the page to swap in the new round; finished means a
    # pomodoro was just written, so a page showing another day goes to today
    return {**clock, 'finished': bool(done) and done['mode'] == 'pomodoro'}


@app.route('/start', methods=['POST'])
def start():
    timer.start()
    return back()


@app.route('/pause', methods=['POST'])
def pause():
    timer.pause()
    return back()


@app.route('/skip', methods=['POST'])
def skip():
    """Finish the round early and go on to the next. A pomodoro cut short is
    kept, as not completed."""
    record_stopped(timer.skip())
    return back()


@app.route('/mode', methods=['POST'])
def set_mode():
    """A mode tab: stop wherever the timer is and wait at the start of that
    mode — the tab it's already on resets it. A pomodoro under way is kept,
    as not completed."""
    mode = request.form.get('mode')
    if mode not in timer.MODES:
        abort(400)
    record_stopped(timer.switch(mode))
    return back()


@app.route('/length', methods=['POST'])
def set_length():
    """The length of a mode, typed into its idle clock."""
    mode = request.form.get('mode')
    minutes = form_int('minutes')
    if mode not in timer.MODES or not 1 <= minutes <= 60:
        abort(400)
    database.set_setting(f'{mode}_length', minutes)
    return back()


def record_stopped(stopped):
    if stopped:
        database.insert_pomodoro(
            stopped['started_at'], stopped['length'], datetime.datetime.now(), completed=False)


@app.route('/add', methods=['POST'])
def add():
    """Record a pomodoro that ran without the timer, on the day being shown."""
    try:
        at = datetime.time.fromisoformat(request.form['time'])
    except (KeyError, ValueError):
        abort(400)
    started = datetime.datetime.combine(chosen_date(request.form), at)
    if started > datetime.datetime.now():
        abort(400)
    length = database.get_setting('pomodoro_length')
    database.insert_pomodoro(started, length, started + datetime.timedelta(minutes=length), completed=True)
    return back()


@app.route('/target', methods=['POST'])
def set_target():
    target = form_int('target')
    if not 1 <= target <= 50:
        abort(400)
    date = chosen_date(request.form)
    if date == datetime.date.today():
        database.set_setting('target', target)  # future days start with it...
    database.set_day(date, 'target', target)  # ...and so does the day being shown
    return back()


@app.route('/day', methods=['POST'])
def set_day():
    """The shown day's project."""
    date = chosen_date(request.form)
    if 'project' in request.form:
        if request.form['project'] not in PROJECTS:
            abort(400)
        database.set_day(date, 'project', request.form['project'])
    else:
        abort(400)
    return back()


@app.route('/rate', methods=['POST'])
def rate():
    quality = form_int('quality')
    if not 1 <= quality <= 5:
        abort(400)
    database.set_quality(form_int('id'), quality)
    return back()


@app.route('/ai', methods=['POST'])
def ai():
    ai_usage = request.form.get('ai_usage')
    if ai_usage not in utils.AI_OPTIONS:
        abort(400)
    database.set_ai_usage(form_int('id'), ai_usage)
    return back()


@app.route('/task', methods=['POST'])
def on_task():
    answer = request.form.get('on_task')
    if answer not in ('yes', 'no'):
        abort(400)
    database.set_on_task(form_int('id'), answer == 'yes')
    return back()


@app.route('/vibe', methods=['POST'])
def set_vibe_scoring():
    """Save the Workday vibe popup: weights 0-10, option scores and level
    cut-offs 0-1, with the cut-offs rising."""
    if 'reset' in request.form:
        database.set_scoring(None)
        return back()
    scoring = {}
    for key in utils.DEFAULT_SCORING:
        value = request.form.get(key, type=float)
        top = 10 if key.startswith('weight_') else 1
        if value is None or not 0 <= value <= top:
            abort(400)
        scoring[key] = value
    if not any(scoring[k] for k in ('weight_quality', 'weight_ai', 'weight_task')):
        abort(400)
    cuts = [scoring[f'cut_{i}'] for i in range(1, 5)]
    if not 0 < cuts[0] < cuts[1] < cuts[2] < cuts[3] < 1:
        abort(400)
    database.set_scoring(scoring)
    return back()


@app.route('/delete', methods=['POST'])
def delete():
    database.delete_pomodoro(form_int('id'))
    return back()


def chosen_date(source):
    """The day a page or form is about: its 'date' field, or today when there's
    none. Garbled dates and future ones are a 400."""
    today = datetime.date.today()
    if not source.get('date'):
        return today
    try:
        date = datetime.date.fromisoformat(source['date'])
    except ValueError:
        abort(400)
    if date > today:
        abort(400)
    return date


def form_int(name):
    """A required whole-number form field; a missing or garbled one is a 400."""
    value = request.form.get(name, type=int)
    if value is None:
        abort(400)
    return value


def back():
    """Back to the page the form was posted from. Only the path is kept, so it
    can never send you to another site."""
    page = urlsplit(request.referrer or '/')
    return redirect((page.path or '/') + (f'?{page.query}' if page.query else ''))


if __name__ == '__main__':
    # loopback only: reachable from this machine, invisible to the rest of the LAN
    app.run(host='127.0.0.1', port=5000)
