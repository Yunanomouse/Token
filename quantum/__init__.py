"""Quantum methods for trading and portfolio management.

A working implementation of the four applications where quantum mechanics has a
defensible role in finance -- with the classical baseline for each sitting right
next to it, because the comparison is the point.

======================  ===========================================  ==================
Module                  Application                                  Status today
======================  ===========================================  ==================
``portfolio``           constrained portfolio optimisation           strongest case
``risk``                VaR / CVaR by amplitude estimation           proven theory,
                                                                     hardware-limited
``pricing``             derivatives, incl. multi-asset baskets       same
``arbitrage``           cyclic arbitrage as an Ising ground state     deployable now,
                                                                     quantum-*inspired*
======================  ===========================================  ==================

The physics is real: :mod:`quantum.statevector` is an exact statevector
simulator, :mod:`quantum.amplitude` implements Grover-based amplitude estimation
with its provable quadratic speedup, and :mod:`quantum.solvers` runs QAOA,
simulated annealing and simulated bifurcation against the same Ising model.

What this package will not do is make money on a day trade.  Nothing here beats
a CPU today, and the module docstrings say where each limit bites -- the input
problem, circuit depth, and the six-order-of-magnitude latency gap that rules
gate-based hardware out of high-frequency execution.

Quick start
-----------
::

    from quantum.market import synthetic_prices
    from quantum.portfolio import PortfolioProblem, PortfolioConstraints, solve_portfolio

    market = synthetic_prices(n_assets=10, seed=1)
    problem = PortfolioProblem(
        market.expected_returns, market.covariance, market.tickers,
        risk_aversion=2.0,
        constraints=PortfolioConstraints(cardinality=4),
    )
    print(solve_portfolio(problem, solver="simulated_bifurcation").report())
"""

from __future__ import annotations

__version__ = "0.1.0"

from .amplitude import (
    AmplitudeEstimationResult,
    canonical_amplitude_estimation,
    classical_monte_carlo_error,
    estimate_amplitude,
    grover_operator,
    maximum_likelihood_amplitude_estimation,
)
from .arbitrage import (
    ArbitrageCycle,
    bellman_ford_negative_cycle,
    build_rate_matrix,
    find_arbitrage,
)
from .market import MarketData, load_price_csv, synthetic_prices
from .portfolio import (
    PortfolioConstraints,
    PortfolioProblem,
    PortfolioResult,
    exhaustive_cardinality,
    solve_portfolio,
    unconstrained_mean_variance,
)
from .preparation import GridDistribution, lognormal_grid, normal_grid, prepare_distribution
from .pricing import (
    OptionSpec,
    PricingResult,
    black_scholes_call,
    black_scholes_put,
    classical_monte_carlo_price,
    price_basket_option,
    price_european_option,
)
from .qubo import QUBO, IsingModel
from .risk import (
    RiskResult,
    classical_var_cvar,
    parametric_var,
    portfolio_loss_distribution,
    quantum_expected_shortfall,
    quantum_value_at_risk,
)
from .locality import LocalityReport, locality_report
from .solvers import SOLVERS, available_solvers, get_solver
from .storage import compare_codecs, load_compressed, save_compressed, shave_mantissa
from .subspace import HammingSubspace, SubspaceQAOAResult, dicke_state, subspace_qaoa
from .statevector import Circuit, estimate_memory, probabilities, sample, statevector

__all__ = [
    "__version__",
    # physics layer
    "Circuit", "statevector", "probabilities", "sample", "estimate_memory",
    "GridDistribution", "prepare_distribution", "lognormal_grid", "normal_grid",
    "grover_operator", "estimate_amplitude", "AmplitudeEstimationResult",
    "canonical_amplitude_estimation", "maximum_likelihood_amplitude_estimation",
    "classical_monte_carlo_error",
    # optimisation layer
    "QUBO", "IsingModel", "get_solver", "available_solvers", "SOLVERS",
    # applications
    "MarketData", "synthetic_prices", "load_price_csv",
    "PortfolioProblem", "PortfolioConstraints", "PortfolioResult", "solve_portfolio",
    "unconstrained_mean_variance", "exhaustive_cardinality",
    "OptionSpec", "PricingResult", "price_european_option", "price_basket_option",
    "black_scholes_call", "black_scholes_put", "classical_monte_carlo_price",
    "RiskResult", "portfolio_loss_distribution", "quantum_value_at_risk",
    "quantum_expected_shortfall", "classical_var_cvar", "parametric_var",
    "ArbitrageCycle", "find_arbitrage", "build_rate_matrix",
    "bellman_ford_negative_cycle",
    # memory
    "HammingSubspace", "SubspaceQAOAResult", "subspace_qaoa", "dicke_state",
    "LocalityReport", "locality_report",
    "save_compressed", "load_compressed", "compare_codecs", "shave_mantissa",
]
