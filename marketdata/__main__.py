"""Command line entry point: ``python3 -m marketdata ...``"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

from .core import CSV_COLUMNS, ProviderError, fetch_history, list_providers
from .crosscheck import cross_check


def cmd_providers(_: argparse.Namespace) -> int:
    print(f"{'PROVIDER':<14}{'KEY':<6}{'ASSETS':<24}DESCRIPTION")
    for provider in list_providers():
        key = "yes" if provider.needs_key else "-"
        assets = ",".join(provider.asset_classes)
        print(f"{provider.name:<14}{key:<6}{assets:<24}{provider.description}")
    print("\nNone of these is Yahoo Finance.")
    return 0


def cmd_history(args: argparse.Namespace) -> int:
    bars = fetch_history(args.symbol, args.provider, start=args.start, end=args.end)

    if args.out:
        path = Path(args.out)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=CSV_COLUMNS)
            writer.writeheader()
            writer.writerows(bar.as_row() for bar in bars)
        print(f"{len(bars)} bars -> {path}")
        return 0

    print(
        f"{'date':<12}{'open':>15}{'high':>15}{'low':>15}{'close':>15}{'volume':>18}"
    )
    for bar in bars[-args.tail :]:
        print(
            f"{bar.date.isoformat():<12}{bar.open:>15,.4f}{bar.high:>15,.4f}"
            f"{bar.low:>15,.4f}{bar.close:>15,.4f}{bar.volume:>18,.2f}"
        )
    print(
        f"\n{len(bars)} bars from {args.provider} "
        f"({bars[0].date} to {bars[-1].date}, {bars[0].currency})"
    )
    return 0


def cmd_crosscheck(args: argparse.Namespace) -> int:
    symbols = {}
    for pair in args.pairs:
        if "=" not in pair:
            raise SystemExit(f"expected provider=SYMBOL, got {pair!r}")
        provider, symbol = pair.split("=", 1)
        symbols[provider] = symbol

    result = cross_check(
        symbols, start=args.start, end=args.end, tolerance_bps=args.tolerance
    )
    print(result.report())

    worst = result.worst
    breached = worst is not None and worst.spread_bps > args.tolerance
    return 1 if (breached and args.strict) else 0


def cmd_fx(args: argparse.Namespace) -> int:
    from . import canada

    if args.on:
        rate = canada.fx_rate_on(args.on, args.pair)
        print(f"{rate.pair} {rate.date} {rate.rate}  (Bank of Canada)")
        return 0
    if args.year:
        average = canada.fx_annual_average(args.year, args.pair)
        print(
            f"{args.pair} {args.year} annual average: {average:.4f}  "
            "(Bank of Canada; CRA accepts this for many similar transactions)"
        )
        return 0

    for rate in canada.fx_series(args.pair, start=args.start, end=args.end):
        print(f"{rate.date} {rate.rate}")
    return 0


def cmd_rates(args: argparse.Namespace) -> int:
    from . import canada

    for name, points in canada.policy_rates(start=args.start).items():
        if points:
            day, value = points[-1]
            print(f"{name:<14}{value:>8.2f}%   as of {day}")
    cpi = canada.cpi_all_items(14)
    print(f"{'cpi_index':<14}{cpi[-1][1]:>8.1f}    as of {cpi[-1][0]}")
    print(f"{'cpi_yoy':<14}{canada.cpi_inflation_rate() * 100:>8.2f}%")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python3 -m marketdata",
        description="Market and official Canadian data, without Yahoo Finance.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("providers", help="list available providers").set_defaults(
        func=cmd_providers
    )

    history = sub.add_parser("history", help="daily OHLCV for one symbol")
    history.add_argument("symbol")
    history.add_argument("-p", "--provider", required=True)
    history.add_argument("-s", "--start")
    history.add_argument("-e", "--end")
    history.add_argument("-o", "--out", help="write CSV here instead of printing")
    history.add_argument("-n", "--tail", type=int, default=10)
    history.set_defaults(func=cmd_history)

    check = sub.add_parser(
        "crosscheck", help="compare one instrument across providers"
    )
    check.add_argument("pairs", nargs="+", metavar="PROVIDER=SYMBOL")
    check.add_argument("-s", "--start")
    check.add_argument("-e", "--end")
    check.add_argument("-t", "--tolerance", type=float, default=10.0, help="in bp")
    check.add_argument(
        "--strict", action="store_true", help="exit non-zero if tolerance is breached"
    )
    check.set_defaults(func=cmd_crosscheck)

    fx = sub.add_parser("fx", help="Bank of Canada exchange rates")
    fx.add_argument("pair", nargs="?", default="USDCAD")
    fx.add_argument("--on", help="rate for a single settlement date")
    fx.add_argument("--year", type=int, help="annual average for a calendar year")
    fx.add_argument("-s", "--start")
    fx.add_argument("-e", "--end")
    fx.set_defaults(func=cmd_fx)

    rates = sub.add_parser("rates", help="Bank of Canada rates and StatCan CPI")
    rates.add_argument("-s", "--start")
    rates.set_defaults(func=cmd_rates)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except ProviderError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
