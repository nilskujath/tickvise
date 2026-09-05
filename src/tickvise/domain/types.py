"""
Type aliases and value types for concepts of the trading domain.

Type aliases are used instead of bare primitives to make function signatures and
dataclass fields self-documenting.

Value types are implemented via named tuple structures.
"""

from datetime import date
from typing import NamedTuple

from .enums import TimeUnit

type UnixNs = int
"""
Nanoseconds since UTC Unix epoch stored as an `int`.

Can be converted to user-readable time by doing a timezone-aware (i.e.
`tz=timezone.utc`) conversion via `datetime`'s `.fromtimestamp` method after first
converting the nanoseconds to seconds (divide by `1e9`).
"""


type ScaledPrice = int
"""
Price multiplied by a fixed scaling factor (typically 1e9) to represent it as an `int`.

Integer arithmetic is faster, deterministic, and avoids the rounding errors inherent to 
floating-point representation of decimal prices.
"""


type SignedPositionSize = int
"""
Position size represented by a (signed) `int`.

Positive sign corresponds to a net long position; negative sign to a net short 
position; zero corresponds to a flattened (no) position.
"""


type Quantity = int
"""
Unsigned quantity assigned to an order request or fill confirmation.

`Quantity` is always a positive value; the direction is conveyed via the `TradeSide`
enum.
"""


type Volume = int
"""
Number of contracts or shares traded during a bar or other aggregation period.
"""


type Multiplier = int
"""
Positive integer scaling factor (e.g., bar period multiplier, contract point
multiplier).
"""


type StrikePrice = float
"""
Strike price of an option contract.

Implementation Note:
    Stored as `float` because strike prices are user-facing values used for instrument
    identification.
    They will be converted to `ScaledPrice` values internally if needed.
"""


type DataSource = str
"""
Identifier for the origin of market data (e.g., information about datafeed provider 
and exchange).
"""


type Ticker = str
"""
Exchange-assigned short code for a tradable instrument (e.g., `"MNQ"`, `"AAPL"`).
"""


type Exchange = str
"""
Identifier for an exchange or trading venue (e.g., `"CME"`, `"NASDAQ"`, `"SMART"`).
"""


type Currency = str
"""
ISO 4217 currency code (e.g., `"USD"`, `"EUR"`).
"""


type Reason = str
"""
Human-readable explanation for a system action that is delivered via an event message. 
"""


type ExpirationDate = date
"""
Expiration or last trade date of a derivative contract.

Example:
    ``ExpirationDate(2025, 9, 19)`` for September 19, 2025.
"""


class BarInterval(NamedTuple):
    """
    Value type that represents a bar aggregation period as a time unit and a multiplier
    (e.g., 5-minute bars would be represented as `BarInterval(TimeUnit.MINUTE, 5)`).

    Parameters:
        time_unit:
            The time unit of the aggregation period.
        multiplier:
            Number of time units per bar.
    """

    time_unit: TimeUnit
    multiplier: Multiplier = 1
