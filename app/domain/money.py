from __future__ import annotations

from decimal import Decimal, InvalidOperation

from app.domain.enums import Currency


class Money:
    """Immutable value object for monetary amounts.

    Rejects float inputs to prevent precision loss.
    Enforces same-currency arithmetic.
    """

    __slots__ = ("_amount", "_currency")

    def __init__(self, amount: Decimal | str | int, currency: Currency | str) -> None:
        if isinstance(amount, float):
            raise TypeError("float is not allowed for Money; use Decimal or str")
        try:
            self._amount = Decimal(str(amount))
        except (InvalidOperation, ValueError) as e:
            raise ValueError(f"Invalid monetary amount: {amount}") from e

        if isinstance(currency, str):
            currency = Currency(currency)
        self._amount = Decimal(str(amount))
        self._currency = currency

    @property
    def amount(self) -> Decimal:
        return self._amount

    @property
    def currency(self) -> Currency:
        return self._currency

    def _check_currency(self, other: Money) -> None:
        if self._currency != other._currency:
            raise ValueError(
                f"Cannot operate on different currencies: "
                f"{self._currency.value} vs {other._currency.value}"
            )

    def __add__(self, other: Money) -> Money:
        if not isinstance(other, Money):
            return NotImplemented
        self._check_currency(other)
        return Money(self._amount + other._amount, self._currency)

    def __sub__(self, other: Money) -> Money:
        if not isinstance(other, Money):
            return NotImplemented
        self._check_currency(other)
        return Money(self._amount - other._amount, self._currency)

    def __neg__(self) -> Money:
        return Money(-self._amount, self._currency)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Money):
            return NotImplemented
        return self._amount == other._amount and self._currency == other._currency

    def __lt__(self, other: Money) -> bool:
        if not isinstance(other, Money):
            return NotImplemented
        self._check_currency(other)
        return self._amount < other._amount

    def __le__(self, other: Money) -> bool:
        if not isinstance(other, Money):
            return NotImplemented
        self._check_currency(other)
        return self._amount <= other._amount

    def __gt__(self, other: Money) -> bool:
        if not isinstance(other, Money):
            return NotImplemented
        self._check_currency(other)
        return self._amount > other._amount

    def __ge__(self, other: Money) -> bool:
        if not isinstance(other, Money):
            return NotImplemented
        self._check_currency(other)
        return self._amount >= other._amount

    def __hash__(self) -> int:
        return hash((self._amount, self._currency))

    def __repr__(self) -> str:
        return f"Money('{self._amount}', '{self._currency.value}')"

    def __str__(self) -> str:
        return f"{self._amount} {self._currency.value}"

    def is_positive(self) -> bool:
        return self._amount > 0

    def is_negative(self) -> bool:
        return self._amount < 0

    def is_zero(self) -> bool:
        return self._amount == 0

    @classmethod
    def zero(cls, currency: Currency | str) -> Money:
        return cls(Decimal("0"), currency)
