let passed = 0;
function test(name, run) { run(); passed++; console.log(`PASS ${name}`); }
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const ts = require('typescript');
const source = fs.readFileSync(require.resolve('../src/lib/chartIndicators.ts'), 'utf8');
const exportsObject = {};
vm.runInNewContext(ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.CommonJS }
}).outputText, { exports: exportsObject });
const calculate = exportsObject.liveCandleIndicators;
const candles = Array.from({ length: 50 }, (_, i) => ({ time: i * 300, close: 100 }));

test('ticks replace one provisional close without consuming extra EMA periods', () => {
  const first = calculate(candles, 110, 15000);
  for (let i = 0; i < 100; i++) calculate(candles, i % 2 ? 90 : 120, 15000);
  const latest = calculate(candles, 110, 15000);
  assert.equal(latest.ema9, 102);
  assert.equal(latest.ema9, first.ema9);
  assert.equal(latest.ema21, first.ema21);
});

test('a completed candle enters EMA exactly once and future candles are ignored', () => {
  const history = [...candles, { time: 15000, close: 110 }, { time: 15600, close: 99999 }];
  assert.equal(calculate(history, 110, 15000).ema9, 102);
  assert.ok(Math.abs(calculate(history, 110, 15300).ema9 - 103.6) < 1e-10);
});

test('RSI reflects current candle close rather than stale server RSI', () => {
  assert.equal(calculate(candles, 110, 15000).rsi, 100);
  assert.equal(calculate(candles, 90, 15000).rsi, 0);
  assert.equal(calculate(candles, 100, 15000).rsi, 50);
});

console.log(`${passed} chart indicator tests passed`);
