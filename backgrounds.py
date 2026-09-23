from pathlib import Path

# Rotates through static/backgrounds, one step per finished pomodoro. Each wide
# photo has a same-named square crop in static/portrait for narrow windows.

BACKGROUND_DIR = Path(__file__).parent / 'static' / 'backgrounds'

_index = 0


def _filenames():
    # read on every call, so adding or removing images needs no restart
    return sorted(p.name for p in BACKGROUND_DIR.iterdir() if p.is_file())


def current():
    filenames = _filenames()
    return filenames[_index % len(filenames)]


def next_background():
    global _index
    _index = (_index + 1) % len(_filenames())
