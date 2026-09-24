"""Official Canadian data: Bank of Canada FX and Statistics Canada CPI.

These are the sources the CRA itself points at. A trade filled in USD has to
be reported in CAD, and the CRA accepts the Bank of Canada daily exchange
rate for the trade date (or the annual average for a whole year of similar
transactions). Pulling that rate from the Bank of Canada rather than from a
quote aggregator means the number in a T1 or T2 matches the number the CRA
would look up.

Standard library only. No keys.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from .core import FxRate, ProviderError, http_json, parse_date

VALET = "https://www.bankofcanada.ca/valet"

# Bank of Canada series codes for the daily indicative rates. The Bank
# publishes one observation per business day, around 16:30 ET.
FX_SERIES = {
    "USDCAD": "FXUSDCAD",
    "EURCAD": "FXEURCAD",
    "GBPCAD": "FXGBPCAD",
    "JPYCAD": "FXJPYCAD",
    "AUDCAD": "FXAUDCAD",
    "CHFCAD": "FXCHFCAD",
    "CNYCAD": "FXCNYCAD",
    "MXNCAD": "FXMXNCAD",
    "INRCAD": "FXINRCAD",
    "BRLCAD": "FXBRLCAD",
}

# Overnight policy rate and benchmark bond yields, for discounting and for
# the CRA's prescribed-rate comparisons.
RATE_SERIES = {
    "policy_rate": "V39079",
    "bond_2y": "BD.CDN.2YR.DQ.YLD",
    "bond_5y": "BD.CDN.5YR.DQ.YLD",
    "bond_10y": "BD.CDN.10YR.DQ.YLD",
}

# Statistics Canada vector for the all-items Consumer Price Index, Canada,
# monthly, 2002=100 (table 18-10-0004-01). Indexation of tax brackets is
# driven by this series.
STATCAN_WDS = "https://www150.statcan.gc.ca/t1/wds/rest"
CPI_ALL_ITEMS_CANADA = 41690973


def fx_series(
    pair: str = "USDCAD",
    start: str | date | None = None,
    end: str | date | None = None,
) -> list[FxRate]:
    """Daily Bank of Canada exchange rates for ``pair``.

    ``pair`` may be given as ``USDCAD``, ``USD/CAD`` or ``USD`` -- the quote
    currency is always CAD, because that is all the Bank publishes.
    """
    key = pair.upper().replace("/", "").replace("-", "")
    if len(key) == 3:
        key += "CAD"
    try:
        series = FX_SERIES[key]
    except KeyError:
        known = ", ".join(sorted(FX_SERIES))
        raise ProviderError(
            f"no Bank of Canada series for {pair!r}; available: {known}"
        ) from None

    today = datetime.now(timezone.utc).date()
    start_date = parse_date(start, default=today - timedelta(days=365))
    end_date = parse_date(end, default=today)

    payload = http_json(
        f"{VALET}/observations/{series}/json",
        params={"start_date": start_date.isoformat(), "end_date": end_date.isoformat()},
    )
    observations = payload.get("observations") or []
    if not observations:
        raise ProviderError(
            f"Bank of Canada returned no {series} observations "
            f"between {start_date} and {end_date}"
        )

    rates = []
    for row in observations:
        value = (row.get(series) or {}).get("v")
        if value in (None, ""):
            continue  # holidays carry an empty observation
        rates.append(
            FxRate(
                date=date.fromisoformat(row["d"]),
                pair=f"{key[:3]}/CAD",
                rate=float(value),
                source="bankofcanada",
            )
        )
    return rates


def fx_rate_on(day: str | date, pair: str = "USDCAD") -> FxRate:
    """The rate the CRA would use for a transaction settled on ``day``.

    Markets are shut on weekends and holidays, so this walks back to the most
    recent published business day -- the same convention the CRA's own
    exchange-rate page applies.
    """
    target = parse_date(day, default=datetime.now(timezone.utc).date())
    rates = fx_series(pair, start=target - timedelta(days=10), end=target)
    usable = [r for r in rates if r.date <= target]
    if not usable:
        raise ProviderError(f"no {pair} rate published on or before {target}")
    return usable[-1]


def fx_annual_average(year: int, pair: str = "USDCAD") -> float:
    """The average rate over a calendar year.

    The CRA allows the annual average where a taxpayer has many similar
    transactions spread through the year, instead of a per-trade lookup.
    """
    rates = fx_series(pair, start=date(year, 1, 1), end=date(year, 12, 31))
    if not rates:
        raise ProviderError(f"no {pair} observations published for {year}")
    return sum(r.rate for r in rates) / len(rates)


def policy_rates(
    names: list[str] | None = None,
    start: str | date | None = None,
    end: str | date | None = None,
) -> dict[str, list[tuple[date, float]]]:
    """Bank of Canada policy rate and benchmark bond yields."""
    wanted = names or list(RATE_SERIES)
    unknown = [n for n in wanted if n not in RATE_SERIES]
    if unknown:
        raise ProviderError(
            f"unknown series {unknown}; available: {sorted(RATE_SERIES)}"
        )

    today = datetime.now(timezone.utc).date()
    start_date = parse_date(start, default=today - timedelta(days=365))
    end_date = parse_date(end, default=today)

    codes = [RATE_SERIES[n] for n in wanted]
    payload = http_json(
        f"{VALET}/observations/{','.join(codes)}/json",
        params={"start_date": start_date.isoformat(), "end_date": end_date.isoformat()},
    )

    out: dict[str, list[tuple[date, float]]] = {n: [] for n in wanted}
    for row in payload.get("observations") or []:
        day = date.fromisoformat(row["d"])
        for name, code in zip(wanted, codes):
            value = (row.get(code) or {}).get("v")
            if value not in (None, ""):
                out[name].append((day, float(value)))
    return out


def cpi_all_items(periods: int = 24) -> list[tuple[date, float]]:
    """Statistics Canada all-items CPI for Canada, most recent first-to-last.

    The Web Data Service takes a POST body and returns one object per
    requested vector.
    """
    payload = http_json(
        f"{STATCAN_WDS}/getDataFromVectorsAndLatestNPeriods",
        json=[{"vectorId": CPI_ALL_ITEMS_CANADA, "latestN": periods}],
    )
    if not payload or payload[0].get("status") != "SUCCESS":
        raise ProviderError(f"Statistics Canada rejected the request: {payload}")

    points = payload[0]["object"]["vectorDataPoint"]
    return [(date.fromisoformat(p["refPer"]), float(p["value"])) for p in points]


def cpi_inflation_rate(months: int = 12) -> float:
    """Year-over-year change in the all-items CPI, as a decimal.

    This is the raw inflation read. It is *not* the CRA's bracket indexation
    factor, which is computed from a 12-month average ending 30 September and
    is announced each autumn -- use it as a sanity check, not as a
    substitute.
    """
    series = cpi_all_items(periods=months + 2)
    if len(series) < months + 1:
        raise ProviderError("not enough CPI history to compute a year-over-year rate")
    latest = series[-1][1]
    year_ago = series[-1 - months][1]
    return latest / year_ago - 1.0
