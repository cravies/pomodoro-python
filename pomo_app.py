"""The desktop app: runs the server in the background and shows it in its own
window instead of a browser tab. Built into Pomo.exe by build.bat. Closing the
window quits, so a round in progress is dropped, as with a server restart."""
import logging
import sys
import threading
import time
import webbrowser

from werkzeug.serving import make_server

import app as server_app
import timer
from app import app, clock_state

PORT = 5123  # fixed, so a second launch finds the first one's server

# what the popup says when each mode runs out, and its two buttons. The timer
# has lined up the next round but waits: the first button starts it, the
# second starts another of the round that just ran out instead.
POPUPS = {
    'pomodoro': ('🍅 Pomodoro done', '☕ Take a break', '🍅 Keep focusing'),
    'short_break': ('☕ Break over', '🍅 Back to focus', '☕ A bit longer'),
    'long_break': ('🌴 Break over', '🍅 Back to focus', '🌴 A bit longer'),
}

POPUP_HTML = """<!doctype html>
<html><head><meta charset="utf-8"><style>
  body {{ margin: 0; height: 100vh; display: flex; flex-direction: column; align-items: center;
         justify-content: center; gap: 18px; font: 600 20px system-ui, sans-serif;
         background: #ba4949; color: #fff; user-select: none; }}
  div {{ display: flex; gap: 10px; }}
  button {{ font: 600 15px system-ui, sans-serif; padding: 10px 16px; border: 0; border-radius: 8px;
           cursor: pointer; background: #fff; color: #ba4949; }}
  button + button {{ background: rgba(255, 255, 255, 0.2); color: #fff; }}
</style></head><body>
  <span>{title}</span>
  <div>
    <button onclick="pywebview.api.keep()">{keep}</button>
    <button onclick="pywebview.api.swap()">{swap}</button>
  </div>
</body></html>"""

popup = None  # the one popup showing, if any


class PopupButtons:
    """What the popup's buttons call, from its page."""

    def __init__(self, ended):
        self.ended = ended  # the mode that ran out

    def keep(self):
        timer.start()
        close_popup()

    def swap(self):
        timer.switch(self.ended)  # nothing's running yet, so nothing is dropped
        timer.start()
        close_popup()


_popup_lock = threading.Lock()


def close_popup():
    global popup
    with _popup_lock:
        window, popup = popup, None
    if window:
        window.destroy()


def show_popup(done):
    """A small window over everything else, even with Pomo minimized."""
    import webview
    global popup
    close_popup()  # a popup nobody answered gives way to the newer one
    title, keep, swap = POPUPS[done['mode']]
    popup = webview.create_window(
        'Pomo', html=POPUP_HTML.format(title=title, keep=keep, swap=swap), js_api=PopupButtons(done['mode']),
        width=380, height=170, resizable=False, on_top=True)


def keep_ticking(window=None):
    """Every second: end a round that's run out (the page's own polling can
    stall while the window is minimized), close a popup made pointless by the
    timer being started from the main window, and count down in the window
    title, which the taskbar shows."""
    while True:
        try:
            server_app.advance()
            if popup and timer.state()['running']:
                close_popup()
            if window:
                window.set_title(clock_state()['title'])
        except Exception:
            pass  # try again next second
        time.sleep(1)


def main():
    logging.getLogger('werkzeug').setLevel(logging.ERROR)
    url = f'http://127.0.0.1:{PORT}/'
    try:
        server = make_server('127.0.0.1', PORT, app, threaded=True)
    except OSError:
        server = None  # already running: open another window on that one
    if server:
        threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        import webview
    except ImportError:
        webbrowser.open(url)
        if server:
            keep_ticking()
        return
    window = webview.create_window('Pomo', url, width=1100, height=800, min_size=(400, 500))
    if server:
        server_app.on_round_end = show_popup
        webview.start(keep_ticking, window)
    else:
        webview.start()


if __name__ == '__main__':
    main()
