import os

BACKGROUND_DIR = os.path.join('static', 'backgrounds')

_index = 0


def _filenames():
    return sorted(os.listdir(BACKGROUND_DIR))


def current():
    filenames = _filenames()
    return filenames[_index % len(filenames)]


def next_background():
    global _index
    _index = (_index + 1) % len(_filenames())
