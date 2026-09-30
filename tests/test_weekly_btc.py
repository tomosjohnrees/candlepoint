"""Weekly BTC-pair signal thresholds and open-candle handling."""

import unittest
from math import sqrt

from triangle_scanner import Candle
from weekly_btc import ABOVE_BAND, MACD_GREEN, detect_weekly_btc


WEEK_MS = 7 * 24 * 60 * 60 * 1000


def candles(closes):
    return [Candle(i * WEEK_MS, (i + 1) * WEEK_MS - 1, close, close * 1.01,
                   close * 0.99, close, 100) for i, close in enumerate(closes)]


class WeeklyBtcTests(unittest.TestCase):
    def test_first_positive_macd_histogram_is_a_weekly_signal(self):
        prices = [100 - i * 0.05 for i in range(59)]
        prices.append(prices[-1] + 2)
        match = detect_weekly_btc("ETHBTC", candles(prices), now_ms=60 * WEEK_MS)
        self.assertEqual(match.signals, [MACD_GREEN])
        self.assertLessEqual(match.prior_macd_histogram, 0)
        self.assertGreater(match.macd_histogram, 0)
        self.assertFalse(match.provisional)
        self.assertEqual(match.candles[-1]["t"], 59 * WEEK_MS)

    def test_band_signal_requires_weekly_close_three_percent_above_upper_band(self):
        prices = [100 + i * 0.1 for i in range(59)]
        prices.append(prices[-1] + 10)
        match = detect_weekly_btc("SOLBTC", candles(prices), now_ms=60 * WEEK_MS - 1)
        self.assertEqual(match.signals, [ABOVE_BAND])
        self.assertGreaterEqual(match.distance_above_band_pct, 3)
        self.assertTrue(match.provisional)
        self.assertIn("week still open", match.reason)
        recent = prices[-21:]
        middle = sum(recent) / 21
        expected_upper = middle + 2 * sqrt(sum((price - middle) ** 2 for price in recent) / 21)
        self.assertAlmostEqual(match.upper_band, expected_upper)

    def test_both_signals_can_appear_on_one_pair(self):
        prices = [100 - i * 0.05 for i in range(59)]
        prices.append(prices[-1] + 10)
        match = detect_weekly_btc("ADABTC", candles(prices), now_ms=60 * WEEK_MS)
        self.assertEqual(match.signals, [MACD_GREEN, ABOVE_BAND])

    def test_no_signal_for_flat_or_short_history(self):
        self.assertIsNone(detect_weekly_btc("ETHBTC", candles([100] * 60)))
        self.assertIsNone(detect_weekly_btc("ETHBTC", candles([100] * 35)))
        rising = [100 + i * 0.1 for i in range(59)]
        self.assertIsNone(detect_weekly_btc("ETHBTC", candles(rising + [rising[-1] + 5])))


if __name__ == "__main__":
    unittest.main()
