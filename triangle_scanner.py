"""Causal monthly descending-triangle and MACD screening.

The thresholds are screening heuristics, not a trading strategy. Every value is
computed from candles available at the time of the alert.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from statistics import median
from typing import Sequence


@dataclass(frozen=True)
class Candle:
    open_time: int  # Unix milliseconds
    close_time: int
    open: float
    high: float
    low: float
    close: float
    quote_volume: float


@dataclass(frozen=True)
class Match:
    symbol: str
    stage: str
    provisional: bool
    score: float
    price: float
    support: float
    resistance: float
    distance_to_resistance_pct: float
    macd_histogram: float
    prior_macd_histogram: float
    support_touches: int
    lower_highs: int
    window_months: int
    months_to_apex: float
    trend_start_index: int
    trend_start_price: float
    month: str
    candles: list[dict[str, float]]
    reason: str

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class MacdWatch:
    symbol: str
    provisional: bool
    price: float
    macd_histogram: float
    prior_macd_histogram: float
    two_months_ago_macd_histogram: float
    improvement_pct: float
    months_to_zero_at_recent_pace: float
    month: str
    candles: list[dict[str, float]]
    reason: str

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class BaseBreakout:
    symbol: str
    stage: str
    provisional: bool
    price: float
    support: float
    resistance: float
    distance_to_resistance_pct: float
    macd_histogram: float
    prior_macd_histogram: float
    support_touches: int
    base_months: int
    month: str
    candles: list[dict[str, float]]
    reason: str

    def to_dict(self) -> dict:
        return asdict(self)


def ema(values: Sequence[float], period: int) -> list[float]:
    if period < 1 or not values:
        raise ValueError("EMA needs a positive period and nonempty values")
    alpha = 2 / (period + 1)
    result = [float(values[0])]
    for value in values[1:]:
        result.append(alpha * value + (1 - alpha) * result[-1])
    return result


def macd_histogram(closes: Sequence[float]) -> list[float]:
    """Standard 12/26/9 EMA MACD histogram, with a 35-bar warmup."""
    if len(closes) < 36:
        return []
    fast, slow = ema(closes, 12), ema(closes, 26)
    line = [a - b for a, b in zip(fast, slow)]
    signal = ema(line, 9)
    return [a - b for a, b in zip(line, signal)]


def detect_macd_watch(symbol: str, candles: Sequence[Candle],
                      now_ms: int | None = None) -> MacdWatch | None:
    """A separate early signal: negative monthly MACD rising toward zero.

    This intentionally makes no claim that the price forms a triangle.
    """
    if now_ms is None:
        now_ms = int(datetime.now(tz=timezone.utc).timestamp() * 1000)
    if len(candles) < 36 or any(c.close <= 0 for c in candles):
        return None
    bars = sorted(candles, key=lambda c: c.open_time)
    if len({c.open_time for c in bars}) != len(bars):
        return None
    hist = macd_histogram([c.close for c in bars])
    older, previous, current = hist[-3:]
    if not (older < previous < current < 0):
        return None
    improvement = (current - older) / -older * 100
    monthly_step = (current - older) / 2
    months_to_zero = -current / monthly_step
    if improvement < 25 or months_to_zero > 3:
        return None
    last = bars[-1]
    provisional = last.close_time >= now_ms
    month = datetime.fromtimestamp(last.open_time / 1000, tz=timezone.utc).strftime("%Y-%m")
    reason = (f"Monthly MACD histogram is still negative, but has risen for two "
              f"consecutive months and moved {improvement:.0f}% closer to zero. "
              f"At that recent pace, the gap equals {months_to_zero:.1f} months; "
              f"this is not a crossover forecast or a triangle match"
              f"{' (month still open)' if provisional else ''}.")
    return MacdWatch(
        symbol, provisional, last.close, current, previous, older,
        round(improvement, 1), round(months_to_zero, 1), month,
        [{"o": c.open, "h": c.high, "l": c.low, "c": c.close}
         for c in bars[-36:]], reason,
    )


def detect_short_base_breakout(symbol: str, candles: Sequence[Candle],
                               now_ms: int | None = None) -> BaseBreakout | None:
    """First monthly candle above an eight-month floor/ceiling after a decline.

    This is deliberately distinct from the multiyear descending-triangle fit.
    """
    if now_ms is None:
        now_ms = int(datetime.now(tz=timezone.utc).timestamp() * 1000)
    if len(candles) < 36 or any(c.close <= 0 or c.low <= 0 for c in candles):
        return None
    bars = sorted(candles, key=lambda c: c.open_time)
    if len({c.open_time for c in bars}) != len(bars):
        return None
    hist = macd_histogram([c.close for c in bars])
    if hist[-1] <= 0 or not any(h <= 0 for h in hist[-4:-1]):
        return None

    base = bars[-9:-1]
    floor_lows = sorted(c.low for c in base)
    support = median(floor_lows[:3])
    ceiling = max(c.high for c in base)
    if ceiling / support > 4.5:
        return None
    touches = [i for i, c in enumerate(base)
               if abs(c.low / support - 1) <= 0.40]
    if len(touches) < 3 or touches[-1] - touches[0] < 6:
        return None
    if max(c.high for c in bars[-36:-9]) < ceiling * 2:
        return None
    if max(c.close for c in base[-3:]) >= ceiling * 0.95:
        return None
    previous_ceiling = max(c.high for c in bars[-10:-2])
    if bars[-2].close >= previous_ceiling * 1.05:
        return None

    current = bars[-1]
    if current.close < ceiling * 1.05 or current.close > ceiling * 2:
        return None
    distance = (ceiling - current.close) / ceiling * 100
    provisional = current.close_time >= now_ms
    month = datetime.fromtimestamp(current.open_time / 1000,
                                   tz=timezone.utc).strftime("%Y-%m")
    price_label = "Current price" if provisional else "First monthly close"
    reason = (f"{price_label} {abs(distance):.1f}% above the prior "
              f"eight-month base high; {len(touches)} floor-zone tests across "
              f"at least seven months; monthly MACD histogram positive. "
              f"Short-base breakout, not a multiyear triangle"
              f"{' (month still open)' if provisional else ''}.")
    return BaseBreakout(
        symbol, "short-base breakout", provisional, current.close, support,
        ceiling, round(distance, 2), hist[-1], hist[-2], len(touches), 8,
        month, [{"o": c.open, "h": c.high, "l": c.low, "c": c.close}
                for c in bars[-24:]], reason,
    )


def pivots(values: Sequence[float], kind: str, radius: int = 2) -> list[int]:
    result = []
    for i in range(radius, len(values) - radius):
        neighbours = values[i - radius : i] + values[i + 1 : i + radius + 1]
        if kind == "low" and values[i] <= min(neighbours):
            result.append(i)
        elif kind == "high" and values[i] >= max(neighbours):
            result.append(i)
    return result


def _candidate(candles: Sequence[Candle], symbol: str, start: int,
               hist: Sequence[float], provisional: bool) -> Match | None:
    bars = candles[start:]
    n = len(bars)
    lows = [c.low for c in bars]
    highs = [c.high for c in bars]
    high_pivots = pivots(highs, "high")
    if len(high_pivots) < 2:
        return None

    # Treat the bottom as a zone. The reference chart has several lower wicks
    # through its manually drawn floor, so a rigid horizontal line misses it.
    recent_start = max(0, n - 24)
    recent_lows = sorted(lows[recent_start:])
    support = median(recent_lows[:max(3, len(recent_lows) // 3)])
    touching = [i for i in range(n) if
                abs(lows[i] / support - 1) <= 0.35]
    touches = []
    for i in touching:
        if not touches or i - touches[-1] >= 3:
            touches.append(i)
    if (len(touches) < 3 or touches[-1] - touches[0] < 18
            or touches[-1] < n - 12):
        return None
    if bars[-1].close < support * 0.85:
        return None

    # Fit an upper boundary through an early prominent peak and a later lower
    # swing high. The fit is accepted only if most highs remain below it.
    early = [i for i in high_pivots if i <= n // 3]
    if not early:
        return None
    first = max(early, key=lambda i: highs[i])
    if max(highs[first + 1:]) > highs[first] * 1.10:
        return None
    later = [i for i in high_pivots if i >= n // 2 and i < n - 2 and highs[i] < highs[first] * 0.80]
    if not later:
        return None
    fits = []
    for last in later:
        slope = (highs[last] - highs[first]) / (last - first)
        resistance = highs[first] + slope * (n - 1 - first)
        if slope >= 0 or resistance <= support:
            continue
        upper = [highs[first] + slope * (i - first) for i in range(first, n)]
        violations = sum(highs[first + i] > level * 1.18 for i, level in enumerate(upper))
        if violations > max(2, len(upper) // 6):
            continue
        peak_values = [highs[i] for i in high_pivots if first <= i <= last]
        declining = sum(current < previous * 0.98
                        for previous, current in zip(peak_values, peak_values[1:]))
        if declining < 2:
            continue
        width_at_first = highs[first] - support
        width_now = resistance - support
        if width_now / width_at_first > 0.35:
            continue
        months_to_apex = (resistance - support) / -slope
        if months_to_apex > 8:
            continue
        fits.append((violations, abs(highs[last] - resistance), resistance, declining,
                     months_to_apex, first, highs[first]))
    if not fits:
        return None
    _, _, resistance, declining, months_to_apex, trend_start_index, trend_start_price = min(fits)

    price = bars[-1].close
    distance = (resistance - price) / resistance * 100
    if price < support * 0.88 or distance > 25 or distance < -10:
        return None

    # The green histogram must be new or recent; a long-running green MACD is
    # a different setup. The open monthly candle is always marked provisional.
    if hist[-1] <= 0 or not any(h <= 0 for h in hist[-4:-1]):
        return None
    stage = "breaking out" if price >= resistance * 1.01 else "near breakout"
    closeness = max(0.0, 1 - abs(distance) / 25)
    stability = min(1.0, len(touches) / 4)
    score = round(100 * (0.55 * closeness + 0.25 * stability + 0.20 * min(1, declining / 3)), 1)
    month = datetime.fromtimestamp(bars[-1].open_time / 1000, tz=timezone.utc).strftime("%Y-%m")
    reason = (f"{len(touches)} support-zone tests, {declining} lower swing highs; "
              f"price {abs(distance):.1f}% {'below' if distance >= 0 else 'above'} resistance; "
              f"estimated apex in {months_to_apex:.1f} months; "
              f"monthly MACD histogram positive{' (month still open)' if provisional else ''}.")
    return Match(symbol, stage, provisional, score, price, support, resistance,
                 round(distance, 2), hist[-1], hist[-2], len(touches), declining,
                 n, round(months_to_apex, 1), trend_start_index, trend_start_price,
                 month, [{"o": c.open, "h": c.high, "l": c.low, "c": c.close} for c in bars], reason)


def detect(symbol: str, candles: Sequence[Candle], now_ms: int | None = None) -> Match | None:
    if now_ms is None:
        now_ms = int(datetime.now(tz=timezone.utc).timestamp() * 1000)
    if len(candles) < 42 or any(c.close <= 0 or c.low <= 0 for c in candles):
        return None
    bars = sorted(candles, key=lambda c: c.open_time)
    if len({c.open_time for c in bars}) != len(bars):
        return None
    hist = macd_histogram([c.close for c in bars])
    if not hist:
        return None
    provisional = bars[-1].close_time >= now_ms

    # Freeze the triangle at the previous month before testing a new breakout.
    # Including the breakout candle in the fit can move the upper boundary and
    # reject exactly the first breakout candle the user wants to see.
    if len(bars) >= 43 and hist[-1] > 0:
        prior = _best_candidate(symbol, bars[:-1], hist[:-1], False)
        if prior is not None and prior.stage == "near breakout":
            span = prior.window_months - 1 - prior.trend_start_index
            slope = (prior.resistance - prior.trend_start_price) / span
            resistance = prior.resistance + slope
            price = bars[-1].close
            if resistance > 0 and price >= resistance * 1.01:
                distance = (resistance - price) / resistance * 100
                month = datetime.fromtimestamp(bars[-1].open_time / 1000,
                                               tz=timezone.utc).strftime("%Y-%m")
                reason = (f"First monthly candle above the prior triangle boundary; "
                          f"price {abs(distance):.1f}% above projected resistance; "
                          f"monthly MACD histogram positive"
                          f"{' (month still open)' if provisional else ''}.")
                return Match(
                    symbol, "breaking out", provisional, prior.score, price,
                    prior.support, resistance, round(distance, 2), hist[-1], hist[-2],
                    prior.support_touches, prior.lower_highs, prior.window_months + 1,
                    round(max(0, prior.months_to_apex - 1), 1),
                    prior.trend_start_index, prior.trend_start_price, month,
                    prior.candles + [{"o": bars[-1].open, "h": bars[-1].high,
                                      "l": bars[-1].low, "c": price}], reason,
                )

    return _best_candidate(symbol, bars, hist, provisional)


def _best_candidate(symbol: str, bars: Sequence[Candle], hist: Sequence[float],
                    provisional: bool) -> Match | None:
    candidates = []
    for months in (24, 30, 36, 42, 48, 54, 60):
        if len(bars) >= months:
            found = _candidate(bars, symbol, len(bars) - months, hist, provisional)
            if found:
                candidates.append(found)
    return max(candidates, key=lambda m: m.score) if candidates else None
