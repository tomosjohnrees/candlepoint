"""One-hour MACD and RSI extremes from Binance spot candles."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Sequence

from triangle_scanner import Candle, ema


RSI_PERIOD = 14
RSI_HIGH = 80
RSI_LOW = 20
MACD_LOOKBACK = 180
MIN_CANDLES = 36 + MACD_LOOKBACK


@dataclass(frozen=True)
class HourlyExtreme:
    symbol: str
    stage: str
    provisional: bool
    price: float
    rsi: float
    macd_line: float
    macd_pct: float
    macd_percentile: float
    candle_time: str
    candles: list[dict[str, float]]
    reason: str

    def to_dict(self) -> dict:
        return asdict(self)


def rsi_series(closes: Sequence[float], period: int = RSI_PERIOD) -> list[float | None]:
    """Wilder RSI, seeded with the average of the first 14 changes."""
    result: list[float | None] = [None] * len(closes)
    if len(closes) <= period:
        return result
    changes = [current - previous for previous, current in zip(closes, closes[1:])]
    gain = sum(max(change, 0) for change in changes[:period]) / period
    loss = sum(max(-change, 0) for change in changes[:period]) / period

    def value() -> float:
        if loss == 0:
            return 100.0 if gain else 50.0
        return 100 - 100 / (1 + gain / loss)

    result[period] = value()
    for i, change in enumerate(changes[period:], start=period + 1):
        gain = (gain * (period - 1) + max(change, 0)) / period
        loss = (loss * (period - 1) + max(-change, 0)) / period
        result[i] = value()
    return result


def detect_hourly_extreme(symbol: str, candles: Sequence[Candle],
                          now_ms: int | None = None) -> HourlyExtreme | None:
    if len(candles) < MIN_CANDLES:
        return None
    bars = sorted(candles, key=lambda candle: candle.open_time)
    if (len({bar.open_time for bar in bars}) != len(bars)
            or any(bar.close <= 0 for bar in bars)):
        return None
    closes = [bar.close for bar in bars]
    fast, slow = ema(closes, 12), ema(closes, 26)
    lines = [a - b for a, b in zip(fast, slow)]
    current = lines[-1]
    rsi = rsi_series(closes)[-1]
    if rsi is None:
        return None
    # Compare MACD as a percentage of price so the displayed size is comparable
    # across assets. Rank against this symbol's own 180 preceding 1-hour bars.
    relative = [line / close * 100 for line, close in zip(lines, closes)]
    previous = relative[-MACD_LOOKBACK - 1:-1]
    rank = sum(value <= relative[-1] for value in previous) / MACD_LOOKBACK * 100
    high = rsi >= RSI_HIGH and current > 0 and rank >= 95
    low = rsi <= RSI_LOW and current < 0 and rank <= 5
    if not (high or low):
        return None
    last = bars[-1]
    if now_ms is None:
        now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    provisional = last.close_time >= now_ms
    stage = "Extreme high" if high else "Extreme low"
    time = datetime.fromtimestamp(last.open_time / 1000, tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    reason = (f"1-hour RSI is {rsi:.1f} and MACD is at the {rank:.0f}th percentile "
              f"of the previous {MACD_LOOKBACK} 1-hour readings"
              f"{' (current candle still open)' if provisional else ''}.")
    return HourlyExtreme(
        symbol, stage, provisional, last.close, round(rsi, 1), current,
        round(relative[-1], 3), round(rank, 1), time,
        [{"o": bar.open, "h": bar.high, "l": bar.low, "c": bar.close}
         for bar in bars[-48:]], reason,
    )
