/* Binance's default 21-candle simple moving average with two population standard deviations. */
function bollingerBandsForBars(bars, period = 21, deviations = 2) {
  if (!Array.isArray(bars)) return [];
  const result = Array(bars.length).fill(null);
  for (let i = period - 1; i < bars.length; i++) {
    const closes = bars.slice(i - period + 1, i + 1).map(bar => bar.c);
    if (!closes.every(value => Number.isFinite(value) && value > 0)) continue;
    const middle = closes.reduce((sum, value) => sum + value, 0) / period;
    const variance = closes.reduce((sum, value) => sum + (value - middle) ** 2, 0) / period;
    const offset = deviations * Math.sqrt(variance);
    result[i] = {lower:middle - offset, middle, upper:middle + offset};
  }
  return result;
}

if (typeof module !== 'undefined') module.exports = {bollingerBandsForBars};
