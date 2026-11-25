"""Tiny cart with a percentage discount."""
from decimal import Decimal, ROUND_HALF_UP

CENT = Decimal("0.01")


def line_total(price: Decimal, qty: int, discount_pct: Decimal) -> Decimal:
    """Price of one line after discount, rounded to cents."""
    raw = price * qty * (Decimal(1) - discount_pct / Decimal(100))
    return raw.quantize(CENT, rounding=ROUND_HALF_UP)


def cart_total(lines, discount_pct: Decimal = Decimal(0)) -> Decimal:
    """Sum of per-line discounted totals (discount rounded on every line)."""
    return sum((line_total(p, q, discount_pct) for p, q in lines), Decimal("0.00"))
