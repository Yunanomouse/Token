/* Quantum Trading engine, browser port of quantum/live.py + the strategies it
   uses from quantum/backtest.py, quantum/portfolio.py and quantum/market.py.
   Same arithmetic, same order of operations, so a run here matches a run of
   the Python program on the same prices and settings. */
const QT = (function () {
  "use strict";
  const TRADING_DAYS = 252;

  // ---- estimation (quantum/market.py) -----------------------------------
  function logReturns(rows) {
    const t = rows.length, n = rows[0].length, out = [];
    for (let i = 1; i < t; i++) {
      const r = new Array(n);
      for (let j = 0; j < n; j++) r[j] = Math.log(rows[i][j]) - Math.log(rows[i - 1][j]);
      out.push(r);
    }
    return out;
  }

  // Ledoit-Wolf shrinkage toward a scaled identity.  The expected-error term
  // sum_k ||x_k x_k' - S||^2 is evaluated in closed form as
  // sum_k ||x_k||^4 - t ||S||^2, which equals the Python loop exactly in
  // exact arithmetic.
  function ledoitWolf(R) {
    const t = R.length, n = R[0].length;
    const mean = new Array(n).fill(0);
    for (const r of R) for (let j = 0; j < n; j++) mean[j] += r[j];
    for (let j = 0; j < n; j++) mean[j] /= t;
    const C = R.map(r => r.map((v, j) => v - mean[j]));
    const S = Array.from({ length: n }, () => new Array(n).fill(0));
    for (const x of C) for (let a = 0; a < n; a++) { const xa = x[a]; for (let b = 0; b < n; b++) S[a][b] += xa * x[b]; }
    for (let a = 0; a < n; a++) for (let b = 0; b < n; b++) S[a][b] /= t;
    let tr = 0; for (let a = 0; a < n; a++) tr += S[a][a];
    const mu = tr / n;
    let d2 = 0, s2 = 0;
    for (let a = 0; a < n; a++) for (let b = 0; b < n; b++) {
      const v = S[a][b] - (a === b ? mu : 0); d2 += v * v; s2 += S[a][b] * S[a][b];
    }
    let q4 = 0;
    for (const x of C) { let s = 0; for (let j = 0; j < n; j++) s += x[j] * x[j]; q4 += s * s; }
    let b2 = Math.max((q4 - t * s2) / (t * t), 0);
    b2 = Math.min(b2, d2);
    const k = d2 <= 0 ? 0 : Math.max(0, Math.min(1, b2 / d2));
    const cov = S.map((row, a) => row.map((v, b) => k * (a === b ? mu : 0) + (1 - k) * v));
    return { cov, shrinkage: k };
  }

  function marketData(rows) {
    if (rows.length < 3) throw new Error("need at least three price observations");
    const R = logReturns(rows), n = rows[0].length;
    const mu = new Array(n).fill(0);
    for (const r of R) for (let j = 0; j < n; j++) mu[j] += r[j];
    for (let j = 0; j < n; j++) mu[j] = mu[j] / R.length * TRADING_DAYS;
    const { cov } = ledoitWolf(R);
    for (let a = 0; a < n; a++) for (let b = 0; b < n; b++) cov[a][b] *= TRADING_DAYS;
    return { mu, cov, n };
  }

  // ---- strategies (quantum/backtest.py, quantum/portfolio.py) ----------
  function solve(A, b) {
    const n = b.length, M = A.map((r, i) => r.concat([b[i]]));
    for (let c = 0; c < n; c++) {
      let p = c;
      for (let r = c + 1; r < n; r++) if (Math.abs(M[r][c]) > Math.abs(M[p][c])) p = r;
      if (Math.abs(M[p][c]) < 1e-300) return null;
      [M[c], M[p]] = [M[p], M[c]];
      for (let r = 0; r < n; r++) if (r !== c) {
        const f = M[r][c] / M[c][c];
        if (f) for (let k = c; k <= n; k++) M[r][k] -= f * M[c][k];
      }
    }
    return M.map((r, i) => r[n] / r[i]);
  }

  function normalise(w) {
    const c = w.map(v => Math.max(v, 0)), s = c.reduce((a, v) => a + v, 0);
    return s > 0 ? c.map(v => v / s) : c.map(() => 1 / c.length);
  }

  function equalWeight(m) { return new Array(m.n).fill(1 / m.n); }

  // Exact minimiser of lambda w'Sw - mu'w with sum(w) = 1, w >= 0 -- same
  // algorithm as quantum/portfolio.py unconstrained_mean_variance(long_only=True).
  function projectSimplex(v) {
    const u = v.slice().sort((a, b) => b - a);
    let css = 0, theta = 0;
    for (let i = 0; i < u.length; i++) { css += u[i]; if (u[i] - (css - 1) / (i + 1) > 0) theta = (css - 1) / (i + 1); }
    return v.map(x => Math.max(x - theta, 0));
  }
  function markowitz(m, lambda) {
    const n = m.n, A = m.cov.map(r => r.map(v => 2 * lambda * v)), ones = new Array(n).fill(1);
    const x = solve(A, m.mu), y = solve(A, ones);
    if (x && y) {
      const sy = y.reduce((a, v) => a + v, 0), sx = x.reduce((a, v) => a + v, 0);
      if (Math.abs(sy) > 1e-18) {
        const lam = (1 - sx) / sy, w = x.map((v, i) => v + lam * y[i]);
        if (w.every(v => v >= 0)) return w;
      }
    }
    // Lipschitz constant 2*lambda*maxEig(S) by power iteration.
    let e = ones.map(v => v / Math.sqrt(n)), L = 0;
    for (let it = 0; it < 500; it++) {
      const z = A.map(r => r.reduce((a, v, j) => a + v * e[j], 0));
      const nz = Math.sqrt(z.reduce((a, v) => a + v * v, 0)); if (nz <= 0) break;
      L = nz; e = z.map(v => v / nz);
    }
    L = Math.max(L * 1.0001, 1e-18);
    let w = new Array(n).fill(1 / n), yk = w.slice(), t = 1;
    for (let it = 0; it < 20000; it++) {
      const g = A.map((r, i) => r.reduce((a, v, j) => a + v * yk[j], 0) - m.mu[i]);
      const wn = projectSimplex(yk.map((v, i) => v - g[i] / L));
      const tn = 0.5 * (1 + Math.sqrt(1 + 4 * t * t));
      let step = 0; for (let i = 0; i < n; i++) step = Math.max(step, Math.abs(wn[i] - w[i]));
      yk = wn.map((v, i) => v + ((t - 1) / tn) * (v - w[i]));
      w = wn; t = tn;
      if (step < 1e-13) break;
    }
    return w;
  }

  // Exact optimum over all C(n, K) equal-weighted subsets, in the same
  // lexicographic order as itertools.combinations so ties break the same way.
  // The Python program's simulated annealing reached this same optimum at
  // every one of 130 rebalances on these prices.
  function cardinality(m, K, lambda) {
    const n = m.n; K = Math.min(Math.max(1, K | 0), n);
    const idx = Array.from({ length: K }, (_, i) => i);
    let best = null, bestVal = Infinity;
    const w = 1 / K;
    for (;;) {
      let risk = 0, ret = 0;
      for (let a = 0; a < K; a++) { ret += m.mu[idx[a]] * w; for (let b = 0; b < K; b++) risk += m.cov[idx[a]][idx[b]] * w * w; }
      const val = lambda * risk - ret;
      if (val < bestVal) { bestVal = val; best = idx.slice(); }
      let i = K - 1;
      while (i >= 0 && idx[i] === n - K + i) i--;
      if (i < 0) break;
      idx[i]++;
      for (let j = i + 1; j < K; j++) idx[j] = idx[j - 1] + 1;
    }
    const out = new Array(n).fill(0);
    for (const i of best) out[i] = 1;
    return normalise(out);
  }

  function strategyFor(cfg) {
    if (cfg.strategy === "equal_weight") return m => equalWeight(m);
    if (cfg.strategy === "markowitz") return m => markowitz(m, cfg.riskAversion);
    return m => cardinality(m, cfg.cardinality, cfg.riskAversion);
  }

  // ---- paper broker (quantum/live.py PaperBroker) -----------------------
  class PaperBroker {
    constructor(cash, feeRate) { this.cash = cash; this.feeRate = feeRate; this.pos = {}; }
    positions() {
      const o = {};
      for (const [k, v] of Object.entries(this.pos)) if (Math.abs(v) > 1e-12) o[k] = v;
      return o;
    }
    submit(orders, bar) {
      const fills = [];
      const sorted = orders.slice().sort((a, b) => a.quantity - b.quantity);
      for (let o of sorted) {
        if (Math.abs(o.quantity) < 1e-12) continue;
        const price = bar.prices[o.ticker];
        let q = o.quantity, notional = q * price, fee = Math.abs(notional) * this.feeRate;
        if (notional + fee > this.cash + 1e-9) {
          const affordable = Math.max(this.cash / (price * (1 + this.feeRate)), 0);
          if (affordable < 1e-9) continue;
          q = affordable; notional = affordable * price; fee = notional * this.feeRate;
        }
        this.cash -= notional + fee;
        this.pos[o.ticker] = (this.pos[o.ticker] || 0) + q;
        fills.push({ ticker: o.ticker, quantity: q, price, fee, date: bar.date });
      }
      return fills;
    }
  }

  // ---- gains and losses (quantum/live.py trade_ledger) -------------------
  // Average cost from the fills: a buy's fee joins its cost, a sell's fee
  // comes off its proceeds, so realized + unrealized = change in equity.
  function ledger(fills, lastPrices) {
    lastPrices = lastPrices || {};
    const shares = {}, basis = {}, realized = {}, trip = {}, trips = [], annotated = [];
    for (const f of fills) {
      const t = f.ticker, q = f.quantity, px = f.price, fee = f.fee, held = shares[t] || 0;
      let pnl = 0;
      if (q > 0) {
        if (held <= 1e-12) trip[t] = { ticker: t, entry_date: f.date, cost: 0, pnl: 0 };
        shares[t] = held + q; basis[t] = (basis[t] || 0) + q * px + fee; trip[t].cost += q * px + fee;
      } else if (held > 1e-12) {
        const sold = Math.min(-q, held), avg = basis[t] / held;
        pnl = sold * px - fee - avg * sold;
        shares[t] = held - sold; basis[t] -= avg * sold;
        realized[t] = (realized[t] || 0) + pnl; trip[t].pnl += pnl;
        if (shares[t] <= 1e-9 * Math.max(held, 1)) {
          shares[t] = 0; basis[t] = 0;
          const done = trip[t]; delete trip[t];
          done.exit_date = f.date; done.exit_price = px; done.return_pct = done.cost > 0 ? done.pnl / done.cost : 0;
          trips.push(done);
        }
      }
      annotated.push(Object.assign({}, f, { realized_pnl: pnl }));
    }
    const names = [...new Set([...Object.keys(shares), ...Object.keys(realized)])].sort();
    const byTicker = {}, positions = {};
    let totalReal = 0, totalUnreal = 0;
    for (const t of names) {
      let unreal = 0;
      if ((shares[t] || 0) > 1e-12) {
        const px = lastPrices[t], value = px != null ? shares[t] * px : basis[t];
        unreal = value - basis[t];
        positions[t] = { shares: shares[t], avg_cost: basis[t] / shares[t], cost_basis: basis[t], price: px == null ? null : px,
                         market_value: value, unrealized_pnl: unreal, unrealized_pct: basis[t] > 0 ? unreal / basis[t] : 0,
                         since: trip[t].entry_date };
      }
      const r = realized[t] || 0;
      byTicker[t] = { realized_pnl: r, unrealized_pnl: unreal, total_pnl: r + unreal };
      totalReal += r; totalUnreal += unreal;
    }
    const wins = trips.filter(x => x.pnl > 0), losses = trips.filter(x => x.pnl <= 0);
    return { fills: annotated, positions, by_ticker: byTicker, round_trips: trips,
             realized_pnl: totalReal, unrealized_pnl: totalUnreal, total_pnl: totalReal + totalUnreal,
             n_round_trips: trips.length, n_wins: wins.length, win_rate: trips.length ? wins.length / trips.length : null,
             avg_win: wins.length ? wins.reduce((a, x) => a + x.pnl, 0) / wins.length : null,
             avg_loss: losses.length ? losses.reduce((a, x) => a + x.pnl, 0) / losses.length : null };
  }

  // ---- engine (quantum/live.py Engine) ----------------------------------
  class Engine {
    constructor(cfg) {
      this.cfg = cfg;
      this.tickers = cfg.tickers.slice();
      this.broker = new PaperBroker(cfg.initialCash, cfg.feeRate);
      this.strategy = strategyFor(cfg);
      this.dates = []; this.prices = [];
      this.equity = []; this.peak = 0; this.lastRebalance = -1;
      this.targets = {}; this.halted = false; this.haltReason = "";
      this.fills = []; this.log = [];
    }
    value(bar) {
      let v = this.broker.cash;
      for (const [t, q] of Object.entries(this.broker.positions())) v += q * bar.prices[t];
      return v;
    }
    weights(bar) {
      const eq = this.value(bar), o = {};
      if (eq <= 0) return o;
      for (const [t, q] of Object.entries(this.broker.positions())) o[t] = q * bar.prices[t] / eq;
      return o;
    }
    onBar(bar) {
      if (this.dates.length && bar.date <= this.dates[this.dates.length - 1]) return { action: "duplicate" };
      this.dates.push(bar.date);
      this.prices.push(this.tickers.map(t => bar.prices[t]));
      const eq = this.value(bar);
      this.equity.push(eq);
      this.peak = Math.max(this.peak, eq);
      const dd = this.peak > 0 ? 1 - eq / this.peak : 0;
      const L = this.cfg.limits, n = this.dates.length;
      let action = "hold", fills = [], note = "";
      if (this.halted) action = "halted";
      else if (dd >= L.maxDrawdown && Object.keys(this.broker.positions()).length) {
        fills = this.broker.submit(Object.entries(this.broker.positions()).map(([t, q]) => ({ ticker: t, quantity: -q })), bar);
        this.halted = true; this.targets = {};
        this.haltReason = `drawdown ${(dd * 100).toFixed(1)}% >= limit ${(L.maxDrawdown * 100).toFixed(1)}% on ${bar.date}`;
        action = "kill_switch";
      } else if (this.cfg.tradeFrom && bar.date < this.cfg.tradeFrom) {
        action = "warmup";
      } else if (n >= Math.max(L.minHistory, this.cfg.window) &&
                 (this.lastRebalance < 0 || n - this.lastRebalance >= this.cfg.rebalanceEvery)) {
        [fills, note] = this.rebalance(bar);
        this.lastRebalance = n;
        action = "rebalance";
      }
      this.fills.push(...fills);
      const line = `${bar.date} equity=${eq.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })} dd=${(dd * 100).toFixed(1)}% ${action}` +
        (fills.length ? ` fills=${fills.length}` : "") + (note ? ` note=${note}` : "");
      this.log.push(line);
      if (this.log.length > 500) this.log.splice(0, this.log.length - 500);
      return { action, equity: eq, drawdown: dd, fills };
    }
    rebalance(bar) {
      const m = marketData(this.prices.slice(-this.cfg.window));
      const raw = this.strategy(m).map(v => Math.max(v, 0));
      const s = raw.reduce((a, v) => a + v, 0);
      if (s <= 0) return [[], "strategy returned no positions"];
      let target = raw.map(v => v / s);
      const L = this.cfg.limits, cap = L.maxWeight;
      for (let it = 0; it < target.length; it++) {
        const over = target.map(v => v > cap);
        if (!over.some(Boolean)) break;
        let excess = 0;
        target = target.map((v, i) => { if (over[i]) { excess += v - cap; return cap; } return v; });
        const underSum = target.reduce((a, v, i) => a + (over[i] ? 0 : v), 0);
        if (over.some(o => !o) && underSum > 0) target = target.map((v, i) => over[i] ? v : v + excess * v / underSum);
      }
      const w = this.weights(bar);
      const current = this.tickers.map(t => w[t] || 0);
      const move = target.map((v, i) => v - current[i]);
      const turnover = (move.reduce((a, v) => a + Math.abs(v), 0) + Math.abs(move.reduce((a, v) => a + v, 0))) / 2;  // cash counts: max(buys, sells)
      let note = "";
      if (turnover > L.maxTurnover && turnover > 0) {
        const sc = L.maxTurnover / turnover;
        target = current.map((c, i) => c + move[i] * sc);
        note = `turnover ${(turnover * 100).toFixed(1)}% capped to ${(L.maxTurnover * 100).toFixed(1)}%`;
      }
      const eq = this.value(bar), held = this.broker.positions(), orders = [];
      this.tickers.forEach((t, i) => {
        const delta = target[i] * eq / bar.prices[t] - (held[t] || 0);
        if (Math.abs(delta * bar.prices[t]) >= 1) orders.push({ ticker: t, quantity: delta });
      });
      const fills = this.broker.submit(orders, bar);
      this.targets = {};
      this.tickers.forEach((t, i) => { if (target[i] > 1e-9) this.targets[t] = target[i]; });
      return [fills, note];
    }
  }

  return { Engine, PaperBroker, marketData, ledoitWolf, markowitz, cardinality, equalWeight, ledger };
})();
if (typeof module !== "undefined") module.exports = QT;
