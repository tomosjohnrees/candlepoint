import json
import unittest
from dataclasses import replace
from pathlib import Path

from triangle_scanner import Candle, detect, detect_macd_watch


FIXTURE = Path(__file__).parent / "fixtures" / "near_monthly_through_2026_08.json"
BREAKOUT = Path(__file__).parent / "fixtures" / "near_2026_09_first_breakout.json"
FALSE_POSITIVE = Path(__file__).parent / "fixtures" / "pha_monthly_through_2026_09.json"
FET = Path(__file__).parent / "fixtures" / "fet_monthly_through_2026_09.json"


class TriangleScannerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.candles = [Candle(**row) for row in json.loads(FIXTURE.read_text())]

    def test_reference_pattern_is_found_before_breakout(self):
        last = self.candles[-1]
        match = detect("NEARUSDT", self.candles, now_ms=last.close_time + 1)
        self.assertIsNotNone(match)
        self.assertEqual(match.stage, "near breakout")
        self.assertEqual(match.month, "2026-08")
        self.assertGreater(match.macd_histogram, 0)
        self.assertLessEqual(match.months_to_apex, 8)
        self.assertFalse(match.provisional)

    def test_open_month_is_marked_provisional(self):
        last = self.candles[-1]
        match = detect("NEARUSDT", self.candles, now_ms=last.close_time - 1000)
        self.assertIsNotNone(match)
        self.assertTrue(match.provisional)

    def test_first_breakout_month_remains_visible_after_a_large_move(self):
        breakout = Candle(**json.loads(BREAKOUT.read_text()))
        match = detect("NEARUSDT", self.candles + [breakout],
                       now_ms=breakout.close_time - 1000)
        self.assertIsNotNone(match)
        self.assertEqual(match.stage, "breaking out")
        self.assertEqual(match.month, "2026-09")
        self.assertGreater(match.price, match.resistance)
        self.assertTrue(match.provisional)

    def test_breakout_is_not_repeated_the_following_month(self):
        breakout = Candle(**json.loads(BREAKOUT.read_text()))
        next_month = Candle(1790812800000, 1793491199999, 4.95, 5.3,
                            4.5, 5.0, 1_000_000_000)
        self.assertIsNone(detect("NEARUSDT", self.candles + [breakout, next_month],
                                 now_ms=next_month.close_time + 1))

    def test_duplicate_candles_are_rejected(self):
        self.assertIsNone(detect("NEARUSDT", self.candles + [self.candles[-1]]))

    def test_recent_collapse_is_not_a_multiyear_flat_base(self):
        candles = [Candle(**row) for row in json.loads(FALSE_POSITIVE.read_text())]
        self.assertIsNone(detect("PHAUSDT", candles[:-1],
                                 now_ms=candles[-2].close_time + 1))
        self.assertIsNone(detect("PHAUSDT", candles,
                                 now_ms=candles[-1].close_time - 1000))

    def test_fet_is_an_early_macd_watch_but_not_a_triangle_match(self):
        candles = [Candle(**row) for row in json.loads(FET.read_text())]
        self.assertIsNone(detect("FETUSDT", candles,
                                 now_ms=candles[-1].close_time - 1000))
        watch = detect_macd_watch("FETUSDT", candles,
                                  now_ms=candles[-1].close_time - 1000)
        self.assertIsNotNone(watch)
        self.assertEqual(watch.symbol, "FETUSDT")
        self.assertTrue(watch.provisional)
        self.assertLess(watch.macd_histogram, 0)
        self.assertGreater(watch.improvement_pct, 25)

        # A positive histogram has crossed zero and cannot be an early watch.
        crossed = candles[:-1] + [replace(candles[-1], close=0.5)]
        self.assertIsNone(detect_macd_watch("FETUSDT", crossed,
                                            now_ms=candles[-1].close_time - 1000))


if __name__ == "__main__":
    unittest.main()
