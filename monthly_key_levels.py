"""Monthly swing-level proximity and close-to-close crossing signals."""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Sequence

from triangle_scanner import Candle


@dataclass(frozen=True)
class Level:
    price: float
    touches: int
    prominence: float = 0
    last: int = -1
    span: int = 0


@dataclass(frozen=True)
class KeyLevelSignal:
    symbol: str
    stage: str
    level_signal: str
    level_price: float
    level_touches: int
    distance_pct: float
    price: float
    previous_price: float
    provisional: bool
    month: str
    candles: list[dict[str, float]]
    reason: str

    def to_dict(self) -> dict:
        return asdict(self)


def key_levels_for_bars(bars: Sequence[Candle], limit: int = 5) -> list[Level]:
    """Mirror the chart's swing-level ranking for a fixed monthly window."""
    if not bars or limit < 1:
        return []
    if len(bars) < 3:
        low = min(bar.low for bar in bars)
        high = max(bar.high for bar in bars)
        prices = [low] if low == high else [low, high]
        return [Level(price, 1) for price in prices[:limit]]

    radius = 2 if len(bars) >= 7 else 1
    pivots: list[tuple[float, int, float]] = []
    for i in range(radius, len(bars) - radius):
        neighbors = list(bars[i - radius:i]) + list(bars[i + 1:i + radius + 1])
        high = bars[i].high
        low = bars[i].low
        if high >= max(bar.high for bar in neighbors) and any(high > bar.high for bar in neighbors):
            pivots.append((high, i, math.log(high / max(bar.high for bar in neighbors))))
        if low <= min(bar.low for bar in neighbors) and any(low < bar.low for bar in neighbors):
            pivots.append((low, i, math.log(min(bar.low for bar in neighbors) / low)))

    groups: list[dict] = []
    for price, index, prominence in sorted(pivots):
        if price <= 0:
            continue
        group = next((item for item in groups
                      if abs(math.log(price / item["price"])) <= math.log(1.025)), None)
        if group is None:
            group = {"price": price, "pivots": []}
            groups.append(group)
        group["pivots"].append((price, index, prominence))
        prices = sorted(pivot[0] for pivot in group["pivots"])
        group["price"] = prices[len(prices) // 2]

    levels = []
    for group in groups:
        touches = []
        for _, index, _ in sorted(group["pivots"], key=lambda pivot: pivot[1]):
            if not touches or index - touches[-1] > radius * 2:
                touches.append(index)
        levels.append(Level(group["price"], len(touches),
                            max(pivot[2] for pivot in group["pivots"]),
                            touches[-1] if touches else -1,
                            touches[-1] - touches[0] if len(touches) > 1 else 0))

    def score(level: Level) -> float:
        return (level.touches * 2 + min(3, level.prominence / .12)
                + min(1, level.span / len(bars)) + level.last / len(bars) * .5)

    levels.sort(key=score, reverse=True)
    if len(levels) < 2:
        levels.extend((Level(max(bar.high for bar in bars), 1),
                       Level(min(bar.low for bar in bars), 1)))
    selected = []
    for level in levels:
        if len(selected) == limit:
            break
        if all(abs(math.log(level.price / other.price)) > math.log(1.045)
               for other in selected):
            selected.append(level)
    return sorted(selected, key=lambda level: level.price)


def detect_key_level_signal(symbol: str, candles: Sequence[Candle],
                            now_ms: int | None = None) -> KeyLevelSignal | None:
    """Find the nearest crossing, or an approach within 3%, this month."""
    if now_ms is None:
        now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    bars = sorted(candles, key=lambda bar: bar.open_time)
    if (len(bars) < 12 or len({bar.open_time for bar in bars}) != len(bars)
            or any(bar.low <= 0 or bar.high < bar.low or bar.close <= 0 for bar in bars)):
        return None
    previous, current = bars[-2:]
    candidates = []
    for level in key_levels_for_bars(bars[:-1]):
        price = level.price
        if previous.close < price <= current.close:
            direction = "Crossed above"
            crossed = True
        elif previous.close > price >= current.close:
            direction = "Crossed below"
            crossed = True
        elif (previous.close < current.close < price
              and (price - current.close) / price <= .03):
            direction = "Approaching from below"
            crossed = False
        elif (previous.close > current.close > price
              and (current.close - price) / price <= .03):
            direction = "Approaching from above"
            crossed = False
        else:
            continue
        distance = (current.close / price - 1) * 100
        candidates.append((not crossed, abs(distance), -level.touches, level, direction, distance))
    if not candidates:
        return None
    _, _, _, level, direction, distance = min(candidates, key=lambda item: item[:3])
    provisional = current.close_time >= now_ms
    month = datetime.fromtimestamp(current.open_time / 1000, timezone.utc).strftime("%Y-%m")
    reason = (f"Monthly price {direction.lower()} the {level.price:.8g} swing level "
              f"({level.touches} separate swing {'test' if level.touches == 1 else 'tests'}); "
              f"previous close {previous.close:.8g}, current {'price' if provisional else 'close'} "
              f"{current.close:.8g}, {abs(distance):.1f}% from the level"
              f"{' (month still open)' if provisional else ''}.")
    return KeyLevelSignal(
        symbol, "monthly key level", direction, level.price, level.touches,
        round(distance, 2), current.close, previous.close, provisional, month,
        [{"o": bar.open, "h": bar.high, "l": bar.low, "c": bar.close}
         for bar in bars[-36:]], reason,
    )
