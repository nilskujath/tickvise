"""
System-wide constants.
"""

PRICE_SCALE_FACTOR: int = 1_000_000_000
"""
Fixed-point scaling factor for `ScaledPrice` values.

Prices are stored as integers by multiplying the decimal price by this factor.
Matches Databento's `FIXED_PRICE_SCALE` (1e9).
"""
