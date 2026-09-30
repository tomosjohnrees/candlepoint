"""Monthly level signals use prior candles and work in both directions."""

from dataclasses import replace
import unittest

from monthly_key_levels import detect_key_level_signal, key_levels_for_bars
from triangle_scanner import Candle


def candles(previous_close: float, current_close: float) -> list[Candle]:
    bars = [Candle(i * 2_600_000_000, (i + 1) * 2_600_000_000 - 1,
                   100, 110, 90, 100, 1000) for i in range(18)]
    for index in (4, 10):
        bars[index] = replace(bars[index], high=120, low=80)
    bars[-2] = replace(bars[-2], close=previous_close)
    bars[-1] = replace(bars[-1], open=previous_close,
                       high=max(110, current_close), low=min(90, current_close),
                       close=current_close)
    return bars


class MonthlyKeyLevelTests(unittest.TestCase):
    def test_prior_swing_levels_are_detected(self):
        levels = key_levels_for_bars(candles(100, 121)[:-1])
        self.assertEqual([(level.price, level.touches) for level in levels],
                         [(80, 2), (120, 2)])

    def test_crosses_in_both_directions(self):
        for previous, current, direction, price in [
            (100, 121, "Crossed above", 120),
            (100, 79, "Crossed below", 80),
        ]:
            with self.subTest(direction=direction):
                bars = candles(previous, current)
                signal = detect_key_level_signal("TESTUSDT", bars,
                                                 now_ms=bars[-1].close_time - 1)
                self.assertEqual(signal.level_signal, direction)
                self.assertEqual(signal.level_price, price)
                self.assertTrue(signal.provisional)

    def test_approach_must_be_close_and_moving_toward_level(self):
        for previous, current, direction in [
            (100, 117.5, "Approaching from below"),
            (100, 82, "Approaching from above"),
        ]:
            with self.subTest(direction=direction):
                signal = detect_key_level_signal("TESTUSDT", candles(previous, current))
                self.assertEqual(signal.level_signal, direction)
        self.assertIsNone(detect_key_level_signal("TESTUSDT", candles(100, 115)))
        self.assertIsNone(detect_key_level_signal("TESTUSDT", candles(119, 117)))

    def test_current_candle_cannot_create_its_own_level(self):
        bars = candles(100, 115)
        bars[-1] = replace(bars[-1], high=200)
        self.assertIsNone(detect_key_level_signal("TESTUSDT", bars))


if __name__ == "__main__":
    unittest.main()
