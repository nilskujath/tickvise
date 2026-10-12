from dataclasses import dataclass

from ..domain.enums import PositionSide
from ..domain.events import DomainEvents
from ..domain.instruments import InstrumentBase
from ..domain.types import Quantity, ScaledMonetaryAmount

type RoundtripNumber = int
"""
Position of a roundtrip among all roundtrips of its instrument within one run, starting
at 1.
This number is only meaningful within the run it was extracted from.
"""


type BarCount = int
"""
Number of bars.
"""


@dataclass(frozen=True, kw_only=True)
class Roundtrip:
    """
    A completed roundtrip on one instrument, from the fill that opens a position to the
    fill that closes it or flips it to commence another roundtrip.

    PnL values are gross of costs and in the instrument's currency (i.e., price points
    times contracts times the instrument's contract multiplier).

    Parameters:
        instrument:
            The instrument the roundtrip was made in.
        number:
            Position of the roundtrip among all roundtrips of its instrument within the
                run (see `RoundtripNumber`).
        side:
            Side of the position held during the roundtrip.
        fills:
            The fills of the roundtrip from entry to exit.
            A fill that flips the position belongs to both the roundtrip it closes and
                the roundtrip it opens.
        pnl:
            Realized PnL of the roundtrip.
        mfe:
            Maximum favorable excursion: the highest PnL (realized plus unrealized) the
                roundtrip reached on any bar it was open, never below zero or `pnl`.
        mae:
            Maximum adverse excursion: the lowest PnL (realized plus unrealized) the
                roundtrip reached on any bar it was open, never above zero or `pnl`.
        holding_period_in_bars:
            Number of bars during which the position was open, including the entry and
                exit bars.
        max_position:
            Largest position size held during the roundtrip.
    """

    # fmt: off
    instrument:             InstrumentBase
    number:                 RoundtripNumber
    side:                   PositionSide
    fills:                  tuple[DomainEvents.Fill, ...]
    pnl:                    ScaledMonetaryAmount
    mfe:                    ScaledMonetaryAmount
    mae:                    ScaledMonetaryAmount
    holding_period_in_bars: BarCount
    max_position:           Quantity
    # fmt: on
