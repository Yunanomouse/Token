"""Non-Yahoo market data providers.

Every provider here is either an exchange operator publishing its own prints,
a central bank / statistical agency, or a regulator filing system. None of
them scrape Yahoo Finance.

Only the Python standard library is required.
"""

from . import providers as _providers  # noqa: F401  (populates the registry)
from .core import (
    Bar,
    FxRate,
    ProviderError,
    fetch_history,
    list_providers,
    PROVIDERS,
)

__all__ = [
    "Bar",
    "FxRate",
    "ProviderError",
    "fetch_history",
    "list_providers",
    "PROVIDERS",
]
__version__ = "0.1.0"
