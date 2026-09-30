const pair = decodeURIComponent(location.pathname.split('/').pop());
const isBtcPair = pair.endsWith('BTC') && !pair.endsWith('USDT');
const base = pair.slice(0, isBtcPair ? -3 : -4);
const coinName = document.querySelector('#coin-name');
const summary = document.querySelector('#summary');
const signals = document.querySelector('#signals');
const readout = document.querySelector('#readout');
const priceCanvas = document.querySelector('#price-chart');
const macdCanvas = document.querySelector('#macd-chart');
const chartSection = document.querySelector('#chart-section');
const chartRange = document.querySelector('#chart-range');
const chartCache = new Map();
let interval = '1M', quote = isBtcPair ? 'BTC' : 'USDT';
let bars = [], bands = [], macd = [], hover = -1, requestId = 0, derivedChart = false;
let chartView = '/patterns', chartInitialized = false;

function node(tag, className, value) {
  const element = document.createElement(tag);
  if (className) element.className = className;
  if (value !== undefined) element.textContent = value;
  return element;
}
function num(value) {
  return Number(value).toLocaleString(undefined, {maximumSignificantDigits: 6});
}
function title(value) {
  return value.replaceAll('_', ' ').replace(/\b\w/g, letter => letter.toUpperCase());
}
function dateTime(value) {
  return new Date(value).toLocaleString(undefined, {dateStyle:'medium', timeStyle:'short'});
}
function signalTitle(group, match) {
  if (group === 'btc_weekly') return 'Weekly BTC signals';
  if (group === 'hourly_extremes') return '1-hour extreme';
  if (group === 'key_levels') return 'Monthly key level';
  if (group === 'watchlist') return 'Monthly MACD watch';
  return match.stage === 'short-base breakout' ? 'Short-base breakout' : 'Monthly triangle';
}
const labels = {
  rsi:'RSI (14)', macd_line:'MACD line', macd_pct:'MACD as % of price',
  macd_percentile:'MACD historical rank', macd_histogram:'MACD histogram',
  prior_macd_histogram:'Prior MACD histogram', two_months_ago_macd_histogram:'Histogram two months ago',
  improvement_pct:'Closer to zero in 2 months', months_to_zero_at_recent_pace:'Gap at recent pace',
  upper_band:'Upper Bollinger Band', distance_above_band_pct:'Close vs upper band',
  level_price:'Monthly level', previous_price:'Prior monthly close', distance_pct:'Distance to level',
  level_touches:'Swing tests', level_signal:'Direction', support:'Support / base floor',
  resistance:'Upper boundary / prior high', distance_to_resistance_pct:'Distance to boundary',
  support_touches:'Support tests', lower_highs:'Lower highs', window_months:'Pattern window',
  months_to_apex:'Estimated apex', trend_start_price:'Trend start price',
  base_months:'Base duration', score:'Triangle fit score',
  month:'Month opened', week:'Week opened', candle_time:'Candle opened', price:'Last price'
};
const percentKeys = new Set(['macd_pct', 'improvement_pct', 'distance_above_band_pct', 'distance_pct', 'distance_to_resistance_pct']);
const monthKeys = new Set(['months_to_zero_at_recent_pace', 'months_to_apex', 'base_months', 'window_months']);
const rawKeys = new Set(['symbol', 'stage', 'reason', 'signals', 'candles', 'provisional', 'is_new', 'trend_start_index']);
function metricValue(key, value) {
  if (typeof value !== 'number') return String(value);
  if (percentKeys.has(key)) return (value > 0 ? '+' : '') + value.toFixed(key === 'macd_pct' ? 3 : 1) + '%';
  if (monthKeys.has(key)) return num(value) + (value === 1 ? ' month' : ' months');
  if (key === 'score') return value.toFixed(1) + ' / 100';
  if (key === 'macd_percentile') return value.toFixed(1) + 'th percentile';
  if (key === 'rsi') return value.toFixed(1);
  return num(value);
}
function signalCard(group, match) {
  const article = node('article', 'panel signal');
  const heading = node('div', 'signal-heading');
  heading.append(node('h3', '', signalTitle(group, match)));
  const names = group === 'btc_weekly' ? match.signals :
    [group === 'key_levels' ? match.level_signal : group === 'watchlist' ? 'Early MACD' : match.stage];
  for (const [index, name] of names.entries()) heading.append(node('span', 'badge' + (index ? ' secondary' : ''), name));
  if (match.is_new) heading.append(node('span', 'badge new', 'New'));
  if (match.provisional) heading.append(node('span', 'badge provisional',
    group === 'hourly_extremes' ? 'Open 1-hour candle' : group === 'btc_weekly' ? 'Open week' : 'Open month'));
  article.append(heading, node('p', 'reason', match.reason));
  const details = node('dl');
  for (const [key, value] of Object.entries(match)) {
    if (rawKeys.has(key) || value === null || typeof value === 'object') continue;
    const breakout = key === 'distance_to_resistance_pct' &&
      (match.stage === 'breaking out' || match.stage === 'short-base breakout');
    const item = node('div');
    item.append(node('dt', '', breakout ? (match.stage === 'short-base breakout' ?
      'Above prior 8-month high' : 'Above boundary') : labels[key] || title(key)),
    node('dd', '', breakout ? Math.abs(value).toFixed(1) + '%' : metricValue(key, value)));
    details.append(item);
  }
  article.append(details);
  const footer = node('div', 'signal-footer');
  const binance = node('a', '', 'Inspect on Binance ↗');
  binance.href = 'https://www.binance.com/en/trade/' + encodeURIComponent(base + '_' + (isBtcPair ? 'BTC' : 'USDT')) + '?type=spot';
  binance.target = '_blank'; binance.rel = 'noopener noreferrer';
  footer.append(binance); article.append(footer);
  return article;
}
function setChartControls() {
  for (const button of document.querySelectorAll('[data-interval]')) {
    const active = button.dataset.interval === interval;
    button.classList.toggle('active', active); button.setAttribute('aria-pressed', String(active));
  }
  for (const button of document.querySelectorAll('[data-quote]')) {
    const active = button.dataset.quote === quote;
    button.classList.toggle('active', active); button.setAttribute('aria-pressed', String(active));
  }
  document.querySelector('#chart-heading').textContent = base + ' / ' + quote + ' price history';
  const url = new URL(chartView, location.origin);
  url.searchParams.set('chart', pair);
  url.searchParams.set('interval', interval);
  if (isBtcPair && quote === 'USDT') url.searchParams.set('quote', 'USDT');
  const fullLink = document.querySelector('#full-chart-link');
  fullLink.hidden = !isBtcPair && quote === 'BTC';
  fullLink.href = url.pathname + url.search;
}
async function loadChart() {
  const id = ++requestId;
  setChartControls();
  const chartSymbol = base + quote;
  const key = chartSymbol + ':' + interval;
  readout.textContent = 'Loading ' + (quote === 'BTC' ? 'BTC' : 'USD') + ' chart…';
  bars = []; derivedChart = false; drawCharts();
  try {
    if (!chartCache.has(key)) {
      const response = await fetch('/api/chart?symbol=' + encodeURIComponent(chartSymbol) + '&interval=' + interval);
      if (!response.ok) throw new Error('History unavailable');
      const result = await response.json();
      if (!Array.isArray(result.candles) || !result.candles.length) throw new Error('History unavailable');
      chartCache.set(key, result);
    }
    if (id !== requestId) return;
    const result = chartCache.get(key);
    bars = result.candles;
    derivedChart = !!result.derived;
    priceCanvas.setAttribute('aria-label', derivedChart ?
      'BTC equivalent close price line chart' : 'Price candlestick chart with Bollinger bands');
    if (!isBtcPair) document.querySelector('[data-quote="BTC"]').textContent =
      derivedChart ? 'BTC equivalent' : 'BTC';
    document.querySelector('#chart-note').textContent = derivedChart ?
      'BTC equivalent from ' + base + '/USDT ÷ BTC/USDT closes · calculated comparison, not a traded pair' :
      (quote === 'BTC' ? 'Direct Binance ' + base + '/BTC candles · ' : 'Green / red candles · ') +
      'shaded Bollinger bands (21, 2) · MACD below';
    document.querySelector('#chart-heading').textContent = base + ' / ' + quote +
      (derivedChart ? ' equivalent' : '') + ' price history';
    bands = bollingerBandsForBars(bars);
    macd = macdSeries(bars);
    hover = -1;
    drawCharts();
  } catch (error) {
    if (id !== requestId) return;
    document.querySelector('#chart-note').textContent = 'Chart history is unavailable.';
    readout.textContent = (quote === 'USDT' ? 'USD (USDT)' : 'BTC') +
      ' chart unavailable for this pair right now.';
    drawCharts();
  }
}
function macdSeries(history) {
  if (history.length < 36) return [];
  const ema = (values, period) => {
    const alpha = 2 / (period + 1), output = [values[0]];
    for (let i = 1; i < values.length; i++) output.push(alpha * values[i] + (1 - alpha) * output[i - 1]);
    return output;
  };
  const closes = history.map(bar => bar.c);
  const fast = ema(closes, 12), slow = ema(closes, 26);
  const line = fast.map((value, index) => value - slow[index]);
  const signal = ema(line, 9);
  return line.map((value, index) => index < 35 ? null :
    {line:value, signal:signal[index], histogram:value - signal[index]});
}
function canvasContext(canvas) {
  const width = canvas.clientWidth, height = canvas.clientHeight;
  if (!width || !height) return null;
  const ratio = window.devicePixelRatio || 1;
  canvas.width = Math.round(width * ratio); canvas.height = Math.round(height * ratio);
  const ctx = canvas.getContext('2d'); ctx.scale(ratio, ratio);
  ctx.fillStyle = '#f8faf9'; ctx.fillRect(0, 0, width, height);
  ctx.font = '11px system-ui, sans-serif'; ctx.fillStyle = '#829297';
  return {ctx, width, height};
}
function chartWindow() {
  const first = chartRange.value === 'all' ? 0 : Math.max(0, bars.length - Number(chartRange.value));
  return {first, visible:bars.slice(first)};
}
function drawCharts() {
  const price = canvasContext(priceCanvas), indicator = canvasContext(macdCanvas);
  if (!price || !indicator || !bars.length) return;
  const {first, visible} = chartWindow();
  const left = 24, right = Math.max(left + 10, price.width - 78);
  const top = 18, bottom = price.height - 28;
  const x = index => left + (index - first + .5) * (right - left) / visible.length;
  const values = visible.flatMap(bar => [bar.l, bar.h]);
  for (let i = first; i < bars.length; i++) {
    if (bands[i]) values.push(bands[i].upper, bands[i].lower);
  }
  const lo = Math.min(...values);
  const hi = Math.max(...values);
  const padding = Math.max((hi - lo) * .06, Math.abs(hi) * .001, 1e-12);
  const min = lo - padding, max = hi + padding;
  const y = value => bottom - (value - min) / (max - min) * (bottom - top);
  const ctx = price.ctx;
  for (let tick = 0; tick <= 4; tick++) {
    const py = top + tick * (bottom - top) / 4;
    ctx.strokeStyle = '#e4ebe8'; ctx.beginPath(); ctx.moveTo(left, py); ctx.lineTo(right, py); ctx.stroke();
    ctx.fillStyle = '#829297'; ctx.fillText(num(max - tick * (max - min) / 4), right + 7, py + 4);
  }
  ctx.save(); ctx.beginPath(); ctx.rect(left, top, right - left, bottom - top); ctx.clip();
  const bandIndexes = [];
  for (let i = first; i < bars.length; i++)
    if (bands[i] && Number.isFinite(bands[i].upper) && Number.isFinite(bands[i].lower)) bandIndexes.push(i);
  if (bandIndexes.length > 1) {
    ctx.beginPath();
    for (const [position, index] of bandIndexes.entries()) {
      if (position === 0) ctx.moveTo(x(index), y(bands[index].upper));
      else ctx.lineTo(x(index), y(bands[index].upper));
    }
    for (const index of [...bandIndexes].reverse()) ctx.lineTo(x(index), y(bands[index].lower));
    ctx.closePath(); ctx.fillStyle = '#7477a322'; ctx.fill();
  }
  ctx.lineJoin = 'round'; ctx.lineCap = 'round';
  for (const [key, color] of [['upper','#656eaa'], ['middle','#8790bb'], ['lower','#656eaa']]) {
    ctx.beginPath(); ctx.strokeStyle = color; ctx.lineWidth = key === 'middle' ? 1 : 1.4;
    let started = false;
    for (let i = first; i < bars.length; i++) {
      const value = bands[i]?.[key];
      if (!Number.isFinite(value)) { started = false; continue; }
      if (started) ctx.lineTo(x(i), y(value)); else ctx.moveTo(x(i), y(value));
      started = true;
    }
    ctx.stroke();
  }
  const bodyWidth = Math.max(1, Math.min(10, (right - left) / visible.length * .65));
  if (derivedChart) {
    ctx.beginPath(); ctx.strokeStyle = '#176d60'; ctx.lineWidth = 2;
    for (let i = first; i < bars.length; i++) {
      if (i === first) ctx.moveTo(x(i), y(bars[i].c)); else ctx.lineTo(x(i), y(bars[i].c));
    }
    ctx.stroke();
  } else {
    for (let i = first; i < bars.length; i++) {
      const bar = bars[i];
      ctx.strokeStyle = ctx.fillStyle = bar.c >= bar.o ? '#23866e' : '#c26b62';
      ctx.beginPath(); ctx.moveTo(x(i), y(bar.h)); ctx.lineTo(x(i), y(bar.l)); ctx.stroke();
      ctx.fillRect(x(i) - bodyWidth / 2, Math.min(y(bar.o), y(bar.c)), bodyWidth, Math.max(1, Math.abs(y(bar.o) - y(bar.c))));
    }
  }
  ctx.restore();
  for (let tick = 0; tick < 5; tick++) {
    const i = Math.min(bars.length - 1, first + Math.round(tick * (visible.length - 1) / 4));
    const label = new Date(bars[i].t).toLocaleDateString(undefined, {month:'short', year:'2-digit'});
    ctx.fillStyle = '#829297'; ctx.textAlign = tick === 4 ? 'right' : tick ? 'center' : 'left';
    ctx.fillText(label, x(i), price.height - 8);
  }
  const mctx = indicator.ctx, mtop = 14, mbottom = indicator.height - 16;
  const valuesMacd = macd.slice(first).filter(Boolean).flatMap(value => [value.line, value.signal, value.histogram]);
  if (valuesMacd.length) {
    const span = Math.max(...valuesMacd.map(Math.abs)) * 1.2 || 1;
    const my = value => (mtop + mbottom) / 2 - value / span * (mbottom - mtop) / 2;
    mctx.strokeStyle = '#dce5e3'; mctx.beginPath(); mctx.moveTo(left, my(0)); mctx.lineTo(right, my(0)); mctx.stroke();
    for (let i = first; i < bars.length; i++) {
      if (!macd[i]) continue;
      mctx.fillStyle = macd[i].histogram >= 0 ? '#86bba9' : '#dda5a0';
      mctx.fillRect(x(i) - bodyWidth / 2, Math.min(my(0), my(macd[i].histogram)), bodyWidth,
        Math.max(1, Math.abs(my(0) - my(macd[i].histogram))));
    }
    for (const [key, color] of [['line','#b27332'], ['signal','#8a78a7']]) {
      mctx.beginPath(); mctx.strokeStyle = color; mctx.lineWidth = 1.5;
      let started = false;
      for (let i = first; i < bars.length; i++) {
        if (!macd[i]) { started = false; continue; }
        if (started) mctx.lineTo(x(i), my(macd[i][key])); else mctx.moveTo(x(i), my(macd[i][key]));
        started = true;
      }
      mctx.stroke();
    }
  }
  mctx.fillStyle = '#829297'; mctx.fillText('MACD 12 / 26 / 9', left, 13);
  if (hover >= first && hover < bars.length) {
    for (const [context, height] of [[ctx, price.height], [mctx, indicator.height]]) {
      context.strokeStyle = '#90a6a3'; context.beginPath(); context.moveTo(x(hover), 0); context.lineTo(x(hover), height); context.stroke();
    }
  }
  const selected = hover >= first && hover < bars.length ? hover : bars.length - 1;
  const bar = bars[selected], band = bands[selected], currentMacd = macd[selected];
  readout.replaceChildren(
    node('span', '', new Date(bar.t).toLocaleDateString() + (derivedChart ? ' · BTC equivalent ' + num(bar.c) :
      ' · O ' + num(bar.o) + '  H ' + num(bar.h) + '  L ' + num(bar.l) + '  C ' + num(bar.c))),
    node('span', '', band ? 'BB 21 / 2 · upper ' + num(band.upper) + ' · middle ' +
      num(band.middle) + ' · lower ' + num(band.lower) : 'BB needs 21 candles'),
    node('span', '', currentMacd ? 'MACD ' + num(currentMacd.line) + ' · histogram ' + num(currentMacd.histogram) : 'MACD needs 36 candles')
  );
}
function onPointer(event) {
  if (!bars.length) return;
  const {first, visible} = chartWindow();
  const rect = event.currentTarget.getBoundingClientRect();
  const x = event.clientX - rect.left;
  hover = x < 24 || x > rect.width - 78 ? -1 :
    Math.min(bars.length - 1, first + Math.floor((x - 24) / (rect.width - 102) * visible.length));
  drawCharts();
}
for (const canvas of [priceCanvas, macdCanvas]) {
  canvas.addEventListener('pointermove', onPointer);
  canvas.addEventListener('pointerleave', () => { hover = -1; drawCharts(); });
}
for (const button of document.querySelectorAll('[data-interval]')) button.onclick = () => {
  interval = button.dataset.interval; loadChart();
};
for (const button of document.querySelectorAll('[data-quote]')) button.onclick = () => {
  quote = button.dataset.quote; loadChart();
};
chartRange.onchange = () => { hover = -1; drawCharts(); };
new ResizeObserver(drawCharts).observe(document.querySelector('.chart-area'));

async function refresh() {
  try {
    const response = await fetch('/api/coin?symbol=' + encodeURIComponent(pair));
    if (!response.ok) throw new Error('Could not load scan details');
    const data = await response.json();
    document.title = pair + ' — Candlepoint';
    coinName.replaceChildren(document.createTextNode(base), node('span', 'quote', ' / ' + (isBtcPair ? 'BTC' : 'USDT')));
    const count = data.signals.reduce((total, item) => total +
      (item.group === 'btc_weekly' ? item.match.signals.length : 1), 0);
    document.querySelector('#signal-count').textContent = count + (count === 1 ? ' signal' : ' signals');
    document.querySelector('#hero-copy').textContent = count ? 'Every current signal for this pair, in one place.' :
      'This pair is not in the latest completed scan.';
    summary.replaceChildren(node('span', 'dot'), node('span', '', data.status),
      node('span', '', count + (count === 1 ? ' current signal' : ' current signals')),
      node('span', '', data.updated_at ? 'Last scan ' + dateTime(data.updated_at) : 'Awaiting first scan'));
    if (count) {
      document.querySelector('#price').textContent = num(data.signals[0].match.price) + ' ' + (isBtcPair ? 'BTC' : 'USDT');
      document.querySelector('#hero-price').hidden = false;
      signals.replaceChildren(...data.signals.map(item => signalCard(item.group, item.match)));
      chartSection.hidden = false;
      if (!chartInitialized) {
        const firstGroup = data.signals[0].group;
        chartView = ({matches:'/patterns', watchlist:'/macd-watch', key_levels:'/key-levels',
          hourly_extremes:'/hourly-extremes', btc_weekly:'/btc-weekly'})[firstGroup];
        interval = firstGroup === 'btc_weekly' ? '1w' : firstGroup === 'hourly_extremes' ? '1h' : '1M';
        document.querySelector('#quote-options').hidden = false;
        chartInitialized = true;
        loadChart();
      }
    } else {
      chartInitialized = false;
      requestId++;
      document.querySelector('#hero-price').hidden = true;
      chartSection.hidden = true;
      signals.replaceChildren(node('div', 'panel message',
        data.updated_at ? 'No current signal for ' + pair + '. Return to all signals to choose another pair.' :
          'The first scan has not finished yet. This page will update automatically.'));
    }
  } catch (error) {
    summary.textContent = 'Cannot reach the scanner. Retrying automatically…';
  }
}
refresh(); setInterval(refresh, 15000);
