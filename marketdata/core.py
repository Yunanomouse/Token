"""Shared plumbing: HTTP, the Bar/FxRate records, and the provider registry.

Standard library only. Every network call goes through :func:`http_json` or
:func:`http_text` so that timeouts, retries, proxies and User-Agent handling
are consistent across providers.
"""

from __future__ import annotations

import gzip
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Any, Callable, Iterable, Sequence

# A descriptive User-Agent is not optional politeness: SEC EDGAR rejects
# requests without one, and TMX/Nasdaq return 403 to the urllib default.
USER_AGENT = (
    "Token-marketdata/0.1 (+https://github.com/Yunanomouse/token) "
    "Python-urllib"
)

DEFAULT_TIMEOUT = 30.0
DEFAULT_RETRIES = 3


class ProviderError(RuntimeError):
    """A provider could not return usable data."""


@dataclass(frozen=True)
class Bar:
    """One OHLCV candle, normalised across providers.

    ``close`` is the exchange's closing print in ``currency``. Providers that
    expose a separately adjusted series populate ``adj_close``; where a
    provider does not, ``adj_close`` is ``None`` rather than a silent copy of
    ``close``, so callers can tell "unadjusted" from "adjusted and unchanged".
    """

    date: date
    open: float
    high: float
    low: float
    close: float
    volume: float
    currency: str
    provider: str
    symbol: str
    adj_close: float | None = None

    def as_row(self) -> dict[str, Any]:
        return {
            "date": self.date.isoformat(),
            "open": self.open,
            "high": self.high,
            "low": self.low,
            "close": self.close,
            "adj_close": "" if self.adj_close is None else self.adj_close,
            "volume": self.volume,
            "currency": self.currency,
            "provider": self.provider,
            "symbol": self.symbol,
        }


@dataclass(frozen=True)
class FxRate:
    """One daily foreign-exchange observation."""

    date: date
    pair: str
    rate: float
    source: str


CSV_COLUMNS = [
    "date",
    "open",
    "high",
    "low",
    "close",
    "adj_close",
    "volume",
    "currency",
    "provider",
    "symbol",
]


def _open(request: urllib.request.Request, timeout: float) -> bytes:
    with urllib.request.urlopen(request, timeout=timeout) as response:
        raw = response.read()
        if response.headers.get("Content-Encoding") == "gzip":
            raw = gzip.decompress(raw)
        return raw


def http_bytes(
    url: str,
    *,
    params: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    data: bytes | None = None,
    method: str | None = None,
    timeout: float = DEFAULT_TIMEOUT,
    retries: int = DEFAULT_RETRIES,
) -> bytes:
    """GET/POST a URL with retry-on-transient-failure.

    Retries cover connection resets, timeouts and 5xx/429 responses with
    exponential backoff. A 4xx other than 429 is a permanent answer and is
    raised immediately -- retrying a bad symbol just wastes the rate limit.
    """
    if params:
        url = f"{url}?{urllib.parse.urlencode(params)}"

    all_headers = {"User-Agent": USER_AGENT, "Accept-Encoding": "gzip"}
    all_headers.update(headers or {})

    last_error: Exception | None = None
    for attempt in range(retries):
        request = urllib.request.Request(
            url, data=data, headers=all_headers, method=method
        )
        try:
            return _open(request, timeout)
        except urllib.error.HTTPError as exc:
            if exc.code not in (429, 500, 502, 503, 504) or attempt == retries - 1:
                body = exc.read()[:400].decode("utf-8", "replace")
                raise ProviderError(
                    f"HTTP {exc.code} from {url}: {body}"
                ) from exc
            last_error = exc
        except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as exc:
            if attempt == retries - 1:
                raise ProviderError(f"could not reach {url}: {exc}") from exc
            last_error = exc
        time.sleep(2**attempt)

    raise ProviderError(f"could not reach {url}: {last_error}")


def http_json(url: str, **kwargs: Any) -> Any:
    payload = kwargs.pop("json", None)
    if payload is not None:
        kwargs["data"] = json.dumps(payload).encode()
        kwargs.setdefault("headers", {})
        kwargs["headers"] = {"Content-Type": "application/json", **kwargs["headers"]}
        kwargs.setdefault("method", "POST")

    raw = http_bytes(url, **kwargs)
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        preview = raw[:200].decode("utf-8", "replace")
        raise ProviderError(f"{url} did not return JSON: {preview!r}") from exc


def http_text(url: str, **kwargs: Any) -> str:
    return http_bytes(url, **kwargs).decode("utf-8", "replace")


def parse_date(value: str | date | datetime | None, *, default: date) -> date:
    if value is None:
        return default
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


def from_epoch(seconds: float) -> date:
    return datetime.fromtimestamp(seconds, tz=timezone.utc).date()


def clean_number(value: Any) -> float:
    """Turn provider-formatted numbers into floats.

    Nasdaq returns ``"$336.13"`` and ``"86,588,200"``; Kraken returns numeric
    strings; TMX returns real JSON numbers. ``"N/A"`` and ``"--"`` mean the
    field is absent.
    """
    if value is None:
        return float("nan")
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().replace("$", "").replace(",", "").replace("%", "")
    if text in ("", "N/A", "--", "-", "null"):
        return float("nan")
    return float(text)


# --- provider registry -------------------------------------------------

HistoryFn = Callable[..., list[Bar]]


@dataclass(frozen=True)
class Provider:
    name: str
    description: str
    asset_classes: tuple[str, ...]
    needs_key: bool
    fetch: HistoryFn = field(repr=False)


PROVIDERS: dict[str, Provider] = {}


def register(
    name: str, description: str, asset_classes: Sequence[str], needs_key: bool = False
) -> Callable[[HistoryFn], HistoryFn]:
    def decorator(fn: HistoryFn) -> HistoryFn:
        PROVIDERS[name] = Provider(
            name=name,
            description=description,
            asset_classes=tuple(asset_classes),
            needs_key=needs_key,
            fetch=fn,
        )
        return fn

    return decorator


def list_providers() -> list[Provider]:
    return sorted(PROVIDERS.values(), key=lambda p: p.name)


def fetch_history(
    symbol: str,
    provider: str,
    start: str | date | None = None,
    end: str | date | None = None,
) -> list[Bar]:
    """Fetch daily bars for ``symbol`` from ``provider``.

    Bars come back oldest-first, de-duplicated by date.
    """
    # Importing here keeps the provider modules from having to be imported
    # before the registry they decorate themselves into exists.
    from . import providers as _providers  # noqa: F401

    try:
        entry = PROVIDERS[provider]
    except KeyError:
        known = ", ".join(sorted(PROVIDERS))
        raise ProviderError(
            f"unknown provider {provider!r}; available: {known}"
        ) from None

    today = datetime.now(timezone.utc).date()
    start_date = parse_date(start, default=date(today.year - 2, today.month, today.day))
    end_date = parse_date(end, default=today)
    if start_date > end_date:
        raise ProviderError(f"start {start_date} is after end {end_date}")

    bars = entry.fetch(symbol, start_date, end_date)
    return dedupe_sorted(bars)


def dedupe_sorted(bars: Iterable[Bar]) -> list[Bar]:
    """Sort oldest-first and drop duplicate dates, keeping the last seen."""
    by_date: dict[date, Bar] = {}
    for bar in bars:
        by_date[bar.date] = bar
    return [by_date[key] for key in sorted(by_date)]


def to_epoch(value: date) -> int:
    """Seconds since the epoch for midnight UTC on ``value``."""
    return int(
        datetime(value.year, value.month, value.day, tzinfo=timezone.utc).timestamp()
    )
