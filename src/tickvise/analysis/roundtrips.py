from dataclasses import dataclass
from typing import NamedTuple

from ..domain.enums import PositionSide
from ..domain.events import DomainEvents, EventMessageBase
from ..domain.instruments import InstrumentBase
from ..domain.types import (
    Multiplier,
    Quantity,
    ScaledMonetaryAmount,
    ScaledPrice,
    SignedPositionSize,
)

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


class RoundtripWindow(NamedTuple):
    """
    The event messages of a roundtrip's instrument recorded during the roundtrip and
    during a number of bars before and after it (the left and right context of the
    roundtrip).

    The three parts (`left_context`, `holding_period`, and `right_context`) follow each
    other without gaps, so together they are an unfiltered excerpt of the recording
    (including, e.g., the fills of neighboring roundtrips if they happened within the
    window).

    Parameters:
        left_context:
            Event messages of the bars before the bar the position was opened in.
        holding_period:
            Event messages of the bars from the one the position was opened in to the
                one it was closed in.
        right_context:
            Event messages of the bars after the one the position was closed in.
    """

    # fmt: off
    left_context:   list[EventMessageBase]
    holding_period: list[EventMessageBase]
    right_context:  list[EventMessageBase]
    # fmt: on


type RoundtripWithWindow = tuple[Roundtrip, RoundtripWindow]
"""
A completed roundtrip together with its window.
"""


@dataclass(kw_only=True)
class _RoundtripInProgress:
    """
    Data collected to build a `Roundtrip` and its `RoundtripWindow`, from the fill that
    opens the position, at which point the left context is already final, until the
    right context after its exit is complete or the stream of event messages has ended.

    The `Roundtrip` and its `RoundtripWindow` can be built from the collected data at
    any point after the exit fill by calling the `.completed` method.

    Parameters:
        instrument:
            Same as in `Roundtrip`.
        number:
            Same as in `Roundtrip`.
        side:
            Same as in `Roundtrip`.
        multiplier:
            Not part of `Roundtrip`.
            Contract multiplier of the instrument, used to value the position in the
                instrument's currency.
        size:
            Not part of `Roundtrip`.
            Signed position size after the last processed fill of the roundtrip,
                not counting its exit fill.
        cash_flow:
            Not part of `Roundtrip`.
            Net amount of money paid (negative) and received (positive) through the
                fills of the roundtrip processed so far, not counting its exit fill.
            Together with `size`, it gives the PnL at any price (see `pnl_at`): the
                cash flow so far plus the cash flow of closing the position at that
                price.
        max_position:
            Same as in `Roundtrip`, up to the last processed fill.
        fills:
            Differs from `Roundtrip`: the fills of the roundtrip processed so far, as a
                list; calling `.completed` copies them into a tuple for use within
                `Roundtrip`.
        pnl:
            Differs from `Roundtrip`: `None` while the position is open and set only
                once, by the exit fill, to the PnL of the whole roundtrip (the cash flow
                plus the cash flow of closing the position at the exit price).
            Partial exits before that do not change it; the PnL they realize is
                contained in `cash_flow`.
        mfe:
            Differs from `Roundtrip`: the highest PnL at the high or low of any bar
                processed so far, never below zero.
            The entry and exit bars are valued as if their high and low happened while
                the position was held, which may overstate the excursion.
        mae:
            Differs from `Roundtrip`: the lowest PnL at the high or low of any bar
                processed so far, never above zero.
            The entry and exit bars are valued as if their high and low happened while
                the position was held, which may overstate the excursion.
        holding_period_in_bars:
            Same as in `Roundtrip`, up to the last processed bar.
        left_context:
            Not part of `Roundtrip`.
            Event messages of the bars before the bar the position was opened in; final
                from the start.
        holding_period:
            Not part of `Roundtrip`.
            Event messages of the bars from the one the position was opened in to the
                one it was closed in, collected so far.
        right_context:
            Not part of `Roundtrip`.
            Event messages of the bars after the one the position was closed in,
                collected so far.
        right_context_bars:
            Not part of `Roundtrip`.
            Number of bars whose event messages have been collected in `right_context`
                so far.
    """

    # fmt: off
    instrument:             InstrumentBase
    number:                 RoundtripNumber
    side:                   PositionSide
    multiplier:             Multiplier
    size:                   SignedPositionSize
    cash_flow:              ScaledMonetaryAmount
    max_position:           Quantity
    fills:                  list[DomainEvents.Fill]
    pnl:                    ScaledMonetaryAmount | None = None
    mfe:                    ScaledMonetaryAmount = 0
    mae:                    ScaledMonetaryAmount = 0
    holding_period_in_bars: BarCount = 0
    left_context:           list[EventMessageBase]
    holding_period:         list[EventMessageBase]
    right_context:          list[EventMessageBase]
    right_context_bars:     BarCount = 0
    # fmt: on

    def pnl_at(self, price: ScaledPrice) -> ScaledMonetaryAmount:
        """
        Return the PnL (realized plus unrealized) of the roundtrip with its position
        valued at the given price.

        Parameters:
            price:
                Price at which the position is valued.

        Returns:
            The cash flow so far plus the cash flow of closing the position at `price`.
        """
        return self.cash_flow + self.size * price * self.multiplier

    def completed(self) -> RoundtripWithWindow:
        """
        Return the roundtrip and its window, built from the data collected so far.

        Must only be called after the exit fill has set `pnl`.
        The exit price is a point on the roundtrip's path, so the excursions include
        `pnl`.

        Returns:
            The `Roundtrip` built from the collected data, together with the
                `RoundtripWindow` of the collected event messages.
        """
        assert self.pnl is not None, "The exit fill has not been processed yet."
        roundtrip = Roundtrip(
            instrument=self.instrument,
            number=self.number,
            side=self.side,
            fills=tuple(self.fills),
            pnl=self.pnl,
            mfe=max(self.mfe, self.pnl),
            mae=min(self.mae, self.pnl),
            holding_period_in_bars=self.holding_period_in_bars,
            max_position=self.max_position,
        )
        window = RoundtripWindow(
            left_context=self.left_context,
            holding_period=self.holding_period,
            right_context=self.right_context,
        )
        return roundtrip, window
