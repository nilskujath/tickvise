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


class Position(NamedTuple):
    """
    A value type that represents a non-flat position.

    The cost basis follows weighted average accounting: each fill's price is weighted
    by its quantity to produce a single blended entry price for the position.
    The alternative would have been to use FIFO (first-in-first-out) accounting, where
    each unit retains its original entry price and partial exits close the oldest units
    first.
    Weighted average was chosen because it requires only a single value instead of a
    queue of individual lots, it matches how most brokers report cost basis,
    and it is sufficient for strategies that only need to know the aggregate position's
    breakeven price rather than the profitability of individual lots (which might be
    important for strategies that work with partial exits).

    Parameters:
        size:
            Signed position size; positive for long, negative for short.
        cost_basis:
            Weighted average entry price per unit of the position.

    Implementation Note:
        A flat position (no position held) is represented by the absence of an entry,
        not by a position with a size of 0 in the parts of the system concerned with
        positions.

        Strategies that require lot-level accounting (e.g., for selective partial exits
        or FIFO-based P&L attribution) can build their own lot tracking from the
        individual `Fill` events they receive.

        However, lot-level state is not restored on reconnect in our system:
        While broker APIs may offer recent fill history, this history is usually
        limited in time range and cannot reliably cover positions held across days or
        weeks.
        Rather than providing lot-level state that is silently incomplete, the system
        restores only the aggregate position, which is always correct and complete.
        Strategies that rely on lot-level tracking should persist and restore
        that state independently, taking into account that this makes the system more
        fragile.
    """

    # fmt: off
    size:       SignedPositionSize
    cost_basis: ScaledPrice
    # fmt: on
