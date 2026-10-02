"""Known paths distinguish USDT resilience from merely losing less than BTC."""

import unittest
from dataclasses import replace

from btc_resilience import HOUR_MS, detect_btc_resilience
from triangle_scanner import Candle

START = 1_780_000 * HOUR_MS
NOW = START + 25 * HOUR_MS


def candles(closes):
    return [Candle(START + i * HOUR_MS, START + (i + 1) * HOUR_MS - 1,
                   price, price, price, price, 100)
            for i, price in enumerate(closes)]


def detect(coin, btc=None, now=NOW):
    return detect_btc_resilience('ALTUSDT', candles(coin),
                                 candles(btc if btc is not None else [100] + [99] * 24), now)


class BtcResilienceTests(unittest.TestCase):
    def test_score_rewards_size_and_duration(self):
        sustained = detect([100] + [102] * 24)
        late = detect([100] * 24 + [102])
        larger = detect([100] + [104] * 24)
        self.assertEqual(sustained.strength_score, 48)
        self.assertEqual(late.strength_score, 2)
        self.assertEqual(larger.strength_score, 96)
        self.assertEqual(sustained.strength_hours, 24)
        self.assertEqual(sustained.current_streak_hours, 24)
        self.assertEqual(sustained.coin_gain_pct, 2)
        self.assertEqual(sustained.btc_change_pct, -1)
        self.assertFalse(sustained.provisional)
        self.assertEqual(len(sustained.candles), 25)

    def test_only_joint_conditions_contribute_and_streak_resets(self):
        coin = [100] + [102] * 24
        btc = [100] + [99] * 10 + [101] * 10 + [99] * 4
        result = detect(coin, btc)
        self.assertEqual(result.strength_hours, 14)
        self.assertEqual(result.current_streak_hours, 4)
        self.assertEqual(result.strength_score, 28)
        coin[23] = 99
        result = detect(coin, btc)
        self.assertEqual(result.current_streak_hours, 1)
        self.assertEqual(result.strength_hours, 13)
        self.assertEqual(result.strength_score, 26)

    def test_latest_close_must_have_actual_gain_and_bitcoin_loss(self):
        for coin, btc in ((99, 98), (100, 99), (102, 100), (102, 101)):
            with self.subTest(coin=coin, btc=btc):
                self.assertIsNone(detect([100] + [coin] * 24, [100] + [btc] * 24))
        self.assertIsNone(detect([100] + [102] * 23 + [99]))

    def test_open_candle_is_ignored_even_when_it_reverses_signal(self):
        result = detect([100] + [102] * 24 + [1], [100] + [99] * 24 + [200], NOW + HOUR_MS // 2)
        self.assertEqual(result.price, 102)
        self.assertEqual(result.strength_score, 48)
        self.assertIsNone(detect([100] * 25 + [200], now=NOW + HOUR_MS // 2))

    def test_gaps_stale_duplicates_and_invalid_prices_are_rejected(self):
        coin = candles([100] + [102] * 24)
        btc = candles([100] + [99] * 24)
        variants = [coin[:-1], coin[1:], coin[:10] + coin[11:], coin + [coin[-1]],
                    [replace(bar, open_time=bar.open_time + 1) for bar in coin],
                    coin[:-1] + [replace(coin[-1], close_time=NOW)]]
        for value in (0, -1, float('nan'), float('inf')):
            variants.append(coin[:-1] + [replace(coin[-1], close=value)])
        for invalid in variants:
            with self.subTest(invalid=invalid[-1]):
                self.assertIsNone(detect_btc_resilience('ALTUSDT', invalid, btc, NOW))
                self.assertIsNone(detect_btc_resilience('ALTUSDT', coin, invalid, NOW))
        self.assertIsNone(detect_btc_resilience('ALTUSDT', coin, btc, NOW + HOUR_MS))

    def test_exact_timestamp_alignment_and_scale_independence(self):
        coin = candles([100] + [102] * 24)
        btc = candles([100] + [99] * 24)
        result = detect_btc_resilience('ALTUSDT', list(reversed(coin)), btc, NOW)
        self.assertEqual(result.strength_score, 48)
        scaled = [replace(bar, close=bar.close * 1000) for bar in coin]
        self.assertEqual(detect_btc_resilience('ALTUSDT', scaled, btc, NOW).strength_score, 48)
        self.assertIsNone(detect_btc_resilience('BTCUSDT', coin, btc, NOW))
        self.assertIsNone(detect_btc_resilience('ALTBTC', coin, btc, NOW))


if __name__ == '__main__':
    unittest.main()
