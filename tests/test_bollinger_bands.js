const assert = require('node:assert/strict');
const test = require('node:test');
const {bollingerBandsForBars} = require('../bollinger_bands.js');

test('uses the last 20 closes with population standard deviation', () => {
  const bars = Array.from({length:21}, (_, i) => ({c:i + 1}));
  const bands = bollingerBandsForBars(bars);
  assert.equal(bands.length, 21);
  assert.ok(bands.slice(0, 19).every(item => item === null));
  const deviation = Math.sqrt(33.25);
  assert.ok(Math.abs(bands[19].middle - 10.5) < 1e-12);
  assert.ok(Math.abs(bands[19].upper - (10.5 + 2 * deviation)) < 1e-12);
  assert.ok(Math.abs(bands[19].lower - (10.5 - 2 * deviation)) < 1e-12);
  assert.ok(Math.abs(bands[20].middle - 11.5) < 1e-12);
});

test('flat candles have coincident bands and short histories have none', () => {
  assert.deepEqual(bollingerBandsForBars(Array.from({length:19}, () => ({c:5}))), Array(19).fill(null));
  assert.deepEqual(bollingerBandsForBars(Array.from({length:20}, () => ({c:5}))).at(-1),
    {lower:5, middle:5, upper:5});
});
