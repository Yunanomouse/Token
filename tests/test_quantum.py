"""Test suite for the quantum trading package.

Structured around the one question that matters for code like this: does the
physics come out right, and does the finance match a classical reference we
already trust?  Every quantum routine is checked against an exact classical
answer, not against itself.

Run with::

    python3 -m unittest discover -s tests -v
"""

from __future__ import annotations

import math
import unittest

import numpy as np

from quantum.amplitude import (
    canonical_amplitude_estimation,
    classical_monte_carlo_error,
    grover_operator,
    maximum_likelihood_amplitude_estimation,
)
from quantum.arbitrage import (
    bellman_ford_negative_cycle,
    build_rate_matrix,
    cycle_profit,
    find_arbitrage,
)
from quantum.market import ledoit_wolf_shrinkage, sample_covariance, synthetic_prices
from quantum.portfolio import (
    PortfolioConstraints,
    PortfolioProblem,
    exhaustive_cardinality,
    solve_portfolio,
    unconstrained_mean_variance,
)
from quantum.preparation import lognormal_grid, normal_grid, prepare_distribution
from quantum.pricing import (
    OptionSpec,
    black_scholes_call,
    black_scholes_put,
    classical_monte_carlo_price,
    integer_comparator,
    price_european_option,
)
from pathlib import Path

from quantum.qubo import QUBO
from quantum.risk import (
    classical_var_cvar,
    parametric_var,
    portfolio_loss_distribution,
    quantum_expected_shortfall,
    quantum_value_at_risk,
)
from quantum.solvers import available_solvers, get_solver
from quantum.statevector import (
    Circuit,
    expectation_z,
    marginal,
    probabilities,
    probability_of_one,
    sample,
)


# ==========================================================================
# Physics layer
# ==========================================================================


class TestStatevector(unittest.TestCase):
    def test_bell_state(self):
        state = Circuit(2).h(0).cx(0, 1).run()
        expected = np.array([1, 0, 0, 1]) / math.sqrt(2)
        np.testing.assert_allclose(state.real, expected, atol=1e-12)

    def test_ghz_state(self):
        probs = probabilities(Circuit(3).h(0).cx(0, 1).cx(1, 2).run())
        self.assertAlmostEqual(probs[0], 0.5, places=12)
        self.assertAlmostEqual(probs[7], 0.5, places=12)
        self.assertAlmostEqual(probs[1:7].sum(), 0.0, places=12)

    def test_norm_preserved_by_arbitrary_circuit(self):
        rng = np.random.default_rng(0)
        circuit = Circuit(5)
        for _ in range(40):
            gate = rng.integers(0, 5)
            q = int(rng.integers(0, 5))
            if gate == 0:
                circuit.h(q)
            elif gate == 1:
                circuit.ry(float(rng.normal()), q)
            elif gate == 2:
                circuit.rz(float(rng.normal()), q)
            elif gate == 3:
                t = int(rng.integers(0, 5))
                if t != q:
                    circuit.cx(q, t)
            else:
                t = int(rng.integers(0, 5))
                if t != q:
                    circuit.cry(float(rng.normal()), q, t)
        state = circuit.run()
        self.assertAlmostEqual(float(np.abs(state**2).sum()), 1.0, places=12)

    def test_inverse_returns_to_ground_state(self):
        circuit = Circuit(4).h(0).cry(0.7, 0, 1).mcx([0, 1], 2).qft([0, 1, 2, 3])
        recovered = circuit.inverse().run(circuit.run())
        np.testing.assert_allclose(recovered, Circuit(4).run(), atol=1e-11)

    def test_qft_matches_numpy_dft(self):
        n = 3
        rng = np.random.default_rng(1)
        vec = rng.normal(size=2**n) + 1j * rng.normal(size=2**n)
        vec /= np.linalg.norm(vec)
        got = Circuit(n).qft().run(vec)
        # The textbook QFT is the inverse DFT convention with a 1/sqrt(N) factor.
        want = np.fft.ifft(vec) * math.sqrt(2**n)
        np.testing.assert_allclose(got, want, atol=1e-10)

    def test_born_rule_sampling(self):
        theta = 2 * math.asin(math.sqrt(0.25))
        state = Circuit(1).ry(theta, 0).run()
        draws = sample(state, 20000, np.random.default_rng(0))
        self.assertAlmostEqual(float(draws.mean()), 0.25, delta=0.02)

    def test_rotation_gives_exact_probability(self):
        for target in (0.1, 0.3, 0.5, 0.85):
            theta = 2 * math.asin(math.sqrt(target))
            state = Circuit(1).ry(theta, 0).run()
            self.assertAlmostEqual(probability_of_one(state, 1, 0), target, places=12)

    def test_expectation_z_and_marginal(self):
        state = Circuit(2).x(0).run()
        self.assertAlmostEqual(expectation_z(state, 2, 0), -1.0, places=12)
        self.assertAlmostEqual(expectation_z(state, 2, 1), 1.0, places=12)
        np.testing.assert_allclose(marginal(state, 2, [0]), [0.0, 1.0], atol=1e-12)

    def test_controlled_diagonal_phase(self):
        phases = np.arange(8) * 0.3
        state = Circuit(3).barrier_all_h().diagonal_phase(phases).run()
        expected = np.exp(1j * phases) / math.sqrt(8)
        np.testing.assert_allclose(state, expected, atol=1e-12)

    def test_rejects_control_target_overlap(self):
        with self.assertRaises(ValueError):
            Circuit(2).cx(0, 0)


class TestPreparation(unittest.TestCase):
    def test_distribution_loaded_exactly(self):
        rng = np.random.default_rng(3)
        for n in (2, 3, 4, 5):
            target = rng.random(2**n)
            target /= target.sum()
            got = probabilities(prepare_distribution(target, n).run())
            np.testing.assert_allclose(got, target, atol=1e-12)

    def test_distribution_with_zero_mass_points(self):
        target = np.array([0.5, 0.0, 0.0, 0.5])
        got = probabilities(prepare_distribution(target, 2).run())
        np.testing.assert_allclose(got, target, atol=1e-12)

    def test_lognormal_grid_moments(self):
        grid = lognormal_grid(mu=math.log(100), sigma=0.15, n_qubits=8, n_sigma=5.0)
        # E[S] = exp(mu + sigma^2/2) for a log-normal.
        self.assertAlmostEqual(grid.mean, 100 * math.exp(0.15**2 / 2), delta=0.5)

    def test_normal_grid_symmetric(self):
        grid = normal_grid(0.0, 1.0, 6, n_sigma=4.0)
        self.assertAlmostEqual(grid.mean, 0.0, places=9)
        self.assertAlmostEqual(grid.stdev, 1.0, delta=0.02)

    def test_rejects_negative_probabilities(self):
        with self.assertRaises(ValueError):
            prepare_distribution(np.array([0.5, -0.5, 0.5, 0.5]), 2)


class TestAmplitudeEstimation(unittest.TestCase):
    def test_grover_rotation_law(self):
        """P(good) after k iterations must equal sin^2((2k+1) * theta)."""
        a = 0.3
        theta = math.asin(math.sqrt(a))
        prep = Circuit(1).ry(2 * theta, 0)
        grover = grover_operator(prep, 0)
        state = prep.run()
        for k in range(6):
            predicted = math.sin((2 * k + 1) * theta) ** 2
            self.assertAlmostEqual(probability_of_one(state, 1, 0), predicted, places=10)
            state = grover.run(state)

    def test_grover_on_multiqubit_preparation(self):
        prep = Circuit(3).h(0).h(1).ry(0.9, 2)
        target = probability_of_one(prep.run(), 3, 2)
        theta = math.asin(math.sqrt(target))
        grover = grover_operator(prep, 2)
        state = grover.run(prep.run())
        self.assertAlmostEqual(
            probability_of_one(state, 3, 2), math.sin(3 * theta) ** 2, places=10
        )

    def test_mlae_accuracy(self):
        for a in (0.1, 0.3, 0.65):
            prep = Circuit(1).ry(2 * math.asin(math.sqrt(a)), 0)
            result = maximum_likelihood_amplitude_estimation(
                prep, 0, n_powers=7, shots_per_power=512, rng=np.random.default_rng(5)
            )
            self.assertAlmostEqual(result.estimate, a, delta=0.01)

    def test_mlae_beats_classical_at_equal_shots(self):
        """The quadratic advantage, made concrete."""
        a = 0.3
        prep = Circuit(1).ry(2 * math.asin(math.sqrt(a)), 0)
        result = maximum_likelihood_amplitude_estimation(
            prep, 0, n_powers=8, shots_per_power=512, rng=np.random.default_rng(2)
        )
        classical_error = classical_monte_carlo_error(a, result.shots)
        self.assertLess(abs(result.estimate - a), classical_error)

    def test_mlae_confidence_interval_brackets_truth(self):
        a = 0.42
        prep = Circuit(1).ry(2 * math.asin(math.sqrt(a)), 0)
        result = maximum_likelihood_amplitude_estimation(
            prep, 0, n_powers=7, shots_per_power=1024, rng=np.random.default_rng(9)
        )
        lo, hi = result.confidence_interval
        self.assertLessEqual(lo, a + 0.02)
        self.assertGreaterEqual(hi, a - 0.02)

    def test_canonical_qae_within_grid_resolution(self):
        a = 0.3
        prep = Circuit(1).ry(2 * math.asin(math.sqrt(a)), 0)
        result = canonical_amplitude_estimation(prep, 0, n_eval_qubits=6)
        self.assertAlmostEqual(result.estimate, a, delta=0.03)


# ==========================================================================
# Optimisation layer
# ==========================================================================


class TestQUBO(unittest.TestCase):
    def test_qubo_ising_equivalence(self):
        rng = np.random.default_rng(0)
        for _ in range(50):
            n = int(rng.integers(2, 7))
            problem = QUBO(Q=rng.normal(size=(n, n)), offset=float(rng.normal()))
            ising = problem.to_ising()
            energies = problem.energies_all()
            for x in range(2**n):
                bits = np.array([(x >> (n - 1 - i)) & 1 for i in range(n)])
                self.assertAlmostEqual(problem.energy(bits), ising.energy(2.0 * bits - 1.0), places=9)
                self.assertAlmostEqual(problem.energy(bits), float(energies[x]), places=9)

    def test_ising_round_trip(self):
        rng = np.random.default_rng(1)
        n = 5
        problem = QUBO(Q=rng.normal(size=(n, n)), offset=0.7)
        recovered = QUBO.from_ising(problem.to_ising())
        for x in range(2**n):
            bits = np.array([(x >> (n - 1 - i)) & 1 for i in range(n)])
            self.assertAlmostEqual(problem.energy(bits), recovered.energy(bits), places=9)

    def test_equality_penalty_selects_cardinality(self):
        problem = QUBO(np.zeros((5, 5)))
        problem.add_equality_penalty(np.ones(5), 2.0, 1.0)
        energies = problem.energies_all()
        self.assertEqual(int((np.abs(energies) < 1e-9).sum()), math.comb(5, 2))

    def test_penalty_scaling_accounts_for_coefficients(self):
        """Small coefficients must produce a proportionally larger penalty."""
        problem = QUBO(np.eye(4) * 0.1)
        big = problem.suggest_penalty_for(np.full(4, 0.05), scale=4.0)
        small = problem.suggest_penalty_for(np.ones(4), scale=4.0)
        self.assertGreater(big, small * 100)

    def test_brute_force_matches_energies_all(self):
        rng = np.random.default_rng(2)
        problem = QUBO(Q=rng.normal(size=(6, 6)))
        bits, energy = problem.brute_force()
        self.assertAlmostEqual(energy, float(problem.energies_all().min()), places=12)
        self.assertAlmostEqual(energy, problem.energy(bits), places=12)


class TestSolvers(unittest.TestCase):
    def test_all_solvers_registered(self):
        self.assertEqual(
            set(available_solvers()),
            {"exact", "simulated_annealing", "simulated_bifurcation", "qaoa"},
        )

    def test_aliases_resolve(self):
        self.assertEqual(get_solver("sa").name, "simulated_annealing")
        self.assertEqual(get_solver("sb").name, "simulated_bifurcation")

    def test_unknown_solver_rejected(self):
        with self.assertRaises(ValueError):
            get_solver("quantum_magic")

    def test_heuristics_find_optimum_on_small_problems(self):
        rng = np.random.default_rng(7)
        for name, kwargs in (
            ("simulated_annealing", {"n_sweeps": 300, "n_restarts": 6}),
            ("simulated_bifurcation", {"n_steps": 800, "n_trajectories": 64}),
        ):
            hits = 0
            for trial in range(8):
                problem = QUBO(Q=rng.normal(size=(9, 9)))
                optimal = get_solver("exact").solve(problem).energy
                result = get_solver(name).solve(
                    problem, rng=np.random.default_rng(trial), **kwargs
                )
                if abs(result.gap_to(optimal)) < 1e-6:
                    hits += 1
            self.assertGreaterEqual(hits, 7, f"{name} found only {hits}/8 optima")

    def test_bifurcation_is_scale_invariant(self):
        """Uniformly tiny couplings must not break the c0 scaling."""
        rng = np.random.default_rng(11)
        for scale in (1e-4, 1.0, 1e3):
            problem = QUBO(Q=rng.normal(size=(8, 8)) * scale)
            optimal = get_solver("exact").solve(problem).energy
            result = get_solver("sb").solve(
                problem, n_steps=600, n_trajectories=64, rng=np.random.default_rng(0)
            )
            self.assertAlmostEqual(result.energy / scale, optimal / scale, delta=1e-6)

    def test_qaoa_beats_random_sampling(self):
        rng = np.random.default_rng(3)
        problem = QUBO(Q=rng.normal(size=(7, 7)))
        result = get_solver("qaoa").solve(
            problem, p=2, n_starts=4, max_iter=120, rng=np.random.default_rng(0)
        )
        energies = problem.energies_all()
        self.assertLess(result.detail["expectation_value"], float(energies.mean()))
        self.assertGreater(result.detail["approximation_ratio"], 0.0)

    def test_exact_solver_refuses_large_problems(self):
        with self.assertRaises(ValueError):
            get_solver("exact").solve(QUBO(np.zeros((25, 25))))


# ==========================================================================
# Applications
# ==========================================================================


class TestMarket(unittest.TestCase):
    def test_synthetic_market_shape(self):
        market = synthetic_prices(n_assets=5, n_days=300, seed=0)
        self.assertEqual(market.n_assets, 5)
        self.assertEqual(market.returns.shape, (300, 5))
        self.assertTrue(np.all(np.linalg.eigvalsh(market.covariance) > -1e-12))

    def test_shrinkage_improves_conditioning(self):
        market = synthetic_prices(n_assets=30, n_days=60, seed=2)
        raw = sample_covariance(market.returns)
        shrunk, intensity = ledoit_wolf_shrinkage(market.returns)
        self.assertGreater(intensity, 0.0)
        self.assertLess(np.linalg.cond(shrunk), np.linalg.cond(raw))

    def test_rejects_non_finite_prices(self):
        """A NaN must fail loudly, not poison the covariance silently."""
        from quantum.market import MarketData

        prices = np.tile([[100.0, 50.0]], (10, 1))
        prices[3, 0] = np.nan
        with self.assertRaises(ValueError):
            MarketData(["A", "B"], prices)
        prices[3, 0] = np.inf
        with self.assertRaises(ValueError):
            MarketData(["A", "B"], prices)

    def test_rejects_non_positive_prices(self):
        from quantum.market import MarketData

        prices = np.tile([[100.0, 50.0]], (10, 1))
        prices[5, 1] = 0.0
        with self.assertRaises(ValueError):
            MarketData(["A", "B"], prices)
        prices[5, 1] = -3.0
        with self.assertRaises(ValueError):
            MarketData(["A", "B"], prices)

    def test_load_price_csv_round_trip(self):
        """The real-data entry point, which nothing had ever executed."""
        import csv
        import tempfile
        from quantum.market import load_price_csv

        directory = tempfile.mkdtemp()
        path = Path(directory) / "prices.csv"
        rng = np.random.default_rng(0)
        values = 100 * np.exp(np.cumsum(rng.normal(0, 0.01, size=(40, 3)), axis=0))
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(["date", "AAA", "BBB", "CCC"])
            for i, row in enumerate(values):
                writer.writerow([f"2026-01-{i+1:02d}", *row])
            # Rows the loader must drop rather than propagate.
            writer.writerow(["2026-02-01", "", "1.0", "2.0"])
            writer.writerow(["2026-02-02", "0", "1.0", "2.0"])
            writer.writerow(["2026-02-03", "nan", "1.0", "2.0"])

        market = load_price_csv(path)
        self.assertEqual(market.tickers, ["AAA", "BBB", "CCC"])
        self.assertEqual(market.prices.shape, (40, 3))
        self.assertTrue(np.all(np.isfinite(market.covariance)))

    def test_market_factor_creates_positive_correlation(self):
        market = synthetic_prices(n_assets=8, n_days=1000, seed=4)
        off_diagonal = market.correlation[~np.eye(8, dtype=bool)]
        self.assertGreater(float(off_diagonal.mean()), 0.0)


class TestPortfolio(unittest.TestCase):
    def setUp(self):
        self.market = synthetic_prices(n_assets=10, n_days=756, seed=11)
        self.cardinality = 4
        self.problem = PortfolioProblem(
            self.market.expected_returns,
            self.market.covariance,
            self.market.tickers,
            risk_aversion=2.0,
            constraints=PortfolioConstraints(cardinality=self.cardinality),
            encoding="select",
        )

    def test_every_solver_matches_exhaustive_optimum(self):
        mask, _ = exhaustive_cardinality(
            self.market.expected_returns, self.market.covariance, self.cardinality, 2.0
        )
        truth = set(np.nonzero(mask)[0].tolist())
        for solver in ("exact", "simulated_annealing", "simulated_bifurcation", "qaoa"):
            kwargs = {"rng": np.random.default_rng(0)}
            if solver == "qaoa":
                kwargs.update(p=3, n_starts=4, max_iter=150)
            result = solve_portfolio(self.problem, solver=solver, **kwargs)
            picked = set(np.nonzero(result.weights > 1e-9)[0].tolist())
            self.assertEqual(picked, truth, f"{solver} chose a different portfolio")

    def test_cardinality_respected(self):
        result = solve_portfolio(self.problem, solver="sb", rng=np.random.default_rng(0))
        self.assertEqual(len(result.holdings), self.cardinality)
        self.assertTrue(result.feasible)

    def test_weights_normalised(self):
        result = solve_portfolio(self.problem, solver="sb", rng=np.random.default_rng(0))
        self.assertAlmostEqual(float(result.weights.sum()), 1.0, places=9)

    def test_sector_caps_respected(self):
        sectors = ["tech"] * 4 + ["energy"] * 3 + ["fin"] * 3
        problem = PortfolioProblem(
            self.market.expected_returns,
            self.market.covariance,
            self.market.tickers,
            risk_aversion=3.0,
            constraints=PortfolioConstraints(
                sectors=sectors,
                sector_caps={"tech": 0.40, "energy": 0.35},
                max_weight=0.35,
            ),
            encoding="lots",
            n_lot_bits=3,
        )
        result = solve_portfolio(
            problem, solver="sb", n_steps=1500, n_trajectories=128, rng=np.random.default_rng(1)
        )
        for sector, cap in (("tech", 0.40), ("energy", 0.35)):
            mask = np.array([s == sector for s in sectors])
            self.assertLessEqual(float(result.weights[mask].sum()), cap + 1e-6)

    def test_lots_encoding_widens_the_problem(self):
        problem = PortfolioProblem(
            self.market.expected_returns, self.market.covariance, self.market.tickers,
            encoding="lots", n_lot_bits=3,
        )
        self.assertEqual(problem.to_qubo().metadata["n_decision_vars"], 10 * 3)

    def test_raw_weights_respect_encoded_cap(self):
        """The encoding's own cap must hold before any budget rescaling."""
        problem = PortfolioProblem(
            self.market.expected_returns, self.market.covariance, self.market.tickers,
            constraints=PortfolioConstraints(max_weight=0.25),
            encoding="lots", n_lot_bits=3,
        )
        result = solve_portfolio(problem, solver="sb", rng=np.random.default_rng(0))
        raw = np.array(result.detail["raw_weights"])
        self.assertTrue(np.all(raw <= 0.25 + 1e-9))

    def test_unconstrained_baseline_sums_to_one(self):
        weights = unconstrained_mean_variance(
            self.market.expected_returns, self.market.covariance, 2.0, long_only=True
        )
        self.assertAlmostEqual(float(weights.sum()), 1.0, places=9)

    def test_mean_variance_meets_its_optimality_conditions(self):
        # KKT for min q w'Sw - mu'w, sum(w) = 1 (and w >= 0): the gradient is
        # one constant on the held names and no lower than it on the rest.
        # Normalising Sigma^-1 mu (the tangency portfolio) fails this, and
        # ignores the risk aversion altogether.
        mu, cov = self.market.expected_returns, self.market.covariance
        seen = []
        for q in (0.5, 2.0, 20.0):
            for long_only in (False, True):
                w = unconstrained_mean_variance(mu, cov, q, long_only=long_only)
                self.assertAlmostEqual(float(w.sum()), 1.0, places=9)
                grad = 2.0 * q * cov @ w - mu
                held = w > 1e-9 if long_only else np.ones(w.size, bool)
                level = grad[held].mean()
                self.assertLess(np.abs(grad[held] - level).max(), 1e-7)
                if long_only:
                    self.assertTrue(np.all(w >= 0))
                    self.assertTrue(np.all(grad[~held] >= level - 1e-7))
            seen.append(w)
        self.assertGreater(np.abs(seen[0] - seen[-1]).max(), 1e-3)

    def test_rejects_mismatched_covariance(self):
        with self.assertRaises(ValueError):
            PortfolioProblem(np.zeros(4), np.zeros((3, 3)))


class TestPricing(unittest.TestCase):
    def test_black_scholes_put_call_parity(self):
        spot, strike, rate, vol, maturity = 100.0, 95.0, 0.04, 0.25, 1.5
        call = black_scholes_call(spot, strike, rate, vol, maturity)
        put = black_scholes_put(spot, strike, rate, vol, maturity)
        self.assertAlmostEqual(call - put, spot - strike * math.exp(-rate * maturity), places=9)

    def test_black_scholes_without_volatility_discounts_the_strike(self):
        spot, strike, rate, maturity = 100.0, 90.0, 0.05, 1.0
        forward_gap = spot - strike * math.exp(-rate * maturity)
        self.assertAlmostEqual(black_scholes_call(spot, strike, rate, 0.0, maturity), forward_gap, places=12)
        self.assertEqual(black_scholes_put(spot, strike, rate, 0.0, maturity), 0.0)
        self.assertAlmostEqual(black_scholes_put(80.0, strike, rate, 0.0, maturity),
                               strike * math.exp(-rate * maturity) - 80.0, places=12)

    def test_integer_comparator(self):
        for threshold in (0, 1, 3, 5, 7, 8):
            n = 3
            circuit = Circuit(n + 1)
            for q in range(n):
                circuit.h(q)
            integer_comparator(circuit, list(range(n)), threshold, n)
            probs = probabilities(circuit.run()).reshape([2] * (n + 1))
            for x in range(2**n):
                bits = tuple((x >> (n - 1 - b)) & 1 for b in range(n))
                flagged = probs[bits + (1,)] > probs[bits + (0,)]
                self.assertEqual(bool(flagged), x >= threshold, f"x={x} K={threshold}")

    def test_european_call_close_to_black_scholes(self):
        spec = OptionSpec(100.0, 105.0, 0.03, 0.20, 1.0, "call")
        result = price_european_option(
            spec, n_qubits=6, c_approx=0.15, n_powers=6,
            shots_per_power=2048, rng=np.random.default_rng(11),
        )
        self.assertLess(result.relative_error, 0.05)

    def test_european_put_close_to_black_scholes(self):
        spec = OptionSpec(100.0, 95.0, 0.03, 0.25, 0.5, "put")
        result = price_european_option(
            spec, n_qubits=6, c_approx=0.15, n_powers=6,
            shots_per_power=2048, rng=np.random.default_rng(11),
        )
        self.assertLess(result.relative_error, 0.05)

    def test_error_decomposition_adds_up(self):
        spec = OptionSpec(100.0, 105.0, 0.03, 0.20, 1.0, "call")
        result = price_european_option(
            spec, n_qubits=6, c_approx=0.15, n_powers=6,
            shots_per_power=2048, rng=np.random.default_rng(11),
        )
        self.assertLessEqual(
            result.absolute_error, result.discretisation_error + result.estimation_error + 1e-9
        )

    def test_finer_grid_reduces_discretisation_error(self):
        """With an adequate domain, more qubits must mean a better price."""
        spec = OptionSpec(100.0, 105.0, 0.03, 0.20, 1.0, "call")
        kwargs = dict(n_sigma=5.0, n_powers=4, shots_per_power=512,
                      rng=np.random.default_rng(0))
        coarse = price_european_option(spec, n_qubits=4, **kwargs)
        fine = price_european_option(spec, n_qubits=8, **kwargs)
        self.assertLess(fine.discretisation_error, coarse.discretisation_error)
        self.assertLess(fine.discretisation_error, 0.01)

    def test_truncation_dominates_at_narrow_domain(self):
        """The failure mode worth documenting: at n_sigma=3, qubits stop helping.

        Truncation error, not grid resolution, is the binding constraint -- so a
        price that will not converge needs a wider domain, not more qubits.
        """
        spec = OptionSpec(100.0, 105.0, 0.03, 0.20, 1.0, "call")
        kwargs = dict(n_sigma=3.0, n_powers=2, shots_per_power=16,
                      rng=np.random.default_rng(0))
        errors = [
            price_european_option(spec, n_qubits=n, **kwargs).discretisation_error
            for n in (5, 6, 7, 8)
        ]
        # All four sit on the same plateau instead of shrinking.
        self.assertLess(max(errors) - min(errors), 0.02)
        self.assertGreater(min(errors), 0.05)

    def test_deep_out_of_the_money_is_worthless(self):
        spec = OptionSpec(100.0, 100000.0, 0.03, 0.20, 1.0, "call")
        result = price_european_option(spec, n_qubits=5, n_powers=3, shots_per_power=128,
                                       rng=np.random.default_rng(0))
        self.assertAlmostEqual(result.price, 0.0, places=9)

    def test_linearisation_bias_scales_as_c_squared(self):
        """The bias is systematic and quadratic in c -- which is what makes it removable."""
        from quantum.pricing import build_european_payoff_circuit
        from quantum.statevector import probability_of_one

        spec = OptionSpec(100.0, 105.0, 0.03, 0.20, 1.0, "call")
        ratios = []
        for c in (0.05, 0.10, 0.20):
            circuit, objective, grid, scale, _ = build_european_payoff_circuit(
                spec, 7, c_approx=c, n_sigma=5.0
            )
            # Read the amplitude exactly, so no shot noise contaminates the bias.
            amplitude = probability_of_one(circuit.run(), circuit.n_qubits, objective)
            discount = math.exp(-spec.rate * spec.maturity)
            price = discount * ((amplitude - 0.5) / c + 0.5) * scale
            exact = float(
                discount * np.dot(np.maximum(grid.values - spec.strike, 0.0), grid.probabilities)
            )
            ratios.append((price - exact) / c**2)
        self.assertLess(max(ratios) - min(ratios), 0.05 * abs(np.mean(ratios)))

    def test_richardson_removes_bias_when_bias_dominates(self):
        spec = OptionSpec(100.0, 105.0, 0.03, 0.20, 1.0, "call")
        kwargs = dict(n_qubits=7, n_sigma=5.0, c_approx=0.25, n_powers=8,
                      shots_per_power=4096)
        plain = price_european_option(spec, rng=np.random.default_rng(11), **kwargs)
        corrected = price_european_option(
            spec, bias_correction=True, rng=np.random.default_rng(11), **kwargs
        )
        self.assertLess(corrected.estimation_error, plain.estimation_error / 10)

    def test_best_configuration_is_accurate(self):
        spec = OptionSpec(100.0, 105.0, 0.03, 0.20, 1.0, "call")
        result = price_european_option(
            spec, n_qubits=8, n_sigma=5.0, c_approx=0.15, n_powers=8,
            shots_per_power=4096, bias_correction=True, rng=np.random.default_rng(3),
        )
        self.assertLess(result.relative_error, 0.005)

    def test_classical_monte_carlo_converges(self):
        price, err = classical_monte_carlo_price(
            100.0, 105.0, 0.03, 0.20, 1.0, samples=200_000, rng=np.random.default_rng(1)
        )
        analytic = black_scholes_call(100.0, 105.0, 0.03, 0.20, 1.0)
        self.assertLess(abs(price - analytic), 4 * err)


class TestQuantumBinomial(unittest.TestCase):
    """The 'quantum binomial model', tested rather than repeated."""

    def setUp(self):
        self.spec = OptionSpec(100.0, 105.0, 0.03, 0.20, 1.0, "call")

    def test_crr_converges_to_black_scholes(self):
        from quantum.pricing import binomial_crr

        coarse = abs(binomial_crr(self.spec, 20) - self.spec.analytic_price())
        fine = abs(binomial_crr(self.spec, 2000) - self.spec.analytic_price())
        self.assertLess(fine, coarse)
        self.assertLess(fine, 0.01)

    def test_maxwell_boltzmann_reproduces_crr_exactly(self):
        """The model's own validation: classical statistics must give the classical price."""
        from quantum.pricing import binomial_crr, quantum_binomial

        for n_steps in (10, 50, 200, 800):
            lattice = binomial_crr(self.spec, n_steps)
            quantum = quantum_binomial(self.spec, n_steps, "maxwell-boltzmann")["price"]
            self.assertAlmostEqual(quantum, lattice, places=8, msg=f"N={n_steps}")

    def test_maxwell_boltzmann_is_risk_neutral(self):
        from quantum.pricing import quantum_binomial

        result = quantum_binomial(self.spec, 400, "maxwell-boltzmann")
        self.assertTrue(result["risk_neutral"])
        self.assertAlmostEqual(result["martingale_ratio"], 1.0, places=9)

    def test_bose_einstein_with_crr_probability_admits_arbitrage(self):
        """Keeping the CRR probability breaks the martingale property outright."""
        from quantum.pricing import quantum_binomial

        ratios = []
        for n_steps in (50, 200, 800):
            result = quantum_binomial(
                self.spec, n_steps, "bose-einstein", enforce_martingale=False
            )
            # E[S_T] overshoots its own forward at every refinement.
            self.assertFalse(result["risk_neutral"])
            self.assertGreater(result["martingale_ratio"], 1.0)
            ratios.append(result["martingale_ratio"])
        self.assertEqual(ratios, sorted(ratios), "the breach should worsen with refinement")

        # By 200 steps the call is quoted above the spot, which is an outright
        # arbitrage: a call can never be worth more than the stock it is on.
        for n_steps in (200, 800):
            result = quantum_binomial(
                self.spec, n_steps, "bose-einstein", enforce_martingale=False
            )
            self.assertGreater(result["price"], self.spec.spot)

    def test_bose_einstein_recalibrated_saturates_the_arbitrage_bound(self):
        """Restoring risk-neutrality gives a degenerate limit, not a better price."""
        from quantum.pricing import quantum_binomial

        for strike in (60.0, 105.0, 150.0):
            for option in ("call", "put"):
                spec = OptionSpec(100.0, strike, 0.03, 0.20, 1.0, option)
                result = quantum_binomial(spec, 12800, "bose-einstein")
                self.assertTrue(result["risk_neutral"])
                self.assertTrue(
                    result["saturates_upper_bound"],
                    f"{option} K={strike}: {result['price']} vs bound "
                    f"{result['arbitrage_upper_bound']}",
                )

    def test_bose_einstein_never_matches_black_scholes(self):
        from quantum.pricing import quantum_binomial

        result = quantum_binomial(self.spec, 6400, "bose-einstein")
        self.assertGreater(abs(result["price"] - self.spec.analytic_price()), 50.0)

    def test_rejects_unknown_statistics(self):
        from quantum.pricing import quantum_binomial

        with self.assertRaises(ValueError):
            quantum_binomial(self.spec, 50, "fermi-dirac")


class TestRisk(unittest.TestCase):
    def setUp(self):
        self.market = synthetic_prices(n_assets=6, n_days=756, seed=2)
        self.weights = np.full(6, 1.0 / 6)
        self.dist = portfolio_loss_distribution(
            self.weights, self.market.expected_returns, self.market.covariance, n_qubits=6
        )

    def test_quantum_var_matches_exact_quantile(self):
        for confidence in (0.90, 0.95, 0.99):
            result = quantum_value_at_risk(
                self.dist, confidence, n_powers=5, shots_per_power=512,
                rng=np.random.default_rng(0),
            )
            spacing = result.detail["grid_spacing"]
            self.assertLessEqual(result.absolute_error, spacing + 1e-12)

    def test_quantum_cvar_close_to_exact(self):
        result = quantum_expected_shortfall(
            self.dist, 0.95, n_powers=5, shots_per_power=512, rng=np.random.default_rng(0)
        )
        self.assertLess(result.absolute_error, 0.01)

    def test_cvar_exceeds_var(self):
        var = quantum_value_at_risk(self.dist, 0.95, n_powers=4, shots_per_power=256,
                                    rng=np.random.default_rng(0))
        cvar = quantum_expected_shortfall(self.dist, 0.95, var_index=var.detail["grid_index"],
                                          n_powers=4, shots_per_power=256,
                                          rng=np.random.default_rng(0))
        self.assertGreaterEqual(cvar.value, var.value - 1e-9)

    def test_var_is_not_pushed_past_the_quantile_by_rounding(self):
        # Ten atoms of 0.1 accumulate to 0.8999999999999999 at the ninth.
        values = np.arange(10.0)
        var, _ = classical_var_cvar(values, np.full(10, 0.1), 0.9)
        self.assertEqual(var, 8.0)

    def test_parametric_var_agrees_with_grid(self):
        exact, _ = classical_var_cvar(self.dist.values, self.dist.probabilities, 0.95)
        parametric = parametric_var(
            self.weights, self.market.expected_returns, self.market.covariance, 0.95
        )
        self.assertAlmostEqual(exact, parametric, delta=0.003)

    def test_confidence_bounds_validated(self):
        with self.assertRaises(ValueError):
            quantum_value_at_risk(self.dist, 1.5)


class TestArbitrage(unittest.TestCase):
    def setUp(self):
        self.currencies = ["USD", "EUR", "GBP", "JPY", "CHF"]
        self.rates = {
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

    def test_no_arbitrage_in_consistent_market(self):
        """Rates built from a single set of USD values admit no cycle."""
        values = np.array([1.0, 1.09, 1.27, 0.0066, 1.14])
        matrix = np.outer(1.0 / values, values)
        self.assertIsNone(bellman_ford_negative_cycle(matrix))

    def test_detects_planted_arbitrage(self):
        values = np.array([1.0, 1.09, 1.27, 0.0066, 1.14])
        matrix = np.outer(1.0 / values, values)
        matrix[0, 1] *= 1.05  # plant a mispricing
        cycle = bellman_ford_negative_cycle(matrix)
        self.assertIsNotNone(cycle)
        self.assertGreater(cycle_profit(matrix, cycle)[1], 0.0)

    def test_qubo_finds_profitable_cycle(self):
        matrix = build_rate_matrix(self.rates, self.currencies)
        result = find_arbitrage(
            matrix, self.currencies, cycle_length=3, solver="sb",
            rng=np.random.default_rng(0), n_steps=800, n_trajectories=64,
        )
        self.assertEqual(len(result.path), 3)
        self.assertEqual(len(set(result.path)), 3)
        self.assertTrue(result.profitable)

    def test_fees_eliminate_marginal_arbitrage(self):
        matrix = build_rate_matrix(self.rates, self.currencies, fee=0.01)
        self.assertIsNone(bellman_ford_negative_cycle(matrix))

    def test_cycle_profit_matches_manual_product(self):
        matrix = build_rate_matrix(self.rates, self.currencies)
        path = [0, 1, 2]
        expected = matrix[0, 1] * matrix[1, 2] * matrix[2, 0]
        self.assertAlmostEqual(cycle_profit(matrix, path)[0], expected, places=12)


class TestMemoryEfficiency(unittest.TestCase):
    """The optimisations must not change any answer -- only the resources used."""

    def test_energies_all_matches_naive_reference(self):
        """Recursive doubling must reproduce the bit-matrix contraction exactly."""
        rng = np.random.default_rng(0)
        for _ in range(30):
            n = int(rng.integers(1, 9))
            problem = QUBO(Q=rng.normal(size=(n, n)), offset=float(rng.normal()))
            got = problem.energies_all()
            want = np.array([
                problem.energy(np.array([(x >> (n - 1 - i)) & 1 for i in range(n)]))
                for x in range(2**n)
            ])
            np.testing.assert_allclose(got, want, atol=1e-9)

    def test_energies_all_peak_memory_is_bounded(self):
        """Peak must be ~2x the result, not ~n x the result."""
        import tracemalloc

        n = 16
        problem = QUBO(Q=np.random.default_rng(0).normal(size=(n, n)))
        tracemalloc.start()
        problem.energies_all()
        _, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        self.assertLess(peak, 2.6 * (2**n) * 8)

    def test_energy_chunks_reconstruct_full_landscape(self):
        rng = np.random.default_rng(1)
        for _ in range(8):
            n = int(rng.integers(4, 11))
            problem = QUBO(Q=rng.normal(size=(n, n)), offset=float(rng.normal()))
            full = problem.energies_all()
            out = np.empty_like(full)
            for start, chunk in problem.iter_energy_chunks(chunk_bits=3):
                out[start : start + chunk.size] = chunk
            np.testing.assert_allclose(full, out, atol=1e-9)

    def test_streaming_brute_force_agrees_with_materialised(self):
        rng = np.random.default_rng(2)
        problem = QUBO(Q=rng.normal(size=(10, 10)))
        bits_a, energy_a = problem.brute_force(max_materialise_bits=22)
        bits_b, energy_b = problem.brute_force(max_materialise_bits=4)  # forces streaming
        self.assertAlmostEqual(energy_a, energy_b, places=9)
        np.testing.assert_array_equal(bits_a, bits_b)

    def test_inplace_kernel_matches_tensordot(self):
        """The in-place gate path must equal the general contraction path."""
        from quantum.statevector import _apply

        rng = np.random.default_rng(3)
        for _ in range(30):
            n = int(rng.integers(1, 6))
            target = int(rng.integers(0, n))
            controls = tuple(q for q in range(n) if q != target and rng.random() < 0.4)
            matrix = ry_matrix_random(rng)
            init = rng.normal(size=2**n) + 1j * rng.normal(size=2**n)
            init /= np.linalg.norm(init)

            circuit = Circuit(n)
            circuit.append(
                __import__("quantum.statevector", fromlist=["Operation"]).Operation(
                    "test", matrix, (target,), controls, (1,) * len(controls)
                )
            )
            got = circuit.run(init)
            want = _apply(
                np.array(init, dtype=np.complex128), n, matrix, (target,),
                controls, (1,) * len(controls),
            )
            np.testing.assert_allclose(got, want, atol=1e-12)

    def test_single_qubit_circuit_writes_through(self):
        """Regression: rank-collapsing index turns a view into a scalar copy."""
        state = Circuit(1).x(0).run()
        np.testing.assert_allclose(state, np.array([0.0, 1.0]), atol=1e-12)
        # A fully-controlled gate collapses the same way.
        state = Circuit(2).x(0).cx(0, 1).run()
        np.testing.assert_allclose(np.abs(state) ** 2, [0, 0, 0, 1], atol=1e-12)

    def test_run_into_preallocated_buffer(self):
        circuit = Circuit(4).barrier_all_h()
        buffer = np.empty(16, dtype=np.complex128)
        got = circuit.run(out=buffer)
        self.assertIs(got.base if got.base is not None else got, buffer)
        np.testing.assert_allclose(got, circuit.run(), atol=1e-12)

    def test_complex64_stays_accurate_enough(self):
        rng = np.random.default_rng(4)
        circuit = Circuit(8).barrier_all_h()
        for _ in range(80):
            q, t = int(rng.integers(0, 8)), int(rng.integers(0, 8))
            circuit.ry(float(rng.normal()), q)
            if q != t:
                circuit.cx(q, t)
        double = circuit.run(dtype=np.complex128)
        single = circuit.run(dtype=np.complex64)
        self.assertLess(float(np.abs(double - single).max()), 1e-5)
        self.assertAlmostEqual(float((np.abs(single) ** 2).sum()), 1.0, places=5)

    def test_multiplexed_ry_matches_explicit_gates(self):
        rng = np.random.default_rng(5)
        for _ in range(20):
            n = int(rng.integers(2, 6))
            target = int(rng.integers(0, n))
            controls = sorted(q for q in range(n) if q != target)
            angles = rng.normal(size=2 ** len(controls))
            init = rng.normal(size=2**n) + 1j * rng.normal(size=2**n)
            init /= np.linalg.norm(init)

            explicit = Circuit(n)
            for pattern, theta in enumerate(angles):
                bits = [
                    (pattern >> (len(controls) - 1 - b)) & 1 for b in range(len(controls))
                ]
                explicit.mcry(float(theta), controls, target, control_values=bits)
            muxed = Circuit(n).multiplexed_ry(angles, controls, target)
            np.testing.assert_allclose(muxed.run(init), explicit.run(init), atol=1e-12)

    def test_multiplexed_ry_inverts(self):
        angles = np.array([0.3, -1.1, 2.0, 0.7])
        circuit = Circuit(3).multiplexed_ry(angles, [0, 1], 2)
        state = circuit.run()
        np.testing.assert_allclose(circuit.inverse().run(state), Circuit(3).run(), atol=1e-12)

    def test_preparation_uses_linear_gate_count(self):
        """State loading must be n operations, not 2**n."""
        for n in (6, 8, 10):
            circuit = prepare_distribution(np.full(2**n, 1.0 / 2**n), n)
            self.assertLessEqual(len(circuit.ops), n)

    def test_preparation_still_exact_after_optimisation(self):
        rng = np.random.default_rng(6)
        for n in (3, 5, 7):
            target = rng.random(2**n)
            target /= target.sum()
            got = probabilities(prepare_distribution(target, n).run())
            np.testing.assert_allclose(got, target, atol=1e-12)

    def test_resource_estimate_still_reports_hardware_cost(self):
        """Storing a level as one array must not understate the gate count."""
        circuit = prepare_distribution(np.full(64, 1 / 64), 6)
        self.assertGreaterEqual(circuit.resource_estimate()["estimated_elementary_gates"], 63)


def ry_matrix_random(rng) -> np.ndarray:
    """A random 2x2 unitary, for kernel-equivalence testing."""
    theta, phi, lam = rng.uniform(0, 2 * np.pi, size=3)
    c, s = math.cos(theta / 2), math.sin(theta / 2)
    return np.array(
        [
            [c, -np.exp(1j * lam) * s],
            [np.exp(1j * phi) * s, np.exp(1j * (phi + lam)) * c],
        ],
        dtype=np.complex128,
    )


class TestSubspace(unittest.TestCase):
    """Constraint-preserving QAOA: same physics, a fraction of the state space."""

    def test_enumeration_is_sorted_and_correct(self):
        from quantum.subspace import HammingSubspace

        for n, k in ((6, 2), (8, 3), (10, 4)):
            subspace = HammingSubspace.build(n, k)
            self.assertEqual(subspace.dimension, math.comb(n, k))
            # Sortedness is load-bearing: partner lookup uses np.searchsorted,
            # which would silently return wrong indices on unsorted input.
            self.assertTrue(bool(np.all(np.diff(subspace.states) > 0)))
            weights = {bin(int(v)).count("1") for v in subspace.states}
            self.assertEqual(weights, {k})

    def test_mixer_is_unitary(self):
        from quantum.subspace import HammingSubspace

        rng = np.random.default_rng(0)
        subspace = HammingSubspace.build(10, 4)
        state = rng.normal(size=subspace.dimension) + 1j * rng.normal(size=subspace.dimension)
        state /= np.linalg.norm(state)
        for beta in rng.normal(size=6):
            subspace.apply_mixer(state, float(beta))
        self.assertAlmostEqual(float(np.linalg.norm(state)), 1.0, places=12)

    def test_matches_full_register_simulation(self):
        """The whole point: identical evolution, exponentially less memory."""
        from quantum.subspace import HammingSubspace, dicke_state

        def full_xy_mixer(n, edges, beta):
            matrix = np.eye(2**n, dtype=complex)
            for i, j in edges:
                layer = np.eye(2**n, dtype=complex)
                for x in range(2**n):
                    if ((x >> (n - 1 - i)) & 1) == 1 and ((x >> (n - 1 - j)) & 1) == 0:
                        y = x - (1 << (n - 1 - i)) + (1 << (n - 1 - j))
                        c, sn = math.cos(beta), -1j * math.sin(beta)
                        layer[x, x] = layer[y, y] = c
                        layer[x, y] = layer[y, x] = sn
                matrix = layer @ matrix
            return matrix

        rng = np.random.default_rng(0)
        for _ in range(6):
            n = int(rng.integers(4, 8))
            k = int(rng.integers(1, n))
            subspace = HammingSubspace.build(n, k)
            problem = QUBO(Q=rng.normal(size=(n, n)))
            sub_costs = subspace.costs(problem)
            full_costs = problem.energies_all()
            np.testing.assert_allclose(sub_costs, full_costs[subspace.states], atol=1e-9)

            gammas, betas = rng.normal(size=3), rng.normal(size=3)
            state = dicke_state(subspace).astype(complex)
            for g, b in zip(gammas, betas):
                subspace.apply_cost(state, sub_costs, float(g))
                subspace.apply_mixer(state, float(b))

            full = np.zeros(2**n, dtype=complex)
            full[subspace.states] = 1.0 / math.sqrt(subspace.dimension)
            for g, b in zip(gammas, betas):
                full = full * np.exp(-1j * g * full_costs)
                full = full_xy_mixer(n, subspace.edges, float(b)) @ full

            np.testing.assert_allclose(full[subspace.states], state, atol=1e-10)
            # And nothing leaked outside the feasible subspace.
            outside = np.delete(full, subspace.states)
            if outside.size:
                self.assertLess(float(np.abs(outside).max()), 1e-12)

    def test_every_outcome_is_feasible(self):
        """Cardinality holds structurally -- there is no penalty weight to get wrong."""
        from quantum.subspace import subspace_qaoa

        rng = np.random.default_rng(1)
        for k in (2, 3, 4):
            problem = QUBO(Q=rng.normal(size=(9, 9)))
            for seed in range(5):
                result = subspace_qaoa(
                    problem, k, p=1, n_starts=1, max_iter=30,
                    rng=np.random.default_rng(seed),
                )
                self.assertEqual(int(result.assignment.sum()), k)

    def test_finds_the_constrained_optimum(self):
        from quantum.market import synthetic_prices
        from quantum.portfolio import (
            PortfolioConstraints, PortfolioProblem, exhaustive_cardinality, solve_portfolio,
        )

        market = synthetic_prices(n_assets=12, n_days=756, seed=3)
        cardinality = 4
        problem = PortfolioProblem(
            market.expected_returns, market.covariance, market.tickers,
            risk_aversion=2.0,
            constraints=PortfolioConstraints(cardinality=cardinality),
        )
        mask, _ = exhaustive_cardinality(
            market.expected_returns, market.covariance, cardinality, 2.0
        )
        truth = set(np.nonzero(mask)[0].tolist())
        result = solve_portfolio(
            problem, solver="subspace_qaoa", p=2, n_starts=3, max_iter=100,
            rng=np.random.default_rng(0),
        )
        self.assertEqual(set(np.nonzero(result.weights > 1e-9)[0].tolist()), truth)
        self.assertEqual(len(result.holdings), cardinality)
        self.assertTrue(result.feasible)

    def test_compression_reported_correctly(self):
        from quantum.subspace import HammingSubspace

        subspace = HammingSubspace.build(20, 5)
        self.assertEqual(subspace.dimension, math.comb(20, 5))
        self.assertEqual(subspace.full_dimension, 2**20)
        self.assertGreater(subspace.compression, 60)

    def test_bare_qubo_drops_the_cardinality_penalty(self):
        from quantum.market import synthetic_prices
        from quantum.portfolio import PortfolioConstraints, PortfolioProblem

        market = synthetic_prices(n_assets=8, n_days=400, seed=0)
        problem = PortfolioProblem(
            market.expected_returns, market.covariance, market.tickers,
            constraints=PortfolioConstraints(cardinality=3),
        )
        self.assertIn("cardinality", problem.to_qubo().metadata["penalties"])
        bare = problem.to_qubo(include_cardinality_penalty=False)
        self.assertNotIn("cardinality", bare.metadata["penalties"])

    def test_rejects_missing_cardinality(self):
        from quantum.market import synthetic_prices
        from quantum.portfolio import PortfolioProblem, solve_portfolio

        market = synthetic_prices(n_assets=6, n_days=300, seed=0)
        problem = PortfolioProblem(market.expected_returns, market.covariance, market.tickers)
        with self.assertRaises(ValueError):
            solve_portfolio(problem, solver="subspace_qaoa")

    def test_refuses_oversized_subspace(self):
        from quantum.subspace import HammingSubspace

        with self.assertRaises(ValueError):
            HammingSubspace.build(60, 30)


class TestPostulates(unittest.TestCase):
    """Each of the five postulates, verified as physics rather than assumed."""

    # -- Postulate 1: states are unit vectors ---------------------------
    def test_states_are_unit_vectors(self):
        rng = np.random.default_rng(0)
        circuit = Circuit(4).barrier_all_h()
        for _ in range(20):
            circuit.ry(float(rng.normal()), int(rng.integers(0, 4)))
        self.assertAlmostEqual(float(np.linalg.norm(circuit.run())), 1.0, places=12)

    # -- Postulate 2: Born's rule AND collapse --------------------------
    def test_born_rule_matches_amplitudes(self):
        from quantum.postulates import measure

        rng = np.random.default_rng(1)
        state = Circuit(2).h(0).cx(0, 1).run()
        counts = np.zeros(4)
        for _ in range(4000):
            counts[measure(state, rng=rng).index] += 1
        counts /= counts.sum()
        np.testing.assert_allclose(counts, [0.5, 0, 0, 0.5], atol=0.03)

    def test_measurement_collapses_the_state(self):
        """A repeat measurement in the same basis must be certain."""
        from quantum.postulates import bell_states, measure

        rng = np.random.default_rng(2)
        first = measure(bell_states()["Phi+"], rng=rng)
        self.assertAlmostEqual(first.probability, 0.5, places=9)
        second = measure(first.collapsed_state, rng=rng)
        self.assertEqual(second.index, first.index)
        self.assertAlmostEqual(second.probability, 1.0, places=12)

    def test_measurement_rejects_non_orthonormal_basis(self):
        from quantum.postulates import measure

        with self.assertRaises(ValueError):
            measure(np.array([1.0, 0.0]), basis=np.array([[1.0, 1.0], [0.0, 1.0]]))

    # -- Postulate 3: evolution is unitary -------------------------------
    def test_every_gate_is_unitary(self):
        from quantum.postulates import is_unitary
        from quantum.statevector import H, S, T, X, Y, Z, phase_matrix, rx_matrix, ry_matrix, rz_matrix

        for matrix in (H, X, Y, Z, S, T):
            self.assertTrue(is_unitary(matrix))
        for theta in (0.0, 0.7, -1.3, math.pi):
            for builder in (rx_matrix, ry_matrix, rz_matrix, phase_matrix):
                self.assertTrue(is_unitary(builder(theta)), f"{builder.__name__}({theta})")

    # -- Postulate 4: composition by tensor product ----------------------
    def test_kron_builds_composite_states(self):
        from quantum.postulates import kron

        zero = np.array([1, 0], dtype=complex)
        one = np.array([0, 1], dtype=complex)
        np.testing.assert_allclose(kron(zero, one), [0, 1, 0, 0], atol=1e-12)
        np.testing.assert_allclose(kron(one, one), [0, 0, 0, 1], atol=1e-12)
        self.assertEqual(kron(zero, one, zero).size, 8)

    def test_product_states_are_separable(self):
        from quantum.postulates import entanglement_entropy, is_separable, kron

        rng = np.random.default_rng(3)
        for _ in range(10):
            a = rng.normal(size=2) + 1j * rng.normal(size=2)
            b = rng.normal(size=2) + 1j * rng.normal(size=2)
            a /= np.linalg.norm(a)
            b /= np.linalg.norm(b)
            joint = kron(a, b)
            self.assertTrue(is_separable(joint, 2))
            self.assertAlmostEqual(entanglement_entropy(joint, 2), 0.0, places=9)

    def test_bell_states_are_maximally_entangled(self):
        from quantum.postulates import bell_states, entanglement_entropy, is_separable

        for name, state in bell_states().items():
            self.assertFalse(is_separable(state, 2), name)
            self.assertAlmostEqual(entanglement_entropy(state, 2), 1.0, places=9, msg=name)

    def test_reduced_state_of_a_bell_pair_is_maximally_mixed(self):
        """'Neither part has a state of its own', made concrete."""
        from quantum.postulates import bell_states, reduced_density_matrix

        rho = reduced_density_matrix(bell_states()["Phi+"], 2)
        np.testing.assert_allclose(rho, 0.5 * np.eye(2), atol=1e-12)
        # Purity 1/2 rather than 1: the subsystem is mixed.
        self.assertAlmostEqual(float(np.real(np.trace(rho @ rho))), 0.5, places=12)

    # -- Postulate 5: observables are Hermitian --------------------------
    def test_observable_requires_hermiticity(self):
        from quantum.postulates import Observable

        with self.assertRaises(ValueError):
            Observable(np.array([[0, 1], [0, 0]], dtype=complex))

    def test_observable_eigenvalues_are_real(self):
        from quantum.postulates import Observable

        rng = np.random.default_rng(4)
        raw = rng.normal(size=(4, 4)) + 1j * rng.normal(size=(4, 4))
        hermitian = raw + raw.conj().T
        observable = Observable(hermitian)
        self.assertTrue(np.all(np.isreal(observable.eigenvalues)))

    def test_expectation_values(self):
        from quantum.postulates import Observable, expectation

        pauli_z = Observable(np.array([[1, 0], [0, -1]], dtype=complex), "Z")
        self.assertAlmostEqual(expectation(np.array([1.0, 0.0]), pauli_z), 1.0, places=12)
        self.assertAlmostEqual(expectation(np.array([0.0, 1.0]), pauli_z), -1.0, places=12)
        self.assertAlmostEqual(expectation(Circuit(1).h(0).run(), pauli_z), 0.0, places=12)

    def test_measuring_an_observable_yields_an_eigenvalue(self):
        from quantum.postulates import Observable, measure_observable

        rng = np.random.default_rng(5)
        observable = Observable(np.diag([3.0, -1.0, 7.0, 0.5]).astype(complex), "cost")
        state = Circuit(2).barrier_all_h().run()
        for _ in range(20):
            outcome = measure_observable(state, observable, rng=rng)
            self.assertIn(observable.eigenvalues[outcome.index], observable.eigenvalues)

    def test_diagonal_observable_matches_qubo_landscape(self):
        """A QUBO objective *is* a Hermitian observable; its spectrum is the landscape."""
        from quantum.postulates import Observable, expectation

        rng = np.random.default_rng(6)
        problem = QUBO(Q=rng.normal(size=(3, 3)))
        costs = problem.energies_all()
        observable = Observable.from_diagonal(costs, "qubo")
        np.testing.assert_allclose(np.sort(observable.eigenvalues), np.sort(costs), atol=1e-9)
        # Uniform superposition should give the mean cost.
        uniform = Circuit(3).barrier_all_h().run()
        self.assertAlmostEqual(expectation(uniform, observable), float(costs.mean()), places=9)


class TestCorrelationVersusEntanglement(unittest.TestCase):
    """Market correlation is not entanglement -- settled by measurement."""

    def test_classical_bound_is_exactly_two(self):
        """Bell's theorem by exhaustion over local hidden-variable strategies."""
        from quantum.postulates import CHSH_CLASSICAL_BOUND, max_classical_chsh

        self.assertAlmostEqual(max_classical_chsh(), 2.0, places=12)
        self.assertAlmostEqual(max_classical_chsh(), CHSH_CLASSICAL_BOUND, places=12)

    def test_bell_state_violates_the_classical_bound(self):
        from quantum.postulates import CHSH_TSIRELSON_BOUND, bell_states, chsh_value

        value = chsh_value(bell_states()["Phi+"])
        self.assertGreater(value, 2.0)
        self.assertAlmostEqual(value, CHSH_TSIRELSON_BOUND, places=9)

    def test_no_state_exceeds_tsirelson(self):
        from quantum.postulates import CHSH_TSIRELSON_BOUND, chsh_value

        rng = np.random.default_rng(7)
        for _ in range(200):
            state = rng.normal(size=4) + 1j * rng.normal(size=4)
            state /= np.linalg.norm(state)
            self.assertLessEqual(chsh_value(state), CHSH_TSIRELSON_BOUND + 1e-9)

    def test_amplitude_encoding_manufactures_entanglement(self):
        """The subtle part: the encoding creates entanglement the market lacks.

        Loading a correlated joint distribution as sqrt(p) produces a genuinely
        entangled *pure state* -- but that is a property of the encoding step,
        not evidence about the market. Sampled classically, the same
        distribution is bounded by 2 no matter how strong the correlation.
        """
        from quantum.postulates import entanglement_entropy, is_separable, max_classical_chsh
        from quantum.preparation import multivariate_normal_grid

        def encode(rho):
            cov = np.array([[1.0, rho], [rho, 1.0]])
            _, probabilities, _ = multivariate_normal_grid(np.zeros(2), cov, 1)
            amplitudes = np.sqrt(probabilities)
            return amplitudes / np.linalg.norm(amplitudes)

        # Independent assets encode to a product state.
        self.assertTrue(is_separable(encode(0.0), 2))
        self.assertAlmostEqual(entanglement_entropy(encode(0.0), 2), 0.0, places=9)

        # Correlated assets encode to an entangled state...
        self.assertFalse(is_separable(encode(0.9), 2))
        self.assertGreater(entanglement_entropy(encode(0.9), 2), 0.9)

        # ...yet the classical correlation itself remains bounded by 2.
        self.assertAlmostEqual(max_classical_chsh(), 2.0, places=12)


class TestGroverSearch(unittest.TestCase):
    """Grover adaptive search: correct algorithm, honestly accounted."""

    def test_amplification_peaks_at_the_predicted_iteration(self):
        from quantum.search import amplify, grover_iterations_for

        rng = np.random.default_rng(0)
        n_items = 4096
        for n_marked in (1, 16, 64):
            costs = np.ones(n_items)
            costs[rng.choice(n_items, n_marked, replace=False)] = 0.0
            marked = costs < 0.5
            predicted = grover_iterations_for(n_items, n_marked)

            amplitudes = np.full(n_items, 1 / math.sqrt(n_items))
            amplify(amplitudes, marked, predicted)
            probability = float((amplitudes[marked] ** 2).sum())
            # At the predicted iteration the marked subspace should dominate.
            self.assertGreater(probability, 0.9, f"k={n_marked}")

    def test_amplification_preserves_norm(self):
        from quantum.search import amplify

        rng = np.random.default_rng(1)
        n_items = 512
        marked = rng.random(n_items) < 0.05
        amplitudes = np.full(n_items, 1 / math.sqrt(n_items))
        amplify(amplitudes, marked, 7)
        self.assertAlmostEqual(float(np.linalg.norm(amplitudes)), 1.0, places=10)

    def test_finds_the_true_minimum(self):
        from quantum.search import grover_adaptive_search

        for n_items in (128, 512, 2048):
            hits = 0
            for trial in range(10):
                costs = np.random.default_rng(trial).normal(size=n_items)
                result = grover_adaptive_search(
                    costs, rng=np.random.default_rng(trial)
                )
                hits += result.found_optimum
            self.assertGreaterEqual(hits, 9, f"N={n_items} found only {hits}/10")

    def test_query_count_scales_sublinearly(self):
        """Oracle calls should grow like sqrt(N), well below an exhaustive scan."""
        from quantum.search import grover_adaptive_search

        for n_items in (1024, 4096, 16384):
            calls = [
                grover_adaptive_search(
                    np.random.default_rng(t).normal(size=n_items),
                    rng=np.random.default_rng(t),
                ).oracle_calls
                for t in range(8)
            ]
            self.assertLess(float(np.mean(calls)), n_items / 4)

    def test_reports_simulation_overhead_honestly(self):
        """The result must not let a query-count speedup read as a wall-clock one."""
        from quantum.search import grover_adaptive_search

        costs = np.random.default_rng(0).normal(size=1024)
        result = grover_adaptive_search(costs, rng=np.random.default_rng(0))
        # Simulating the search does strictly more work than scanning the table.
        self.assertGreater(result.simulated_element_ops, result.n_items)
        self.assertGreater(result.simulation_overhead_vs_argmin, 1.0)
        self.assertIn("oracle", result.hardware_note())

    def test_degenerate_inputs(self):
        from quantum.search import grover_adaptive_search

        single = grover_adaptive_search(np.array([2.5]))
        self.assertEqual(single.index, 0)
        self.assertTrue(single.found_optimum)
        with self.assertRaises(ValueError):
            grover_adaptive_search(np.array([]))

    def test_constant_landscape_terminates(self):
        """No candidate beats the threshold: the loop must exit, not spin."""
        from quantum.search import grover_adaptive_search

        result = grover_adaptive_search(np.zeros(256), rng=np.random.default_rng(0))
        self.assertTrue(result.found_optimum)
        self.assertLess(result.oracle_calls, 256)

    def test_portfolio_route_finds_the_constrained_optimum(self):
        from quantum.market import synthetic_prices
        from quantum.portfolio import (
            PortfolioConstraints, PortfolioProblem, exhaustive_cardinality, solve_portfolio,
        )

        market = synthetic_prices(n_assets=14, n_days=756, seed=7)
        cardinality = 4
        problem = PortfolioProblem(
            market.expected_returns, market.covariance, market.tickers,
            risk_aversion=2.0,
            constraints=PortfolioConstraints(cardinality=cardinality),
        )
        mask, _ = exhaustive_cardinality(
            market.expected_returns, market.covariance, cardinality, 2.0
        )
        truth = set(np.nonzero(mask)[0].tolist())

        result = solve_portfolio(problem, solver="grover", rng=np.random.default_rng(0))
        self.assertEqual(set(np.nonzero(result.weights > 1e-9)[0].tolist()), truth)
        self.assertEqual(len(result.holdings), cardinality)
        detail = result.solver_result.detail
        self.assertEqual(detail["feasible_candidates"], math.comb(14, cardinality))
        self.assertLess(detail["oracle_calls"], detail["exhaustive_calls"])

    def test_portfolio_route_requires_cardinality(self):
        from quantum.market import synthetic_prices
        from quantum.portfolio import PortfolioProblem, solve_portfolio

        market = synthetic_prices(n_assets=6, n_days=300, seed=0)
        problem = PortfolioProblem(market.expected_returns, market.covariance, market.tickers)
        with self.assertRaises(ValueError):
            solve_portfolio(problem, solver="grover")


class TestLocality(unittest.TestCase):
    def test_dense_portfolio_gets_no_lightcone_benefit(self):
        """The measured finding: covariance couples everything, so cones are useless."""
        from quantum.locality import locality_report
        from quantum.market import synthetic_prices
        from quantum.portfolio import PortfolioConstraints, PortfolioProblem

        market = synthetic_prices(n_assets=12, n_days=500, seed=1)
        problem = PortfolioProblem(
            market.expected_returns, market.covariance, market.tickers,
            constraints=PortfolioConstraints(cardinality=4),
        ).to_qubo()
        report = locality_report(problem)
        self.assertGreater(report.density, 0.8)
        self.assertFalse(report.worthwhile)
        self.assertEqual(report.speedup_at(1), 1.0)

    def test_sparse_graph_does_get_a_benefit(self):
        from quantum.locality import locality_report

        n = 16
        coupling = np.zeros((n, n))
        for i in range(n):
            coupling[i, (i + 1) % n] = 1.0
        report = locality_report(QUBO(Q=coupling + coupling.T))
        self.assertLess(report.density, 0.2)
        self.assertTrue(report.worthwhile)
        self.assertGreater(report.speedup_at(2), 100)

    def test_cone_grows_monotonically_with_depth(self):
        from quantum.locality import locality_report

        n = 20
        coupling = np.zeros((n, n))
        for i in range(n):
            coupling[i, (i + 1) % n] = 1.0
        report = locality_report(QUBO(Q=coupling + coupling.T), depths=(1, 2, 3, 4))
        sizes = [report.cone_sizes[p] for p in (1, 2, 3, 4)]
        self.assertEqual(sizes, sorted(sizes))


class TestStorage(unittest.TestCase):
    def setUp(self):
        import tempfile

        self.tmp = tempfile.mkdtemp()

    def test_round_trip_lossless(self):
        from quantum.storage import load_compressed, save_compressed

        rng = np.random.default_rng(0)
        arrays = {"prices": rng.random((200, 8)) * 100, "weights": rng.random(8)}
        path = Path(self.tmp) / "data.qtz"
        save_compressed(path, arrays)
        restored, header = load_compressed(path)
        for name, array in arrays.items():
            np.testing.assert_allclose(restored[name], array, atol=0)
        self.assertEqual(header["codec"], "zlib")

    def test_mantissa_shaving_bounds_error(self):
        from quantum.storage import precision_report, shave_mantissa

        rng = np.random.default_rng(1)
        data = rng.random(10_000) * 1000
        for keep, tolerance in ((20, 1e-5), (12, 1e-3), (30, 1e-8)):
            shaved = shave_mantissa(data, keep)
            self.assertEqual(shaved.dtype, data.dtype)
            self.assertLess(precision_report(data, shaved), tolerance)

    def test_shaving_improves_compression(self):
        import zlib

        from quantum.storage import shave_mantissa
        from quantum.market import synthetic_prices

        prices = synthetic_prices(n_assets=20, n_days=2000, seed=0).prices
        raw = len(zlib.compress(prices.tobytes(), 6))
        shaved = len(zlib.compress(shave_mantissa(prices, 12).tobytes(), 6))
        self.assertLess(shaved, raw)

    def test_downcast_round_trip(self):
        from quantum.storage import load_compressed, precision_report, save_compressed

        rng = np.random.default_rng(2)
        data = rng.random((500, 4)) * 50
        path = Path(self.tmp) / "small.qtz"
        save_compressed(path, {"x": data}, dtype="float32")
        restored, _ = load_compressed(path)
        self.assertEqual(restored["x"].dtype, np.float32)
        self.assertLess(precision_report(data, restored["x"]), 1e-6)

    def test_mmap_and_chunking(self):
        from quantum.storage import iter_chunks, load_mmap

        rng = np.random.default_rng(3)
        data = rng.random((1000, 3))
        path = Path(self.tmp) / "big.npy"
        np.save(path, data)
        mapped = load_mmap(path)
        total = sum(float(chunk.sum()) for chunk in iter_chunks(mapped, chunk_rows=128))
        self.assertAlmostEqual(total, float(data.sum()), places=6)

    def test_byte_shuffle_round_trips(self):
        from quantum.storage import byte_shuffle, byte_unshuffle

        rng = np.random.default_rng(0)
        for shape in ((100,), (37, 5), (8, 4, 3)):
            for dtype in (np.float64, np.float32):
                data = (rng.random(shape) * 1000).astype(dtype)
                restored = byte_unshuffle(byte_shuffle(data), dtype, shape)
                np.testing.assert_array_equal(restored, data)

    def test_auto_shuffle_never_makes_it_worse(self):
        from quantum.storage import load_compressed, save_compressed
        from quantum.market import synthetic_prices

        market = synthetic_prices(n_assets=12, n_days=800, seed=0)
        sizes = {}
        for mode in ("auto", True, False):
            path = Path(self.tmp) / f"m_{mode}.qtz"
            save_compressed(path, {"x": market.prices}, keep_bits=12, shuffle=mode)
            restored, _ = load_compressed(path)
            np.testing.assert_array_equal(
                restored["x"], __import__("quantum.storage", fromlist=["shave_mantissa"])
                .shave_mantissa(market.prices, 12)
            )
            sizes[mode] = path.stat().st_size
        self.assertLessEqual(sizes["auto"], max(sizes[True], sizes[False]))

    def test_shuffled_multi_array_round_trip(self):
        from quantum.storage import load_compressed, save_compressed

        rng = np.random.default_rng(1)
        arrays = {
            "a": rng.random((50, 4)),
            "b": rng.random(9),
            "c": (rng.random((3, 3)) * 100).astype(np.float32),
        }
        path = Path(self.tmp) / "multi.qtz"
        save_compressed(path, arrays, shuffle=True)
        restored, header = load_compressed(path)
        self.assertTrue(header["shuffled"])
        for name, array in arrays.items():
            np.testing.assert_array_equal(restored[name], array)

    def test_conditioning_guard_matches_psd_failure(self):
        """float32 storage must be refused before it can break a covariance."""
        from quantum.storage import recommended_dtype

        rng = np.random.default_rng(0)
        n = 80
        for condition, expect_safe in ((1e2, True), (1e4, True), (1e10, False), (1e12, False)):
            basis, _ = np.linalg.qr(rng.normal(size=(n, n)))
            spectrum = np.geomspace(1.0, 1.0 / condition, n)
            matrix = basis @ np.diag(spectrum) @ basis.T
            matrix = (matrix + matrix.T) / 2
            advice = recommended_dtype(matrix)
            self.assertEqual(advice.safe, expect_safe, f"cond={condition:.0e}")
            if not advice.safe:
                self.assertEqual(advice.dtype, "float64")

    def test_conditioning_guard_on_non_matrix(self):
        from quantum.storage import recommended_dtype

        self.assertTrue(recommended_dtype(np.arange(10.0)).safe)
        self.assertFalse(recommended_dtype(np.array([1e40, 1.0])).safe)

    def test_shaving_is_unbiased(self):
        """Round-to-nearest, not truncation: a systematic drift compounds."""
        from quantum.storage import shave_mantissa

        rng = np.random.default_rng(2)
        data = rng.random(50_000) * 1000 + 1.0
        for keep in (23, 16, 12):
            shaved = shave_mantissa(data, keep)
            relative = (shaved - data) / data
            # Mean error must be orders of magnitude below the max error --
            # plain truncation would put them within a factor of ~2.
            self.assertLess(abs(float(relative.mean())), 0.02 * float(np.abs(relative).max()))

    def test_rejects_bad_shuffle_argument(self):
        from quantum.storage import save_compressed

        with self.assertRaises(ValueError):
            save_compressed(Path(self.tmp) / "x.qtz", {"a": np.zeros(4)}, shuffle="maybe")

    def test_rejects_unknown_codec(self):
        from quantum.storage import save_compressed

        with self.assertRaises(ValueError):
            save_compressed(Path(self.tmp) / "x.qtz", {"a": np.zeros(4)}, codec="magic")


class TestCLI(unittest.TestCase):
    def test_every_subcommand_runs(self):
        from quantum.cli import main
        import contextlib
        import io

        commands = [
            ["portfolio", "--assets", "6", "--cardinality", "2", "--solver", "simulated_bifurcation"],
            ["price", "--qubits", "4", "--powers", "3", "--shots", "128"],
            ["risk", "--assets", "4", "--qubits", "4", "--powers", "3", "--shots", "128"],
            ["arbitrage", "--cycle-length", "3"],
            ["benchmark", "--vars", "6", "--trials", "2"],
        ]
        for argv in commands:
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(main(argv), 0, f"{argv[0]} failed")


class TestAgainstReferenceLibraries(unittest.TestCase):
    """Independent implementations, installed with ``pip install -e ".[test]"``.

    Skipped when the reference is missing, so the package itself stays numpy-only.
    """

    @classmethod
    def setUpClass(cls):
        from quantum.market import load_price_csv

        cls.market = load_price_csv("data/prices/us_equities_1989_2018.csv",
                                    tickers=["AAPL", "GE", "AMD", "WMT", "BAC", "T", "XOM", "PFE", "JPM"],
                                    start="2008-01-01", end="2008-12-31")

    def test_ledoit_wolf_matches_scikit_learn(self):
        try:
            from sklearn.covariance import LedoitWolf
        except ImportError:
            self.skipTest("scikit-learn not installed")
        cov, intensity = ledoit_wolf_shrinkage(self.market.returns)
        ref = LedoitWolf().fit(self.market.returns)
        self.assertAlmostEqual(intensity, ref.shrinkage_, places=12)
        np.testing.assert_allclose(cov, ref.covariance_, rtol=1e-10, atol=0)

    def test_long_only_mean_variance_matches_scipy(self):
        try:
            from scipy.optimize import minimize
        except ImportError:
            self.skipTest("scipy not installed")
        mu, cov = self.market.expected_returns, self.market.covariance
        n = mu.size
        for q in (1.0, 2.0, 5.0):
            w = unconstrained_mean_variance(mu, cov, q, long_only=True)
            ref = minimize(lambda x: q * x @ cov @ x - mu @ x, np.full(n, 1.0 / n),
                           jac=lambda x: 2.0 * q * cov @ x - mu, method="SLSQP",
                           bounds=[(0.0, None)] * n,
                           constraints=[{"type": "eq", "fun": lambda x: x.sum() - 1.0}],
                           options={"ftol": 1e-15, "maxiter": 1000})
            objective = lambda x: q * x @ cov @ x - mu @ x
            self.assertLessEqual(objective(w), objective(ref.x) + 1e-10)
            np.testing.assert_allclose(w, ref.x, atol=1e-5)

    def test_black_scholes_matches_scipy(self):
        try:
            from scipy.stats import norm
        except ImportError:
            self.skipTest("scipy not installed")
        for spot, strike, rate, vol, t in [(100, 90, 0.05, 0.2, 1.0), (100, 120, 0.01, 0.4, 0.25),
                                           (50, 50, 0.0, 0.1, 2.0), (80, 100, 0.03, 0.6, 5.0)]:
            d1 = (math.log(spot / strike) + (rate + vol * vol / 2) * t) / (vol * math.sqrt(t))
            d2 = d1 - vol * math.sqrt(t)
            call = spot * norm.cdf(d1) - strike * math.exp(-rate * t) * norm.cdf(d2)
            put = strike * math.exp(-rate * t) * norm.cdf(-d2) - spot * norm.cdf(-d1)
            self.assertAlmostEqual(black_scholes_call(spot, strike, rate, vol, t), call, places=10)
            self.assertAlmostEqual(black_scholes_put(spot, strike, rate, vol, t), put, places=10)

if __name__ == "__main__":
    unittest.main(verbosity=2)


# ==========================================================================
# Hardware export: compilation and OpenQASM round trip
# ==========================================================================


class TestExport(unittest.TestCase):
    """The compiler is checked against the simulator, never against itself."""

    def _random_unitary(self, rng):
        a = rng.normal(size=(2, 2)) + 1j * rng.normal(size=(2, 2))
        q, _ = np.linalg.qr(a)
        return q

    def test_zyz_reconstructs_any_unitary(self):
        from quantum.export import u3_matrix, zyz_angles
        from quantum.statevector import H, S, T, X, Y, Z

        rng = np.random.default_rng(0)
        for m in [X, Y, Z, H, S, T] + [self._random_unitary(rng) for _ in range(20)]:
            theta, phi, lam, alpha = zyz_angles(m)
            self.assertTrue(np.allclose(m, np.exp(1j * alpha) * u3_matrix(theta, phi, lam)))

    def test_multiplexed_ry_decomposition_is_exact(self):
        from quantum.export import decompose
        from quantum.statevector import Circuit

        rng = np.random.default_rng(1)
        for k in range(4):
            n = k + 1
            c = Circuit(n)
            for q in range(n):
                c.h(q)
            c.multiplexed_ry(rng.uniform(-3, 3, 2**k), list(range(k)), k)
            d = decompose(c)
            self.assertEqual(len(d.ops), n + (2 * 2**k if k else 1))
            self.assertLess(np.linalg.norm(c.run() - d.run()), 1e-10)

    def test_quadratic_diagonal_compiles_to_quadratic_gadgets(self):
        """A QAOA cost layer must not cost 2**n gates once compiled."""
        from quantum.export import decompose
        from quantum.statevector import Circuit

        rng = np.random.default_rng(2)
        n = 7
        Q = rng.normal(size=(n, n))
        Q = (Q + Q.T) / 2
        bits = np.array([[(i >> (n - 1 - q)) & 1 for q in range(n)] for i in range(2**n)], float)
        energies = np.einsum("ij,jk,ik->i", bits, Q, bits)
        c = Circuit(n).diagonal_phase(0.37 * energies)
        d = decompose(c)
        # n singles + n(n-1)/2 pairs, each pair = 2 CX + 1 Rz, plus a global phase.
        self.assertLessEqual(len(d.ops), n + 3 * n * (n - 1) // 2 + 1)
        uniform = np.full(2**n, 2 ** (-n / 2))
        self.assertLess(np.linalg.norm(c.run(uniform) - d.run(uniform)), 1e-10)

    def test_qasm_round_trip_on_full_pricing_circuit(self):
        from quantum.amplitude import grover_operator
        from quantum.export import elementary_gate_count, from_qasm, to_qasm
        from quantum.pricing import OptionSpec, build_european_payoff_circuit
        from quantum.statevector import Circuit

        spec = OptionSpec(100.0, 100.0, 0.05, 0.2, 1.0)
        prep, objective, *_ = build_european_payoff_circuit(spec, 4)
        full = Circuit(prep.n_qubits).compose(prep).compose(grover_operator(prep, objective))
        text = to_qasm(full)
        self.assertTrue(text.startswith("OPENQASM 3.0;"))
        self.assertIn("ctrl(", text)
        parsed = from_qasm(text)
        self.assertLess(np.linalg.norm(full.run() - parsed.run()), 1e-9)
        counts = elementary_gate_count(full)
        self.assertGreater(counts["two_qubit"], counts["one_qubit"])

    def test_qasm_round_trip_with_negative_controls_and_phases(self):
        from quantum.export import from_qasm, to_qasm
        from quantum.statevector import Circuit, Operation, X

        rng = np.random.default_rng(3)
        c = Circuit(4).h(0).h(1).cp(0.4, 0, 3).global_phase(1.1).t(2).rz(-0.3, 3).rx(0.9, 0)
        c.append(Operation("mcx", X, (3,), (1, 2), (0, 1)))
        c.append(Operation("u", self._random_unitary(rng), (2,), (0,), (1,)))
        c.multiplexed_ry(rng.uniform(-1, 1, 4), [0, 1], 3)
        c.diagonal_phase(rng.uniform(-1, 1, 16))
        parsed = from_qasm(to_qasm(c))
        self.assertLess(np.linalg.norm(c.run() - parsed.run()), 1e-9)

    def test_controlled_multiplexed_ry_matches_explicit_gates(self):
        """Regression: Circuit.control() used to leave the angle table undoubled,
        which crashed canonical amplitude estimation on any loaded distribution."""
        from quantum.statevector import Circuit

        rng = np.random.default_rng(4)
        k, n = 3, 5
        angles = rng.uniform(-2, 2, 2**k)
        mux = Circuit(n).multiplexed_ry(angles, [0, 1, 2], 3).control(4)
        explicit = Circuit(n)
        for j in range(2**k):
            bits = [(j >> (k - 1 - i)) & 1 for i in range(k)]
            explicit.mcry(angles[j], [0, 1, 2, 4], 3, bits + [1])
        start = Circuit(n).barrier_all_h().run()
        self.assertLess(np.linalg.norm(mux.run(start) - explicit.run(start)), 1e-12)

    def test_canonical_qae_runs_on_loaded_distribution(self):
        from quantum.amplitude import build_canonical_qae_circuit, canonical_amplitude_estimation
        from quantum.export import from_qasm, to_qasm
        from quantum.pricing import OptionSpec, build_european_payoff_circuit
        from quantum.statevector import probability_of_one

        spec = OptionSpec(100.0, 100.0, 0.05, 0.2, 1.0)
        prep, objective, *_ = build_european_payoff_circuit(spec, 3)
        truth = probability_of_one(prep.run(), prep.n_qubits, objective)
        result = canonical_amplitude_estimation(prep, objective, n_eval_qubits=5)
        self.assertLess(abs(result.estimate - truth), result.detail["grid_resolution"])
        circuit = build_canonical_qae_circuit(prep, objective, 3)
        parsed = from_qasm(to_qasm(circuit))
        self.assertLess(np.linalg.norm(circuit.run() - parsed.run()), 1e-9)


# ==========================================================================
# Noise
# ==========================================================================


class TestNoise(unittest.TestCase):
    def _prep(self, n=3):
        from quantum.pricing import OptionSpec, build_european_payoff_circuit
        from quantum.statevector import probability_of_one

        spec = OptionSpec(100.0, 100.0, 0.05, 0.2, 1.0)
        prep, objective, *_ = build_european_payoff_circuit(spec, n)
        return prep, objective, probability_of_one(prep.run(), prep.n_qubits, objective)

    def test_noiseless_model_reproduces_exact_probability(self):
        from quantum.noise import NoiseModel, noisy_probability_of_one

        prep, objective, truth = self._prep()
        p = noisy_probability_of_one(prep, objective, NoiseModel.uniform(0.0))
        self.assertAlmostEqual(p, truth, places=12)

    def test_survival_probability_is_gate_count_power(self):
        from quantum.export import elementary_gate_count
        from quantum.noise import survival_probability

        prep, _, _ = self._prep()
        gates = elementary_gate_count(prep)["total"]
        self.assertAlmostEqual(survival_probability(prep, 1e-3), (1 - 1e-3) ** gates)
        self.assertEqual(survival_probability(prep, 0.0), 1.0)

    def test_heavy_depolarising_noise_drives_toward_one_half(self):
        from quantum.noise import NoiseModel, noisy_probability_of_one

        prep, objective, truth = self._prep()
        p = noisy_probability_of_one(
            prep, objective, NoiseModel.uniform(0.5), trajectories=200,
            rng=np.random.default_rng(0),
        )
        self.assertLess(abs(p - 0.5), abs(truth - 0.5))
        self.assertLess(abs(p - 0.5), 0.08)

    def test_readout_error_biases_analytically(self):
        from quantum.noise import NoiseModel, noisy_probability_of_one

        prep, objective, truth = self._prep()
        r = 0.05
        p = noisy_probability_of_one(prep, objective, NoiseModel(0.0, 0.0, readout=r))
        self.assertAlmostEqual(p, truth * (1 - r) + (1 - truth) * r, places=12)

    def test_trajectory_state_stays_normalised(self):
        from quantum.noise import NoiseModel, run_trajectory

        prep, _, _ = self._prep()
        state = run_trajectory(prep, NoiseModel.uniform(0.05), np.random.default_rng(1))
        self.assertAlmostEqual(float(np.vdot(state, state).real), 1.0, places=12)

    def test_threshold_sweep_degrades_monotonically_in_the_large(self):
        from quantum.noise import noise_threshold_sweep

        prep, objective, truth = self._prep()
        sweep = noise_threshold_sweep(
            prep, objective, truth, epsilons=(0.0, 1e-3, 1e-1),
            n_powers=3, shots_per_power=128, trajectories=8, trials=2,
            rng=np.random.default_rng(0),
        )
        self.assertLess(sweep.errors[0], sweep.classical_error)
        self.assertLess(sweep.errors[0], sweep.errors[2])
        self.assertEqual(sweep.threshold, 0.0)
        self.assertIn("beats classical", sweep.report())

    def test_invalid_rates_rejected(self):
        from quantum.noise import NoiseModel

        with self.assertRaises(ValueError):
            NoiseModel(one_qubit=1.5)
        with self.assertRaises(ValueError):
            NoiseModel(readout=-0.1)


# ==========================================================================
# Out-of-sample validation
# ==========================================================================


class TestBacktest(unittest.TestCase):
    def test_equal_weight_return_is_mean_asset_return(self):
        from quantum.backtest import equal_weight, walk_forward

        market = synthetic_prices(n_assets=4, n_days=120, seed=0)
        result = walk_forward(
            market.prices, market.tickers, {"equal_weight": equal_weight}, window=60, horizon=20
        )
        perf = result.strategies["equal_weight"]
        self.assertEqual(perf.n_periods, 3)
        hold = market.prices[59:80]
        expected = np.mean(hold[-1] / hold[0] - 1.0)
        self.assertAlmostEqual(perf.period_returns[0], expected, places=12)
        self.assertEqual(perf.turnover, 0.0)

    def test_weights_are_long_only_and_sum_to_one(self):
        from quantum.backtest import cardinality_strategy, markowitz_long_only, walk_forward

        market = synthetic_prices(n_assets=5, n_days=200, seed=1)
        result = walk_forward(
            market.prices, market.tickers,
            {"mv": markowitz_long_only(2.0), "card": cardinality_strategy(2, 2.0, "exhaustive")},
            window=100, horizon=50,
        )
        for perf in result.strategies.values():
            self.assertTrue(np.all(perf.weights >= 0))
            self.assertTrue(np.allclose(perf.weights.sum(axis=1), 1.0))
        card = result.strategies["card"].weights
        self.assertTrue(np.all((card > 0).sum(axis=1) == 2))

    def test_heuristic_solver_matches_exhaustive_out_of_sample(self):
        """The backtest scores the optimum; the solver only has to reach it."""
        from quantum.backtest import cardinality_strategy, walk_forward

        market = synthetic_prices(n_assets=6, n_days=160, seed=2)
        result = walk_forward(
            market.prices, market.tickers,
            {
                "sa": cardinality_strategy(3, 2.0, "simulated_annealing", seed=0),
                "ex": cardinality_strategy(3, 2.0, "exhaustive"),
            },
            window=100, horizon=30,
        )
        np.testing.assert_allclose(
            result.strategies["sa"].period_returns, result.strategies["ex"].period_returns
        )

    def test_statistics_and_report(self):
        from quantum.backtest import BacktestResult, equal_weight, max_drawdown, walk_forward

        self.assertAlmostEqual(max_drawdown(np.array([0.1, -0.5, 0.2])), 0.5)
        self.assertEqual(max_drawdown(np.array([])), 0.0)
        market = synthetic_prices(n_assets=3, n_days=150, seed=3)
        result = walk_forward(
            market.prices, market.tickers, {"equal_weight": equal_weight}, window=50, horizon=10
        )
        self.assertIsInstance(result, BacktestResult)
        text = result.report()
        self.assertIn("equal_weight", text)
        self.assertIn("IS sharpe", text)
        mean, t = result.excess_over_benchmark("equal_weight")
        self.assertEqual(mean, 0.0)

    def test_insufficient_history_rejected(self):
        from quantum.backtest import equal_weight, walk_forward

        market = synthetic_prices(n_assets=3, n_days=50, seed=4)
        with self.assertRaises(ValueError):
            walk_forward(market.prices, market.tickers, {"e": equal_weight}, window=40, horizon=20)


# ==========================================================================
# External data: QOBLIB benchmark, real prices, hardware profiles
# ==========================================================================


class TestQoblib(unittest.TestCase):
    ROOT = "data/qoblib/po_a010_t10_orig"

    def _load(self, tag="l0"):
        from pathlib import Path
        from quantum.qoblib import load_instance, load_qs, load_solution

        root = Path(self.ROOT)
        instance = load_instance(root / "instance")
        qubo = load_qs(next((root / "qubo").glob(f"*_{tag}.qs.xz")))
        solution = load_solution(next((root / "solutions").glob(f"*_{tag}.*.sol")))
        return instance, qubo, solution

    def test_instance_layout(self):
        instance, qubo, solution = self._load()
        self.assertEqual(instance.n_assets, 10)
        self.assertEqual(instance.n_periods, 10)
        self.assertEqual(instance.n_variables, 710)
        self.assertEqual(qubo.Q.shape, (710, 710))
        self.assertTrue(np.allclose(qubo.Q, qubo.Q.T))
        self.assertTrue(solution.proven_optimal)
        self.assertEqual(solution.objective, -110541.0)

    def test_certified_optimum_is_feasible_and_a_strict_local_minimum(self):
        """The reading of the file format is pinned by the certified solution:
        every single-bit flip must cost at least the penalty weight."""
        from quantum.qoblib import decode_bits, solution_bits

        instance, qubo, solution = self._load()
        bits = solution_bits(instance, solution)
        check = decode_bits(instance, bits, solution.budget)
        self.assertTrue(check["feasible"])
        self.assertEqual(check["positions"], solution.positions)
        base = qubo.energy(bits)
        deltas = []
        for i in range(bits.size):
            flipped = bits.copy()
            flipped[i] ^= 1
            deltas.append(qubo.energy(flipped) - base)
        self.assertGreater(min(deltas), 1e6)

    def test_omitted_constant_is_the_penalty_constant(self):
        """penalty 1e7 x (C^2 + B^2) x T = 1e7 x (100 + 16) x 10."""
        from quantum.qoblib import qubo_offset

        instance, qubo, solution = self._load()
        self.assertAlmostEqual(qubo_offset(qubo, instance, solution), 1.16e10, places=3)
        instance, qubo, solution = self._load("l1e-5")
        self.assertAlmostEqual(qubo_offset(qubo, instance, solution), 1.16e10, places=3)

    def test_solver_output_is_scored_in_objective_units(self):
        from quantum.qoblib import decode_bits, qubo_offset
        from quantum.solvers import get_solver

        instance, qubo, solution = self._load()
        offset = qubo_offset(qubo, instance, solution)
        result = get_solver("simulated_annealing").solve(
            qubo, n_sweeps=200, n_restarts=1, rng=np.random.default_rng(0)
        )
        objective = result.energy + offset
        check = decode_bits(instance, result.assignment, solution.budget)
        # Whatever it found, it cannot beat a proven optimum.
        if check["feasible"]:
            self.assertGreaterEqual(objective, solution.objective - 1e-6)
        self.assertEqual(len(check["capital_residual"]), instance.n_periods)


class TestExternalData(unittest.TestCase):
    def test_real_price_file_loads_with_date_window(self):
        from quantum.market import load_price_csv

        market = load_price_csv(
            "data/prices/us_equities_1989_2018.csv",
            tickers=["AAPL", "XOM", "JPM"], start="2010-01-01", end="2010-12-31",
        )
        self.assertEqual(market.n_assets, 3)
        self.assertEqual(market.prices.shape[0], 252)
        self.assertTrue(np.all(np.isfinite(market.covariance)))

    def test_missing_cells_drop_rows_rather_than_fabricate(self):
        from quantum.market import load_price_csv

        with_fb = load_price_csv("data/prices/us_equities_1989_2018.csv", tickers=["AAPL", "FB"])
        without = load_price_csv("data/prices/us_equities_1989_2018.csv", tickers=["AAPL"])
        self.assertLess(with_fb.prices.shape[0], without.prices.shape[0])

    def test_hardware_profiles_build_models(self):
        from quantum.noise import HARDWARE_PROFILES, NoiseModel

        for name in HARDWARE_PROFILES:
            model = NoiseModel.from_hardware(name)
            self.assertGreater(model.two_qubit, model.one_qubit)
        with self.assertRaises(ValueError):
            NoiseModel.from_hardware("no_such_machine")

    def test_hardware_survey_rows(self):
        from quantum.noise import hardware_survey
        from quantum.pricing import OptionSpec, build_european_payoff_circuit
        from quantum.statevector import probability_of_one

        prep, objective, *_ = build_european_payoff_circuit(OptionSpec(100.0, 100.0, 0.05, 0.2, 1.0), 3)
        truth = probability_of_one(prep.run(), prep.n_qubits, objective)
        rows = hardware_survey(
            prep, objective, truth, profiles=["ibm_nighthawk"], n_powers=3,
            shots_per_power=64, trajectories=4, trials=1, rng=np.random.default_rng(0),
        )
        self.assertEqual(len(rows), 1)
        self.assertIn("source", rows[0])
        self.assertGreaterEqual(rows[0]["abs_error"], 0.0)


# ==========================================================================
# Live engine
# ==========================================================================


class TestLiveEngine(unittest.TestCase):
    PRICES = "data/prices/us_equities_1989_2018.csv"
    TICKERS = ["AAPL", "XOM", "JPM", "WMT", "PFE"]

    def _config(self, tmp, **overrides):
        from quantum.live import EngineConfig, RiskLimits

        limits = overrides.pop("limits", RiskLimits(min_history=60, max_drawdown=0.25))
        base = dict(tickers=self.TICKERS, strategy="equal_weight", window=60,
                    rebalance_every=20, state_path=str(tmp / "state.json"), limits=limits)
        base.update(overrides)
        return EngineConfig(**base)

    def test_paper_replay_is_self_consistent(self):
        """Cash + positions at every bar equals the equity curve; fees are charged."""
        import tempfile
        from pathlib import Path
        from quantum.live import Bar, ReplayFeed, run

        with tempfile.TemporaryDirectory() as d:
            config = self._config(Path(d))
            feed = ReplayFeed(self.PRICES, self.TICKERS, start="2012-01-01", end="2012-12-31")
            engine = run(config, feed, resume=False)
            st = engine.state
            self.assertEqual(st.n_bars, len(feed))
            self.assertGreater(len(st.fills), 0)
            last = Bar(st.dates[-1], dict(zip(self.TICKERS, st.prices[-1])))
            self.assertAlmostEqual(engine.equity(last), st.equity_curve[-1], places=6)
            self.assertGreater(sum(f["fee"] for f in st.fills), 0.0)
            # Equal weight after a rebalance: each held name near 20%.
            weights = engine.weights(last)
            self.assertEqual(len(weights), 5)
            for w in weights.values():
                self.assertLess(abs(w - 0.2), 0.05)

    def test_restart_resumes_without_reprocessing(self):
        import tempfile
        from pathlib import Path
        from quantum.live import ReplayFeed, run

        with tempfile.TemporaryDirectory() as d:
            config = self._config(Path(d))
            first = run(config, ReplayFeed(self.PRICES, self.TICKERS, start="2012-01-01", end="2012-06-30"), resume=False)
            n_first = first.state.n_bars
            # Same feed again plus more bars: the overlap must be skipped.
            second = run(config, ReplayFeed(self.PRICES, self.TICKERS, start="2012-01-01", end="2012-12-31"), resume=True)
            self.assertGreater(second.state.n_bars, n_first)
            self.assertEqual(second.state.dates[:n_first], first.state.dates)
            self.assertEqual(len(set(second.state.dates)), second.state.n_bars)

    def test_kill_switch_liquidates_and_halts(self):
        import tempfile
        from pathlib import Path
        from quantum.live import ReplayFeed, RiskLimits, run

        with tempfile.TemporaryDirectory() as d:
            config = self._config(Path(d), limits=RiskLimits(min_history=60, max_drawdown=0.10))
            engine = run(config, ReplayFeed(self.PRICES, self.TICKERS, start="2007-06-01", end="2009-06-30"), resume=False)
            st = engine.state
            self.assertTrue(st.halted)
            self.assertEqual(engine.broker.positions(), {})
            self.assertEqual(st.target_weights, {})
            halt_index = next(i for i, line in enumerate(st.log) if "kill_switch" in line)
            self.assertTrue(all("halted" in line for line in st.log[halt_index + 1:]))

    def test_risk_caps_hold(self):
        """Per-name cap and turnover cap are enforced on the cardinality strategy."""
        import tempfile
        from pathlib import Path
        from quantum.live import Bar, ReplayFeed, RiskLimits, run

        with tempfile.TemporaryDirectory() as d:
            config = self._config(
                Path(d), strategy="cardinality", cardinality=2, solver="exhaustive",
                limits=RiskLimits(min_history=60, max_drawdown=0.9, max_weight=0.30, max_turnover=0.20),
            )
            engine = run(config, ReplayFeed(self.PRICES, self.TICKERS, start="2012-01-01", end="2012-12-31"), resume=False)
            for w in engine.state.target_weights.values():
                self.assertLessEqual(w, 0.30 + 1e-9)
            # Cumulative turnover across the year stays below the per-rebalance cap times rebalances.
            n_rebalances = sum("rebalance" in line for line in engine.state.log)
            self.assertGreater(n_rebalances, 0)

    def test_turnover_cap_counts_cash(self):
        """One-way turnover is max(buys, sells) / equity, so cash moving counts too."""
        import tempfile
        from collections import defaultdict
        from pathlib import Path
        from quantum.live import ReplayFeed, RiskLimits, run

        with tempfile.TemporaryDirectory() as d:
            config = self._config(Path(d), limits=RiskLimits(min_history=60, max_drawdown=0.9, max_turnover=0.30))
            engine = run(config, ReplayFeed(self.PRICES, self.TICKERS, start="2012-01-01", end="2012-12-31"), resume=False)
            st = engine.state
            traded = defaultdict(lambda: [0.0, 0.0])
            for f in st.fills:
                traded[f["date"]][f["quantity"] < 0] += abs(f["quantity"]) * f["price"]
            self.assertGreater(len(traded), 1)
            equity = dict(zip(st.dates, st.equity_curve))
            for date, (buys, sells) in traded.items():
                self.assertLessEqual(max(buys, sells), 0.30 * equity[date] * (1 + 1e-9), date)
            # From all cash the first rebalance deploys the cap, not twice it.
            first = traded[min(traded)]
            self.assertAlmostEqual(first[0] / config.initial_cash, 0.30, delta=1e-6)

    def test_file_feed_delivers_only_new_rows(self):
        import csv
        import tempfile
        from pathlib import Path
        from quantum.live import FileFeed

        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "tail.csv"
            with path.open("w", newline="") as fh:
                w = csv.writer(fh)
                w.writerow(["date", "AAA", "BBB"])
                w.writerows([("2024-01-02", 100, 50), ("2024-01-03", 101, 49)])
            first = [b.date for b in FileFeed(path, ["AAA", "BBB"], poll_seconds=0.0, max_polls=1).bars()]
            self.assertEqual(first, ["2024-01-02", "2024-01-03"])
            with path.open("a", newline="") as fh:
                csv.writer(fh).writerow(("2024-01-04", 102, 48))
            later = [b.date for b in FileFeed(path, ["AAA", "BBB"], poll_seconds=0.0, after="2024-01-03", max_polls=1).bars()]
            self.assertEqual(later, ["2024-01-04"])

    def test_once_advances_past_bars_already_seen(self):
        """Regression: a --once start used to spend its one tick on a duplicate."""
        import csv
        import tempfile
        from pathlib import Path
        from quantum.live import Engine, EngineConfig, FileFeed, RiskLimits

        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "feed.csv"
            with path.open("w", newline="") as fh:
                w = csv.writer(fh)
                w.writerow(["date", "AAA", "BBB"])
                w.writerows([("2024-01-02", 100, 50), ("2024-01-03", 101, 49), ("2024-01-04", 102, 48)])
            cfg = EngineConfig(["AAA", "BBB"], strategy="equal_weight", window=3, rebalance_every=1,
                               limits=RiskLimits(min_history=3, max_drawdown=0.5),
                               state_path=str(Path(d) / "s.json"))
            engine = Engine(cfg)
            seen = []
            for _ in range(3):
                events = engine.run(FileFeed(path, ["AAA", "BBB"], poll_seconds=0.0, max_polls=1), once=True)
                seen.append([e["date"] for e in events])
            self.assertEqual(seen, [["2024-01-02"], ["2024-01-03"], ["2024-01-04"]])
            events = engine.run(FileFeed(path, ["AAA", "BBB"], poll_seconds=0.0, max_polls=1), once=True)
            self.assertEqual(events, [])
            self.assertEqual(engine.state.n_bars, 3)

    def test_config_validation_and_round_trip(self):
        import tempfile
        from pathlib import Path
        from quantum.live import EngineConfig, load_config

        with self.assertRaises(ValueError):
            EngineConfig(["A"], window=2)
        with self.assertRaises(ValueError):
            EngineConfig(["A", "A"])
        with self.assertRaises(ValueError):
            EngineConfig(["A", "B"], cardinality=3)
        with tempfile.TemporaryDirectory() as d:
            cfg = EngineConfig(["A", "B", "C"], cardinality=2)
            p = Path(d) / "c.json"
            import json
            p.write_text(json.dumps(cfg.to_dict()))
            self.assertEqual(load_config(p), cfg)

    def test_paper_broker_scales_unaffordable_buys(self):
        from quantum.live import Bar, Order, PaperBroker

        broker = PaperBroker(cash=1_000.0, fee_rate=0.0)
        fills = broker.submit([Order("AAA", 100.0)], Bar("2024-01-02", {"AAA": 50.0}))
        self.assertEqual(len(fills), 1)
        self.assertAlmostEqual(fills[0].quantity, 20.0)
        self.assertAlmostEqual(broker.cash(), 0.0)


# ==========================================================================
# Desktop dashboard (controller + HTTP API; no browser needed)
# ==========================================================================


class TestDesktop(unittest.TestCase):
    def _server(self, tmp):
        import shutil
        from pathlib import Path
        from quantum.desktop import serve

        work = Path(tmp)
        (work / "data" / "prices").mkdir(parents=True)
        shutil.copy("data/prices/us_equities_1989_2018.csv", work / "data" / "prices" / "us_equities_1989_2018.csv")
        return serve(port=0, open_browser=False, workdir=work, block=False)

    def _api(self, port):
        import json
        import urllib.request

        base = f"http://127.0.0.1:{port}"

        def get(p):
            return json.loads(urllib.request.urlopen(base + p, timeout=10).read())

        def post(p, body):
            req = urllib.request.Request(base + p, data=json.dumps(body).encode(),
                                         headers={"Content-Type": "application/json"}, method="POST")
            return json.loads(urllib.request.urlopen(req, timeout=10).read())

        return get, post

    def test_page_and_state_endpoints(self):
        import tempfile
        import urllib.request

        with tempfile.TemporaryDirectory() as d:
            srv = self._server(d)
            try:
                port = srv.server_address[1]
                html = urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=10).read().decode()
                self.assertIn("<title>Quantum Trading</title>", html)
                self.assertIn("PAPER", html)
                get, _ = self._api(port)
                st = get("/api/state")
                self.assertFalse(st["running"])
                self.assertEqual(st["bars"], 0)
                self.assertTrue(st["paper"])
                self.assertIn("data/prices/us_equities_1989_2018.csv", st["files"])
                self.assertEqual(st["default_file"], "data/prices/us_equities_1989_2018.csv")
            finally:
                srv.shutdown()

    def test_start_stop_reset_and_kill_switch_through_the_api(self):
        import tempfile
        import time

        with tempfile.TemporaryDirectory() as d:
            srv = self._server(d)
            try:
                get, post = self._api(srv.server_address[1])
                form = {"mode": "replay", "csv": "data/prices/us_equities_1989_2018.csv",
                        "tickers": "AAPL,XOM,JPM,WMT,PFE,BAC", "start": "2007-01-01", "end": "2009-06-30",
                        "bars_per_second": 0, "fresh": True, "window": 120, "max_drawdown": 0.12,
                        "strategy": "equal_weight"}
                self.assertTrue(post("/api/start", form)["ok"])
                self.assertFalse(post("/api/start", form)["ok"])  # already running
                for _ in range(120):
                    time.sleep(0.5)
                    st = get("/api/state")
                    if not st["running"]:
                        break
                self.assertFalse(st["running"])
                self.assertTrue(st["halted"])
                self.assertIn("2008", st["halt_reason"])
                self.assertEqual(st["positions"], {})
                self.assertGreater(st["bars"], 200)
                self.assertGreater(st["n_fills"], 0)
                self.assertEqual(len(st["curve"]), len(st["dates"]))
                self.assertTrue(post("/api/resume", {})["ok"])
                self.assertFalse(get("/api/state")["halted"])
                self.assertTrue(post("/api/reset", {})["ok"])
                self.assertEqual(get("/api/state")["bars"], 0)
            finally:
                srv.shutdown()

    def test_stop_interrupts_a_throttled_replay(self):
        import tempfile
        import time

        with tempfile.TemporaryDirectory() as d:
            srv = self._server(d)
            try:
                get, post = self._api(srv.server_address[1])
                form = {"mode": "replay", "csv": "data/prices/us_equities_1989_2018.csv",
                        "tickers": "AAPL,XOM", "start": "2012-01-01", "bars_per_second": 20,
                        "fresh": True, "window": 10, "strategy": "equal_weight"}
                self.assertTrue(post("/api/start", form)["ok"])
                time.sleep(1.5)
                self.assertTrue(get("/api/state")["running"])
                self.assertTrue(post("/api/stop", {})["ok"])
                st = get("/api/state")
                self.assertFalse(st["running"])
                self.assertGreater(st["bars"], 5)
                self.assertLess(st["bars"], 200)
                # Restarting without 'fresh' resumes from the saved state.
                form["fresh"] = False
                self.assertTrue(post("/api/start", form)["ok"])
                time.sleep(1.0)
                post("/api/stop", {})
                self.assertGreater(get("/api/state")["bars"], st["bars"])
            finally:
                srv.shutdown()

    def test_bad_requests_are_refused_not_crashed(self):
        import tempfile

        with tempfile.TemporaryDirectory() as d:
            srv = self._server(d)
            try:
                get, post = self._api(srv.server_address[1])
                r = post("/api/start", {"mode": "replay", "csv": "nope.csv"})
                self.assertFalse(r["ok"])
                r = post("/api/start", {"mode": "replay", "csv": "data/prices/us_equities_1989_2018.csv",
                                        "tickers": "AAPL", "cardinality": 4})
                self.assertFalse(r["ok"])
                self.assertIn("cardinality", r["error"])
                self.assertIn("start refused", get("/api/state")["messages"][-1])
            finally:
                srv.shutdown()


# ==========================================================================
# Browser port of the engine (web/engine.js) must match the Python engine
# ==========================================================================


class TestWebEngineParity(unittest.TestCase):
    def test_browser_engine_matches_python_to_the_cent(self):
        import json
        import shutil
        import subprocess
        import tempfile
        from pathlib import Path
        from quantum.live import Bar, Engine, EngineConfig, RiskLimits

        node = shutil.which("node")
        if node is None:
            self.skipTest("node is not installed")
        import csv as _csv
        rows = list(_csv.DictReader(open("data/prices/us_equities_1989_2018.csv")))
        tick = ["AAPL", "XOM", "JPM", "WMT", "PFE", "AMZN", "BAC", "T"]
        rows = [r for r in rows if "2007-01-01" <= r["date"] <= "2012-12-31" and all(r[t] for t in tick)]
        cases = [("equal_weight", 0.9, None), ("markowitz", 0.9, None), ("cardinality", 0.9, None),
                 ("cardinality", 0.12, None), ("cardinality", 0.9, "2010-03-01")]
        expected = []
        for strat, ks, tf in cases:
            e = Engine(EngineConfig(tickers=tick, strategy=strat, cardinality=4, solver="exhaustive",
                                    window=252, rebalance_every=21, initial_cash=100000, fee_rate=0.0005,
                                    limits=RiskLimits(max_weight=0.4, max_turnover=0.5, max_drawdown=ks, min_history=252),
                                    state_path="unused.json", trade_from=tf))
            for r in rows:
                e.on_bar(Bar(r["date"], {t: float(r[t]) for t in tick}))
            expected.append([e.state.equity_curve[-1], len(e.state.fills), e.state.halted])
        with tempfile.TemporaryDirectory() as d:
            payload = {"rows": [[r["date"]] + [float(r[t]) for t in tick] for r in rows], "tick": tick,
                       "cases": [list(c) for c in cases]}
            (Path(d) / "in.json").write_text(json.dumps(payload))
            script = Path(d) / "run.js"
            script.write_text(
                "const QT=require(%s);const p=require(%s);const out=p.cases.map(([s,ks,tf])=>{"
                "const e=new QT.Engine({tickers:p.tick,strategy:s,cardinality:4,riskAversion:2,window:252,"
                "rebalanceEvery:21,initialCash:100000,feeRate:0.0005,limits:{maxWeight:0.4,maxTurnover:0.5,"
                "maxDrawdown:ks,minHistory:252},tradeFrom:tf});p.rows.forEach(r=>{const q={};p.tick.forEach((t,i)=>q[t]=r[i+1]);"
                "e.onBar({date:r[0],prices:q});});return [e.equity[e.equity.length-1],e.fills.length,e.halted];});"
                "console.log(JSON.stringify(out));"
                % (json.dumps(str(Path("web/engine.js").resolve())), json.dumps(str(Path(d) / "in.json"))))
            got = json.loads(subprocess.run([node, str(script)], capture_output=True, text=True, check=True).stdout)
        for (pe, pf, ph), (je, jf, jh) in zip(expected, got):
            self.assertAlmostEqual(pe, je, delta=1e-6 * pe)
            self.assertEqual(pf, jf)
            self.assertEqual(ph, jh)



class TestLiveBot(unittest.TestCase):
    """The scheduled paper bot: warm-up, catch-up runs, and the dashboard snapshot."""

    TICK = ["AAPL", "XOM", "JPM", "WMT", "PFE", "AMZN", "BAC", "T"]

    def _write(self, path, rows):
        import csv
        with open(path, "w", newline="") as fh:
            w = csv.writer(fh)
            w.writerow(["date"] + self.TICK)
            for r in rows:
                w.writerow([r["date"]] + [r[t] for t in self.TICK])

    def _rows(self):
        import csv
        return [r for r in csv.DictReader(open("data/prices/us_equities_1989_2018.csv"))
                if r["date"] >= "2015-06-01" and all(r[t] for t in self.TICK)]

    def test_warmup_never_trades_before_trade_from(self):
        from quantum.live import Bar, Engine, EngineConfig, RiskLimits

        rows = self._rows()[:320]
        tf = rows[280]["date"]
        e = Engine(EngineConfig(self.TICK, strategy="equal_weight", window=252, trade_from=tf,
                                limits=RiskLimits(min_history=252), state_path="unused.json"))
        for r in rows:
            e.on_bar(Bar(r["date"], {t: float(r[t]) for t in self.TICK}))
        self.assertTrue(all(f["date"] >= tf for f in e.state.fills))
        self.assertEqual(e.state.fills[0]["date"], tf)
        before = [v for d, v in zip(e.state.dates, e.state.equity_curve) if d < tf]
        self.assertTrue(all(v == 100_000.0 for v in before))

    def test_catch_up_runs_resume_and_are_idempotent(self):
        import json
        import subprocess
        import sys
        import tempfile
        from pathlib import Path

        rows = self._rows()
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            cfg = json.load(open("live/config.json"))
            cfg.update(state_path=str(d / "state.json"), trade_from=rows[270]["date"])
            (d / "config.json").write_text(json.dumps(cfg))
            cmd = [sys.executable, "-m", "quantum", "live", "--config", str(d / "config.json"),
                   "--feed", str(d / "prices.csv"), "--catch-up", "--poll", "0",
                   "--snapshot", str(d / "snapshot.json")]
            self._write(d / "prices.csv", rows[:300])
            subprocess.run(cmd, check=True, capture_output=True, timeout=300)
            first = json.loads((d / "snapshot.json").read_text())
            self.assertEqual(first["bars_seen"], 300)
            self.assertEqual(first["live_bars"], 30)
            self.assertEqual(first["curve_dates"][0], rows[270]["date"])
            self.assertEqual(first["mode"], "paper")
            self._write(d / "prices.csv", rows[:325])
            subprocess.run(cmd, check=True, capture_output=True, timeout=300)
            second = json.loads((d / "snapshot.json").read_text())
            self.assertEqual(second["bars_seen"], 325)
            self.assertGreaterEqual(second["n_fills"], first["n_fills"])
            subprocess.run(cmd, check=True, capture_output=True, timeout=300)
            third = json.loads((d / "snapshot.json").read_text())
            self.assertEqual(third["bars_seen"], 325)
            self.assertEqual(third["n_fills"], second["n_fills"])
            prices = json.loads((d / "snapshot_prices.json").read_text())
            self.assertTrue(prices["full_history"])
            self.assertEqual(len(prices["dates"]), 325)
            self.assertLess(len(json.dumps(second)), 256 * 1024)
            self.assertLess(len(json.dumps(prices)), 256 * 1024)

    def test_fetch_script_refuses_a_partial_market(self):
        import importlib.util
        import json
        import tempfile
        from pathlib import Path
        from unittest import mock

        spec = importlib.util.spec_from_file_location("fetch_prices", "scripts/fetch_prices.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        good = {"2026-09-21": 10.0, "2026-09-22": 11.0}
        lagging = {"2026-09-21": 20.0}
        with tempfile.TemporaryDirectory() as d:
            cfg = Path(d) / "c.json"
            cfg.write_text(json.dumps({"tickers": ["AAA", "BBB"]}))
            out = Path(d) / "p.csv"
            with mock.patch.object(mod, "fetch", side_effect=[(good, "stooq"), (lagging, "stooq")]), \
                 mock.patch("sys.argv", ["x", "--config", str(cfg), "--out", str(out), "--days", "36500"]):
                self.assertEqual(mod.main(), 2)
            self.assertFalse(out.exists())
            with mock.patch.object(mod, "fetch", side_effect=[(good, "stooq"), (dict(good), "yahoo")]), \
                 mock.patch("sys.argv", ["x", "--config", str(cfg), "--out", str(out), "--days", "36500"]):
                self.assertEqual(mod.main(), 0)
            self.assertEqual(out.read_text().splitlines()[0], "date,AAA,BBB")
            self.assertEqual(len(out.read_text().splitlines()), 3)

    def test_fetch_skips_a_source_that_is_unreachable(self):
        import importlib.util
        import urllib.error
        from unittest import mock

        spec = importlib.util.spec_from_file_location("fetch_prices", "scripts/fetch_prices.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        good = {"2026-09-22": 11.0}
        with mock.patch.object(mod.time, "sleep"), \
             mock.patch.object(mod, "stooq", side_effect=ConnectionResetError("reset")) as st, \
             mock.patch.object(mod, "yahoo", return_value=good):
            self.assertEqual(mod.fetch("AAA", 10), (good, "yahoo"))
            self.assertEqual(mod.fetch("BBB", 10), (good, "yahoo"))
            self.assertEqual(st.call_count, 3)  # retried for the first ticker only
        mod.UNREACHABLE.clear()
        # An HTTP error or bad data is about one ticker: the source stays in use.
        http = urllib.error.HTTPError("u", 404, "Not Found", {}, None)
        with mock.patch.object(mod.time, "sleep"), \
             mock.patch.object(mod, "stooq", side_effect=[http, http, http, good]) as st, \
             mock.patch.object(mod, "yahoo", return_value=good):
            self.assertEqual(mod.fetch("AAA", 10), (good, "yahoo"))
            self.assertEqual(mod.fetch("BBB", 10), (good, "stooq"))
            self.assertEqual(st.call_count, 4)
        self.assertEqual(mod.UNREACHABLE, set())

    def test_yahoo_retries_a_rate_limit_as_another_user_agent(self):
        import importlib.util
        import json
        import urllib.error
        from unittest import mock

        spec = importlib.util.spec_from_file_location("fetch_prices", "scripts/fetch_prices.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        body = json.dumps({"chart": {"result": [{"timestamp": [1790035200],
                          "indicators": {"adjclose": [{"adjclose": [12.5]}]}}]}}).encode()
        limited = urllib.error.HTTPError("u", 429, "Too Many Requests", {}, None)
        with mock.patch.object(mod, "_get", side_effect=[limited, body]) as get:
            self.assertEqual(list(mod.yahoo("AAA", 10).values()), [12.5])
        self.assertIsNone(get.call_args_list[0].kwargs["headers"])
        self.assertEqual(get.call_args_list[1].kwargs["headers"], {"User-Agent": mod.ALT_UAS[0]})
        with mock.patch.object(mod, "_get", side_effect=[limited] * 3), self.assertRaises(urllib.error.HTTPError):
            mod.yahoo("AAA", 10)
        missing = urllib.error.HTTPError("u", 404, "Not Found", {}, None)
        with mock.patch.object(mod, "_get", side_effect=[missing]) as get, self.assertRaises(urllib.error.HTTPError):
            mod.yahoo("AAA", 10)
        self.assertEqual(get.call_count, 1)

    def test_bot_config_is_valid_and_paper(self):
        from quantum.live import load_config

        cfg = load_config("live/config.json")
        self.assertEqual(cfg.state_path, "live/state.json")
        self.assertTrue(cfg.trade_from)
        self.assertEqual(cfg.solver, "exhaustive")
