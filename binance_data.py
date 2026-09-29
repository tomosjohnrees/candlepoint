"""Read-only Binance Spot market data adapter."""

from __future__ import annotations

import json
import os
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from triangle_scanner import Candle


BASE = os.environ.get("BINANCE_API_BASE", "https://data-api.binance.vision").rstrip("/")
EXCLUDED_BASES = {
    "USDC", "FDUSD", "TUSD", "BUSD", "DAI", "USDP", "USDE", "USD1",
    "PYUSD", "RLUSD", "EUR", "GBP", "TRY",
}


def _get(path: str, params: dict | None = None):
    url = BASE + path + ("?" + urlencode(params) if params else "")
    for attempt in range(3):
        try:
            request = Request(url, headers={"User-Agent": "TriangleScanner/0.1"})
            with urlopen(request, timeout=18) as response:
                return json.load(response)
        except HTTPError as exc:
            if exc.code not in (429, 500, 502, 503, 504) or attempt == 2:
                raise
            retry_after = exc.headers.get("Retry-After")
            time.sleep(float(retry_after) if retry_after else 2 ** attempt)
        except (URLError, TimeoutError):
            if attempt == 2:
                raise
            time.sleep(2 ** attempt)


def active_usdt_symbols(limit: int = 1000, min_daily_quote_volume: float = 1_000_000) -> list[str]:
    exchange = _get("/api/v3/exchangeInfo")
    active = {
        entry["symbol"] for entry in exchange["symbols"]
        if entry.get("status") == "TRADING"
        and entry.get("quoteAsset") == "USDT"
        and entry.get("isSpotTradingAllowed", True)
        and entry.get("baseAsset") not in EXCLUDED_BASES
    }
    tickers = _get("/api/v3/ticker/24hr")
    ranked = sorted(
        ((entry["symbol"], float(entry.get("quoteVolume", 0))) for entry in tickers
         if entry.get("symbol") in active),
        key=lambda pair: pair[1], reverse=True,
    )
    return [symbol for symbol, volume in ranked if volume >= min_daily_quote_volume][:limit]


def monthly_candles(symbol: str, limit: int = 100) -> list[Candle]:
    rows = _get("/api/v3/klines", {"symbol": symbol, "interval": "1M", "limit": limit})
    return [Candle(
        open_time=int(row[0]), open=float(row[1]), high=float(row[2]),
        low=float(row[3]), close=float(row[4]), close_time=int(row[6]),
        quote_volume=float(row[7]),
    ) for row in rows]
