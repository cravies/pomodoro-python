DAY_LABELS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
AI_OPTIONS = ['chat', 'agents', 'none']  # what you can pick on a pomodoro
# fixed colour order; 'unset' is the bucket for rows where it was never recorded
AI_CATEGORIES = AI_OPTIONS + ['unset']


def format_time(dt):
    return dt.strftime('%I:%M %p').lstrip('0')


def weekday_totals(rows):
    """Per weekday (Mon..Sun): how many pomodoros, how many of those were on
    task (anything not marked off), their average quality, and their average
    workday vibe (locked_in_scaled). Used for the current week."""
    return _by_weekday(rows, per_day=False)


def usual_weekday_averages(rows, week_start):
    """The same figures averaged per day, over previous weeks only (everything
    before this week's Monday) — so this week is never compared against itself."""
    return _by_weekday([r for r in rows if r['started_at'].date() < week_start], per_day=True)


def _by_weekday(rows, per_day):
    counts, on_task, quality, vibe = [], [], [], []
    for weekday in range(7):
        day_rows = [r for r in rows if r['started_at'].weekday() == weekday]
        days = len({r['started_at'].date() for r in day_rows})
        divisor = days if per_day and days else 1
        counts.append(len(day_rows) / divisor)
        on_task.append(sum(1 for r in day_rows if r['on_task'] != 0) / divisor)  # on unless marked off
        quality.append(_average([r['quality'] for r in day_rows if r['quality'] is not None]))
        vibe.append(_average([locked_in_scaled(r) for r in day_rows]))
    return counts, on_task, quality, vibe


def ai_totals(rows):
    """How many pomodoros in each AI_CATEGORIES slot, in that fixed order."""
    return [sum(1 for r in rows if (r['ai_usage'] or 'unset') == c) for c in AI_CATEGORIES]


def off_task_by_ai(rows):
    """How many pomodoros marked off task in each AI_CATEGORIES slot (unmarked ones don't count)."""
    return [sum(1 for r in rows if (r['ai_usage'] or 'unset') == c and r['on_task'] == 0) for c in AI_CATEGORIES]


def quality_by_ai(rows):
    """Average quality in each AI_CATEGORIES slot, in that fixed order."""
    return [
        _average([r['quality'] for r in rows if (r['ai_usage'] or 'unset') == c and r['quality'] is not None])
        for c in AI_CATEGORIES
    ]


# how the workday vibe is scored; changed from the Workday vibe popup and
# saved as a setting. Weights say how much each factor counts; the rest are
# each option's score out of 1 (quality is always stars / 5).
DEFAULT_SCORING = {
    'weight_quality': 1.0, 'weight_ai': 1.0, 'weight_task': 1.0,
    'ai_none': 1.0, 'ai_chat': 0.6, 'ai_agents': 0.2,
    'task_on': 1.0, 'task_off': 0.5,
    # where each level ends on the 0..1 vibe scale; heroic runs from cut_4 to 1
    'cut_1': 0.2, 'cut_2': 0.4, 'cut_3': 0.6, 'cut_4': 0.8,
}
scoring = dict(DEFAULT_SCORING)  # the saved scoring, loaded by app.py before each request


def _factors(row):
    """(weight, score) for each factor that's set; an unmarked on-task counts as on."""
    s = scoring
    factors = [(s['weight_task'], s['task_off'] if row['on_task'] == 0 else s['task_on'])]
    if row['quality'] is not None:
        factors.append((s['weight_quality'], row['quality'] / 5))
    if row['ai_usage'] in AI_OPTIONS:
        factors.append((s['weight_ai'], s['ai_' + row['ai_usage']]))
    return factors


def _weighted(factors):
    total = sum(w for w, _ in factors)
    return sum(w * score for w, score in factors) / total if total else 0


def locked_in(row):
    """How good a pomodoro was overall: the weighted average of its quality,
    AI use and on task scores. A factor that isn't set yet is left out."""
    return _weighted(_factors(row))


def locked_in_scaled(row):
    """locked_in() stretched onto 0..1, from the worst possible mix of scores
    to the best, for colours and labels."""
    s = scoring
    ai = [s['ai_none'], s['ai_chat'], s['ai_agents']]
    task = [s['task_on'], s['task_off']]
    weights = (s['weight_quality'], s['weight_ai'], s['weight_task'])
    worst = _weighted(list(zip(weights, (0.2, min(ai), min(task)))))
    best = _weighted(list(zip(weights, (1.0, max(ai), max(task)))))
    if best == worst:
        return 0.5
    return min(1, max(0, (locked_in(row) - worst) / (best - worst)))


LEVEL_NAMES = [('cooked', '🍳'), ('brain rot', '🧟'), ('NPC', '🤖'), ('locked in', '🔒'), ('heroic', '🦸')]


def levels():
    """Each level as {name, emoji, low, high, cut}: its range on the 0..1 vibe
    scale, and the scoring key for its upper end (None for heroic, which ends at 1)."""
    cuts = [scoring[f'cut_{i}'] for i in range(1, 5)]
    lows, highs = [0] + cuts, cuts + [1]
    keys = [f'cut_{i}' for i in range(1, 5)] + [None]
    return [{'name': n, 'emoji': e, 'low': lo, 'high': hi, 'cut': k}
            for (n, e), lo, hi, k in zip(LEVEL_NAMES, lows, highs, keys)]


def _level(score):
    return next((l for l in levels() if score < l['high']), levels()[-1])


def vibe_emoji(score):
    return _level(score)['emoji']


def add_vibe_emoji(rows, week, usual):
    """Put the level's emoji in front of each workday vibe value in compare rows."""
    for row, w, u in zip(rows, week, usual):
        if row['value'] not in ('', '–'):
            row['value'] = f"{vibe_emoji(w)} {row['value']}"
        if row['usual'] != '–':
            row['usual'] = f"{vibe_emoji(u)} {row['usual']}"
    return rows


def day_locked_in(rows):
    """The day's average scaled locked-in score with its label and emoji, or None for no rows."""
    if not rows:
        return None
    score = _average([locked_in_scaled(r) for r in rows])
    level = _level(score)
    return {'score': f'{score:.2f}', 'label': level['name'], 'emoji': level['emoji']}


def on_task_percent(rows):
    """Whole-number percent of the rows that weren't marked off task, or None for no rows."""
    return round(100 * sum(r['on_task'] != 0 for r in rows) / len(rows)) if rows else None


def daily_quality(rows):
    """Average rating of the given day's pomodoros as stars out of 5, rounded to
    the nearest star (half rounds up), or a dash when none is rated yet."""
    ratings = [r['quality'] for r in rows if r['quality'] is not None]
    if not ratings:
        return '–'
    stars = int(_average(ratings) + 0.5)
    return '⭐' * stars + '☆' * (5 - stars)


def compare_rows(week, usual, scale, today, zero_means_no_data):
    """This week against the usual, one row per weekday, on a shared scale.
    For quality a zero means "nothing rated", so it reads as a dash, not a score."""
    rows = []
    for i, label in enumerate(DAY_LABELS):
        upcoming = i > today.weekday()
        if upcoming:
            value = ''
        elif zero_means_no_data and week[i] == 0:
            value = '–'
        else:
            value = _format_value(week[i])
        # a zero "usual" means no past days of this weekday yet, not a score of zero
        has_usual = usual[i] > 0
        rows.append({
            'label': label,
            'value': value,
            'fill_pct': _percent(week[i], scale),
            'usual': _format_value(usual[i]) if has_usual else '–',
            'usual_pct': _percent(usual[i], scale) if has_usual else None,
            'upcoming': upcoming,
            'colour': '',
        })
    return rows


def category_rows(values, scale=None, zero_means_no_data=False):
    """One coloured row per AI category, scaled to the largest unless given a scale."""
    scale = scale or max(values)
    return [
        {
            'label': category,
            'value': '–' if zero_means_no_data and value == 0 else _format_value(value),
            'fill_pct': _percent(value, scale),
            'usual': None,
            'usual_pct': None,
            'upcoming': False,
            'colour': f'ai-{category}',
        }
        for category, value in zip(AI_CATEGORIES, values)
    ]


def _percent(value, scale):
    return round(value / scale * 100) if scale else 0


def _average(values):
    return sum(values) / len(values) if values else 0


def _format_value(value):
    """One decimal place, dropping a trailing ".0": 5.0 -> "5", 4.17 -> "4.2"."""
    rounded = round(value, 1)
    return str(int(rounded)) if rounded == int(rounded) else str(rounded)
