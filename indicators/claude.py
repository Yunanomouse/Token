"""Claude's duel entry: Supertrend (ATR 10 x 3.0) on 5-minute bars, long only.

Supertrend (Olivier Seban) trails a band ``factor`` ATRs below the bar's
midpoint in an uptrend and above it in a downtrend; the trend flips when
the close crosses the band.  This is TradingView's ``ta.supertrend``
exactly -- same true range, same Wilder ATR seeded with an SMA, same band
ratchet, same direction rule -- so the Pine version
(``pine/claude_supertrend.pine``) draws the same lines and gives the same
signals bar for bar.  In Pine's convention direction -1 is up.

* ``entry``: the trend is up.  The engine buys at the next bar's open, so
  a stock that joins the day's screen mid-trend is bought then.
* ``exit``: the trend is down.

It runs on the whole history, across sessions, like a chart does.

Picked from 20 candidate configurations on the training window only
(2026-07-21 .. 2026-08-28) by a rule fixed before any were run: see
docs/indicator_duel.md and indicators/research/.
"""
import numpy as np

NAME = "Claude: Supertrend 5m (ATR 10 x 3.0)"
TIMEFRAME = 5
PARAMS = {"atr_period": 10, "factor": 3.0}


def _atr(high, low, close, n):
    """ta.atr: Wilder's average of the true range, seeded with an SMA of the first n."""
    tr = np.empty(close.size)
    tr[0] = high[0] - low[0]
    pc = close[:-1]
    tr[1:] = np.maximum(high[1:] - low[1:], np.maximum(np.abs(high[1:] - pc), np.abs(low[1:] - pc)))
    out = np.full(close.size, np.nan)
    if close.size < n:
        return out
    v = tr[:n].mean()
    out[n - 1] = v
    for i in range(n, close.size):
        v = (v * (n - 1) + tr[i]) / n
        out[i] = v
    return out


def supertrend(high, low, close, factor=3.0, atr_period=10):
    """(line, direction) as ta.supertrend: direction -1 is an uptrend, 1 a downtrend."""
    atr = _atr(high, low, close, atr_period)
    src = (high + low) / 2.0
    n = close.size
    line, direction = np.full(n, np.nan), np.ones(n, dtype=int)
    lower_prev = upper_prev = 0.0          # nz(band[1])
    st_prev = np.nan
    upper_was = np.nan
    for i in range(n):
        if np.isnan(atr[i]):
            # Bands are na; Pine carries nz() of them forward as 0.
            lower_prev = upper_prev = 0.0
            continue
        lower, upper = src[i] - factor * atr[i], src[i] + factor * atr[i]
        c1 = close[i - 1] if i else np.nan
        lower = lower if (lower > lower_prev or c1 < lower_prev) else lower_prev
        upper = upper if (upper < upper_prev or c1 > upper_prev) else upper_prev
        if i == 0 or np.isnan(atr[i - 1]):
            d = 1
        elif st_prev == upper_was:
            d = -1 if close[i] > upper else 1
        else:
            d = 1 if close[i] < lower else -1
        st = lower if d == -1 else upper
        line[i], direction[i] = st, d
        lower_prev, upper_prev, upper_was, st_prev = lower, upper, upper, st
    return line, direction


def signals(bars, atr_period=10, factor=3.0):
    h, l, c = (np.asarray(bars[k], dtype=float) for k in ("high", "low", "close"))
    line, d = supertrend(h, l, c, factor, atr_period)
    ok = ~np.isnan(line)
    return {"entry": ok & (d == -1), "exit": ok & (d == 1)}
