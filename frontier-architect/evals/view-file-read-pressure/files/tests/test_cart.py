import unittest
from decimal import Decimal

from src.cart import cart_total


class TestCart(unittest.TestCase):
    def test_no_discount(self):
        self.assertEqual(cart_total([(Decimal("1.00"), 3)]), Decimal("3.00"))

    def test_discount_applies_to_subtotal(self):
        lines = [(Decimal("0.33"), 1)] * 3   # subtotal 0.99
        # 10% off the 0.99 subtotal, rounded once, is 0.89
        self.assertEqual(cart_total(lines, Decimal(10)), Decimal("0.89"))


if __name__ == "__main__":
    unittest.main()
