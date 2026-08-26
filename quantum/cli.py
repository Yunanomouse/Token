"""Command-line interface: ``python3 -m quantum <command>``.

Every subcommand prints the quantum result next to its classical baseline. That
side-by-side is deliberate -- it is the only way to see what these methods do and
do not buy you.
"""

from __future__ import annotations

import argparse
import math
import sys

import numpy as np

from .amplitude import classical_monte_carlo_error
from .arbitrage import build_rate_matrix, cycle_profit, find_arbitrage
from .market import load_price_csv, synthetic_prices
from .portfolio import (
    PortfolioConstraints,
    PortfolioProblem,
    exhaustive_cardinality,
    solve_portfolio,
    unconstrained_mean_variance,
)
from .pricing import OptionSpec, classical_monte_carlo_price, price_european_option
from .qubo import QUBO
from .risk import (
    parametric_var,
    portfolio_loss_distribution,
    quantum_expected_shortfall,
    quantum_value_at_risk,
)
from .solvers import available_solvers, get_solver

DEMO_CURRENCIES = ["USD", "EUR", "GBP", "JPY", "CHF"]
DEMO_RATES = {
    ("USD", "EUR"): 0.9200, ("EUR", "USD"): 1.0870,
    ("USD", "GBP"): 0.7900, ("GBP", "USD"): 1.2658,
    ("EUR", "GBP"): 0.8600, ("GBP", "EUR"): 1.1650,
    ("USD", "JPY"): 151.00, ("JPY", "USD"): 1 / 151.2,
    ("EUR", "JPY"): 164.50, ("JPY", "EUR"): 1 / 164.9,
    ("GBP", "JPY"): 191.00, ("JPY", "GBP"): 1 / 191.5,
    ("USD", "CHF"): 0.8800, ("CHF", "USD"): 1.1364,
    ("EUR", "CHF"): 0.9560, ("CHF", "EUR"): 1.0460,
    ("GBP", "CHF"): 1.1120, ("CHF", "GBP"): 0.8990,
}


def _rule(title: str) -> None:
    print(f"\n{title}\n{'=' * len(title)}")


def _load_market(args):
    if args.csv:
        return load_price_csv(args.csv)
    return synthetic_prices(n_assets=args.assets, n_days=args.days, seed=args.seed)


# --------------------------------------------------------------------------


def cmd_portfolio(args) -> int:
    market = _load_market(args)
    _rule("Market")
    print(market.summary())

    constraints = PortfolioConstraints(cardinality=args.cardinality)
    problem = PortfolioProblem(
        market.expected_returns,
        market.covariance,
        market.tickers,
        risk_aversion=args.risk_aversion,
        constraints=constraints,
        encoding=args.encoding,
        n_lot_bits=args.lot_bits,
    )

    _rule(f"Constrained portfolio ({args.solver})")
    kwargs = {"rng": np.random.default_rng(args.seed)}
    if args.solver in ("qaoa",):
        kwargs.update(p=args.qaoa_layers, n_starts=4)
    result = solve_portfolio(problem, solver=args.solver, **kwargs)
    print(f"QUBO variables : {result.detail['n_qubo_vars']}")
    print(result.report())

    _rule("Classical baselines")
    w = unconstrained_mean_variance(
        market.expected_returns, market.covariance, args.risk_aversion, long_only=True
    )
    ret = float(market.expected_returns @ w)
    vol = math.sqrt(max(float(w @ market.covariance @ w), 0.0))
    print(f"unconstrained mean-variance : return {ret:7.2%}  vol {vol:7.2%}  "
          f"sharpe {ret/vol if vol else float('nan'):5.2f}  (closed form, milliseconds)")

    if args.cardinality and market.n_assets <= 20 and args.encoding == "select":
        mask, value = exhaustive_cardinality(
            market.expected_returns, market.covariance, args.cardinality, args.risk_aversion
        )
        picks = [market.tickers[i] for i in np.nonzero(mask)[0]]
        matched = set(picks) == set(result.holdings)
        print(f"exhaustive optimum          : objective {value:.6f}  picks {picks}")
        print(f"solver objective            : {result.objective:.6f}  "
              f"{'MATCHES the proven optimum' if matched else 'DIFFERS from the optimum'}")
    return 0


def cmd_price(args) -> int:
    spec = OptionSpec(
        spot=args.spot, strike=args.strike, rate=args.rate,
        volatility=args.volatility, maturity=args.maturity, option=args.option,
    )
    _rule(f"European {args.option} by amplitude estimation")
    result = price_european_option(
        spec, n_qubits=args.qubits, c_approx=args.c_approx,
        n_powers=args.powers, shots_per_power=args.shots,
        rng=np.random.default_rng(args.seed),
    )
    res = result.detail["circuit_resources"]
    print(f"quantum price        : {result.price:.6f}")
    print(f"Black-Scholes        : {result.analytic_price:.6f}")
    print(f"exact on this grid   : {result.discretised_price:.6f}")
    print(f"  discretisation err : {result.discretisation_error:.6f}  (finite price grid)")
    print(f"  estimation err     : {result.estimation_error:.6f}  (amplitude est. + payoff linearisation)")
    print(f"relative error       : {result.relative_error:.4%}")
    print(f"\ncircuit  : {res['qubits']} qubits, {res['logical_gates']} logical gates, "
          f"~{res['estimated_elementary_gates']} elementary after decomposition")
    print(f"AE       : {result.amplitude.method}, {result.amplitude.oracle_calls} oracle calls, "
          f"{result.amplitude.shots} shots")

    mc_price, mc_err = classical_monte_carlo_price(
        args.spot, args.strike, args.rate, args.volatility, args.maturity,
        samples=args.shots * args.powers, option=args.option,
        rng=np.random.default_rng(args.seed),
    )
    print(f"\nclassical Monte Carlo at the same shot budget: {mc_price:.6f} +/- {mc_err:.6f}")
    print("(the quadratic advantage is in oracle calls, not wall-clock -- a CPU wins today)")
    return 0


def cmd_risk(args) -> int:
    market = _load_market(args)
    weights = np.full(market.n_assets, 1.0 / market.n_assets)
    dist = portfolio_loss_distribution(
        weights, market.expected_returns, market.covariance,
        n_qubits=args.qubits, horizon=1.0 / 252.0,
    )

    _rule(f"Daily risk, equal-weighted book ({market.n_assets} assets)")
    var = quantum_value_at_risk(
        dist, args.confidence, n_powers=args.powers,
        shots_per_power=args.shots, rng=np.random.default_rng(args.seed),
    )
    cvar = quantum_expected_shortfall(
        dist, args.confidence, var_index=var.detail["grid_index"],
        n_powers=args.powers, shots_per_power=args.shots,
        rng=np.random.default_rng(args.seed),
    )
    print(f"VaR  {args.confidence:.0%}  quantum {var.value:8.5f}   exact {var.classical_value:8.5f}"
          f"   err {var.absolute_error:.6f}")
    print(f"CVaR {args.confidence:.0%}  quantum {cvar.value:8.5f}   exact {cvar.classical_value:8.5f}"
          f"   err {cvar.absolute_error:.6f}")
    print(f"\nparametric Gaussian VaR: "
          f"{parametric_var(weights, market.expected_returns, market.covariance, args.confidence):.5f}")
    print(f"grid spacing           : {var.detail['grid_spacing']:.6f} "
          f"({2**args.qubits} points) -- the floor on quantile accuracy")
    print(f"oracle calls           : VaR {var.oracle_calls:,} over "
          f"{var.detail['bisection_steps']} bisection steps")
    return 0


def cmd_arbitrage(args) -> int:
    rates = build_rate_matrix(DEMO_RATES, DEMO_CURRENCIES, fee=args.fee)
    _rule(f"Cyclic arbitrage, length {args.cycle_length}, {args.fee:.2%} fee per leg")
    result = find_arbitrage(
        rates, DEMO_CURRENCIES, cycle_length=args.cycle_length,
        solver=args.solver, rng=np.random.default_rng(args.seed),
    )
    if result.path:
        route = " -> ".join(result.named_path + [result.named_path[0]])
        print(f"best cycle    : {route}")
        print(f"gross multiple: {result.gross_multiple:.8f}")
        print(f"net profit    : {result.profit:+.4%}  "
              f"{'TRADEABLE' if result.profitable else '(not profitable after fees)'}")
    else:
        print("no feasible cycle decoded")

    classical = result.detail.get("classical_cycle_named")
    print(f"\nBellman-Ford (exact, polynomial): "
          f"{' -> '.join(classical + [classical[0]]) if classical else 'no negative cycle'}"
          f"   profit {result.detail.get('classical_profit', 0.0):+.4%}")
    print("Use Bellman-Ford for the unconstrained problem; the QUBO earns its keep")
    print("only once cycle length, capacity or multi-cycle selection are constrained.")
    return 0


def cmd_benchmark(args) -> int:
    _rule(f"Solver comparison on random {args.vars}-variable QUBOs")
    rng = np.random.default_rng(args.seed)
    names = [s for s in available_solvers() if s != "exact"]
    stats = {n: {"gap": [], "time": [], "hits": 0} for n in names}

    for trial in range(args.trials):
        problem = QUBO(Q=rng.normal(size=(args.vars, args.vars)))
        optimal = get_solver("exact").solve(problem).energy
        for name in names:
            kwargs = {"rng": np.random.default_rng(trial)}
            if name == "qaoa":
                kwargs.update(p=2, n_starts=3, max_iter=120)
            result = get_solver(name).solve(problem, **kwargs)
            gap = result.gap_to(optimal)
            stats[name]["gap"].append(gap)
            stats[name]["time"].append(result.runtime_seconds)
            if abs(gap) < 1e-6:
                stats[name]["hits"] += 1

    print(f"{'solver':<26}{'optimum found':>15}{'mean gap':>12}{'mean time':>12}")
    print("-" * 65)
    for name in names:
        s = stats[name]
        print(f"{name:<26}{s['hits']}/{args.trials:<13}"
              f"{np.mean(s['gap']):>12.5f}{np.mean(s['time']):>11.3f}s")
    print("\nAll three are heuristics; 'exact' proves the optimum but costs 2^n.")
    return 0


def cmd_demo(args) -> int:
    print("Quantum methods for trading -- end-to-end demonstration")
    for fn, sub in (
        (cmd_portfolio, "portfolio"), (cmd_price, "price"),
        (cmd_risk, "risk"), (cmd_arbitrage, "arbitrage"),
    ):
        parser = build_parser()
        sub_args = parser.parse_args([sub])
        sub_args.seed = args.seed
        fn(sub_args)
    print("\n" + "=" * 60)
    print("Every number above has its classical baseline beside it. On today's")
    print("hardware the classical column wins on wall-clock in every case.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python3 -m quantum",
        description="Quantum optimisation, pricing and risk for trading.",
    )
    parser.add_argument("--seed", type=int, default=0, help="random seed")
    sub = parser.add_subparsers(dest="command", required=True)

    def add_market_args(p):
        p.add_argument("--csv", help="wide price CSV (date column + one column per ticker)")
        p.add_argument("--assets", type=int, default=8, help="synthetic universe size")
        p.add_argument("--days", type=int, default=756, help="synthetic history length")

    p = sub.add_parser("portfolio", help="constrained portfolio optimisation")
    add_market_args(p)
    p.add_argument("--cardinality", type=int, default=4, help="hold exactly this many names")
    p.add_argument("--risk-aversion", type=float, default=2.0, dest="risk_aversion")
    p.add_argument("--solver", default="simulated_bifurcation", choices=available_solvers())
    p.add_argument("--encoding", default="select", choices=["select", "lots"])
    p.add_argument("--lot-bits", type=int, default=2, dest="lot_bits")
    p.add_argument("--qaoa-layers", type=int, default=2, dest="qaoa_layers")
    p.set_defaults(func=cmd_portfolio)

    p = sub.add_parser("price", help="price a European option by amplitude estimation")
    p.add_argument("--spot", type=float, default=100.0)
    p.add_argument("--strike", type=float, default=105.0)
    p.add_argument("--rate", type=float, default=0.03)
    p.add_argument("--volatility", type=float, default=0.20)
    p.add_argument("--maturity", type=float, default=1.0)
    p.add_argument("--option", default="call", choices=["call", "put"])
    p.add_argument("--qubits", type=int, default=6)
    p.add_argument("--c-approx", type=float, default=0.15, dest="c_approx")
    p.add_argument("--powers", type=int, default=6)
    p.add_argument("--shots", type=int, default=1024)
    p.set_defaults(func=cmd_price)

    p = sub.add_parser("risk", help="VaR and CVaR by amplitude estimation")
    add_market_args(p)
    p.add_argument("--confidence", type=float, default=0.95)
    p.add_argument("--qubits", type=int, default=6)
    p.add_argument("--powers", type=int, default=5)
    p.add_argument("--shots", type=int, default=512)
    p.set_defaults(func=cmd_risk)

    p = sub.add_parser("arbitrage", help="cyclic arbitrage detection")
    p.add_argument("--cycle-length", type=int, default=3, dest="cycle_length")
    p.add_argument("--fee", type=float, default=0.0, help="proportional fee per leg")
    p.add_argument("--solver", default="simulated_bifurcation", choices=available_solvers())
    p.set_defaults(func=cmd_arbitrage)

    p = sub.add_parser("benchmark", help="compare solvers against the proven optimum")
    p.add_argument("--vars", type=int, default=10)
    p.add_argument("--trials", type=int, default=10)
    p.set_defaults(func=cmd_benchmark)

    p = sub.add_parser("demo", help="run every application end to end")
    p.set_defaults(func=cmd_demo)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
