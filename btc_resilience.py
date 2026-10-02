"""USDT gains sustained while Bitcoin is below the same window's baseline."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from math import isfinite
from typing import Sequence

from triangle_scanner import Candle


HOUR_MS = 3_600_000
WINDOW_HOURS = 24


@dataclass(frozen=True)
class BtcResilience:
    symbol: str
    stage: str
    provisional: bool
    price: float
    strength_score: float
    coin_gain_pct: float
    btc_change_pct: float
    strength_hours: int
    current_streak_hours: int
    window_hours: int
    window_start: str
    window_end: str
    candle_time: str
    candles: list[dict[str, float]]
    reason: str

    def to_dict(self) -> dict:
        return asdict(self)


def detect_btc_resilience(symbol: str, candles: Sequence[Candle],
                          btc_candles: Sequence[Candle],
                          now_ms: int | None = None) -> BtcResilience | None:
    """Sum positive baseline returns at hourly closes where BTC is below baseline.

    Each reading has one hour of weight. This discrete %-hour score rewards
    size and persistence without confusing falling less than BTC with USDT gains.
    Both series must cover the exact same 25 closes, ending at the latest fully
    closed hour at scan start. Open candles, stale data and gaps cannot qualify.
    """
    if symbol == "BTCUSDT" or not symbol.endswith("USDT"):
        return None
    if now_ms is None:
        now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    end = now_ms // HOUR_MS * HOUR_MS - HOUR_MS
    times = [end - i * HOUR_MS for i in range(WINDOW_HOURS, -1, -1)]

    def aligned(source):
        relevant = [bar for bar in source if times[0] <= bar.open_time <= end]
        by_time = {bar.open_time: bar for bar in relevant}
        if len(by_time) != len(relevant) or any(t not in by_time for t in times):
            return None
        bars = [by_time[t] for t in times]
        if any(bar.close_time != bar.open_time + HOUR_MS - 1
               or not isfinite(bar.close) or bar.close <= 0 for bar in bars):
            return None
        return bars

    bars, bitcoin = aligned(candles), aligned(btc_candles)
    if bars is None or bitcoin is None:
        return None
    coin_returns = [(bar.close / bars[0].close - 1) * 100 for bar in bars[1:]]
    btc_returns = [(bar.close / bitcoin[0].close - 1) * 100 for bar in bitcoin[1:]]
    if not all(isfinite(value) for value in coin_returns + btc_returns):
        return None
    qualifying = [gain > 0 and btc < 0 for gain, btc in zip(coin_returns, btc_returns)]
    if not qualifying[-1]:
        return None
    streak = 0
    for qualifies in reversed(qualifying):
        if not qualifies:
            break
        streak += 1
    score = sum(gain for gain, qualifies in zip(coin_returns, qualifying) if qualifies)
    if not isfinite(score):
        return None

    def timestamp(ms):
        return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    return BtcResilience(
        symbol=symbol, stage="BTC resilience", provisional=False, price=bars[-1].close,
        strength_score=round(score, 4), coin_gain_pct=round(coin_returns[-1], 4),
        btc_change_pct=round(btc_returns[-1], 4), strength_hours=sum(qualifying),
        current_streak_hours=streak, window_hours=WINDOW_HOURS,
        window_start=timestamp(bars[0].close_time + 1),
        window_end=timestamp(bars[-1].close_time + 1),
        candle_time=timestamp(bars[-1].open_time),
        candles=[{"t": bar.open_time, "o": bar.open, "h": bar.high,
                  "l": bar.low, "c": bar.close} for bar in bars],
        reason=(f"Over {WINDOW_HOURS} completed hours, {symbol} gained {coin_returns[-1]:.2f}% "
                f"in USDT while BTC changed {btc_returns[-1]:.2f}%. "
                f"Coin above baseline and BTC below baseline at {sum(qualifying)} of "
                f"{WINDOW_HOURS} hourly closes; current streak {streak}. "
                f"Strength {score:.2f} %-hours is the sum of coin gains at qualifying "
                "hourly closes, measured from the same window-start prices."),
    )
