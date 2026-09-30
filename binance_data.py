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
            request = Request(url, headers={"User-Agent": "Candlepoint/0.1"})
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


def _active_spot_symbols(quote_asset: str, limit: int, min_daily_quote_volume: float) -> list[str]:
    exchange = _get("/api/v3/exchangeInfo")
    active = {
        entry["symbol"] for entry in exchange["symbols"]
        if entry.get("status") == "TRADING"
        and entry.get("quoteAsset") == quote_asset
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


def active_usdt_symbols(limit: int = 1000, min_daily_quote_volume: float = 1_000_000) -> list[str]:
    return _active_spot_symbols("USDT", limit, min_daily_quote_volume)


def active_btc_symbols(limit: int = 1000, min_daily_quote_volume: float = 10) -> list[str]:
    return _active_spot_symbols("BTC", limit, min_daily_quote_volume)


def spot_symbol_trading(symbol: str) -> bool:
    """Whether Binance currently allows spot trading for one exact market."""
    try:
        exchange = _get("/api/v3/exchangeInfo", {"symbol": symbol})
    except HTTPError as exc:
        if exc.code in (400, 404):
            return False
        raise
    return any(entry.get("symbol") == symbol and entry.get("status") == "TRADING"
               and entry.get("isSpotTradingAllowed", True)
               for entry in exchange.get("symbols", []))


def monthly_candles(symbol: str, limit: int = 100) -> list[Candle]:
    rows = _get("/api/v3/klines", {"symbol": symbol, "interval": "1M", "limit": limit})
    return _parse_candles(rows)


def hourly_candles(symbol: str, limit: int = 300) -> list[Candle]:
    rows = _get("/api/v3/klines", {"symbol": symbol, "interval": "1h", "limit": limit})
    return _parse_candles(rows)


def weekly_candles(symbol: str, limit: int = 1000) -> list[Candle]:
    rows = _get("/api/v3/klines", {"symbol": symbol, "interval": "1w", "limit": limit})
    return _parse_candles(rows)


def _parse_candles(rows: list) -> list[Candle]:
    return [Candle(
        open_time=int(row[0]), open=float(row[1]), high=float(row[2]),
        low=float(row[3]), close=float(row[4]), close_time=int(row[6]),
        quote_volume=float(row[7]),
    ) for row in rows]


def historical_candles(symbol: str, interval: str, max_bars: int = 5000) -> list[Candle]:
    """Fetch chart history, paging backward past Binance's 1,000-bar limit."""
    if interval not in {"1h", "1d", "1w", "1M"}:
        raise ValueError("Unsupported candle interval")
    if max_bars < 1:
        raise ValueError("max_bars must be positive")
    batches: list[list[Candle]] = []
    total = 0
    end_time = None
    while total < max_bars:
        limit = min(1000, max_bars - total)
        params = {"symbol": symbol, "interval": interval, "limit": limit}
        if end_time is not None:
            params["endTime"] = end_time
        candles = _parse_candles(_get("/api/v3/klines", params))
        if not candles:
            break
        if end_time is not None and candles[-1].open_time > end_time:
            raise ValueError("Overlapping candle history")
        batches.append(candles)
        total += len(candles)
        if len(candles) < limit:
            break
        end_time = candles[0].open_time - 1
    return [candle for batch in reversed(batches) for candle in batch]
