const assert = require('node:assert/strict');
const test = require('node:test');
const {readFileSync} = require('node:fs');
const {join} = require('node:path');
const vm = require('node:vm');
const {signalGuideSlug} = require('../signal_guides.js');
const {bollingerBandsForBars} = require('../bollinger_bands.js');

// Run the actual page scripts with a minimal DOM; drawing and timers are disabled.
// These checks cover signal routing and interaction, not browser layout.
class Element {
  constructor(tag = 'div', attrs = {}) {
    this.tag = tag; this.attrs = attrs; this.children = []; this.dataset = {};
    this.className = attrs.class || ''; this.value = ''; this.hidden = false;
    this.clientWidth = 0; this.clientHeight = 0;
    this.options = [{value:'all'}];
    for (const [key, value] of Object.entries(attrs))
      if (key.startsWith('data-')) this.dataset[key.slice(5).replace(/-([a-z])/g, (_, c) => c.toUpperCase())] = value;
    this.classList = {toggle() {}};
  }
  set textContent(value) { this.text = String(value); this.children = []; }
  get textContent() { return (this.text || '') + this.children.map(child => child.textContent).join(' '); }
  append(...children) {
    for (const child of children) { child.parentNode = this; this.children.push(child); }
  }
  replaceChildren(...children) { this.text = ''; this.children = []; this.append(...children); }
  setAttribute(key, value) { this.attrs[key] = String(value); }
  removeAttribute(key) { delete this.attrs[key]; }
  addEventListener() {}
  showModal() { this.open = true; }
  close() { this.open = false; }
  matches(selector) {
    if (selector.startsWith('#')) return this.attrs.id === selector.slice(1);
    if (selector.startsWith('.')) return this.className.split(' ').includes(selector.slice(1));
    if (selector.startsWith('[')) return selector.slice(1, -1) in this.attrs;
    return this.tag === selector;
  }
  querySelectorAll(selector) {
    return this.children.flatMap(child => [
      ...(child.matches(selector) ? [child] : []), ...child.querySelectorAll(selector)
    ]);
  }
  querySelector(selector) { return this.querySelectorAll(selector)[0] || null; }
}

function page(filename, pathname) {
  const root = join(__dirname, '..');
  const html = readFileSync(join(root, filename), 'utf8');
  const document = new Element();
  for (const [, tag, source] of html.matchAll(/<([a-z][\w-]*)\b([^>]*)>/g)) {
    const attrs = Object.fromEntries([...source.matchAll(/([\w-]+)="([^"]*)"/g)].map(m => [m[1], m[2]]));
    document.append(new Element(tag, attrs));
  }
  document.createElement = tag => new Element(tag);
  document.createTextNode = text => { const node = new Element(); node.textContent = text; return node; };
  const context = vm.createContext({
    document, location:new URL(pathname, 'http://localhost'), URL,
    localStorage:{getItem:() => null}, window:{addEventListener() {}},
    history:{state:null, pushState() {}, replaceState() {}},
    ResizeObserver:class { observe() {} }, requestAnimationFrame() {}, setInterval() {},
    fetch:() => new Promise(() => {}), signalGuideSlug, bollingerBandsForBars
  });
  const script = filename === 'index.html' ? html.match(/<script>([\s\S]*?)<\/script>/)[1] :
    readFileSync(join(root, 'coin.js'), 'utf8');
  vm.runInContext(script, context);
  return {document, context, run:code => vm.runInContext(code, context)};
}

function resilience(symbol = 'ALTUSDT') {
  return {
    symbol, stage:'BTC resilience', price:102, provisional:false, is_new:true,
    strength_score:48, coin_gain_pct:2, btc_change_pct:-1,
    strength_hours:24, current_streak_hours:24, window_hours:24,
    window_start:'2026-10-01 10:00 UTC', window_end:'2026-10-02 10:00 UTC',
    candle_time:'2026-10-02 09:00 UTC', reason:'Sustained USDT gains during BTC weakness.',
    candles:Array.from({length:25}, (_, i) => ({t:1790845200000 + i * 3600000, o:100, h:102, l:100, c:i ? 102 : 100}))
  };
}

test('resilience tab renders metrics, searches coins and filters new signals', () => {
  const ui = page('index.html', '/btc-resilience');
  ui.context.data = {status:'Ready', scanned:2, universe:2, comparison_available:true,
    btc_resilience:[resilience(), {...resilience('OLDUSDT'), is_new:false}]};
  ui.run('latestData = data; restoreRoute();');
  const cards = ui.document.querySelector('#cards');
  assert.equal(cards.attrs['aria-labelledby'], 'resilience-tab');
  assert.equal(cards.children.length, 2);
  assert.match(cards.textContent, /48.00 %-hours/);
  assert.match(cards.textContent, /\+2.00% USDT · BTC -1.00%/);
  assert.match(cards.textContent, /24\/24h strength · 24h streak/);
  assert.ok(cards.querySelectorAll('a').some(link => link.href === '/learn/btc-resilience'));
  assert.equal(ui.document.querySelector('#resilience-description').hidden, false);
  assert.match(ui.document.querySelector('#resilience-tab').textContent, /2$/);
  assert.match(ui.document.querySelector('#summary').textContent, /2 BTC resilience/);
  assert.deepEqual(Array.from(ui.run('availableCoins()')), ['ALT', 'OLD']);

  ui.run('newOnlyToggle.checked = true; render(data);');
  assert.equal(cards.children.length, 1);
  assert.equal(cards.children[0].dataset.symbol, 'ALTUSDT');
  ui.run('symbolSearch.value = "OLD"; newOnlyToggle.checked = false; render(data);');
  assert.equal(cards.children.length, 1);
  assert.equal(cards.children[0].dataset.symbol, 'OLDUSDT');
});

test('resilience chart links restore hourly candles with their original timestamps', () => {
  const ui = page('index.html', '/btc-resilience?chart=ALTUSDT&detail=ALTUSDT');
  ui.context.data = {status:'Ready', btc_resilience:[resilience()]};
  ui.run('latestData = data; restoreRoute();');
  assert.equal(ui.run('readRoute().view'), 'btc_resilience');
  assert.equal(ui.run('activeChart.interval'), '1h');
  assert.equal(ui.run('activeChart.bars.length'), 25);
  assert.equal(ui.run('activeChart.bars[0].t'), ui.context.data.btc_resilience[0].candles[0].t);
  assert.equal(ui.document.querySelector('#chart-dialog').open, true);
  assert.equal(ui.document.querySelector('#route-notice').hidden, true);
  assert.equal(ui.document.querySelector('#cards').querySelector('details').open, true);
});

test('resilience gracefully handles saved states without the new result group', () => {
  const ui = page('index.html', '/btc-resilience');
  ui.context.data = {status:'Ready', scanned:0, universe:0};
  ui.run('latestData = data; restoreRoute();');
  assert.match(ui.document.querySelector('#cards').textContent, /No coins gained USDT while BTC lost USDT/);
  assert.match(ui.document.querySelector('#resilience-tab').textContent, /0$/);
});

test('coin page shows resilience units and opens its hourly full-chart link', async () => {
  const ui = page('coin.html', '/coin/ALTUSDT');
  const match = resilience();
  ui.context.fetch = async url => ({ok:true, json:async () => url.startsWith('/api/coin') ?
    {status:'Ready', signals:[{group:'btc_resilience', match}]} : {candles:match.candles}});
  await ui.run('refresh()');
  assert.equal(ui.run('interval'), '1h');
  const link = ui.document.querySelector('#full-chart-link');
  assert.equal(link.href, '/btc-resilience?chart=ALTUSDT&interval=1h');
  const content = ui.document.querySelector('#signals').textContent;
  assert.match(content, /BTC resilience/);
  assert.match(content, /Strength score 48.00 %-hours/);
  assert.match(content, /Coin gain \(USDT\) \+2.00%/);
  assert.match(content, /BTC change \(USDT\) -1.00%/);
  assert.match(content, /Current strength streak 24 hours/);
});
