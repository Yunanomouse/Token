"""Baseline: the live bot's own rule, Kaufman's KAMA filter (10/2/30, k = 0.5), on 5-minute bars.

Entry when KAMA has risen more than its noise filter above its 3-bar low;
exit when it has fallen more than the filter below its high.  The exit
here uses the highest KAMA of the last ``exit_lookback`` bars instead of
"since entry", because an indicator does not know when the engine filled.
"""
import numpy as np

NAME = "KAMA baseline (live bot rule)"
TIMEFRAME = 5
PARAMS = {"n": 10, "fast": 2, "slow": 30, "filter_n": 20, "k": 0.5, "entry_lookback": 3, "exit_lookback": 12}


def _kama(c, n, fast, slow):
    out = np.full(c.size, np.nan)
    if c.size <= n:
        return out
    change = np.abs(c[n:] - c[:-n])
    vol = np.convolve(np.abs(np.diff(c)), np.ones(n), "valid")
    er = np.where(vol > 0, change / np.where(vol > 0, vol, 1.0), 0.0)
    fsc, ssc = 2.0 / (fast + 1), 2.0 / (slow + 1)
    sc = (er * (fsc - ssc) + ssc) ** 2
    k = c[n]
    out[n] = k
    for t in range(n + 1, c.size):
        k += sc[t - n] * (c[t] - k)
        out[t] = k
    return out


def _roll(a, w, fn):
    out = np.full(a.size, np.nan)
    if a.size >= w:
        out[w - 1:] = fn(np.lib.stride_tricks.sliding_window_view(a, w), axis=1)
    return out


def signals(bars, n=10, fast=2, slow=30, filter_n=20, k=0.5, entry_lookback=3, exit_lookback=12):
    a = _kama(bars["close"].astype(float), n, fast, slow)
    d = np.r_[np.nan, np.diff(a)]
    f = k * _roll(d, filter_n, np.std)
    with np.errstate(invalid="ignore"):
        entry = (a - _roll(a, entry_lookback, np.min)) > f
        exit_ = (_roll(a, exit_lookback, np.max) - a) > f
    ok = ~np.isnan(f)
    return {"entry": entry & ok, "exit": exit_ & ok}
