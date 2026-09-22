import datetime

AI_OPTIONS = ['chat', 'agents', 'none']  # what you can pick on a pomodoro
# fixed colour order; 'unset' is the bucket for rows where it was never recorded
AI_CATEGORIES = AI_OPTIONS + ['unset']


def format_time(timestamp):
    dt = datetime.datetime.fromisoformat(timestamp)
    return dt.strftime('%I:%M %p').lstrip('0')


def weekday_index(timestamp):
    return datetime.datetime.fromisoformat(timestamp).weekday()  # 0=Mon .. 6=Sun


def _average(values):
    return sum(values) / len(values) if values else 0


def weekday_totals(rows):
    """Per weekday: how many pomodoros, and their average quality."""
    counts = [0] * 7
    qualities = [[] for _ in range(7)]

    for row in rows:
        weekday = weekday_index(row['timestamp'])
        counts[weekday] += 1
        if row['quality'] is not None:
            qualities[weekday].append(row['quality'])

    return counts, [_average(q) for q in qualities]


def historical_weekday_averages(rows, today):
    """The same two figures, but averaged per day across every day strictly
    before today — so a half-finished today never drags down its own average."""
    today_str = today.isoformat()
    dates_seen = [set() for _ in range(7)]
    counts = [0] * 7
    qualities = [[] for _ in range(7)]

    for row in rows:
        date_str = row['timestamp'][:10]
        if date_str >= today_str:
            continue
        weekday = weekday_index(row['timestamp'])
        dates_seen[weekday].add(date_str)
        counts[weekday] += 1
        if row['quality'] is not None:
            qualities[weekday].append(row['quality'])

    avg_counts = [
        counts[w] / len(dates_seen[w]) if dates_seen[w] else 0 for w in range(7)
    ]
    return avg_counts, [_average(q) for q in qualities]


def ai_totals(rows):
    """How many pomodoros in each AI_CATEGORIES slot, in that fixed order."""
    totals = dict.fromkeys(AI_CATEGORIES, 0)
    for row in rows:
        totals[row['ai_usage'] or 'unset'] += 1
    return [totals[category] for category in AI_CATEGORIES]


def bars(values, labels, max_value):
    return [
        {
            'label': label,
            'value': round(value, 1),
            'height_pct': round(value / max_value * 100) if max_value else 0,
        }
        for label, value in zip(labels, values)
    ]
