"""Convert USD trades to CAD at Bank of Canada rates, and compute the gain.

Why this exists: the CRA requires amounts on a Canadian return to be reported
in Canadian dollars, converted at the rate in effect on the transaction date.
For a security bought and sold in USD that means *two* conversions -- one at
the buy, one at the sell -- and the difference between those two rates is
itself part of the taxable gain. Converting only the net USD profit at a
single year-end rate is a common and expensive mistake.

This script uses the Bank of Canada's published daily rates, which is the
source the CRA itself points at, rather than a quote from a data aggregator.

Run:
    python3 examples/cad_trade_conversion.py
    python3 examples/cad_trade_conversion.py my_trades.csv

The CSV needs the columns: symbol, buy_date, buy_price, sell_date,
sell_price, quantity  (prices in USD).
"""

from __future__ import annotations

import csv
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from marketdata import canada  # noqa: E402
from marketdata.core import ProviderError  # noqa: E402

# A few illustrative round trips, used when no CSV is supplied.
SAMPLE_TRADES = [
    # symbol, buy_date, buy_price, sell_date, sell_price, quantity
    ("AAPL", "2026-01-15", 245.10, "2026-06-12", 289.40, 100),
    ("MSFT", "2026-02-03", 412.75, "2026-08-21", 398.10, 50),
    ("NVDA", "2026-03-11", 118.20, "2026-09-04", 176.55, 200),
]


@dataclass
class ConvertedTrade:
    symbol: str
    quantity: float
    buy_date: str
    buy_price_usd: float
    buy_rate: float
    sell_date: str
    sell_price_usd: float
    sell_rate: float

    @property
    def proceeds_cad(self) -> float:
        return self.sell_price_usd * self.quantity * self.sell_rate

    @property
    def cost_base_cad(self) -> float:
        return self.buy_price_usd * self.quantity * self.buy_rate

    @property
    def gain_cad(self) -> float:
        return self.proceeds_cad - self.cost_base_cad

    @property
    def gain_usd(self) -> float:
        return (self.sell_price_usd - self.buy_price_usd) * self.quantity

    @property
    def fx_effect_cad(self) -> float:
        """The part of the CAD gain that came from the currency, not the stock.

        This is the gap between converting properly at two dates and the
        shortcut of converting the USD profit once at the sell-date rate.
        """
        return self.gain_cad - self.gain_usd * self.sell_rate


def convert(rows: list[tuple]) -> list[ConvertedTrade]:
    trades = []
    for symbol, buy_date, buy_price, sell_date, sell_price, quantity in rows:
        buy_rate = canada.fx_rate_on(buy_date, "USDCAD")
        sell_rate = canada.fx_rate_on(sell_date, "USDCAD")
        trades.append(
            ConvertedTrade(
                symbol=symbol,
                quantity=float(quantity),
                buy_date=buy_date,
                buy_price_usd=float(buy_price),
                buy_rate=buy_rate.rate,
                sell_date=sell_date,
                sell_price_usd=float(sell_price),
                sell_rate=sell_rate.rate,
            )
        )
    return trades


def load_csv(path: Path) -> list[tuple]:
    with path.open(newline="", encoding="utf-8") as handle:
        return [
            (
                row["symbol"],
                row["buy_date"],
                float(row["buy_price"]),
                row["sell_date"],
                float(row["sell_price"]),
                float(row["quantity"]),
            )
            for row in csv.DictReader(handle)
        ]


def main() -> int:
    if len(sys.argv) > 1:
        rows = load_csv(Path(sys.argv[1]))
    else:
        rows = SAMPLE_TRADES
        print("No CSV given -- using the built-in sample trades.\n")

    try:
        trades = convert(rows)
    except ProviderError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    header = (
        f"{'SYMBOL':<8}{'QTY':>7}{'BUY RATE':>10}{'SELL RATE':>11}"
        f"{'COST (CAD)':>14}{'PROCEEDS (CAD)':>16}{'GAIN (CAD)':>14}"
    )
    print(header)
    print("-" * len(header))

    total_gain = total_fx = 0.0
    for trade in trades:
        total_gain += trade.gain_cad
        total_fx += trade.fx_effect_cad
        print(
            f"{trade.symbol:<8}{trade.quantity:>7,.0f}{trade.buy_rate:>10.4f}"
            f"{trade.sell_rate:>11.4f}{trade.cost_base_cad:>14,.2f}"
            f"{trade.proceeds_cad:>16,.2f}{trade.gain_cad:>14,.2f}"
        )

    print("-" * len(header))
    print(f"{'TOTAL':<8}{'':>28}{'':>14}{'':>16}{total_gain:>14,.2f}")
    print()
    print(f"Of that CAD gain, {total_fx:,.2f} came from the exchange rate moving")
    print("between the buy and the sell, not from the position itself.")
    print()
    print("Capital gains treatment (50% inclusion) assumes these are investments.")
    print("Frequent, short-holding-period trading is generally taxed as business")
    print("income at 100% inclusion -- see docs/trader_taxation.md.")
    print()
    print("Rates: Bank of Canada daily indicative rates, the source the CRA")
    print("points at. Not tax advice; confirm each rate before filing.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
