const signalGuides = {
  'short-base-breakout': {
    title: 'Short-base breakout', category: 'Monthly pattern',
    summary: 'Price has moved above a shorter, roughly sideways base after an earlier decline.',
    meaning: 'The scanner looks for an eight-month floor and ceiling, then flags a monthly price move above that ceiling. This is a shorter setup than the multiyear descending triangle.',
    checks: [
      'The base lasts eight completed months, with at least three floor-zone tests spread across seven months.',
      'There was an earlier high at least twice the base high, and the previous month had not already broken out.',
      'The latest monthly price is at least 5% above the base high, but no more than twice it. Monthly MACD has turned positive recently.'
    ],
    example: 'If the highest price in the eight-month base was 1.00 and the latest monthly price is 1.07, it is 7% above that base high.',
    note: 'The “above prior 8-month high” value on a result measures the distance from that ceiling. An open month can fall back below it.'
  },
  'near-breakout': {
    title: 'Near breakout', category: 'Monthly triangle',
    summary: 'A long descending triangle is close to its falling upper boundary.',
    meaning: 'Repeated lows form a support zone while swing highs step down. The two lines are converging, and price has not cleared the upper boundary by the scanner’s breakout threshold.',
    checks: [
      'The scanner fits 24–60 monthly candles, with at least three support-zone tests over 18 months and at least two lower swing highs.',
      'The falling boundary is projected to meet support within eight months.',
      'Price is no more than 25% below the boundary, and the monthly MACD histogram is positive after a recent nonpositive reading.'
    ],
    example: 'If the projected upper boundary is 1.00 and price is 0.95, the result shows a 5% distance to the boundary.',
    note: '“Near” describes the pattern and price position. It does not say that a breakout will happen.'
  },
  'breaking-out': {
    title: 'Breaking out', category: 'Monthly triangle',
    summary: 'Price is at least 1% above the falling upper boundary of a qualifying triangle.',
    meaning: 'The same long triangle rules apply, but the latest monthly price has moved beyond its projected resistance. For a first breakout candle, the scanner uses the boundary fitted before that candle began.',
    checks: [
      'The triangle has repeated support tests, lower swing highs and a falling upper boundary.',
      'The latest monthly price is at least 1% above that boundary.',
      'The monthly MACD histogram is positive, with a nonpositive reading in the recent three candles.'
    ],
    example: 'If the projected boundary is 1.00 and price is 1.03, the result shows 3% above the boundary.',
    note: 'A breakout shown during an open month is provisional. Price can move back below the line before month end.'
  },
  'monthly-key-level': {
    title: 'Monthly key level', category: 'Monthly price level',
    summary: 'Price has crossed or moved close to a level marked by earlier monthly swing highs or lows.',
    meaning: 'The scanner ranks recurring swing prices from earlier candles, then compares the previous monthly close with the latest monthly price.',
    checks: [
      'A prior swing level is selected without using the month being evaluated.',
      'A “crossed above” or “crossed below” result means the previous close and latest price are on opposite sides of the level.',
      'An “approaching” result means price is moving toward the level and is within 3% of it.'
    ],
    example: 'If last month closed at 0.98, the level is 1.00 and the latest price is 1.02, the label is “Crossed above.”',
    note: 'The level is a past price area, not a guaranteed support or resistance line. Open-month crosses can reverse.'
  },
  'early-macd': {
    title: 'Early MACD watch', category: 'Monthly momentum',
    summary: 'Monthly momentum is still negative, but it has improved for two months in a row.',
    meaning: 'This watchlist catches a MACD histogram moving toward zero before it turns positive. It does not require a chart pattern.',
    checks: [
      'The latest three monthly histogram readings are all negative and rise consecutively.',
      'The move toward zero over those two months is at least 25%.',
      'At the same recent pace, the remaining gap to zero is no more than three months. Existing triangle matches are excluded.'
    ],
    example: 'Readings of −0.30, −0.20 and −0.10 are improving while still below zero.',
    note: 'The “gap at recent pace” is a distance measure, not a prediction of when MACD will cross zero.'
  },
  'hourly-extremes': {
    title: '1-hour extreme', category: 'Hourly momentum',
    summary: 'RSI and MACD are unusually strong or weak on the same one-hour candle.',
    meaning: 'The scanner compares the latest hour with the coin’s own recent hourly readings. It can label an extreme high or an extreme low.',
    checks: [
      'Extreme high: RSI is at least 80, the MACD line is positive, and MACD ranks in the top 5% of its previous 180 hourly readings.',
      'Extreme low: RSI is at most 20, the MACD line is negative, and MACD ranks in the bottom 5%.',
      'MACD is divided by price before ranking, so the comparison is relative to this coin’s history.'
    ],
    example: 'An RSI of 84 with positive MACD at the 97th percentile meets the momentum part of an extreme-high result.',
    note: 'An extreme is a description of the current hour, not a reversal or continuation forecast. The open hour can still change.'
  },
  'weekly-macd': {
    title: 'Weekly MACD turning green', category: 'BTC pair',
    summary: 'The weekly MACD histogram has just moved from zero or below to above zero.',
    meaning: 'This is a first positive weekly momentum reading for a coin priced in BTC.',
    checks: [
      'The previous weekly MACD histogram was zero or negative.',
      'The latest weekly histogram is positive.',
      'The calculation uses the standard 12, 26 and 9 period MACD settings.'
    ],
    example: 'A previous histogram of −0.001 followed by +0.0002 meets this condition.',
    note: '“Turning green” refers to the histogram crossing zero. An open week can return below zero.'
  },
  'weekly-upper-band': {
    title: 'Above upper Bollinger Band', category: 'BTC pair',
    summary: 'The weekly BTC-pair price is at least 3% above its upper Bollinger Band.',
    meaning: 'The band is a moving price envelope. This result calls out a large move beyond its upper edge on the weekly chart.',
    checks: [
      'The middle band is the average of the last 21 weekly closes.',
      'The upper band is two standard deviations above that average.',
      'The latest weekly price is at least 3% above the upper band.'
    ],
    example: 'If the upper band is 0.000100 BTC and price is 0.000104 BTC, price is 4% above the band.',
    note: 'A move beyond the band does not guarantee that price will keep rising. An open week can move back inside it.'
  }
};

function signalGuideSlug(match, label) {
  if (match.stage === 'weekly BTC')
    return label === 'MACD turning green' ? 'weekly-macd' :
      label === 'Above upper band' ? 'weekly-upper-band' : null;
  if (match.stage === 'monthly key level') return 'monthly-key-level';
  if (match.stage === 'Extreme high' || match.stage === 'Extreme low') return 'hourly-extremes';
  if (!match.stage) return 'early-macd';
  return ({'short-base breakout':'short-base-breakout', 'near breakout':'near-breakout',
    'breaking out':'breaking-out'})[match.stage] || null;
}

if (typeof module !== 'undefined') module.exports = {signalGuides, signalGuideSlug};
