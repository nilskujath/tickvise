"""
Enumerations for concepts of the trading domain.
"""

from enum import Enum


class TradeSide(Enum):
    """
    Enumeration of possible trade directions.

    `TradeSide` specifies the direction of change applied to the (net) signed position
    quantity from the perspective of the trading account.
    """

    BUY = "BUY"
    SELL = "SELL"


class TimeUnit(Enum):
    """
    Enumeration of time units recognized by the system (primarily used to define bar
    aggregation period units).
    """

    SECOND = "SECOND"
    MINUTE = "MINUTE"
    HOUR = "HOUR"
    DAY = "DAY"
