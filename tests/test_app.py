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

    def test_resilience_only_result_can_open_hourly_chart(self):
        with patch.dict(app.state, {"btc_resilience": [{"symbol": "STRONGUSDT"}]}), \
             patch.object(app, "historical_candles", return_value=[]) as fetch:
            handler = self.request("symbol=STRONGUSDT&interval=1h")
        fetch.assert_called_once_with("STRONGUSDT", "1h", max_bars=1000)
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
        with patch.object(app, "spot_symbol_trading", return_value=False) as trading, \
             patch.object(app, "historical_candles", side_effect=[[near], [unrelated, btc]]) as fetch:
            handler = self.request("symbol=NEARBTC&interval=1w")
        trading.assert_called_once_with("NEARBTC")
        self.assertEqual(fetch.call_count, 2)
        self.assertEqual([call.args for call in fetch.call_args_list],
                         [("NEARUSDT", "1w"), ("BTCUSDT", "1w")])
        data = json.loads(handler.wfile.getvalue())
        self.assertTrue(data["derived"])
        self.assertEqual(data["symbol"], "NEARBTC")
        self.assertEqual(data["candles"], [{"t": near.open_time, "o": .0001,
                                             "h": .0001, "l": .0001, "c": .0001}])

    def test_trading_btc_market_uses_real_candles(self):
        candle = Candle(1_700_000_000_000, 1_700_100_000_000, .0001, .00012,
                        .00008, .00011, 100)
        with patch.object(app, "spot_symbol_trading", return_value=True) as trading, \
             patch.object(app, "historical_candles", return_value=[candle]) as fetch:
            handler = self.request("symbol=NEARBTC&interval=1w")
        trading.assert_called_once_with("NEARBTC")
        fetch.assert_called_once_with("NEARBTC", "1w")
        data = json.loads(handler.wfile.getvalue())
        self.assertFalse(data["derived"])
        self.assertEqual(data["candles"], [{"t": candle.open_time, "o": .0001,
                                             "h": .00012, "l": .00008, "c": .00011}])

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
        for path in ("/patterns", "/key-levels", "/macd-watch", "/hourly-extremes", "/btc-weekly", "/btc-resilience"):
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

    def test_coin_api_includes_resilience_only_signal(self):
        match = {"symbol": "STRONGUSDT", "stage": "BTC resilience", "strength_score": 48}
        with patch.dict(app.state, {**{group: [] for group in app.RESULT_GROUPS},
                                    "btc_resilience": [match]}):
            handler = self.request("/api/coin?symbol=STRONGUSDT")
        handler.send_response.assert_called_once_with(200)
        self.assertEqual(json.loads(handler.wfile.getvalue())["signals"],
                         [{"group": "btc_resilience", "match": match}])

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

    def test_signal_guide_routes_and_scripts_are_served(self):
        for path in ["/learn"] + ["/learn/" + slug for slug in app.SIGNAL_GUIDE_SLUGS]:
            page = self.request(path)
            page.send_response.assert_called_once_with(200)
            page.send_header.assert_any_call("Content-Type", "text/html; charset=utf-8")
            self.assertIn(b"Signal guide", page.wfile.getvalue())
        for path in ("/signal_guides.js", "/learn.js"):
            script = self.request(path)
            script.send_response.assert_called_once_with(200)
            script.send_header.assert_any_call("Content-Type", "application/javascript; charset=utf-8")
        self.request("/learn/unknown").send_error.assert_called_once_with(404)

    def test_invalid_coin_path_and_query_are_rejected(self):
        self.request("/coin/../app.py").send_error.assert_called_once_with(404)
        self.request("/api/coin?symbol=ETHBTC&symbol=BNBBTC").send_error.assert_called_once_with(400, "Invalid symbol")


class ScanIsolationTests(unittest.TestCase):
    def test_hourly_history_is_shared_with_resilience(self):
        hours, bitcoin = [Mock()], [Mock()]
        with patch.object(app, "monthly_candles", side_effect=RuntimeError("unavailable")), \
             patch.object(app, "hourly_candles", return_value=hours) as hourly, \
             patch.object(app, "detect_hourly_extreme", return_value="extreme"), \
             patch.object(app, "detect_btc_resilience", return_value="resilient") as detector:
            result = app._scan_symbol("ALTUSDT", bitcoin, 123)
        hourly.assert_called_once_with("ALTUSDT")
        detector.assert_called_once_with("ALTUSDT", hours, bitcoin, 123)
        self.assertEqual(result[3:5], ("extreme", "resilient"))

    def test_hourly_scan_still_runs_when_monthly_data_fails(self):
        with patch.object(app, "monthly_candles", side_effect=RuntimeError("monthly unavailable")), \
             patch.object(app, "hourly_candles", return_value=[]) as hourly, \
             patch.object(app, "detect_hourly_extreme", return_value="hourly match"):
            match, watch, level, extreme, resilience, monthly_error, hourly_error = app._scan_symbol("HOURUSDT")
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


class ResilienceScanTests(unittest.TestCase):
    def test_benchmark_fetched_once_and_results_sorted_and_compared(self):
        def scan(symbol, bitcoin, now_ms):
            self.assertEqual(bitcoin, ["benchmark"])
            self.assertIsInstance(now_ms, int)
            result = Mock()
            result.to_dict.return_value = {"symbol": symbol, "stage": "BTC resilience",
                                           "strength_score": 2 if symbol == "AUSDT" else 48}
            return None, None, None, None, result, None, None

        with patch.dict(app.state, {"updated_at": "previous", "btc_resilience": [
                {"symbol": "BUSDT", "stage": "BTC resilience", "strength_score": 30}] }), \
             patch.object(app, "active_usdt_symbols", return_value=["AUSDT", "BUSDT"]), \
             patch.object(app, "active_btc_symbols", return_value=[]), \
             patch.object(app, "hourly_candles", return_value=["benchmark"]) as hourly, \
             patch.object(app, "_scan_symbol", side_effect=scan) as scanner, \
             patch.object(app, "save_state"):
            app.scan_once()
            hourly.assert_called_once_with("BTCUSDT")
            self.assertEqual(scanner.call_args_list[0].args[2], scanner.call_args_list[1].args[2])
            self.assertEqual([r["symbol"] for r in app.state["btc_resilience"]], ["BUSDT", "AUSDT"])
            self.assertEqual([r["is_new"] for r in app.state["btc_resilience"]], [False, True])
            self.assertEqual(app.state["scanned"], 2)

    def test_failed_benchmark_clears_old_results_and_preserves_other_screens(self):
        with patch.dict(app.state, {"btc_resilience": [{"symbol": "OLDUSDT"}]}), \
             patch.object(app, "active_usdt_symbols", return_value=["ALTUSDT"]), \
             patch.object(app, "active_btc_symbols", return_value=[]), \
             patch.object(app, "hourly_candles", side_effect=RuntimeError("unavailable")), \
             patch.object(app, "_scan_symbol", return_value=(None,) * 7) as scanner, \
             patch.object(app, "save_state"):
            app.scan_once()
            self.assertEqual(app.state["status"], "Ready")
            self.assertEqual(app.state["btc_resilience"], [])
            self.assertEqual(app.state["errors"], 1)
            self.assertIn("benchmark unavailable", app.state["last_error"])
            self.assertIsNone(scanner.call_args.args[1])


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
