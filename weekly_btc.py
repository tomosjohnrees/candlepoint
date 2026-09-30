"""Weekly MACD and Bollinger Band signals for BTC-quoted spot pairs."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from math import sqrt
from typing import Sequence

from triangle_scanner import Candle, macd_histogram


MACD_GREEN = "MACD turning green"
ABOVE_BAND = "Above upper band"
BAND_MARGIN = 0.03
BAND_PERIOD = 21


@dataclass(frozen=True)
class WeeklyBtcSignal:
    symbol: str
    stage: str
    signals: list[str]
    provisional: bool
    price: float
    week: str
    macd_histogram: float
    prior_macd_histogram: float
    upper_band: float
    distance_above_band_pct: float
    candles: list[dict[str, float]]
    reason: str

    def to_dict(self) -> dict:
        return asdict(self)


def detect_weekly_btc(symbol: str, candles: Sequence[Candle],
                      now_ms: int | None = None) -> WeeklyBtcSignal | None:
    if now_ms is None:
        now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    if len(candles) < 36 or any(c.close <= 0 or c.low <= 0 for c in candles):
        return None
    bars = sorted(candles, key=lambda bar: bar.open_time)
    if len({bar.open_time for bar in bars}) != len(bars):
        return None
    closes = [bar.close for bar in bars]
    histogram = macd_histogram(closes)
    green = histogram[-2] <= 0 < histogram[-1]
    recent = closes[-BAND_PERIOD:]
    middle = sum(recent) / BAND_PERIOD
    deviation = sqrt(sum((close - middle) ** 2 for close in recent) / BAND_PERIOD)
    upper = middle + 2 * deviation
    distance = (closes[-1] / upper - 1) * 100
    above_band = distance >= BAND_MARGIN * 100
    if not green and not above_band:
        return None
    signals = ([MACD_GREEN] if green else []) + ([ABOVE_BAND] if above_band else [])
    last = bars[-1]
    provisional = last.close_time >= now_ms
    week = datetime.fromtimestamp(last.open_time / 1000, tz=timezone.utc).strftime("%Y-%m-%d")
    reasons = []
    if green:
        reasons.append("Weekly MACD 12/26/9 histogram turned positive after a nonpositive week")
    if above_band:
        reasons.append(f"weekly close is {distance:.1f}% above the upper Bollinger Band (21 closes, 2 standard deviations)")
    reason = "; ".join(reasons) + (" (week still open)." if provisional else ".")
    return WeeklyBtcSignal(
        symbol, "weekly BTC", signals, provisional, last.close, week,
        histogram[-1], histogram[-2], upper, round(distance, 2),
        [{"t": bar.open_time, "o": bar.open, "h": bar.high, "l": bar.low,
          "c": bar.close} for bar in bars[-52:]], reason,
    )
