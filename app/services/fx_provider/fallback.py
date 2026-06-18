from decimal import Decimal

from app.services.fx_provider import FxProvider, register_provider


@register_provider("fallback")
class FallbackProvider(FxProvider):
    _RATES: dict[tuple[str, str], Decimal] = {
        ("USD", "EUR"): Decimal("0.92"),
        ("EUR", "USD"): Decimal("1.09"),
        ("USD", "GBP"): Decimal("0.79"),
        ("GBP", "USD"): Decimal("1.27"),
        ("EUR", "GBP"): Decimal("0.86"),
        ("GBP", "EUR"): Decimal("1.16"),
        ("USD", "NGN"): Decimal("1550.00"),
        ("NGN", "USD"): Decimal("0.000645"),
        ("USD", "XAF"): Decimal("605.00"),
        ("XAF", "USD"): Decimal("0.001653"),
    }

    def fetch_rate(self, source: str, target: str) -> Decimal | None:
        return self._RATES.get((source, target))
