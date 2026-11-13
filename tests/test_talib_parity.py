"""Our indicators against TA-Lib, an independent C implementation.

TA-Lib (>= 0.8.1) is a test-only dependency; the bots run on numpy alone.
The two sides start their recursive averages differently (TA-Lib's ATR
leaves out the first bar's high - low, and its KAMA is seeded one bar
earlier), so values are compared only after a warm-up, where the seed's
weight has decayed to nothing.  TA-Lib's Supertrend reports the trend with
the opposite sign to TradingView's ``ta.supertrend``, which ours follows
(-1 is an uptrend there).

Run with::

    python3 -m pytest tests/test_talib_parity.py -q
"""
from __future__ import annotations

import unittest

import numpy as np

try:
    import talib
except ImportError:  # pragma: no cover - the test extra installs it
    talib = None

import indicators.claude as claude
from quantum.intraday import efficiency_ratio, kama

WARMUP = 200


def _ohlc(seed: int, n: int = 3000):
    """A random walk with trending stretches and gaps, so the trend flips often."""
    rng = np.random.default_rng(seed)
    drift = np.repeat(rng.normal(0, 0.002, n // 100 + 1), 100)[:n]
    ret = drift + rng.normal(0, 0.006, n)
    ret[rng.integers(0, n, 15)] += rng.normal(0, 0.04, 15)  # overnight-style gaps
    close = 20.0 * np.exp(np.cumsum(ret))
    opn = np.r_[close[0], close[:-1]] * np.exp(rng.normal(0, 0.001, n))
    high = np.maximum(opn, close) * np.exp(np.abs(rng.normal(0, 0.003, n)))
    low = np.minimum(opn, close) * np.exp(-np.abs(rng.normal(0, 0.003, n)))
    return high, low, close


@unittest.skipIf(talib is None, "TA-Lib not installed (pip install -e '.[test]')")
class TestTalibParity(unittest.TestCase):
    SEEDS = (0, 1, 2, 3)

    def test_efficiency_ratio_is_identical(self):
        for seed in self.SEEDS:
            _, _, c = _ohlc(seed)
            for n in (10, 20):
                ours, ref = efficiency_ratio(c, n), talib.ER(c, n)
                m = ~np.isnan(ref)
                self.assertGreater(m.sum(), len(c) - n - 1)
                np.testing.assert_allclose(ours[m], ref[m], rtol=0, atol=1e-12)

    def test_kama_converges_to_talib(self):
        # TA-Lib's KAMA is Kaufman's with fast 2 and slow 30, the live bot's settings.
        for seed in self.SEEDS:
            _, _, c = _ohlc(seed)
            ours, ref = kama(c, 10, 2, 30), talib.KAMA(c, 10)
            rel = np.abs(ours - ref) / c
            self.assertLess(np.nanmax(rel[WARMUP:]), 1e-6)
            self.assertLess(np.nanmax(rel[-500:]), 1e-12)  # the seed has decayed away

    def test_atr_converges_to_talib(self):
        for seed in self.SEEDS:
            h, low, c = _ohlc(seed)
            ours, ref = claude._atr(h, low, c, 10), talib.ATR(h, low, c, 10)
            rel = np.abs(ours - ref) / c
            self.assertLess(np.nanmax(rel[WARMUP:]), 1e-9)

    def test_supertrend_matches_talib_after_warmup(self):
        flips = 0
        for seed in self.SEEDS:
            h, low, c = _ohlc(seed)
            for factor, period in ((3.0, 10), (2.0, 14)):
                line, direction = claude.supertrend(h, low, c, factor, period)
                ref_line, ref_trend = talib.SUPERTREND(h, low, c, timeperiod=period, multiplier=factor)
                np.testing.assert_array_equal(-direction[WARMUP:], ref_trend[WARMUP:].astype(int))
                # The ATR seed decays as ((period-1)/period)**bars: slower for 14 than for 10.
                np.testing.assert_allclose(line[WARMUP:], ref_line[WARMUP:], rtol=1e-7, atol=0)
                np.testing.assert_allclose(line[-500:], ref_line[-500:], rtol=1e-12, atol=0)
                flips += int(np.sum(np.diff(direction[WARMUP:]) != 0))
        self.assertGreater(flips, 100)  # the comparison covered many trend changes


if __name__ == "__main__":
    unittest.main()
