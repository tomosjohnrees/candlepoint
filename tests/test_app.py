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
        with patch.object(app, "monthly_candles", return_value=[candle]) as fetch:
            handler = self.request("symbol=NEARUSDT")
        fetch.assert_called_once_with("NEARUSDT", limit=1000)
        handler.send_response.assert_called_once_with(200)
        result = json.loads(handler.wfile.getvalue())
        self.assertEqual(result, {"symbol": "NEARUSDT", "candles": [
            {"t": candle.open_time, "o": 2, "h": 3, "l": 1, "c": 2.5}]})

    def test_unknown_symbol_is_rejected_without_fetching(self):
        with patch.object(app, "monthly_candles") as fetch:
            handler = self.request("symbol=OTHERUSDT")
        handler.send_error.assert_called_once_with(404, "Chart unavailable")
        fetch.assert_not_called()


if __name__ == "__main__":
    unittest.main()
