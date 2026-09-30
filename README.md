# Triangle Watch

![CI](https://github.com/tomosjohnrees/triangle-watch/actions/workflows/ci.yml/badge.svg)

A local, read-only scanner for Binance USDT spot coins approaching the decision
point of a descending triangle while the **monthly MACD histogram has recently
turned positive**. It also labels shorter flat-base breakouts separately. An
early MACD watchlist shows coins whose histogram is still negative but rising
toward zero. A monthly key levels tab shows coins approaching or crossing
established swing levels in either direction. It uses monthly price and volume
candles, not screenshots.

## Run

```sh
python3 app.py
```

Open [http://127.0.0.1:8765](http://127.0.0.1:8765). The first scan starts
automatically and repeats every two hours. Select **Enable alerts** to
get notifications while the dashboard is open. No exchange account, API key,
or third-party package is required.

The dashboard shows scan status, category totals, and compact result rows.
Choose **Patterns**, **Key levels**, or **MACD watch**; the first two views have
dropdowns for pattern type or price movement. Expand **Signal details** on a
row for the full metrics and scanner explanation. Select **View chart** to
switch between daily, weekly, monthly, and yearly candles inside the dashboard.
The chart groups candle timeframe, date range, and price overlays separately.
Daily and weekly history is fetched from Binance when selected; yearly candles
are assembled from monthly history. These chart candles are held in the open
dashboard and are not saved to `scan_state.json`; scanner results still use
monthly data. The chart includes date and price scales, time ranges, candle
values, and a 12/26/9 MACD panel
recalculated for the selected candle interval.
The price chart also shows Bollinger Bands based on the last 20 closes and two
population standard deviations. Use the **Bollinger bands** checkbox to hide
or restore the overlay; the setting is remembered in the browser. The first
19 candles have no band values, and short yearly histories may have no bands
at all. A lower band at zero or below is omitted from the logarithmic price
plot.
Scanner support and boundary lines appear on monthly candles, the interval
used for screening. MACD needs at least 36 candles, so yearly MACD may be
unavailable. If Binance history cannot be loaded, monthly charts use the
scanned window; other intervals show an error.

Use the **Key levels** checkbox in a full chart to show up to five horizontal
price levels from swing highs and lows in the visible date range. Green lines
are below the latest close and amber lines are above it. The checkbox works on
every candle interval and remembers its setting in the browser. A monthly key
level signal also draws its scanned level as a solid line on the monthly chart,
even when the optional visible-range levels are hidden.

Optional settings:

```sh
MAX_SYMBOLS=100 SCAN_INTERVAL_SECONDS=3600 PORT=8765 python3 app.py
```

## Current rule

- Take active Binance USDT spot pairs with at least USDT 1m of reported
  24-hour turnover. The default cap of 1,000 pairs covers all such pairs at
  the time of writing.
- Examine 24–60 monthly candles. Require support-zone tests spanning at least
  18 months, lower swing highs, and a falling upper boundary with an estimated apex
  no more than eight months away. The current price must be within 25% below
  or 10% above that boundary.
- Require the standard 12/26/9 monthly MACD histogram to be positive now and
  negative or zero within the preceding three candles.
- Label a coin **near breakout** while it is approaching the upper boundary.
  Freeze that boundary at the previous month's close; if the next monthly
  candle trades at least 1% above it, label that first candle **breaking out**
  even if the move is already large. An open monthly candle is marked
  **provisional**.
- Label a coin **short-base breakout** when its current monthly price is at
  least 5% above the preceding eight months' high, after an eight-month floor
  with at least three tests spanning seven months. Require an earlier high at
  least twice that base high and a recently positive monthly MACD histogram.
  The signal is provisional until the monthly candle closes.
  This category does **not** imply a multiyear descending triangle.
- Put a coin in **Early MACD watchlist** when the last three monthly histogram
  readings are negative and each is higher than the preceding reading, the
  latest reading is at least 25% closer to zero than two months earlier, and
  the remaining gap is at most three months of the recent two-month pace.
  This is a momentum watch only: it does not require a triangle and does not
  predict when a crossover will occur. A coin already listed as a triangle
  match is not duplicated here.
- Put a coin in **Monthly key levels** when its latest monthly price crosses a
  swing level from below or above relative to the prior monthly close, or moves
  toward a level and comes within 3% of it. Levels are calculated from the
  preceding monthly candles, excluding the candle being evaluated. The scan
  ranks up to five levels by swing tests and prominence, then prioritizes a
  crossing or shows the nearest approach for each coin. A signal can appear in
  this tab and in a pattern tab. An open monthly candle makes its signal
  provisional.

The matching thresholds are starting values. They have not been validated for
profitability. A chart match should be inspected before acting. The app makes
no trades. The local dashboard's browser notifications work only while its tab
is open. The fit score ranks pattern similarity; it is not a forecast or a
probability of profit.

The included NEARUSDT August and September 2026 candle snapshots are regression
examples: August is **near breakout** and September is **breaking out**. The
FETUSDT September 2026 snapshot is an **early MACD watch** without a triangle
match. The PHAUSDT September snapshot is a **short-base breakout**, not a
multiyear triangle. These examples are not a backtest of returns.
