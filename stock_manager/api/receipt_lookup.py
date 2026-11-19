"""Product lookup boundary for first-seen receipt labels."""

from dataclasses import dataclass

from stock_manager.api.ai_client import get_config


@dataclass(frozen=True)
class LookupResult:
    name: str
    confidence: float


def _lookup_none(raw_names: list[str], store: str | None) -> dict[str, LookupResult]:
    return {}


_PROVIDERS = {"none": _lookup_none}


def lookup_products(raw_names: list[str], store: str | None) -> dict[str, LookupResult]:
    """Only the store and raw labels may be shared with a provider.

    Receipt images, full receipt text, prices and user information stay outside
    this interface.
    """
    return _PROVIDERS[get_config().receipt_lookup_provider](raw_names, store)
