"""
Extracts the roundtrips of a run and their statistics from the run's recorded stream of
event messages.
"""

from collections import defaultdict
from collections.abc import Iterable, Iterator
from dataclasses import dataclass

from ..domain.enums import PositionSide
from ..domain.events import DomainEvents, EventMessageBase, SystemEvents
from ..domain.instruments import InstrumentBase
from ..domain.types import (
    Quantity,
    ScaledMonetaryAmount,
    ScaledPrice,
    SignedPositionSize,
    UnixNs,
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
        entry_period_start:
            Start of the aggregation period of the bar during which the position was
                opened, or `None` if it was opened after the last bar of the instrument.
        exit_period_start:
            Start of the aggregation period of the bar during which the position was
                closed, or `None` if it was closed after the last bar of the instrument.
        fills:
            The fills of the roundtrip from entry to exit.
            A fill that flips the position belongs to both the roundtrip it closes and
                the roundtrip it opens.
        pnl:
            Realized PnL of the roundtrip.
        mfe:
            Maximum favorable excursion: the highest PnL (realized plus unrealized) the
                roundtrip reached on any bar it was open, never below zero or `pnl`.
            The entry and exit bars are valued as if their high and low happened while
                the position was held, which may overstate the excursion.
        mae:
            Maximum adverse excursion: the lowest PnL (realized plus unrealized) the
                roundtrip reached on any bar it was open, never above zero or `pnl`.
            The entry and exit bars are valued as if their high and low happened while
                the position was held, which may overstate the excursion.
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
    entry_period_start:     UnixNs | None
    exit_period_start:      UnixNs | None
    fills:                  tuple[DomainEvents.Fill, ...]
    pnl:                    ScaledMonetaryAmount
    mfe:                    ScaledMonetaryAmount
    mae:                    ScaledMonetaryAmount
    holding_period_in_bars: BarCount
    max_position:           Quantity
    # fmt: on


@dataclass(kw_only=True)
class _RoundtripInProgress:
    """
    Data collected to build a `Roundtrip`, from the fill that opens the position until
    its exit bar is complete or the stream of event messages has ended.

    The `Roundtrip` can be built from the collected data at any point after the exit
    fill by calling the `.completed` method.

    Parameters:
        instrument:
            Same as in `Roundtrip`.
        number:
            Same as in `Roundtrip`.
        side:
            Same as in `Roundtrip`.
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
        entry_period_start:
            Same as in `Roundtrip`, but `None` until the first bar of the roundtrip is
                complete.
        exit_period_start:
            Same as in `Roundtrip`, but `None` until the exit bar is complete.
    """

    # fmt: off
    instrument:             InstrumentBase
    number:                 RoundtripNumber
    side:                   PositionSide
    size:                   SignedPositionSize
    cash_flow:              ScaledMonetaryAmount
    max_position:           Quantity
    fills:                  list[DomainEvents.Fill]
    pnl:                    ScaledMonetaryAmount | None = None
    mfe:                    ScaledMonetaryAmount = 0
    mae:                    ScaledMonetaryAmount = 0
    holding_period_in_bars: BarCount = 0
    entry_period_start:     UnixNs | None = None
    exit_period_start:      UnixNs | None = None
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
        return self.cash_flow + self.size * price * self.instrument.multiplier

    def completed(self) -> Roundtrip:
        """
        Return the roundtrip built from the data collected so far.

        Must only be called after the exit fill has set `pnl`.
        The exit price is a point on the roundtrip's path, so the excursions include
        `pnl`.

        Returns:
            The `Roundtrip` built from the collected data.
        """
        assert self.pnl is not None, "The exit fill has not been processed yet."
        return Roundtrip(
            instrument=self.instrument,
            number=self.number,
            side=self.side,
            entry_period_start=self.entry_period_start,
            exit_period_start=self.exit_period_start,
            fills=tuple(self.fills),
            pnl=self.pnl,
            mfe=max(self.mfe, self.pnl),
            mae=min(self.mae, self.pnl),
            holding_period_in_bars=self.holding_period_in_bars,
            max_position=self.max_position,
        )


def extract_roundtrips(events: Iterable[EventMessageBase]) -> Iterator[Roundtrip]:
    """
    Extract all completed roundtrips from a stream of event messages in a single pass.

    A roundtrip is yielded as soon as its exit bar is complete, so the roundtrips of
    each instrument are yielded in the order of their numbers; roundtrips closed after
    the last bar of their instrument are yielded at the end of the event messages.
    Roundtrips still open at the end of the event messages are not yielded, since they
    have no PnL yet.

    Only the roundtrips in progress are held in memory, so `events` can be a lazily read
    recording of any length.

    Parameters:
        events:
            Event messages in the order they were recorded.

    Yields:
        Each completed roundtrip.

    Implementation Note:
        A fill counts towards the bar of the next indicator update of its instrument: a
        bar is only completed once its aggregation period has ended, so the fills that
        happened during the period are recorded before its indicator update.
        Timestamps cannot be used instead, since in backtests they are unrelated to the
        bars' aggregation periods.
        Each instrument is assumed to have indicator updates for a single bar interval
        and from a single strategy only.
        In live trading, a fill recorded after its bar has completed but before the
        bar's indicator update counts towards the previous bar.

        A synthetic fill that opens a roundtrip restores a position whose entry fills
        are not part of the event messages, so the position's cost basis is used as its
        entry price.
    """

    open_roundtrips: dict[InstrumentBase, _RoundtripInProgress] = {}
    closed_this_bar: dict[InstrumentBase, list[_RoundtripInProgress]] = defaultdict(
        list
    )
    roundtrip_count: dict[InstrumentBase, RoundtripNumber] = defaultdict(int)

    for event in events:
        match event:
            case DomainEvents.Fill() as fill:
                instrument = fill.instrument
                size_after = fill.signed_position_size
                open_roundtrip = open_roundtrips.get(instrument)

                if (
                    open_roundtrip is not None
                    and size_after != 0
                    and (size_after > 0) == (open_roundtrip.size > 0)
                ):
                    # Adding to or reducing the position
                    open_roundtrip.fills.append(fill)
                    open_roundtrip.cash_flow -= (
                        (size_after - open_roundtrip.size)
                        * fill.fill_price
                        * instrument.multiplier
                    )
                    open_roundtrip.size = size_after
                    open_roundtrip.max_position = max(
                        open_roundtrip.max_position, abs(size_after)
                    )
                    continue

                if open_roundtrip is not None:
                    # Closing or flipping: the closing part of the fill sets the PnL;
                    # size and cash flow are kept so the exit bar is evaluated with the
                    # position held before the exit
                    open_roundtrip.fills.append(fill)
                    open_roundtrip.pnl = open_roundtrip.pnl_at(fill.fill_price)
                    closed_this_bar[instrument].append(open_roundtrips.pop(instrument))

                if size_after != 0:
                    # Opening a position (from flat or through a flip)
                    entry_price = (
                        fill.position_cost_basis
                        if fill.synthetic and fill.position_cost_basis is not None
                        else fill.fill_price
                    )
                    side = PositionSide.LONG if size_after > 0 else PositionSide.SHORT
                    roundtrip_count[instrument] += 1
                    open_roundtrips[instrument] = _RoundtripInProgress(
                        instrument=instrument,
                        number=roundtrip_count[instrument],
                        side=side,
                        size=size_after,
                        cash_flow=-size_after * entry_price * instrument.multiplier,
                        max_position=abs(size_after),
                        fills=[fill],
                    )

            case SystemEvents.IndicatorUpdate() as indicator_update:
                instrument = indicator_update.instrument
                bar = indicator_update.source_bar

                holding = list(closed_this_bar[instrument])
                if instrument in open_roundtrips:
                    holding.append(open_roundtrips[instrument])

                for roundtrip in holding:
                    if roundtrip.entry_period_start is None:
                        roundtrip.entry_period_start = bar.period_start
                    roundtrip.holding_period_in_bars += 1
                    pnl_at_high = roundtrip.pnl_at(bar.high)
                    pnl_at_low = roundtrip.pnl_at(bar.low)
                    roundtrip.mfe = max(roundtrip.mfe, pnl_at_high, pnl_at_low)
                    roundtrip.mae = min(roundtrip.mae, pnl_at_high, pnl_at_low)

                for roundtrip in closed_this_bar.pop(instrument, []):
                    roundtrip.exit_period_start = bar.period_start
                    yield roundtrip.completed()

    # Roundtrips closed after the last bar of their instrument
    for roundtrips in closed_this_bar.values():
        for roundtrip in roundtrips:
            yield roundtrip.completed()
