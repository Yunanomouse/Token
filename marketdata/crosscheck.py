"""Agree-or-disagree checks across independent providers.

A single feed cannot tell you when it is wrong. Two independent feeds can.
This module fetches the same instrument from several providers, aligns the
series by date, and reports where they disagree -- which is how you catch a
missed split, a stale bar, a holiday the feed invented, or a close that was
never printed.

The comparison is deliberately blunt: on the same instrument, on the same
day, two honest feeds should agree on the close to within a basis point or
two. Anything wider is worth looking at before you trade or file on it.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from statistics import median

from .core import Bar, ProviderError, fetch_history


@dataclass(frozen=True)
class Disagreement:
    date: date
    values: dict[str, float]
    spread_bps: float

    def describe(self) -> str:
        parts = " ".join(f"{k}={v:,.4f}" for k, v in sorted(self.values.items()))
        return f"{self.date}  {parts}  spread={self.spread_bps:,.1f}bp"


@dataclass
class CrossCheck:
    symbols: dict[str, str]
    series: dict[str, list[Bar]]
    failures: dict[str, str]
    common_dates: list[date]
    disagreements: list[Disagreement]
    coverage_gaps: dict[str, list[date]]
    tolerance_bps: float

    @property
    def worst(self) -> Disagreement | None:
        return max(self.disagreements, key=lambda d: d.spread_bps, default=None)

    def report(self) -> str:
        lines = ["=" * 68]
        label = " / ".join(f"{p}:{s}" for p, s in sorted(self.symbols.items()))
        lines.append(f"Cross-check  {label}")
        lines.append("=" * 68)

        for provider, bars in sorted(self.series.items()):
            lines.append(
                f"  {provider:<13} {len(bars):>5} bars  "
                f"{bars[0].date} -> {bars[-1].date}  ({bars[0].currency})"
            )
        for provider, reason in sorted(self.failures.items()):
            lines.append(f"  {provider:<13}  unavailable: {reason}")

        if len(self.series) < 2:
            lines.append("")
            lines.append("  Need at least two working providers to compare.")
            return "\n".join(lines)

        lines.append("")
        lines.append(f"  Overlapping trading days: {len(self.common_dates)}")

        for provider, missing in sorted(self.coverage_gaps.items()):
            if missing:
                shown = ", ".join(str(d) for d in missing[:5])
                more = f" (+{len(missing) - 5} more)" if len(missing) > 5 else ""
                lines.append(
                    f"  {provider} is missing {len(missing)} day(s) the others "
                    f"have: {shown}{more}"
                )

        if not self.common_dates:
            lines.append("  No shared dates -- nothing to compare.")
            return "\n".join(lines)

        spreads = [d.spread_bps for d in self.disagreements]
        if spreads:
            lines.append(
                f"  Median spread {median(spreads):,.2f}bp   "
                f"max {max(spreads):,.2f}bp"
            )

        flagged = [d for d in self.disagreements if d.spread_bps > self.tolerance_bps]
        lines.append("")
        if not flagged:
            lines.append(
                f"  PASS - every shared close agrees within "
                f"{self.tolerance_bps:g} basis points."
            )
        else:
            lines.append(
                f"  {len(flagged)} day(s) disagree by more than "
                f"{self.tolerance_bps:g}bp:"
            )
            for item in flagged[:15]:
                lines.append(f"    {item.describe()}")
            if len(flagged) > 15:
                lines.append(f"    ... and {len(flagged) - 15} more")
            lines.append("")
            lines.append(
                "  A persistent offset usually means a corporate action one "
                "feed applied and the other did not. Isolated spikes usually "
                "mean a bad print."
            )
        return "\n".join(lines)


def cross_check(
    symbols: dict[str, str],
    start: str | date | None = None,
    end: str | date | None = None,
    tolerance_bps: float = 10.0,
) -> CrossCheck:
    """Compare the same instrument across providers.

    ``symbols`` maps a provider name to the ticker that provider uses, e.g.
    ``{"kraken": "BTC/USD", "coinbase": "BTC-USD"}``. Providers that fail are
    recorded rather than raised, so one dead feed does not hide what the
    others agree on.
    """
    if len(symbols) < 2:
        raise ProviderError("cross_check needs at least two providers")

    series: dict[str, list[Bar]] = {}
    failures: dict[str, str] = {}
    for provider, symbol in symbols.items():
        try:
            bars = fetch_history(symbol, provider, start=start, end=end)
        except ProviderError as exc:
            failures[provider] = str(exc)
            continue
        if bars:
            series[provider] = bars

    currencies = {p: bars[0].currency for p, bars in series.items()}
    distinct = {c for c in currencies.values() if c}
    if len(distinct) > 1:
        raise ProviderError(
            "refusing to compare series quoted in different currencies: "
            f"{currencies}. Convert first, or compare like for like."
        )

    by_provider = {
        provider: {bar.date: bar.close for bar in bars}
        for provider, bars in series.items()
    }
    date_sets = [set(d) for d in by_provider.values()]
    common = sorted(set.intersection(*date_sets)) if date_sets else []
    union = sorted(set.union(*date_sets)) if date_sets else []

    # Only count a gap where at least two *other* providers printed that day;
    # a single feed's extra row is more likely its own artefact.
    gaps: dict[str, list[date]] = {}
    for provider, closes in by_provider.items():
        missing = [
            day
            for day in union
            if day not in closes
            and sum(day in other for name, other in by_provider.items() if name != provider) >= 2
        ]
        gaps[provider] = missing

    disagreements = []
    for day in common:
        values = {p: closes[day] for p, closes in by_provider.items()}
        numbers = [v for v in values.values() if v == v]  # drop NaN
        if len(numbers) < 2:
            continue
        low, high = min(numbers), max(numbers)
        midpoint = (low + high) / 2
        if midpoint == 0:
            continue
        disagreements.append(
            Disagreement(
                date=day, values=values, spread_bps=(high - low) / midpoint * 10_000
            )
        )

    return CrossCheck(
        symbols=symbols,
        series=series,
        failures=failures,
        common_dates=common,
        disagreements=disagreements,
        coverage_gaps=gaps,
        tolerance_bps=tolerance_bps,
    )
