"""The desktop app: runs the server in the background and shows it in its own
window instead of a browser tab. Built into Pomo.exe by build.bat. Closing the
window quits, so a round in progress is dropped, as with a server restart."""
import logging
import threading
import time
import webbrowser

from werkzeug.serving import make_server

from app import app, clock_state

PORT = 5123  # fixed, so a second launch finds the first one's server


def keep_title_ticking(window):
    # the taskbar shows the window title, so it counts down there too
    while True:
        window.set_title(clock_state()['title'])
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
            server.serve_forever()
        return
    window = webview.create_window('Pomo', url, width=1100, height=800, min_size=(400, 500))
    if server:
        webview.start(keep_title_ticking, window)
    else:
        webview.start()


if __name__ == '__main__':
    main()
