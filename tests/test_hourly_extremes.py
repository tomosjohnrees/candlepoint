"""Hourly indicator screening on known price paths."""

import unittest

from hourly_extremes import detect_hourly_extreme, rsi_series
from triangle_scanner import Candle


def candles(closes):
    start = 1_700_000_000_000
    return [Candle(start + i * 3_600_000, start + (i + 1) * 3_600_000 - 1,
                   price, price, price, price, 100)
            for i, price in enumerate(closes)]


class HourlyExtremeTests(unittest.TestCase):
    def test_rsi_handles_flat_and_one_sided_prices(self):
        self.assertEqual(rsi_series([100] * 20)[-1], 50)
        self.assertEqual(rsi_series(list(range(100, 120)))[-1], 100)
        self.assertEqual(rsi_series(list(range(120, 100, -1)))[-1], 0)

    def test_high_extreme_requires_both_indicators(self):
        prices = [100] * 280 + [100 + i for i in range(1, 21)]
        bars = candles(prices)
        result = detect_hourly_extreme("UPUSDT", bars, now_ms=bars[-1].close_time)
        self.assertEqual(result.stage, "Extreme high")
        self.assertTrue(result.provisional)
        self.assertGreaterEqual(result.rsi, 75)
        self.assertGreaterEqual(result.macd_percentile, 95)
        self.assertGreater(result.macd_line, 0)
        self.assertEqual(len(result.candles), 48)
        self.assertIsNone(detect_hourly_extreme("FLATUSDT", candles([100] * 300)))

    def test_high_rsi_without_macd_extreme_is_ignored(self):
        prices = [100] * 279 + [110] * 20 + [110.5]
        self.assertEqual(rsi_series(prices)[-1], 100)
        self.assertIsNone(detect_hourly_extreme("RSIONLYUSDT", candles(prices)))

    def test_low_extreme(self):
        prices = [100] * 280 + [100 - i for i in range(1, 21)]
        bars = candles(prices)
        result = detect_hourly_extreme("DOWNUSDT", bars, now_ms=bars[-1].close_time + 1)
        self.assertEqual(result.stage, "Extreme low")
        self.assertFalse(result.provisional)
        self.assertLessEqual(result.rsi, 25)
        self.assertLessEqual(result.macd_percentile, 5)
        self.assertLess(result.macd_line, 0)

    def test_short_or_duplicate_history_is_ignored(self):
        bars = candles([100] * 215)
        self.assertIsNone(detect_hourly_extreme("SHORTUSDT", bars))
        bars = candles([100] * 300)
        self.assertIsNone(detect_hourly_extreme("DUPUSDT", bars[:-1] + [bars[-2]]))


if __name__ == "__main__":
    unittest.main()
