const assert = require('node:assert/strict');
const test = require('node:test');
const {signalGuides, signalGuideSlug} = require('../signal_guides.js');

test('each signal label leads to a dedicated guide', () => {
  const cases = [
    [{stage:'short-base breakout'}, 'short-base breakout', 'short-base-breakout'],
    [{stage:'near breakout'}, 'near breakout', 'near-breakout'],
    [{stage:'breaking out'}, 'breaking out', 'breaking-out'],
    [{stage:'monthly key level'}, 'Crossed above', 'monthly-key-level'],
    [{}, 'Early MACD', 'early-macd'],
    [{stage:'Extreme high'}, 'Extreme high', 'hourly-extremes'],
    [{stage:'Extreme low'}, 'Extreme low', 'hourly-extremes'],
    [{stage:'weekly BTC'}, 'MACD turning green', 'weekly-macd'],
    [{stage:'weekly BTC'}, 'Above upper band', 'weekly-upper-band'],
    [{stage:'BTC resilience'}, 'BTC resilience', 'btc-resilience']
  ];
  for (const [match, label, slug] of cases) {
    assert.equal(signalGuideSlug(match, label), slug);
    assert.ok(signalGuides[slug]?.title);
  }
});
