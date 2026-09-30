/* Horizontal levels from swing highs and lows in the visible candles. */
function keyLevelsForBars(bars, limit = 5) {
  if (!Array.isArray(bars) || !bars.length) return [];
  if (bars.length < 3) {
    const low = Math.min(...bars.map(bar => bar.l));
    const high = Math.max(...bars.map(bar => bar.h));
    return low === high ? [{price:low, touches:1}] :
      [{price:low, touches:1}, {price:high, touches:1}].slice(0, limit);
  }
  const radius = bars.length >= 7 ? 2 : 1;
  const pivots = [];
  for (let i = radius; i < bars.length - radius; i++) {
    const neighbors = bars.slice(i - radius, i + radius + 1);
    if (neighbors.every((bar, offset) => offset === radius || bars[i].h >= bar.h) &&
        neighbors.some((bar, offset) => offset !== radius && bars[i].h > bar.h)) {
      const nearbyHigh = Math.max(...neighbors.filter((_, offset) => offset !== radius).map(bar => bar.h));
      pivots.push({price:bars[i].h, index:i, prominence:Math.log(bars[i].h / nearbyHigh)});
    }
    if (neighbors.every((bar, offset) => offset === radius || bars[i].l <= bar.l) &&
        neighbors.some((bar, offset) => offset !== radius && bars[i].l < bar.l)) {
      const nearbyLow = Math.min(...neighbors.filter((_, offset) => offset !== radius).map(bar => bar.l));
      pivots.push({price:bars[i].l, index:i, prominence:Math.log(nearbyLow / bars[i].l)});
    }
  }
  const groups = [];
  const clusterTolerance = Math.log(1.025);
  for (const pivot of pivots.sort((a, b) => a.price - b.price)) {
    if (!(pivot.price > 0)) continue;
    let group = groups.find(item => Math.abs(Math.log(pivot.price / item.price)) <= clusterTolerance);
    if (!group) {
      group = {price:pivot.price, pivots:[]};
      groups.push(group);
    }
    group.pivots.push(pivot);
    const prices = group.pivots.map(item => item.price).sort((a, b) => a - b);
    group.price = prices[Math.floor(prices.length / 2)];
  }
  const levels = groups.map(group => {
    const touches = [];
    for (const pivot of group.pivots.sort((a, b) => a.index - b.index)) {
      if (!touches.length || pivot.index - touches.at(-1) > radius * 2)
        touches.push(pivot.index);
    }
    return {price:group.price, touches:touches.length,
      prominence:Math.max(...group.pivots.map(item => item.prominence)),
      last:touches.at(-1) ?? -1, span:touches.length > 1 ? touches.at(-1) - touches[0] : 0};
  });
  const score = level => level.touches * 2 + Math.min(3, level.prominence / .12) +
    Math.min(1, level.span / bars.length) + level.last / bars.length * .5;
  levels.sort((a, b) => score(b) - score(a));
  if (levels.length < 2) {
    levels.push({price:Math.max(...bars.map(bar => bar.h)), touches:1});
    levels.push({price:Math.min(...bars.map(bar => bar.l)), touches:1});
  }
  const selected = [];
  for (const level of levels) {
    if (selected.length === limit) break;
    if (selected.every(other => Math.abs(Math.log(level.price / other.price)) > Math.log(1.045)))
      selected.push(level);
  }
  return selected.sort((a, b) => a.price - b.price);
}

if (typeof module !== 'undefined') module.exports = {keyLevelsForBars};
