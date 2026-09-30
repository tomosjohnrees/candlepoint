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
            app.state["matches"] = [{"symbol": "NEARUSDT"}]
            app.state["watchlist"] = []

    def tearDown(self):
        with app.lock:
            app.state["matches"] = self.old_matches
            app.state["watchlist"] = self.old_watchlist

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
        self.assertEqual(result, {"symbol": "NEARUSDT", "interval": "1M", "candles": [
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


if __name__ == "__main__":
    unittest.main()
