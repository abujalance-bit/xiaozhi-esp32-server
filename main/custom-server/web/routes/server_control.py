"""Start, stop, and restart the xiaozhi-server process from Flask.

Server stdout/stderr is captured via a pipe into an in-memory ring buffer
(no disk writes). New lines are pushed to all connected browsers in real-time
via Server-Sent Events at GET /server/logs/stream.

Endpoints (all require login):
  GET  /server/status       — {"running": bool, "pid": int|null}
  POST /server/start        — write .config.yaml, spawn server
  POST /server/stop         — SIGTERM (SIGKILL after timeout)
  POST /server/restart      — stop + start in one call
  GET  /server/logs         — browser log-viewer page
  GET  /server/logs/stream  — SSE stream of log lines
"""
import collections
import os
import queue
import shutil
import signal
import subprocess
import threading
import time

from flask import Blueprint, Response, jsonify, make_response, stream_with_context
from flask_login import login_required

server_ctl = Blueprint("server_ctl", __name__, url_prefix="/server")

DATA_DIR = os.environ.get("DATA_DIR", "/app/data")
SERVER_DATA_DIR = os.environ.get("SERVER_DATA_DIR", "/app/server/data")
SERVER_DIR = os.path.dirname(SERVER_DATA_DIR)
PID_FILE = os.path.join(DATA_DIR, ".server.pid")

# Directory containing provider overrides (sibling of the web/ directory)
_OVERRIDES_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
                               "server_overrides")

_SIGTERM_TIMEOUT = 10   # seconds before escalating to SIGKILL
_AUTOSTART_DELAY = 5    # seconds after Flask starts before auto-launching server
_LOG_MAX_LINES = 2000   # ring-buffer size (lines)

# ── In-memory log state ───────────────────────────────────────────────────────
_log_buffer: collections.deque = collections.deque(maxlen=_LOG_MAX_LINES)
_log_subscribers: list = []   # list[queue.Queue] — one per connected SSE client
_log_lock = threading.Lock()


# ── PID helpers ───────────────────────────────────────────────────────────────

def _read_pid():
    try:
        with open(PID_FILE) as f:
            return int(f.read().strip())
    except (FileNotFoundError, ValueError):
        return None


def _write_pid(pid: int):
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(PID_FILE, "w") as f:
        f.write(str(pid))


def _is_running(pid) -> bool:
    if pid is None:
        return False
    try:
        os.kill(pid, 0)
        return True
    except (ProcessLookupError, PermissionError):
        return False


def _kill(pid: int, timeout: int = _SIGTERM_TIMEOUT):
    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not _is_running(pid):
            return
        time.sleep(0.3)
    try:
        os.kill(pid, signal.SIGKILL)
    except ProcessLookupError:
        pass


# ── Log reader ────────────────────────────────────────────────────────────────

def _start_log_reader(proc: subprocess.Popen):
    """Drain proc.stdout in a daemon thread, feeding the buffer and all SSE queues."""
    def _reader():
        for raw in proc.stdout:          # blocks until each line arrives
            line = raw.rstrip("\n")
            with _log_lock:
                _log_buffer.append(line)
                for q in list(_log_subscribers):
                    try:
                        q.put_nowait(line)
                    except queue.Full:
                        pass             # slow subscriber — skip line, don't block

        # Process exited — send sentinel so SSE clients know
        with _log_lock:
            for q in list(_log_subscribers):
                try:
                    q.put_nowait(None)
                except queue.Full:
                    pass

    threading.Thread(target=_reader, daemon=True, name="server-log-reader").start()


# ── Core actions ──────────────────────────────────────────────────────────────

def _copy_overrides():
    """Copy server_overrides/ into the xiaozhi-server directory."""
    if not os.path.isdir(_OVERRIDES_DIR):
        return
    for root, dirs, files in os.walk(_OVERRIDES_DIR):
        rel = os.path.relpath(root, _OVERRIDES_DIR)
        dest_dir = os.path.join(SERVER_DIR, rel)
        os.makedirs(dest_dir, exist_ok=True)
        for fname in files:
            src = os.path.join(root, fname)
            dst = os.path.join(dest_dir, fname)
            shutil.copy2(src, dst)
    print(f"[server_ctl] overrides copied from {_OVERRIDES_DIR}", flush=True)


def _launch(clear_log: bool = True) -> int:
    """Copy overrides, write a fresh .config.yaml, spawn the server. Returns PID."""
    _copy_overrides()
    from app import _write_server_config
    _write_server_config()

    if clear_log:
        with _log_lock:
            _log_buffer.clear()

    proc = subprocess.Popen(
        ["python", "app.py"],
        cwd=SERVER_DIR,
        env={**os.environ, "PYTHONUNBUFFERED": "1"},
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        bufsize=1,      # line-buffered
        text=True,
    )
    _write_pid(proc.pid)
    _start_log_reader(proc)
    return proc.pid


def get_status() -> dict:
    pid = _read_pid()
    running = _is_running(pid)
    return {"running": running, "pid": pid if running else None}


def autostart_server_background():
    """Called at Flask startup — wait for Flask to bind, then launch the server."""
    def _worker():
        time.sleep(_AUTOSTART_DELAY)
        if not get_status()["running"]:
            pid = _launch()
            print(f"[server_ctl] xiaozhi-server started (pid {pid})", flush=True)

    threading.Thread(target=_worker, daemon=True, name="server-autostart").start()


# ── API routes ────────────────────────────────────────────────────────────────

@server_ctl.get("/status")
@login_required
def status():
    return jsonify(get_status())


@server_ctl.post("/start")
@login_required
def start():
    pid = _read_pid()
    if _is_running(pid):
        return jsonify({"ok": False, "error": "Already running", "pid": pid})
    new_pid = _launch()
    return jsonify({"ok": True, "pid": new_pid})


@server_ctl.post("/stop")
@login_required
def stop():
    pid = _read_pid()
    if not _is_running(pid):
        return jsonify({"ok": False, "error": "Not running"})
    _kill(pid)
    return jsonify({"ok": True})


@server_ctl.post("/restart")
@login_required
def restart():
    pid = _read_pid()
    if _is_running(pid):
        _kill(pid)
    new_pid = _launch()
    return jsonify({"ok": True, "pid": new_pid})


# ── SSE log stream ────────────────────────────────────────────────────────────

@server_ctl.get("/logs/stream")
@login_required
def logs_stream():
    client_q: queue.Queue = queue.Queue(maxsize=500)

    with _log_lock:
        _log_subscribers.append(client_q)
        snapshot = list(_log_buffer)   # send history before streaming

    def generate():
        try:
            for line in snapshot:
                yield f"data: {_sse_line(line)}\n\n"
            while True:
                try:
                    line = client_q.get(timeout=20)
                    if line is None:   # server process ended
                        yield "event: server_stopped\ndata: \n\n"
                        return
                    yield f"data: {_sse_line(line)}\n\n"
                except queue.Empty:
                    yield ": keepalive\n\n"   # prevent proxy/browser timeout
        finally:
            with _log_lock:
                try:
                    _log_subscribers.remove(client_q)
                except ValueError:
                    pass

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def _sse_line(text: str) -> str:
    # SSE data field must not contain raw newlines
    return text.replace("\r", "").replace("\n", " ")


# ── Log viewer page ───────────────────────────────────────────────────────────

_LOG_PAGE = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Server Logs — Xiaozhi</title>
<style>
  :root{--bg:#0d1117;--surface:#161b22;--border:#30363d;--text:#c9d1d9;
        --dim:#8b949e;--green:#3fb950;--red:#f85149;--mono:'Consolas','Courier New',monospace}
  *{box-sizing:border-box;margin:0;padding:0}
  body{background:var(--bg);color:var(--text);font:13px/1.5 var(--mono);
       display:flex;flex-direction:column;height:100vh;overflow:hidden}
  header{padding:10px 14px;background:var(--surface);border-bottom:1px solid var(--border);
         display:flex;align-items:center;gap:10px;flex-shrink:0}
  h1{font-size:13px;font-weight:600;color:#e6edf3}
  .dot{width:8px;height:8px;border-radius:50%;background:var(--dim);flex-shrink:0;
       transition:background .3s}
  .dot.ok{background:var(--green)}
  .dot.err{background:var(--red)}
  #statusTxt{font-size:11px;color:var(--dim)}
  .spacer{flex:1}
  button,a.btn{background:#21262d;border:1px solid var(--border);color:var(--text);
               padding:4px 11px;border-radius:6px;cursor:pointer;font-size:11px;
               text-decoration:none;display:inline-block}
  button:hover,a.btn:hover{background:var(--border)}
  #log{flex:1;overflow-y:auto;padding:6px 10px}
  .ln{white-space:pre-wrap;word-break:break-all;padding:1px 0;line-height:1.5}
  .ln:hover{background:rgba(255,255,255,.03)}
</style>
</head>
<body>
<header>
  <h1>xiaozhi-server logs</h1>
  <div class="dot" id="dot"></div>
  <span id="statusTxt">Connecting…</span>
  <div class="spacer"></div>
  <button onclick="clearLog()">Clear</button>
  <button onclick="toggleScroll()" id="scrollBtn">⬇ Auto-scroll</button>
  <a class="btn" href="javascript:void(0)" onclick="restartServer()">↺ Restart</a>
  <a class="btn" href="/">← Back</a>
</header>
<div id="log"></div>

<script>
const logEl   = document.getElementById('log');
const dot     = document.getElementById('dot');
const sTxt    = document.getElementById('statusTxt');
let autoScroll = true;

function clearLog() { logEl.innerHTML = ''; }

function toggleScroll() {
  autoScroll = !autoScroll;
  document.getElementById('scrollBtn').textContent =
    (autoScroll ? '⬇' : '  ') + ' Auto-scroll';
}

function addLine(text) {
  const d = document.createElement('div');
  d.className = 'ln';
  d.textContent = text;
  logEl.appendChild(d);
  if (autoScroll) logEl.scrollTop = logEl.scrollHeight;
}

async function restartServer() {
  addLine('--- restarting server… ---');
  const r = await fetch('/server/restart', {method:'POST'});
  const j = await r.json();
  addLine(j.ok ? `--- server started (pid ${j.pid}) ---` : `--- restart failed: ${j.error} ---`);
}

const es = new EventSource('/server/logs/stream');

es.onopen = () => {
  dot.className = 'dot ok';
  sTxt.textContent = 'Streaming';
};

es.onmessage = e => addLine(e.data);

es.addEventListener('server_stopped', () => {
  addLine('─── server process ended ───');
  dot.className = 'dot err';
  sTxt.textContent = 'Server stopped';
});

es.onerror = () => {
  dot.className = 'dot err';
  sTxt.textContent = 'Stream disconnected — reload to reconnect';
};
</script>
</body>
</html>
"""


@server_ctl.get("/logs")
@login_required
def logs_page():
    return make_response(_LOG_PAGE, 200, {"Content-Type": "text/html; charset=utf-8"})
