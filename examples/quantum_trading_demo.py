#!/usr/bin/env python3
"""End-to-end walkthrough of the quantum trading package.

Runs all four applications and prints the classical baseline beside each result.

    python3 examples/quantum_trading_demo.py
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from quantum.amplitude import classical_monte_carlo_error  # noqa: E402
from quantum.arbitrage import bellman_ford_negative_cycle, build_rate_matrix, find_arbitrage  # noqa: E402
from quantum.market import synthetic_prices  # noqa: E402
from quantum.portfolio import (  # noqa: E402
    PortfolioConstraints,
    PortfolioProblem,
    exhaustive_cardinality,
    solve_portfolio,
    unconstrained_mean_variance,
)
from quantum.pricing import OptionSpec, classical_monte_carlo_price, price_european_option  # noqa: E402
from quantum.risk import portfolio_loss_distribution, quantum_expected_shortfall, quantum_value_at_risk  # noqa: E402
from quantum.solvers import get_solver  # noqa: E402


def section(title: str) -> None:
    print(f"\n{'=' * 70}\n{title}\n{'=' * 70}")


def demo_portfolio() -> None:
    section("1. Constrained portfolio optimisation  (the strongest case)")
    market = synthetic_prices(n_assets=10, n_days=756, seed=11)
    print(market.summary())

    cardinality = 4
    problem = PortfolioProblem(
        market.expected_returns, market.covariance, market.tickers,
        risk_aversion=2.0,
        constraints=PortfolioConstraints(cardinality=cardinality),
    )
    qubo = problem.to_qubo()
    print(f"\ncompiled to a {qubo.n_vars}-variable QUBO "
          f"(penalty {qubo.metadata['penalties']['cardinality']:.4f})")

    mask, optimal = exhaustive_cardinality(
        market.expected_returns, market.covariance, cardinality, 2.0
    )
    truth = sorted(market.tickers[i] for i in np.nonzero(mask)[0])
    print(f"exhaustive optimum: objective {optimal:.6f}  picks {truth}\n")

    print(f"{'solver':<26}{'objective':>12}{'time':>10}   matches optimum")
    print("-" * 66)
    for name in ("exact", "simulated_annealing", "simulated_bifurcation", "qaoa"):
        kwargs = {"rng": np.random.default_rng(0)}
        if name == "qaoa":
            kwargs.update(p=3, n_starts=4, max_iter=150)
        result = solve_portfolio(problem, solver=name, **kwargs)
        matched = sorted(result.holdings) == truth
        print(f"{name:<26}{result.objective:>12.6f}"
              f"{result.solver_result.runtime_seconds:>9.3f}s   {'yes' if matched else 'NO'}")

    weights = unconstrained_mean_variance(market.expected_returns, market.covariance, 2.0, True)
    ret = float(market.expected_returns @ weights)
    vol = math.sqrt(max(float(weights @ market.covariance @ weights), 0.0))
    print(f"\nunconstrained Markowitz (closed form, no constraints): "
          f"return {ret:.2%}, vol {vol:.2%}")
    print("-> convex and instant. The cardinality constraint is what makes it hard.")


def demo_sector_caps() -> None:
    section("2. Sector caps and integer lots  (where problem width comes from)")
    market = synthetic_prices(n_assets=10, n_days=756, seed=11)
    sectors = ["tech"] * 4 + ["energy"] * 3 + ["fin"] * 3
    problem = PortfolioProblem(
        market.expected_returns, market.covariance, market.tickers,
        risk_aversion=3.0,
        constraints=PortfolioConstraints(
            sectors=sectors, sector_caps={"tech": 0.40, "energy": 0.35}, max_weight=0.35
        ),
        encoding="lots", n_lot_bits=3,
    )
    qubo = problem.to_qubo()
    print(f"decision variables : {qubo.metadata['n_decision_vars']} (10 assets x 3 lot bits)")
    print(f"slack variables    : {qubo.metadata['n_slack']} (2 sector caps x 3 bits)")
    print(f"total QUBO width   : {qubo.n_vars}")
    print(f"lot grid           : {np.round(problem.lot_grid(), 4).tolist()}\n")

    result = solve_portfolio(
        problem, solver="sb", n_steps=1500, n_trajectories=128, rng=np.random.default_rng(1)
    )
    print(result.report())
    for sector in ("tech", "energy", "fin"):
        mask = np.array([s == sector for s in sectors])
        print(f"  {sector:<8} exposure {float(result.weights[mask].sum()):.2%}")


def demo_pricing() -> None:
    section("3. Option pricing by amplitude estimation")
    spec = OptionSpec(spot=100.0, strike=105.0, rate=0.03, volatility=0.20,
                      maturity=1.0, option="call")
    result = price_european_option(
        spec, n_qubits=8, n_sigma=5.0, c_approx=0.15, n_powers=8,
        shots_per_power=4096, bias_correction=True, rng=np.random.default_rng(3),
    )
    print(f"quantum price      : {result.price:.6f}")
    print(f"Black-Scholes      : {result.analytic_price:.6f}")
    print(f"exact on this grid : {result.discretised_price:.6f}")
    print(f"  discretisation   : {result.discretisation_error:.6f}")
    print(f"  estimation       : {result.estimation_error:.6f}")
    res = result.detail["circuit_resources"]
    print(f"\ncircuit: {res['qubits']} qubits, {res['logical_gates']} logical gates, "
          f"~{res['estimated_elementary_gates']} elementary")

    print(f"relative error     : {result.relative_error:.4%}")
    mc, err = classical_monte_carlo_price(100.0, 105.0, 0.03, 0.20, 1.0,
                                          samples=result.amplitude.shots,
                                          rng=np.random.default_rng(1))
    print(f"classical MC at equal shots: {mc:.6f} +/- {err:.6f}")

    print("\nTruncation vs resolution (discretisation error):")
    print(f"{'qubits':>8}{'n_sigma=3':>12}{'n_sigma=5':>12}")
    for nq in (5, 6, 7, 8):
        row = [
            price_european_option(spec, n_qubits=nq, n_sigma=ns, n_powers=2,
                                  shots_per_power=16, rng=np.random.default_rng(0)
                                  ).discretisation_error
            for ns in (3.0, 5.0)
        ]
        print(f"{nq:>8}{row[0]:>12.5f}{row[1]:>12.5f}")
    print("-> at n_sigma=3 the error plateaus; widen the domain, do not add qubits.")


def demo_risk() -> None:
    section("4. VaR and CVaR by amplitude estimation")
    market = synthetic_prices(n_assets=6, n_days=756, seed=2)
    weights = np.full(6, 1.0 / 6)
    dist = portfolio_loss_distribution(
        weights, market.expected_returns, market.covariance, n_qubits=6
    )
    print(f"{'confidence':>12}{'quantum VaR':>14}{'exact VaR':>12}"
          f"{'quantum CVaR':>15}{'exact CVaR':>12}")
    print("-" * 66)
    for confidence in (0.90, 0.95, 0.99):
        var = quantum_value_at_risk(dist, confidence, n_powers=5, shots_per_power=512,
                                    rng=np.random.default_rng(0))
        cvar = quantum_expected_shortfall(dist, confidence, var_index=var.detail["grid_index"],
                                          n_powers=5, shots_per_power=512,
                                          rng=np.random.default_rng(0))
        print(f"{confidence:>11.0%}{var.value:>14.5f}{var.classical_value:>12.5f}"
              f"{cvar.value:>15.5f}{cvar.classical_value:>12.5f}")
    print(f"\ngrid spacing {float(dist.values[1] - dist.values[0]):.6f} "
          f"sets the floor on quantile accuracy")


def demo_arbitrage() -> None:
    section("5. Cyclic arbitrage")
    currencies = ["USD", "EUR", "GBP", "JPY", "CHF"]
    rates = {
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
    for fee in (0.0, 0.0005, 0.001):
        matrix = build_rate_matrix(rates, currencies, fee=fee)
        cycle = bellman_ford_negative_cycle(matrix)
        result = find_arbitrage(matrix, currencies, cycle_length=3, solver="sb",
                                rng=np.random.default_rng(0))
        route = " -> ".join(result.named_path + [result.named_path[0]]) if result.path else "none"
        classical = " -> ".join([currencies[i] for i in cycle]) if cycle else "no negative cycle"
        print(f"fee {fee:.2%}  best 3-cycle {route:<26} {result.profit:+.4%}"
              f"   Bellman-Ford: {classical}")
    print("\n-> fees dominate. Bellman-Ford is exact and polynomial; use it unless")
    print("   cycle length, capacity or multi-cycle selection are constrained.")


def demo_amplitude_advantage() -> None:
    section("6. The quadratic speedup, measured")
    from quantum.amplitude import maximum_likelihood_amplitude_estimation
    from quantum.statevector import Circuit

    a = 0.3
    prep = Circuit(1).ry(2 * math.asin(math.sqrt(a)), 0)
    print(f"{'powers':>8}{'estimate':>12}{'AE error':>12}"
          f"{'classical SE':>14}{'oracle calls':>14}")
    print("-" * 60)
    for powers in (3, 5, 7, 9):
        result = maximum_likelihood_amplitude_estimation(
            prep, 0, n_powers=powers, shots_per_power=256, rng=np.random.default_rng(4)
        )
        print(f"{powers:>8}{result.estimate:>12.6f}{abs(result.estimate - a):>12.6f}"
              f"{classical_monte_carlo_error(a, result.shots):>14.6f}"
              f"{result.oracle_calls:>14,}")
    print("\n-> AE error falls as 1/N in oracle calls; Monte Carlo falls as 1/sqrt(N).")
    print("   That gap is the whole theoretical case -- and it is in oracle calls,")
    print("   not wall-clock. On real hardware today, the CPU still wins.")


def main() -> int:
    print("Quantum methods for trading -- worked demonstration")
    demo_portfolio()
    demo_sector_caps()
    demo_pricing()
    demo_risk()
    demo_arbitrage()
    demo_amplitude_advantage()
    print(f"\n{'=' * 70}")
    print("Every result above has its classical baseline beside it.")
    print("On today's hardware the classical column wins on wall-clock, every time.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
