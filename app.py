"""Local dashboard for monthly triangle alerts. Run: python3 app.py"""

from __future__ import annotations

import json
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from binance_data import active_usdt_symbols, monthly_candles
from triangle_scanner import detect, detect_macd_watch


ROOT = Path(__file__).resolve().parent
STATE_FILE = ROOT / "scan_state.json"
SCAN_INTERVAL_SECONDS = int(os.environ.get("SCAN_INTERVAL_SECONDS", "7200"))
MAX_SYMBOLS = int(os.environ.get("MAX_SYMBOLS", "1000"))
PORT = int(os.environ.get("PORT", "8765"))
lock = threading.Lock()
scan_lock = threading.Lock()
state = {
    "status": "Waiting for first scan", "updated_at": None, "scanned": 0,
    "universe": 0, "errors": 0, "matches": [], "watchlist": [], "last_error": None,
}


def save_state() -> None:
    temp = STATE_FILE.with_suffix(".tmp")
    temp.write_text(json.dumps(state, separators=(",", ":")), encoding="utf-8")
    os.replace(temp, STATE_FILE)


def scan_once() -> None:
    if not scan_lock.acquire(blocking=False):
        return
    try:
        with lock:
            state["status"] = "Scanning"
            state["scanned"] = 0
            state["universe"] = 0
            state["errors"] = 0
            state["last_error"] = None
        symbols = active_usdt_symbols(limit=MAX_SYMBOLS)
        matches = []
        watchlist = []
        with lock:
            state["universe"] = len(symbols)
        with ThreadPoolExecutor(max_workers=4) as pool:
            futures = {pool.submit(_scan_symbol, symbol): symbol for symbol in symbols}
            for future in as_completed(futures):
                symbol = futures[future]
                try:
                    match, watch = future.result()
                    if match:
                        matches.append(match.to_dict())
                    elif watch:
                        watchlist.append(watch.to_dict())
                except Exception as exc:
                    with lock:
                        state["errors"] += 1
                        state["last_error"] = f"{symbol}: {exc}"
                with lock:
                    state["scanned"] += 1
        matches.sort(key=lambda item: item["score"], reverse=True)
        watchlist.sort(key=lambda item: item["months_to_zero_at_recent_pace"])
        with lock:
            state.update(status="Ready", updated_at=datetime.now(timezone.utc).isoformat(),
                         matches=matches, watchlist=watchlist)
            save_state()
    except Exception as exc:
        with lock:
            state["status"] = "Scan failed"
            state["last_error"] = str(exc)
            save_state()
    finally:
        scan_lock.release()


def _scan_symbol(symbol: str):
    candles = monthly_candles(symbol)
    match = detect(symbol, candles)
    return match, None if match else detect_macd_watch(symbol, candles)


def scan_forever() -> None:
    while True:
        scan_once()
        time.sleep(SCAN_INTERVAL_SECONDS)


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        if self.path == "/api/state":
            with lock:
                payload = json.dumps(state).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
        elif self.path in ("/", "/index.html"):
            payload = (ROOT / "index.html").read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
        else:
            self.send_error(404)
            return
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_POST(self) -> None:
        if self.path != "/api/scan":
            self.send_error(404)
            return
        if not scan_lock.locked():
            threading.Thread(target=scan_once, daemon=True).start()
        self.send_response(202)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def log_message(self, format: str, *args) -> None:
        return


if __name__ == "__main__":
    if STATE_FILE.exists():
        try:
            state.update(json.loads(STATE_FILE.read_text(encoding="utf-8")))
            state["status"] = "Starting scan"
        except (OSError, ValueError):
            pass
    server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    threading.Thread(target=scan_forever, daemon=True).start()
    print(f"Triangle scanner: http://127.0.0.1:{PORT}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.server_close()
