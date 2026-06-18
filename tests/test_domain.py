from decimal import Decimal

import pytest

from app.domain.enums import Currency
from app.domain.money import Money


class TestMoneyCreation:
    def test_create_from_decimal(self):
        m = Money(Decimal("10.50"), Currency.USD)
        assert m.amount == Decimal("10.50")
        assert m.currency == Currency.USD

    def test_create_from_string(self):
        m = Money("10.50", Currency.USD)
        assert m.amount == Decimal("10.50")

    def test_create_from_int(self):
        m = Money(10, Currency.USD)
        assert m.amount == Decimal("10")

    def test_create_from_currency_string(self):
        m = Money("100", "USD")
        assert m.currency == Currency.USD

    def test_reject_float(self):
        with pytest.raises(TypeError, match="float is not allowed"):
            Money(10.50, Currency.USD)

    def test_reject_invalid_amount(self):
        with pytest.raises(ValueError, match="Invalid monetary amount"):
            Money("not-a-number", Currency.USD)

    def test_reject_invalid_currency(self):
        with pytest.raises(ValueError):
            Money("100", "INVALID")

    def test_zero_factory(self):
        m = Money.zero(Currency.EUR)
        assert m.amount == Decimal("0")
        assert m.currency == Currency.EUR
        assert m.is_zero()


class TestMoneyArithmetic:
    def test_add_same_currency(self):
        a = Money("10.00", Currency.USD)
        b = Money("5.50", Currency.USD)
        result = a + b
        assert result == Money("15.50", Currency.USD)

    def test_subtract_same_currency(self):
        a = Money("10.00", Currency.USD)
        b = Money("3.25", Currency.USD)
        result = a - b
        assert result == Money("6.75", Currency.USD)

    def test_negate(self):
        m = Money("10.00", Currency.USD)
        result = -m
        assert result == Money("-10.00", Currency.USD)

    def test_add_different_currency_raises(self):
        a = Money("10.00", Currency.USD)
        b = Money("10.00", Currency.EUR)
        with pytest.raises(ValueError, match="Cannot operate on different currencies"):
            a + b

    def test_subtract_different_currency_raises(self):
        a = Money("10.00", Currency.USD)
        b = Money("10.00", Currency.GBP)
        with pytest.raises(ValueError, match="Cannot operate on different currencies"):
            a - b


class TestMoneyComparison:
    def test_equality(self):
        assert Money("10.00", Currency.USD) == Money("10.00", Currency.USD)

    def test_inequality_amount(self):
        assert Money("10.00", Currency.USD) != Money("20.00", Currency.USD)

    def test_inequality_currency(self):
        assert Money("10.00", Currency.USD) != Money("10.00", Currency.EUR)

    def test_less_than(self):
        assert Money("5.00", Currency.USD) < Money("10.00", Currency.USD)

    def test_greater_than(self):
        assert Money("10.00", Currency.USD) > Money("5.00", Currency.USD)

    def test_less_equal(self):
        assert Money("10.00", Currency.USD) <= Money("10.00", Currency.USD)

    def test_greater_equal(self):
        assert Money("10.00", Currency.USD) >= Money("10.00", Currency.USD)

    def test_compare_different_currency_raises(self):
        with pytest.raises(ValueError, match="Cannot operate on different currencies"):
            Money("10.00", Currency.USD) < Money("10.00", Currency.EUR)


class TestMoneyPredicates:
    def test_is_positive(self):
        assert Money("10.00", Currency.USD).is_positive()
        assert not Money("-10.00", Currency.USD).is_positive()
        assert not Money("0", Currency.USD).is_positive()

    def test_is_negative(self):
        assert Money("-10.00", Currency.USD).is_negative()
        assert not Money("10.00", Currency.USD).is_negative()

    def test_is_zero(self):
        assert Money("0", Currency.USD).is_zero()
        assert not Money("10.00", Currency.USD).is_zero()


class TestMoneyHashable:
    def test_hashable(self):
        m1 = Money("10.00", Currency.USD)
        m2 = Money("10.00", Currency.USD)
        assert hash(m1) == hash(m2)
        assert len({m1, m2}) == 1

    def test_repr(self):
        m = Money("10.50", Currency.USD)
        assert repr(m) == "Money('10.50', 'USD')"

    def test_str(self):
        m = Money("10.50", Currency.USD)
        assert str(m) == "10.50 USD"
