import datetime

from flask import Flask, render_template, redirect, request

import backgrounds
import database
import timer
import utils

app = Flask(__name__)
app.config['TEMPLATES_AUTO_RELOAD'] = True

DAY_LABELS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']


@app.route('/')
def index():
    today = datetime.date.today()
    pomodoros = database.get_today_pomodoros()
    for p in pomodoros:
        p['time'] = utils.format_time(p['timestamp'])

    all_rows = database.get_all_pomodoros()
    week_counts, week_quality = utils.weekday_totals(
        database.get_this_week_pomodoros()
    )
    past_counts, past_quality = utils.historical_weekday_averages(all_rows, today)

    # the two count charts share a scale so their heights are comparable; the
    # quality charts share the fixed 1-5 rating ceiling. the ai charts don't —
    # today is single digits against an all-time total, so a shared scale would
    # flatten today to nothing. they compare the mix, not the heights.
    max_count = max(week_counts + past_counts)
    today_ai = utils.ai_totals(pomodoros)
    all_time_ai = utils.ai_totals(all_rows)

    return render_template(
        'index.html',
        pomodoros=pomodoros,
        background=backgrounds.current(),
        remaining=timer.remaining_str(),
        ai_options=utils.AI_OPTIONS,
        week_total=sum(week_counts),
        week_bars=utils.bars(week_counts, DAY_LABELS, max_count),
        past_bars=utils.bars(past_counts, DAY_LABELS, max_count),
        week_quality_bars=utils.bars(week_quality, DAY_LABELS, 5),
        past_quality_bars=utils.bars(past_quality, DAY_LABELS, 5),
        today_ai_bars=utils.bars(today_ai, utils.AI_CATEGORIES, max(today_ai)),
        all_time_ai_bars=utils.bars(
            all_time_ai, utils.AI_CATEGORIES, max(all_time_ai)
        ),
    )


@app.route('/state')
def state():
    finished = timer.check_done()
    if finished:
        database.insert_pomodoro(datetime.datetime.now().isoformat(), quality=None)
        backgrounds.next_background()
    return {'remaining': timer.remaining_str(), 'finished': finished}


@app.route('/start', methods=['POST'])
def start():
    minutes = request.form.get('minutes', 25, type=int)
    timer.start(minutes)
    return redirect('/')


@app.route('/stop', methods=['POST'])
def stop():
    timer.stop()
    return redirect('/')


@app.route('/rate', methods=['POST'])
def rate():
    id = request.form.get('id', type=int)
    quality = request.form.get('quality', type=int)
    database.set_quality(id, quality)
    return redirect('/')


@app.route('/ai', methods=['POST'])
def ai():
    id = request.form.get('id', type=int)
    ai_usage = request.form.get('ai_usage')
    database.set_ai_usage(id, ai_usage)
    return redirect('/')


@app.route('/delete', methods=['POST'])
def delete():
    id = request.form.get('id', type=int)
    database.delete_pomodoro(id)
    return redirect('/')


if __name__ == '__main__':
    app.run()
