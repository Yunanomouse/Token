"""Offline tests for the parsing and normalisation layer.

These run without a network: each provider's HTTP call is replaced with a
captured response, so the tests check the part that actually breaks -- the
shape-juggling between each provider's format and :class:`Bar`.

Run:  python3 -m unittest discover -s tests -v
"""

from __future__ import annotations

import dataclasses
import sys
import unittest
from datetime import date
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from marketdata import canada, core, providers  # noqa: E402
from marketdata.core import Bar, ProviderError, clean_number, dedupe_sorted  # noqa: E402
from marketdata.crosscheck import cross_check  # noqa: E402


class CleanNumberTests(unittest.TestCase):
    def test_strips_currency_and_separators(self):
        self.assertEqual(clean_number("$336.13"), 336.13)
        self.assertEqual(clean_number("86,588,200"), 86588200.0)
        self.assertEqual(clean_number("-1,234.5"), -1234.5)

    def test_passes_through_real_numbers(self):
        self.assertEqual(clean_number(181.23), 181.23)
        self.assertEqual(clean_number(7), 7.0)

    def test_absent_values_become_nan(self):
        for value in (None, "", "N/A", "--", "null"):
            self.assertNotEqual(clean_number(value), clean_number(value))


class DedupeTests(unittest.TestCase):
    def _bar(self, day: str, close: float) -> Bar:
        return Bar(
            date=date.fromisoformat(day),
            open=1, high=1, low=1, close=close, volume=1,
            currency="USD", provider="test", symbol="X",
        )

    def test_sorts_oldest_first_and_keeps_last_duplicate(self):
        bars = dedupe_sorted(
            [self._bar("2026-01-03", 3), self._bar("2026-01-01", 1),
             self._bar("2026-01-03", 99)]
        )
        self.assertEqual([b.date.day for b in bars], [1, 3])
        self.assertEqual(bars[-1].close, 99)


class NasdaqTests(unittest.TestCase):
    PAYLOAD = {
        "data": {
            "symbol": "AAPL",
            "tradesTable": {
                "rows": [
                    {"date": "09/18/2026", "close": "$336.13",
                     "volume": "86,588,200", "open": "$337.905",
                     "high": "$338.49", "low": "$332.53"},
                    {"date": "09/17/2026", "close": "$337.00",
                     "volume": "36,700,230", "open": "$334.77",
                     "high": "$338.34", "low": "$333.01"},
                ]
            },
        }
    }

    def test_parses_us_format_dates_and_money(self):
        with mock.patch.object(providers, "http_json", return_value=self.PAYLOAD):
            bars = providers.nasdaq_history("aapl", date(2026, 9, 1), date(2026, 9, 20))
        self.assertEqual(len(bars), 2)
        self.assertEqual(bars[0].date, date(2026, 9, 18))
        self.assertEqual(bars[0].close, 336.13)
        self.assertEqual(bars[0].volume, 86588200.0)
        self.assertEqual(bars[0].currency, "USD")
        self.assertIsNone(bars[0].adj_close)

    def test_empty_table_raises_rather_than_returning_nothing(self):
        empty = {"data": {"tradesTable": {"rows": []}}, "status": {}}
        with mock.patch.object(providers, "http_json", return_value=empty):
            with self.assertRaises(ProviderError):
                providers.nasdaq_history("ZZZZ", date(2026, 9, 1), date(2026, 9, 20))


class TmxTests(unittest.TestCase):
    PAYLOAD = {
        "data": {
            "getTimeSeriesData": [
                {"dateTime": "2026-09-18T16:00:00-04:00", "open": 181.23,
                 "high": 181.24, "low": 177.66, "close": 179.34,
                 "volume": 5514611},
            ]
        }
    }

    def test_prices_are_cad(self):
        with mock.patch.object(providers, "http_json", return_value=self.PAYLOAD):
            bars = providers.tmx_history("SHOP", date(2026, 9, 1), date(2026, 9, 20))
        self.assertEqual(bars[0].currency, "CAD")
        self.assertEqual(bars[0].close, 179.34)

    def test_dot_to_suffix_is_stripped(self):
        seen = {}

        def capture(url, **kwargs):
            seen.update(kwargs["json"]["variables"])
            return self.PAYLOAD

        with mock.patch.object(providers, "http_json", side_effect=capture):
            providers.tmx_history("SHOP.TO", date(2026, 9, 1), date(2026, 9, 20))
        self.assertEqual(seen["symbol"], "SHOP")

    def test_graphql_errors_surface(self):
        with mock.patch.object(
            providers, "http_json", return_value={"errors": [{"message": "nope"}]}
        ):
            with self.assertRaises(ProviderError):
                providers.tmx_history("ZZZZ", date(2026, 9, 1), date(2026, 9, 20))


class KrakenTests(unittest.TestCase):
    # [ time, open, high, low, close, vwap, volume, count ]
    PAYLOAD = {
        "error": [],
        "result": {
            "XXBTZCAD": [
                [1789948800, "115000.0", "118000.0", "114000.0", "117000.0",
                 "116500.0", "12.5", 900],
                [1790035200, "117000.0", "119000.0", "116000.0", "118574.2",
                 "118000.0", "10.1", 800],
            ],
            "last": 1790035200,
        },
    }

    def test_quote_currency_comes_from_the_pair(self):
        with mock.patch.object(providers, "http_json", return_value=self.PAYLOAD):
            bars = providers.kraken_history(
                "BTC/CAD", date(2026, 9, 1), date(2026, 9, 30)
            )
        self.assertEqual(bars[0].currency, "CAD")
        self.assertEqual(bars[-1].close, 118574.2)
        # volume is column 6, not the vwap in column 5
        self.assertEqual(bars[-1].volume, 10.1)

    def test_pair_separators_are_interchangeable(self):
        with mock.patch.object(providers, "http_json", return_value=self.PAYLOAD):
            for symbol in ("BTC-CAD", "btc/cad", "BTC_CAD"):
                bars = providers.kraken_history(
                    symbol, date(2026, 9, 1), date(2026, 9, 30)
                )
                self.assertEqual(bars[0].symbol, "BTC/CAD")

    def test_bare_symbol_is_rejected(self):
        with self.assertRaises(ProviderError):
            providers.kraken_history("BTC", date(2026, 9, 1), date(2026, 9, 30))

    def test_out_of_range_candles_are_dropped(self):
        with mock.patch.object(providers, "http_json", return_value=self.PAYLOAD):
            with self.assertRaises(ProviderError):
                providers.kraken_history(
                    "BTC/CAD", date(2020, 1, 1), date(2020, 2, 1)
                )


class CoinbaseTests(unittest.TestCase):
    # [ time, low, high, open, close, volume ]
    ROWS = [[1790035200, 80000.0, 82000.0, 80500.0, 81159.64, 1234.5]]

    def test_column_order_is_not_ohlc(self):
        with mock.patch.object(providers, "http_json", side_effect=[self.ROWS, []]):
            bars = providers.coinbase_history(
                "BTC-USD", date(2026, 9, 20), date(2026, 9, 21)
            )
        bar = bars[0]
        self.assertEqual((bar.low, bar.high, bar.open, bar.close),
                         (80000.0, 82000.0, 80500.0, 81159.64))


class StooqTests(unittest.TestCase):
    CSV = (
        "Date,Open,High,Low,Close,Volume\n"
        "2026-09-17,334.77,338.34,333.01,337.00,36700230\n"
        "2026-09-18,337.905,338.49,332.53,336.13,86588200\n"
    )

    def test_parses_csv(self):
        with mock.patch.object(providers, "http_text", return_value=self.CSV):
            bars = providers.stooq_history("aapl.us", date(2026, 9, 1), date(2026, 9, 20))
        self.assertEqual(len(bars), 2)
        self.assertEqual(bars[1].close, 336.13)
        self.assertEqual(bars[1].currency, "USD")

    def test_html_block_page_is_reported_clearly(self):
        with mock.patch.object(providers, "http_text", return_value="<html>no</html>"):
            with self.assertRaises(ProviderError) as ctx:
                providers.stooq_history("aapl.us", date(2026, 9, 1), date(2026, 9, 20))
        self.assertIn("datacentre", str(ctx.exception))


class AlphaVantageTests(unittest.TestCase):
    PAYLOAD = {
        "Time Series (Daily)": {
            "2026-09-18": {
                "1. open": "233.47", "2. high": "237.86", "3. low": "232.53",
                "4. close": "232.76", "5. adjusted close": "230.10",
                "6. volume": "4491597",
            }
        }
    }

    def test_adjusted_close_is_kept_separate(self):
        with mock.patch.dict("os.environ", {"ALPHAVANTAGE_API_KEY": "k"}):
            with mock.patch.object(providers, "http_json", return_value=self.PAYLOAD):
                bars = providers.alphavantage_history(
                    "IBM", date(2026, 9, 1), date(2026, 9, 20)
                )
        self.assertEqual(bars[0].close, 232.76)
        self.assertEqual(bars[0].adj_close, 230.10)

    def test_missing_key_is_a_clear_error(self):
        with mock.patch.dict("os.environ", {"ALPHAVANTAGE_API_KEY": ""}):
            with self.assertRaises(ProviderError) as ctx:
                providers.alphavantage_history("IBM", date(2026, 9, 1), date(2026, 9, 2))
        self.assertIn("ALPHAVANTAGE_API_KEY", str(ctx.exception))

    def test_rate_limit_note_is_surfaced(self):
        note = {"Note": "call frequency exceeded"}
        with mock.patch.dict("os.environ", {"ALPHAVANTAGE_API_KEY": "k"}):
            with mock.patch.object(providers, "http_json", return_value=note):
                with self.assertRaises(ProviderError) as ctx:
                    providers.alphavantage_history(
                        "IBM", date(2026, 9, 1), date(2026, 9, 2)
                    )
        self.assertIn("call frequency", str(ctx.exception))


class BankOfCanadaTests(unittest.TestCase):
    PAYLOAD = {
        "observations": [
            {"d": "2026-09-16", "FXUSDCAD": {"v": "1.3990"}},
            {"d": "2026-09-17", "FXUSDCAD": {"v": ""}},          # holiday
            {"d": "2026-09-18", "FXUSDCAD": {"v": "1.4002"}},
        ]
    }

    def test_blank_holiday_observations_are_skipped(self):
        with mock.patch.object(canada, "http_json", return_value=self.PAYLOAD):
            rates = canada.fx_series("USDCAD", "2026-09-15", "2026-09-18")
        self.assertEqual([r.date.day for r in rates], [16, 18])

    def test_three_letter_pair_is_accepted(self):
        with mock.patch.object(canada, "http_json", return_value=self.PAYLOAD):
            rates = canada.fx_series("USD", "2026-09-15", "2026-09-18")
        self.assertEqual(rates[0].pair, "USD/CAD")

    def test_rate_on_walks_back_to_the_last_business_day(self):
        with mock.patch.object(canada, "http_json", return_value=self.PAYLOAD):
            rate = canada.fx_rate_on("2026-09-20")  # a weekend
        self.assertEqual(rate.date, date(2026, 9, 18))
        self.assertEqual(rate.rate, 1.4002)

    def test_unknown_pair_lists_what_is_available(self):
        with self.assertRaises(ProviderError) as ctx:
            canada.fx_series("ZZZCAD")
        self.assertIn("USDCAD", str(ctx.exception))

    def test_annual_average(self):
        with mock.patch.object(canada, "http_json", return_value=self.PAYLOAD):
            self.assertAlmostEqual(canada.fx_annual_average(2026), 1.3996, places=4)


class StatCanTests(unittest.TestCase):
    PAYLOAD = [
        {
            "status": "SUCCESS",
            "object": {
                "vectorDataPoint": [
                    {"refPer": "2025-08-01", "value": 164.8},
                    {"refPer": "2026-08-01", "value": 169.8},
                ]
            },
        }
    ]

    def test_failure_status_raises(self):
        with mock.patch.object(canada, "http_json", return_value=[{"status": "FAILED"}]):
            with self.assertRaises(ProviderError):
                canada.cpi_all_items(4)

    def test_year_over_year(self):
        with mock.patch.object(canada, "http_json", return_value=self.PAYLOAD):
            rate = canada.cpi_inflation_rate(months=1)
        self.assertAlmostEqual(rate, 169.8 / 164.8 - 1, places=6)


class CrossCheckTests(unittest.TestCase):
    def _series(self, provider: str, closes: dict[str, float], currency="USD"):
        return [
            Bar(date=date.fromisoformat(d), open=c, high=c, low=c, close=c,
                volume=1, currency=currency, provider=provider, symbol="X")
            for d, c in closes.items()
        ]

    def test_agreeing_feeds_report_no_breach(self):
        a = self._series("kraken", {"2026-09-01": 100.0, "2026-09-02": 101.0})
        b = self._series("coinbase", {"2026-09-01": 100.02, "2026-09-02": 101.01})
        with mock.patch("marketdata.crosscheck.fetch_history", side_effect=[a, b]):
            result = cross_check({"kraken": "X", "coinbase": "X"}, tolerance_bps=10)
        self.assertIn("PASS", result.report())

    def test_split_shaped_divergence_is_flagged(self):
        a = self._series("one", {"2026-09-01": 100.0, "2026-09-02": 101.0})
        b = self._series("two", {"2026-09-01": 50.0, "2026-09-02": 50.5})
        with mock.patch("marketdata.crosscheck.fetch_history", side_effect=[a, b]):
            result = cross_check({"one": "X", "two": "X"}, tolerance_bps=10)
        self.assertEqual(len(result.disagreements), 2)
        self.assertGreater(result.worst.spread_bps, 3000)
        self.assertIn("corporate action", result.report())

    def test_mixed_currencies_are_refused(self):
        a = self._series("one", {"2026-09-01": 100.0}, currency="USD")
        b = self._series("two", {"2026-09-01": 140.0}, currency="CAD")
        with mock.patch("marketdata.crosscheck.fetch_history", side_effect=[a, b]):
            with self.assertRaises(ProviderError) as ctx:
                cross_check({"one": "X", "two": "X"})
        self.assertIn("different currencies", str(ctx.exception))

    def test_a_dead_provider_does_not_hide_the_others(self):
        a = self._series("one", {"2026-09-01": 100.0})
        b = self._series("two", {"2026-09-01": 100.0})
        with mock.patch(
            "marketdata.crosscheck.fetch_history",
            side_effect=[a, ProviderError("down"), b],
        ):
            result = cross_check({"one": "X", "dead": "X", "two": "X"})
        self.assertIn("dead", result.failures)
        self.assertEqual(len(result.series), 2)
        self.assertIn("PASS", result.report())

    def test_needs_two_providers(self):
        with self.assertRaises(ProviderError):
            cross_check({"only": "X"})


class RegistryTests(unittest.TestCase):
    def test_no_provider_is_yahoo(self):
        names = " ".join(core.PROVIDERS)
        descriptions = " ".join(p.description.lower() for p in core.list_providers())
        self.assertNotIn("yahoo", names.lower())
        self.assertNotIn("yahoo", descriptions)
        self.assertNotIn("yfinance", descriptions)

    def test_unknown_provider_lists_the_known_ones(self):
        with self.assertRaises(ProviderError) as ctx:
            core.fetch_history("AAPL", "yahoo")
        self.assertIn("nasdaq", str(ctx.exception))

    def test_backwards_date_range_is_rejected(self):
        with self.assertRaises(ProviderError):
            core.fetch_history("AAPL", "nasdaq", start="2026-09-20", end="2026-01-01")

    def test_default_start_survives_a_leap_day(self):
        """29 February minus two calendar years is not a date."""
        captured = {}

        def fake_fetch(symbol, start, end):
            captured["start"] = start
            return []

        class FrozenDateTime(core.datetime):
            @classmethod
            def now(cls, tz=None):
                return core.datetime(2028, 2, 29, 12, 0, tzinfo=tz)

        stub = dataclasses.replace(core.PROVIDERS["nasdaq"], fetch=fake_fetch)
        with mock.patch.object(core, "datetime", FrozenDateTime), \
             mock.patch.dict(core.PROVIDERS, {"nasdaq": stub}):
            core.fetch_history("AAPL", "nasdaq")

        self.assertEqual(captured["start"], date(2026, 3, 1))


if __name__ == "__main__":
    unittest.main()
