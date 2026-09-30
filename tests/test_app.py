"""Checks for the chart history route used by the in-app chart view."""

import json
from io import BytesIO
import unittest
from unittest.mock import Mock, patch

import app
from triangle_scanner import Candle


class ChartRouteTests(unittest.TestCase):
    def setUp(self):
        with app.lock:
            self.old_matches = app.state["matches"]
            self.old_watchlist = app.state["watchlist"]
            self.old_key_levels = app.state["key_levels"]
            self.old_hourly_extremes = app.state["hourly_extremes"]
            self.old_btc_weekly = app.state["btc_weekly"]
            app.state["matches"] = [{"symbol": "NEARUSDT"}]
            app.state["watchlist"] = []
            app.state["key_levels"] = [{"symbol": "LEVELUSDT"}]
            app.state["hourly_extremes"] = [{"symbol": "HOURUSDT"}]
            app.state["btc_weekly"] = [{"symbol": "ETHBTC"}]

    def tearDown(self):
        with app.lock:
            app.state["matches"] = self.old_matches
            app.state["watchlist"] = self.old_watchlist
            app.state["key_levels"] = self.old_key_levels
            app.state["hourly_extremes"] = self.old_hourly_extremes
            app.state["btc_weekly"] = self.old_btc_weekly

    def request(self, query):
        handler = app.Handler.__new__(app.Handler)
        handler.path = "/api/chart?" + query
        handler.wfile = BytesIO()
        handler.send_response = Mock()
        handler.send_header = Mock()
        handler.end_headers = Mock()
        handler.send_error = Mock()
        handler.do_GET()
        return handler

    def test_chart_returns_full_monthly_history_for_a_result(self):
        candle = Candle(1_700_000_000_000, 1_702_000_000_000, 2, 3, 1, 2.5, 100)
        with patch.object(app, "historical_candles", return_value=[candle]) as fetch:
            handler = self.request("symbol=NEARUSDT")
        fetch.assert_called_once_with("NEARUSDT", "1M")
        handler.send_response.assert_called_once_with(200)
        result = json.loads(handler.wfile.getvalue())
        self.assertEqual(result, {"symbol": "NEARUSDT", "interval": "1M", "derived": False, "candles": [
            {"t": candle.open_time, "o": 2, "h": 3, "l": 1, "c": 2.5}]})

    def test_unknown_symbol_is_rejected_without_fetching(self):
        with patch.object(app, "historical_candles") as fetch:
            handler = self.request("symbol=OTHERUSDT")
        handler.send_error.assert_called_once_with(404, "Chart unavailable")
        fetch.assert_not_called()

    def test_daily_interval_fetches_daily_candles(self):
        with patch.object(app, "historical_candles", return_value=[]) as fetch:
            handler = self.request("symbol=NEARUSDT&interval=1d")
        fetch.assert_called_once_with("NEARUSDT", "1d")
        self.assertEqual(json.loads(handler.wfile.getvalue())["interval"], "1d")

    def test_key_level_only_result_can_open_chart(self):
        with patch.object(app, "historical_candles", return_value=[]) as fetch:
            handler = self.request("symbol=LEVELUSDT")
        fetch.assert_called_once_with("LEVELUSDT", "1M")
        handler.send_response.assert_called_once_with(200)

    def test_hourly_result_can_open_hourly_chart(self):
        with patch.object(app, "historical_candles", return_value=[]) as fetch:
            handler = self.request("symbol=HOURUSDT&interval=1h")
        fetch.assert_called_once_with("HOURUSDT", "1h", max_bars=1000)
        handler.send_response.assert_called_once_with(200)

    def test_weekly_btc_result_can_open_weekly_chart(self):
        with patch.object(app, "historical_candles", return_value=[]) as fetch:
            handler = self.request("symbol=ETHBTC&interval=1w")
        fetch.assert_called_once_with("ETHBTC", "1w")
        handler.send_response.assert_called_once_with(200)

    def test_weekly_btc_result_can_open_usdt_chart_for_same_coin(self):
        with patch.object(app, "historical_candles", return_value=[]) as fetch:
            handler = self.request("symbol=ETHUSDT&interval=1w")
        fetch.assert_called_once_with("ETHUSDT", "1w")
        handler.send_response.assert_called_once_with(200)

    def test_usdt_result_can_open_current_btc_equivalent_chart(self):
        near = Candle(1_700_000_000_000, 1_700_100_000_000, 4, 5, 3, 4.5, 100)
        btc = Candle(near.open_time, near.close_time, 45000, 46000, 44000, 45000, 100)
        unrelated = Candle(near.open_time - 604800000, near.close_time - 604800000,
                           40000, 41000, 39000, 40000, 100)
        with patch.object(app, "historical_candles", side_effect=[[near], [unrelated, btc]]) as fetch:
            handler = self.request("symbol=NEARBTC&interval=1w")
        self.assertEqual(fetch.call_count, 2)
        self.assertEqual([call.args for call in fetch.call_args_list],
                         [("NEARUSDT", "1w"), ("BTCUSDT", "1w")])
        data = json.loads(handler.wfile.getvalue())
        self.assertTrue(data["derived"])
        self.assertEqual(data["symbol"], "NEARBTC")
        self.assertEqual(data["candles"], [{"t": near.open_time, "o": .0001,
                                             "h": .0001, "l": .0001, "c": .0001}])

    def test_btc_equivalent_requires_an_active_usdt_result(self):
        with patch.object(app, "historical_candles") as fetch:
            handler = self.request("symbol=OTHERBTC&interval=1w")
        handler.send_error.assert_called_once_with(404, "Chart unavailable")
        fetch.assert_not_called()

    def test_unrelated_usdt_chart_remains_unavailable(self):
        with patch.object(app, "historical_candles") as fetch:
            handler = self.request("symbol=BNBUSDT&interval=1w")
        handler.send_error.assert_called_once_with(404, "Chart unavailable")
        fetch.assert_not_called()

    def test_unsupported_interval_is_rejected(self):
        with patch.object(app, "historical_candles") as fetch:
            handler = self.request("symbol=NEARUSDT&interval=1m")
        handler.send_error.assert_called_once_with(400, "Unsupported candle interval")
        fetch.assert_not_called()

    def test_key_levels_script_is_served(self):
        handler = app.Handler.__new__(app.Handler)
        handler.path = "/key_levels.js"
        handler.wfile = BytesIO()
        handler.send_response = Mock()
        handler.send_header = Mock()
        handler.end_headers = Mock()
        handler.do_GET()
        handler.send_response.assert_called_once_with(200)
        handler.send_header.assert_any_call("Content-Type", "application/javascript; charset=utf-8")
        self.assertIn(b"function keyLevelsForBars", handler.wfile.getvalue())

    def test_bollinger_script_is_served(self):
        handler = app.Handler.__new__(app.Handler)
        handler.path = "/bollinger_bands.js"
        handler.wfile = BytesIO()
        handler.send_response = Mock()
        handler.send_header = Mock()
        handler.end_headers = Mock()
        handler.do_GET()
        handler.send_response.assert_called_once_with(200)
        handler.send_header.assert_any_call("Content-Type", "application/javascript; charset=utf-8")
        self.assertIn(b"function bollingerBandsForBars", handler.wfile.getvalue())

    def test_view_paths_serve_the_dashboard(self):
        for path in ("/patterns", "/key-levels", "/macd-watch", "/hourly-extremes", "/btc-weekly"):
            with self.subTest(path=path):
                handler = app.Handler.__new__(app.Handler)
                handler.path = path + "?chart=NEARUSDT&interval=1d"
                handler.wfile = BytesIO()
                handler.send_response = Mock()
                handler.send_header = Mock()
                handler.end_headers = Mock()
                handler.do_GET()
                handler.send_response.assert_called_once_with(200)
                handler.send_header.assert_any_call("Content-Type", "text/html; charset=utf-8")
                self.assertIn(b"Candlepoint", handler.wfile.getvalue())


class CoinPageTests(unittest.TestCase):
    def request(self, path):
        handler = app.Handler.__new__(app.Handler)
        handler.path = path
        handler.wfile = BytesIO()
        handler.send_response = Mock()
        handler.send_header = Mock()
        handler.end_headers = Mock()
        handler.send_error = Mock()
        handler.do_GET()
        return handler

    def test_coin_api_combines_every_signal_for_pair(self):
        with app.lock:
            original = {group: app.state[group] for group in app.RESULT_GROUPS}
            original_status = app.state["status"]
            original_updated = app.state["updated_at"]
            for group in app.RESULT_GROUPS:
                app.state[group] = []
            app.state["matches"] = [{"symbol": "NEARUSDT", "stage": "near breakout"}]
            app.state["key_levels"] = [{"symbol": "NEARUSDT", "level_signal": "Crossed above"},
                                       {"symbol": "OTHERUSDT", "level_signal": "Crossed below"}]
            app.state["status"] = "Ready"
            app.state["updated_at"] = "2026-09-30T12:00:00+00:00"
        try:
            handler = self.request("/api/coin?symbol=NEARUSDT")
        finally:
            with app.lock:
                app.state.update(original, status=original_status, updated_at=original_updated)
        handler.send_response.assert_called_once_with(200)
        data = json.loads(handler.wfile.getvalue())
        self.assertEqual(data["symbol"], "NEARUSDT")
        self.assertEqual([item["group"] for item in data["signals"]], ["matches", "key_levels"])
        self.assertEqual(data["updated_at"], "2026-09-30T12:00:00+00:00")

    def test_coin_route_and_script_are_served(self):
        page = self.request("/coin/ETHBTC")
        page.send_response.assert_called_once_with(200)
        page.send_header.assert_any_call("Content-Type", "text/html; charset=utf-8")
        self.assertIn(b"Coin details", page.wfile.getvalue())
        script = self.request("/coin.js")
        script.send_response.assert_called_once_with(200)
        script.send_header.assert_any_call("Content-Type", "application/javascript; charset=utf-8")

    def test_invalid_coin_path_and_query_are_rejected(self):
        self.request("/coin/../app.py").send_error.assert_called_once_with(404)
        self.request("/api/coin?symbol=ETHBTC&symbol=BNBBTC").send_error.assert_called_once_with(400, "Invalid symbol")


class ScanIsolationTests(unittest.TestCase):
    def test_hourly_scan_still_runs_when_monthly_data_fails(self):
        with patch.object(app, "monthly_candles", side_effect=RuntimeError("monthly unavailable")), \
             patch.object(app, "hourly_candles", return_value=[]) as hourly, \
             patch.object(app, "detect_hourly_extreme", return_value="hourly match"):
            match, watch, level, extreme, monthly_error, hourly_error = app._scan_symbol("HOURUSDT")
        hourly.assert_called_once_with("HOURUSDT")
        self.assertIsNone(match)
        self.assertIsNone(watch)
        self.assertIsNone(level)
        self.assertEqual(extreme, "hourly match")
        self.assertIsInstance(monthly_error, RuntimeError)
        self.assertIsNone(hourly_error)


class WeeklyScanTests(unittest.TestCase):
    def test_btc_weekly_results_join_the_completed_scan(self):
        weekly = Mock()
        weekly.to_dict.return_value = {
            "symbol": "ETHBTC", "stage": "weekly BTC",
            "signals": ["MACD turning green"], "distance_above_band_pct": 0.5,
        }
        with patch.dict(app.state, {"updated_at": None}, clear=False), \
             patch.object(app, "active_usdt_symbols", return_value=[]), \
             patch.object(app, "active_btc_symbols", return_value=["ETHBTC"]), \
             patch.object(app, "_scan_btc_symbol", return_value=weekly), \
             patch.object(app, "save_state"):
            app.scan_once()
            self.assertEqual(app.state["universe"], 1)
            self.assertEqual(app.state["scanned"], 1)
            self.assertEqual(app.state["btc_weekly"][0]["symbol"], "ETHBTC")
            self.assertFalse(app.state["btc_weekly"][0]["is_new"])


class NewSignalTests(unittest.TestCase):
    def test_new_results_are_compared_with_the_previous_completed_scan(self):
        previous = {
            "matches": [{"symbol": "NEARUSDT", "stage": "near breakout", "month": "2026-08"}],
            "watchlist": [],
            "key_levels": [{"symbol": "BTCUSDT", "level_signal": "Approaching from below",
                            "level_price": 100}],
            "hourly_extremes": [],
            "btc_weekly": [{"symbol": "ETHBTC", "signals": ["MACD turning green"]}],
        }
        current = {
            "matches": [{"symbol": "NEARUSDT", "stage": "near breakout", "month": "2026-09"},
                        {"symbol": "FETUSDT", "stage": "breaking out"}],
            "watchlist": [],
            "key_levels": [{"symbol": "BTCUSDT", "level_signal": "Crossed above",
                            "level_price": 100}],
            "hourly_extremes": [],
            "btc_weekly": [{"symbol": "ETHBTC", "signals": ["MACD turning green", "Above upper band"]}],
        }
        app.mark_new_signals(current, previous)
        self.assertEqual([item["is_new"] for item in current["matches"]], [False, True])
        self.assertTrue(current["key_levels"][0]["is_new"])
        self.assertTrue(current["btc_weekly"][0]["is_new"])

    def test_first_scan_has_no_new_badges_without_a_baseline(self):
        current = {group: [] for group in app.RESULT_GROUPS}
        current["matches"] = [{"symbol": "NEARUSDT", "stage": "breaking out"}]
        app.mark_new_signals(current, None)
        self.assertFalse(current["matches"][0]["is_new"])


if __name__ == "__main__":
    unittest.main()
