from collections import defaultdict, deque
from collections.abc import Iterable, Iterator
from itertools import chain

from ..analysis.roundtrips import BarCount, Roundtrip
from ..domain.events import EventMessageBase, InstrumentRelated, SystemEvents
from ..domain.instruments import InstrumentBase
from ..domain.types import UnixNs


def _split_into_bars(
    events: Iterable[EventMessageBase],
) -> Iterator[tuple[InstrumentBase, UnixNs | None, list[EventMessageBase]]]:
    """
    Split event messages into the bars of their instruments.

    Parameters:
        events:
            Event messages in the order they were recorded.

    Yields:
        The instrument, the period start and the event messages of each bar, as soon
            as the bar is complete; the event messages recorded after the last bar of
            an instrument as a final bar with period start `None`.

    Implementation Note:
        The event messages of a bar are those of its instrument recorded after the
        indicator update of the previous bar, up to and including the bar's own
        indicator update, as for the extraction of roundtrips.
    """
    current_bar: dict[InstrumentBase, list[EventMessageBase]] = defaultdict(list)
    for event in events:
        if not isinstance(event, InstrumentRelated):
            continue
        current_bar[event.instrument].append(event)
        if isinstance(event, SystemEvents.IndicatorUpdate):
            period_start = event.source_bar.period_start
            yield event.instrument, period_start, current_bar.pop(event.instrument)
    for instrument, bar_events in current_bar.items():
        yield instrument, None, bar_events


def _events_around_roundtrips(
    events: Iterable[EventMessageBase],
    roundtrips: Iterable[Roundtrip],
    context_bars: BarCount,
) -> dict[Roundtrip, list[EventMessageBase]]:
    """
    Return the event messages of each roundtrip's instrument from `context_bars` bars
    before its entry bar to `context_bars` bars after its exit bar.

    The event messages are not filtered (e.g., they include the fills of neighboring
    roundtrips), so a price chart of them shows what happened around the roundtrip.

    Parameters:
        events:
            Event messages in the order they were recorded, i.e., the same event
                messages the roundtrips were extracted from.
        roundtrips:
            The roundtrips to collect the event messages for.
        context_bars:
            Number of bars before the entry bar and after the exit bar; fewer at the
                start and end of the event messages.

    Returns:
        The event messages around each roundtrip, in the order they were recorded.

    Raises:
        ValueError:
            If the entry bar of a roundtrip is not part of the event messages.
    """
    starting: dict[tuple[InstrumentBase, UnixNs | None], list[Roundtrip]] = defaultdict(
        list
    )
    for roundtrip in roundtrips:
        starting[(roundtrip.instrument, roundtrip.entry_period_start)].append(roundtrip)

    recent_bars: dict[InstrumentBase, deque[list[EventMessageBase]]] = defaultdict(
        lambda: deque(maxlen=context_bars)
    )
    open_windows: dict[InstrumentBase, list[Roundtrip]] = defaultdict(list)
    bars_after_exit_left: dict[Roundtrip, BarCount] = {}
    windows: dict[Roundtrip, list[EventMessageBase]] = {}

    for instrument, period_start, bar_events in _split_into_bars(events):
        for roundtrip in starting.pop((instrument, period_start), []):
            windows[roundtrip] = list(chain.from_iterable(recent_bars[instrument]))
            open_windows[instrument].append(roundtrip)
        recent_bars[instrument].append(bar_events)

        for roundtrip in open_windows[instrument]:
            windows[roundtrip].extend(bar_events)
            if roundtrip.exit_period_start == period_start:
                bars_after_exit_left[roundtrip] = context_bars
            elif roundtrip in bars_after_exit_left:
                bars_after_exit_left[roundtrip] -= 1
        open_windows[instrument] = [
            roundtrip
            for roundtrip in open_windows[instrument]
            if bars_after_exit_left.get(roundtrip) != 0
        ]

    if starting:
        (instrument, period_start), missing = next(iter(starting.items()))
        raise ValueError(
            f"Entry bar of roundtrip {missing[0].number} of {instrument.ticker} "
            f"(period start {period_start}) is not part of the event messages"
        )

    return windows
