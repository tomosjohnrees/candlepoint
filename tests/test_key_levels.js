const assert = require('node:assert/strict');
const test = require('node:test');
const {keyLevelsForBars} = require('../key_levels.js');

test('repeated, separated swing highs become one horizontal level', () => {
  const bars = Array.from({length:19}, () => ({h:9, l:7}));
  bars[3].h = 11;
  bars[9].h = 11.1;
  bars[15].h = 10.95;
  const levels = keyLevelsForBars(bars);
  assert.ok(levels.some(level => level.touches === 3 && Math.abs(level.price - 11) < .15));
});

test('flat or short price history still has useful range levels', () => {
  assert.deepEqual(keyLevelsForBars([]), []);
  assert.deepEqual(keyLevelsForBars([{h:12, l:8}]).map(level => level.price), [8, 12]);
  const levels = keyLevelsForBars(Array.from({length:5}, () => ({h:12, l:8})));
  assert.deepEqual(levels.map(level => level.price), [8, 12]);
});
