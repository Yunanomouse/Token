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

    def test_rejects_mismatched_covariance(self):
        with self.assertRaises(ValueError):
            PortfolioProblem(np.zeros(4), np.zeros((3, 3)))


class TestPricing(unittest.TestCase):
    def test_black_scholes_put_call_parity(self):
        spot, strike, rate, vol, maturity = 100.0, 95.0, 0.04, 0.25, 1.5
        call = black_scholes_call(spot, strike, rate, vol, maturity)
        put = black_scholes_put(spot, strike, rate, vol, maturity)
        self.assertAlmostEqual(call - put, spot - strike * math.exp(-rate * maturity), places=9)

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


if __name__ == "__main__":
    unittest.main(verbosity=2)
