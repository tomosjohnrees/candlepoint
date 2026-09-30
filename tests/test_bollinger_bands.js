const assert = require('node:assert/strict');
const test = require('node:test');
const {bollingerBandsForBars} = require('../bollinger_bands.js');

test('uses the last 21 closes with population standard deviation', () => {
  const bars = Array.from({length:22}, (_, i) => ({c:i + 1}));
  const bands = bollingerBandsForBars(bars);
  assert.equal(bands.length, 22);
  assert.ok(bands.slice(0, 20).every(item => item === null));
  const deviation = Math.sqrt(110 / 3);
  assert.ok(Math.abs(bands[20].middle - 11) < 1e-12);
  assert.ok(Math.abs(bands[20].upper - (11 + 2 * deviation)) < 1e-12);
  assert.ok(Math.abs(bands[20].lower - (11 - 2 * deviation)) < 1e-12);
  assert.ok(Math.abs(bands[21].middle - 12) < 1e-12);
});

test('flat candles have coincident bands and short histories have none', () => {
  assert.deepEqual(bollingerBandsForBars(Array.from({length:20}, () => ({c:5}))), Array(20).fill(null));
  assert.deepEqual(bollingerBandsForBars(Array.from({length:21}, () => ({c:5}))).at(-1),
    {lower:5, middle:5, upper:5});
});
