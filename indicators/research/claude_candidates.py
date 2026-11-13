"""Candidate indicators tried for the duel, before one was picked.

Each ``make_*`` returns an indicator (see quantum/signals.py for the
contract).  The pick is re-written as a self-contained file,
indicators/claude.py; this file is the record of what else was tried.
Every candidate is causal: rolling windows end at the current bar, and
per-session quantities (VWAP, time of day) reset at each session's first
bar.
"""
from __future__ import annotations

import numpy as np

from quantum.signals import Indicator


# ---------------------------------------------------------------- helpers

def session_starts(dt):
    days = np.array([str(d)[:10] for d in dt])
    return np.r_[True, days[1:] != days[:-1]]


def minutes(dt):
    return np.array([int(str(d)[11:13]) * 60 + int(str(d)[14:16]) for d in dt])


def roll(a, w, fn):
    out = np.full(a.size, np.nan)
    if a.size >= w:
        out[w - 1:] = fn(np.lib.stride_tricks.sliding_window_view(a, w), axis=1)
    return out


def ema(a, n):
    out = np.empty(a.size)
    k, v = 2.0 / (n + 1), a[0]
    for i, x in enumerate(a):
        v = x if i == 0 else v + k * (x - v)
        out[i] = v
    return out


def rma(a, n):  # Wilder's average, as Pine's ta.rma (SMA seed)
    out = np.full(a.size, np.nan)
    if a.size < n:
        return out
    v = np.mean(a[:n])
    out[n - 1] = v
    for i in range(n, a.size):
        v = (v * (n - 1) + a[i]) / n
        out[i] = v
    return out


def rsi(c, n):
    d = np.r_[0.0, np.diff(c)]
    up, dn = rma(np.maximum(d, 0), n), rma(np.maximum(-d, 0), n)
    with np.errstate(divide="ignore", invalid="ignore"):
        r = 100 - 100 / (1 + up / dn)
    r = np.where(dn == 0, 100.0, r)
    return np.where(np.isnan(up), np.nan, r)


def atr(h, l, c, n):
    pc = np.r_[c[0], c[:-1]]
    tr = np.maximum(h - l, np.maximum(np.abs(h - pc), np.abs(l - pc)))
    return rma(tr, n)


def vwap(b):
    tp = (b["high"] + b["low"] + b["close"]) / 3.0
    v = b["volume"].astype(float)
    out = np.empty(tp.size)
    starts = np.flatnonzero(session_starts(b["datetime"]))
    for s, e in zip(starts, np.r_[starts[1:], tp.size]):
        cv, ctp = np.cumsum(v[s:e]), np.cumsum(tp[s:e] * v[s:e])
        out[s:e] = np.where(cv > 0, ctp / np.where(cv > 0, cv, 1), tp[s:e])
    return out


def kama(c, n=10, fast=2, slow=30):
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


def er(c, n=10):
    out = np.full(c.size, np.nan)
    if c.size <= n:
        return out
    change = np.abs(c[n:] - c[:-n])
    vol = np.convolve(np.abs(np.diff(c)), np.ones(n), "valid")
    out[n:] = np.where(vol > 0, change / np.where(vol > 0, vol, 1.0), 0.0)
    return out


def same_time_avg_volume(b, days=10):
    """Average volume of the same bar-of-day over the previous ``days`` sessions."""
    m, v = minutes(b["datetime"]), b["volume"].astype(float)
    sess = np.cumsum(session_starts(b["datetime"]))
    out = np.full(v.size, np.nan)
    hist: dict[int, list[float]] = {}
    last_sess, pending = None, []
    for i in range(v.size):
        if sess[i] != last_sess:  # a new session: the previous one joins the history
            for mm, vv in pending:
                hist.setdefault(mm, []).append(vv)
            pending, last_sess = [], sess[i]
        h = hist.get(m[i], [])
        if len(h) >= days:
            out[i] = float(np.mean(h[-days:]))
        pending.append((m[i], v[i]))
    return out


def _nan_false(*arrs):
    ok = np.ones(arrs[0].size, bool)
    for a in arrs:
        ok &= ~np.isnan(a)
    return ok


# ---------------------------------------------------------------- candidates

def make_kama(timeframe=15, k=0.5, exit_lookback=12):
    def fn(b, **_):
        c = b["close"].astype(float)
        a = kama(c)
        d = np.r_[np.nan, np.diff(a)]
        f = k * roll(d, 20, np.std)
        with np.errstate(invalid="ignore"):
            entry = (a - roll(a, 3, np.min)) > f
            ex = (roll(a, exit_lookback, np.max) - a) > f
        ok = _nan_false(f)
        return {"entry": entry & ok, "exit": ex & ok}
    return Indicator(f"KAMA {timeframe}m k={k}", timeframe, fn)


def make_vwap_reversion(timeframe=5, z=2.0, rsi_n=2, rsi_lo=10.0, start="10:00"):
    """Buy a stretched drop below session VWAP; sell on the return to VWAP."""
    t0 = int(start[:2]) * 60 + int(start[3:])

    def fn(b, **_):
        c = b["close"].astype(float)
        w = vwap(b)
        a = atr(b["high"], b["low"], c, 14)
        r = rsi(c, rsi_n)
        m = minutes(b["datetime"])
        with np.errstate(invalid="ignore"):
            entry = (c < w - z * a) & (r < rsi_lo) & (m >= t0)
            ex = (c >= w) | (r > 70)
        ok = _nan_false(a, r)
        return {"entry": entry & ok, "exit": ex & ok}
    return Indicator(f"VWAP reversion {timeframe}m z={z}", timeframe, fn)


def make_supertrend(timeframe=15, n=10, mult=3.0):
    def fn(b, **_):
        h, l, c = (b[k].astype(float) for k in ("high", "low", "close"))
        a = atr(h, l, c, n)
        mid = (h + l) / 2
        up, dn = mid - mult * a, mid + mult * a
        trend = np.zeros(c.size, int)
        fu, fd = np.full(c.size, np.nan), np.full(c.size, np.nan)
        for i in range(c.size):
            if np.isnan(a[i]):
                continue
            pu = fu[i - 1] if i and not np.isnan(fu[i - 1]) else up[i]
            pd = fd[i - 1] if i and not np.isnan(fd[i - 1]) else dn[i]
            fu[i] = max(up[i], pu) if i and c[i - 1] > pu else up[i]
            fd[i] = min(dn[i], pd) if i and c[i - 1] < pd else dn[i]
            prev = trend[i - 1] if i else 0
            trend[i] = 1 if c[i] > pd else (-1 if c[i] < pu else (prev or 1))
        return {"entry": trend == 1, "exit": trend == -1}
    return Indicator(f"Supertrend {timeframe}m x{mult}", timeframe, fn)


def make_volume_surge(timeframe=5, mult=3.0, days=10):
    """A bar trading several times its usual volume for that time of day,
    closing up and above VWAP near its high: buy; exit below VWAP or the 9-EMA."""
    def fn(b, **_):
        o, h, l, c = (b[k].astype(float) for k in ("open", "high", "low", "close"))
        v = b["volume"].astype(float)
        avg = same_time_avg_volume(b, days)
        w, e9 = vwap(b), ema(c, 9)
        rng = np.where(h > l, h - l, np.nan)
        with np.errstate(invalid="ignore"):
            strong = (c > o) & (c > w) & ((c - l) / rng >= 0.75)
            entry = (v > mult * avg) & strong
            ex = (c < w) | (c < e9)
        ok = _nan_false(avg)
        return {"entry": entry & ok, "exit": ex}
    return Indicator(f"Volume surge {timeframe}m x{mult}", timeframe, fn)


def make_er_breakout(timeframe=15, look=12, er_min=0.4, exit_look=6):
    """Close above the prior ``look``-bar high while the move is efficient."""
    def fn(b, **_):
        h, l, c = (b[k].astype(float) for k in ("high", "low", "close"))
        prior_hi = np.r_[np.nan, roll(h, look, np.max)[:-1]]
        prior_lo = np.r_[np.nan, roll(l, exit_look, np.min)[:-1]]
        e = er(c, 10)
        with np.errstate(invalid="ignore"):
            entry = (c > prior_hi) & (e > er_min)
            ex = c < prior_lo
        ok = _nan_false(prior_hi, e)
        return {"entry": entry & ok, "exit": ex & _nan_false(prior_lo)}
    return Indicator(f"ER breakout {timeframe}m er>{er_min}", timeframe, fn)


def grid():
    out = []
    for tf in (15, 30):
        for k in (0.5, 1.0):
            out.append(make_kama(tf, k))
    for tf in (5, 15):
        for z in (1.5, 2.0, 2.5):
            out.append(make_vwap_reversion(tf, z))
    for tf in (5, 15):
        for m in (2.0, 3.0):
            out.append(make_supertrend(tf, 10, m))
    for m in (3.0, 5.0):
        out.append(make_volume_surge(5, m))
    for tf in (5, 15):
        for e in (0.3, 0.5):
            out.append(make_er_breakout(tf, 12, e))
    return out
