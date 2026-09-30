"""Historical chart candle loading."""

import unittest
from unittest.mock import patch

import binance_data


def row(open_time):
    return [open_time, "1", "3", "0.5", "2", "0", open_time + 1, "100"]


class HistoricalCandlesTests(unittest.TestCase):
    def test_btc_universe_uses_btc_quote_volume_and_excludes_stablecoins(self):
        exchange = {"symbols": [
            {"symbol": "ETHBTC", "status": "TRADING", "quoteAsset": "BTC", "baseAsset": "ETH"},
            {"symbol": "SOLBTC", "status": "TRADING", "quoteAsset": "BTC", "baseAsset": "SOL"},
            {"symbol": "USDCBTC", "status": "TRADING", "quoteAsset": "BTC", "baseAsset": "USDC"},
            {"symbol": "ETHUSDT", "status": "TRADING", "quoteAsset": "USDT", "baseAsset": "ETH"},
        ]}
        tickers = [{"symbol": symbol, "quoteVolume": volume} for symbol, volume in
                   [("ETHBTC", "20"), ("SOLBTC", "5"), ("USDCBTC", "30"), ("ETHUSDT", "100")]]
        with patch.object(binance_data, "_get", side_effect=[exchange, tickers]):
            self.assertEqual(binance_data.active_btc_symbols(), ["ETHBTC"])

    def test_weekly_scan_fetches_weekly_candles(self):
        with patch.object(binance_data, "_get", return_value=[row(1000)]) as fetch:
            candles = binance_data.weekly_candles("ETHBTC")
        fetch.assert_called_once_with("/api/v3/klines",
                                      {"symbol": "ETHBTC", "interval": "1w", "limit": 1000})
        self.assertEqual(candles[0].open_time, 1000)

    def test_exact_btc_market_must_be_trading_for_real_chart(self):
        with patch.object(binance_data, "_get", return_value={"symbols": [
            {"symbol": "NEARBTC", "status": "TRADING", "isSpotTradingAllowed": True}
        ]}) as fetch:
            self.assertTrue(binance_data.spot_symbol_trading("NEARBTC"))
        fetch.assert_called_once_with("/api/v3/exchangeInfo", {"symbol": "NEARBTC"})
        with patch.object(binance_data, "_get", return_value={"symbols": [
            {"symbol": "XVSBTC", "status": "BREAK", "isSpotTradingAllowed": True}
        ]}):
            self.assertFalse(binance_data.spot_symbol_trading("XVSBTC"))

    def test_hourly_scan_fetches_hourly_candles(self):
        with patch.object(binance_data, "_get", return_value=[row(1000)]) as fetch:
            candles = binance_data.hourly_candles("NEARUSDT")
        fetch.assert_called_once_with("/api/v3/klines",
                                      {"symbol": "NEARUSDT", "interval": "1h", "limit": 300})
        self.assertEqual(candles[0].open_time, 1000)

    def test_daily_history_pages_backward_without_overlap(self):
        latest = [row(i) for i in range(1000, 2000)]
        older = [row(i) for i in range(998, 1000)]
        with patch.object(binance_data, "_get", side_effect=[latest, older]) as fetch:
            candles = binance_data.historical_candles("NEARUSDT", "1d")
        self.assertEqual([bar.open_time for bar in candles], list(range(998, 2000)))
        self.assertEqual(fetch.call_args_list[0].args[1],
                         {"symbol": "NEARUSDT", "interval": "1d", "limit": 1000})
        self.assertEqual(fetch.call_args_list[1].args[1],
                         {"symbol": "NEARUSDT", "interval": "1d", "limit": 1000,
                          "endTime": 999})


if __name__ == "__main__":
    unittest.main()
