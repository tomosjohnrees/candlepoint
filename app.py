"""Local Candlepoint dashboard. Run: python3 app.py"""

from __future__ import annotations

import json
import os
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from binance_data import (active_btc_symbols, active_usdt_symbols, hourly_candles,
                          historical_candles, monthly_candles, weekly_candles)
from hourly_extremes import detect_hourly_extreme
from monthly_key_levels import detect_key_level_signal
from triangle_scanner import detect, detect_macd_watch, detect_short_base_breakout
from weekly_btc import detect_weekly_btc


ROOT = Path(__file__).resolve().parent
STATE_FILE = ROOT / "scan_state.json"
SCAN_INTERVAL_SECONDS = int(os.environ.get("SCAN_INTERVAL_SECONDS", "7200"))
MAX_SYMBOLS = int(os.environ.get("MAX_SYMBOLS", "1000"))
PORT = int(os.environ.get("PORT", "8765"))
lock = threading.Lock()
scan_lock = threading.Lock()
state = {
    "status": "Waiting for first scan", "updated_at": None, "scanned": 0,
    "universe": 0, "errors": 0, "matches": [], "watchlist": [],
    "key_levels": [], "hourly_extremes": [], "btc_weekly": [], "last_error": None,
    "comparison_available": False,
}
RESULT_GROUPS = ("matches", "watchlist", "key_levels", "hourly_extremes", "btc_weekly")
SYMBOL_PATTERN = re.compile(r"[A-Z0-9]{1,30}(?:USDT|BTC)\Z")


def signal_identity(group: str, item: dict) -> tuple:
    """Identify a signal across scans without treating a new candle as a new result."""
    if group == "btc_weekly":
        return (group, item["symbol"], tuple(item["signals"]))
    return (group, item["symbol"], item.get("stage", item.get("level_signal")),
            item.get("level_price") if group == "key_levels" else None)


def mark_new_signals(results: dict, previous: dict | None) -> None:
    previous_ids = ({signal_identity(group, item) for group in RESULT_GROUPS
                     for item in previous.get(group, [])} if previous else set())
    for group in RESULT_GROUPS:
        for item in results[group]:
            item["is_new"] = previous is not None and signal_identity(group, item) not in previous_ids


def save_state() -> None:
    temp = STATE_FILE.with_suffix(".tmp")
    temp.write_text(json.dumps(state, separators=(",", ":")), encoding="utf-8")
    os.replace(temp, STATE_FILE)


def scan_once() -> None:
    if not scan_lock.acquire(blocking=False):
        return
    try:
        with lock:
            previous = ({group: state.get(group, []) for group in RESULT_GROUPS}
                        if state["updated_at"] else None)
            state["status"] = "Scanning"
            state["scanned"] = 0
            state["universe"] = 0
            state["errors"] = 0
            state["last_error"] = None
        symbols = active_usdt_symbols(limit=MAX_SYMBOLS)
        btc_symbols = active_btc_symbols(limit=MAX_SYMBOLS)
        matches = []
        watchlist = []
        key_levels = []
        hourly_extremes = []
        btc_weekly = []
        with lock:
            state["universe"] = len(symbols) + len(btc_symbols)
        with ThreadPoolExecutor(max_workers=4) as pool:
            futures = {pool.submit(_scan_symbol, symbol): (symbol, "USDT") for symbol in symbols}
            futures.update({pool.submit(_scan_btc_symbol, symbol): (symbol, "BTC")
                            for symbol in btc_symbols})
            for future in as_completed(futures):
                symbol, quote_asset = futures[future]
                try:
                    if quote_asset == "BTC":
                        weekly = future.result()
                        if weekly:
                            btc_weekly.append(weekly.to_dict())
                    else:
                        match, watch, key_level, extreme, monthly_error, hourly_error = future.result()
                        if match:
                            matches.append(match.to_dict())
                        elif watch:
                            watchlist.append(watch.to_dict())
                        if key_level:
                            key_levels.append(key_level.to_dict())
                        if extreme:
                            hourly_extremes.append(extreme.to_dict())
                        if monthly_error:
                            with lock:
                                state["errors"] += 1
                                state["last_error"] = f"{symbol} monthly: {monthly_error}"
                        if hourly_error:
                            with lock:
                                state["errors"] += 1
                                state["last_error"] = f"{symbol} 1-hour: {hourly_error}"
                except Exception as exc:
                    with lock:
                        state["errors"] += 1
                        state["last_error"] = f"{symbol}: {exc}"
                with lock:
                    state["scanned"] += 1
        matches.sort(key=lambda item: (item.get("score") is not None,
                                       item.get("score", 0)), reverse=True)
        watchlist.sort(key=lambda item: item["months_to_zero_at_recent_pace"])
        key_levels.sort(key=lambda item: (item["level_signal"].startswith("Approaching"),
                                          abs(item["distance_pct"])))
        hourly_extremes.sort(key=lambda item: abs(item["rsi"] - 50), reverse=True)
        btc_weekly.sort(key=lambda item: (len(item["signals"]), item["distance_above_band_pct"]),
                        reverse=True)
        results = {"matches": matches, "watchlist": watchlist,
                   "key_levels": key_levels, "hourly_extremes": hourly_extremes,
                   "btc_weekly": btc_weekly}
        mark_new_signals(results, previous)
        with lock:
            state.update(status="Ready", updated_at=datetime.now(timezone.utc).isoformat(),
                         comparison_available=previous is not None, **results)
            save_state()
    except Exception as exc:
        with lock:
            state["status"] = "Scan failed"
            state["last_error"] = str(exc)
            save_state()
    finally:
        scan_lock.release()


def _scan_symbol(symbol: str):
    try:
        candles = monthly_candles(symbol)
        match = detect(symbol, candles) or detect_short_base_breakout(symbol, candles)
        watch = None if match else detect_macd_watch(symbol, candles)
        key_level = detect_key_level_signal(symbol, candles)
        monthly_error = None
    except Exception as exc:
        match, watch, key_level, monthly_error = None, None, None, exc
    try:
        extreme = detect_hourly_extreme(symbol, hourly_candles(symbol))
        hourly_error = None
    except Exception as exc:
        extreme, hourly_error = None, exc
    return match, watch, key_level, extreme, monthly_error, hourly_error


def _scan_btc_symbol(symbol: str):
    return detect_weekly_btc(symbol, weekly_candles(symbol))


def chart_history(symbol: str, interval: str):
    return (historical_candles(symbol, interval, max_bars=1000) if interval == "1h"
            else historical_candles(symbol, interval))


def scan_forever() -> None:
    while True:
        scan_once()
        time.sleep(SCAN_INTERVAL_SECONDS)


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        request = urlsplit(self.path)
        if request.path == "/api/state":
            with lock:
                payload = json.dumps(state).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
        elif request.path == "/api/coin":
            symbols = parse_qs(request.query).get("symbol", [])
            symbol = symbols[0] if len(symbols) == 1 else ""
            if not SYMBOL_PATTERN.fullmatch(symbol):
                self.send_error(400, "Invalid symbol")
                return
            with lock:
                payload = json.dumps({
                    "symbol": symbol,
                    "status": state["status"],
                    "updated_at": state["updated_at"],
                    "signals": [{"group": group, "match": item}
                                for group in RESULT_GROUPS
                                for item in state.get(group, []) if item["symbol"] == symbol],
                }).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
        elif request.path == "/api/chart":
            query = parse_qs(request.query)
            symbols = query.get("symbol", [])
            symbol = symbols[0] if len(symbols) == 1 else ""
            intervals = query.get("interval", ["1M"])
            interval = intervals[0] if len(intervals) == 1 else ""
            if interval not in {"1h", "1d", "1w", "1M"}:
                self.send_error(400, "Unsupported candle interval")
                return
            with lock:
                available = any(item["symbol"] == symbol for group in RESULT_GROUPS
                                for item in state.get(group, []))
                if not available and symbol.endswith("USDT"):
                    btc_pair = symbol[:-4] + "BTC"
                    available = any(item["symbol"] == btc_pair
                                    for item in state.get("btc_weekly", []))
                derived_from = None
                if not available and symbol.endswith("BTC"):
                    usdt_pair = symbol[:-3] + "USDT"
                    if any(item["symbol"] == usdt_pair
                           for group in RESULT_GROUPS for item in state.get(group, [])):
                        derived_from = usdt_pair
            if not available and not derived_from:
                self.send_error(404, "Chart unavailable")
                return
            try:
                if derived_from:
                    coin_candles = chart_history(derived_from, interval)
                    btc_candles = {bar.open_time: bar for bar in chart_history("BTCUSDT", interval)}
                    candles = []
                    for bar in coin_candles:
                        btc = btc_candles.get(bar.open_time)
                        if btc and btc.close > 0:
                            relative_close = bar.close / btc.close
                            candles.append({"t": bar.open_time, "o": relative_close,
                                            "h": relative_close, "l": relative_close,
                                            "c": relative_close})
                    if not candles:
                        raise ValueError("No matching BTC and USDT candles")
                else:
                    candles = [{"t": bar.open_time, "o": bar.open, "h": bar.high,
                                "l": bar.low, "c": bar.close} for bar in chart_history(symbol, interval)]
            except Exception:
                self.send_error(502, "Could not load chart history")
                return
            payload = json.dumps({
                "symbol": symbol, "interval": interval, "derived": bool(derived_from),
                "candles": candles,
            }).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
        elif request.path.startswith("/coin/"):
            if not SYMBOL_PATTERN.fullmatch(request.path[len("/coin/"):]):
                self.send_error(404)
                return
            payload = (ROOT / "coin.html").read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
        elif request.path in ("/", "/index.html", "/patterns", "/key-levels", "/macd-watch", "/hourly-extremes", "/btc-weekly",
                              "/key_levels.js", "/bollinger_bands.js", "/coin.js"):
            filename = request.path.lstrip("/") if request.path.endswith(".js") else "index.html"
            payload = (ROOT / filename).read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "application/javascript; charset=utf-8" if request.path.endswith(".js")
                             else "text/html; charset=utf-8")
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
    print(f"Candlepoint: http://127.0.0.1:{PORT}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.server_close()
