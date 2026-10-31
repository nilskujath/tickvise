"""
Generates charts of roundtrips: price charts around single roundtrips, and journey
charts summarizing all roundtrips of an instrument.
"""

from collections import defaultdict, deque
from collections.abc import Iterable, Iterator
from itertools import accumulate, chain
from statistics import mean

from matplotlib.figure import Figure
from matplotlib.ticker import MaxNLocator

from ..analysis.roundtrips import BarCount, Roundtrip
from ..domain.constants import SCALE_FACTOR
from ..domain.events import EventMessageBase, InstrumentRelated, SystemEvents
from ..domain.instruments import InstrumentBase
from ..domain.types import UnixNs
from .config import ChartConfig
from .price_chart import generate_price_charts


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
    # Each roundtrip once, even if passed more than once (it would be collected twice)
    for roundtrip in dict.fromkeys(roundtrips):
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


def generate_roundtrip_charts(
    events: Iterable[EventMessageBase],
    roundtrips: Iterable[Roundtrip],
    context_bars: BarCount = 20,
    config: ChartConfig | None = None,
) -> dict[Roundtrip, Figure]:
    """
    Generate one price chart per roundtrip, from `context_bars` bars before its entry
    bar to `context_bars` bars after its exit bar.

    The caller chooses the roundtrips to chart (e.g., the five with the lowest PnL).
    The event messages are read in a single pass, so they can come straight from a
    recording read one event message at a time; since the roundtrips are extracted
    from the same event messages beforehand, the recording is read twice.

    Example:
        ```python
        path = Path("recording.pkl")
        roundtrips = list(extract_roundtrips(PickleRecorder.read(path)))
        worst = sorted(roundtrips, key=lambda roundtrip: roundtrip.pnl)[:5]
        charts = generate_roundtrip_charts(PickleRecorder.read(path), worst)
        for roundtrip, figure in charts.items():
            figure.savefig(f"roundtrip_{roundtrip.number}.png")
        ```

    Parameters:
        events:
            Event messages in the order they were recorded, i.e., the same event
                messages the roundtrips were extracted from.
        roundtrips:
            The roundtrips to chart.
        context_bars:
            Number of bars shown before the entry bar and after the exit bar; fewer at
                the start and end of the event messages.
        config:
            Chart configuration. If None, all defaults are used.

    Returns:
        Mapping of each roundtrip to its figure.

    Raises:
        ValueError:
            If the entry bar of a roundtrip is not part of the event messages.
    """
    windows = _events_around_roundtrips(events, roundtrips, context_bars)
    return {
        roundtrip: generate_price_charts(window, config)[roundtrip.instrument]
        for roundtrip, window in windows.items()
    }


def generate_journey_charts(
    roundtrips: Iterable[Roundtrip],
) -> dict[InstrumentBase, Figure]:
    """
    Generate one journey chart per instrument, summarizing its roundtrips.

    Each figure consists of the following panels, from top to bottom, all with the
    roundtrip number on the x-axis: the cumulative PnL panel (net and gross PnL summed
    over the roundtrips in the order of their numbers), the journey panel (one bar per
    roundtrip from its MAE to its MFE, widened with its holding period, with a black
    tick at its PnL, and dashed lines at the average PnL of winners and losers), and
    the holding period panel (holding period in bars).
    The journey panel is gross of costs, since MAE and MFE are price movements; its
    winners are drawn in green and its losers in red, and a roundtrip with a gross PnL
    of zero counts as a loser.
    An info box on each panel, placed where it covers the least data, lists summary
    statistics of what the panel shows.

    Amounts are in the currency of the instrument.

    Parameters:
        roundtrips:
            The roundtrips to chart (e.g., all roundtrips extracted from a run).

    Returns:
        Mapping of each instrument found in `roundtrips` to its figure.

    Implementation Note:
        The maximum drawdown in the info box of the cumulative PnL panel is measured
        on the cumulative net PnL at the exits of the roundtrips, starting from zero,
        so a drawdown within a roundtrip is not part of it.
    """

    roundtrips_by_instrument: dict[InstrumentBase, list[Roundtrip]] = defaultdict(list)
    for roundtrip in roundtrips:
        roundtrips_by_instrument[roundtrip.instrument].append(roundtrip)

    figures: dict[InstrumentBase, Figure] = {}

    for instrument, instrument_roundtrips in roundtrips_by_instrument.items():
        instrument_roundtrips.sort(key=lambda roundtrip: roundtrip.number)
        winners = [
            roundtrip for roundtrip in instrument_roundtrips if roundtrip.pnl > 0
        ]
        losers = [
            roundtrip for roundtrip in instrument_roundtrips if roundtrip.pnl <= 0
        ]

        # ——————————————————————————————————————————————————————————————————————————————
        # Create an empty figure with the three panels

        figure: Figure = Figure(figsize=(16, 11))
        pnl_axes, journey_axes, holding_axes = figure.subplots(
            nrows=3, sharex=True, gridspec_kw={"height_ratios": [3, 6, 2]}
        )

        # ——————————————————————————————————————————————————————————————————————————————
        # Draw the cumulative net and gross PnL onto the cumulative PnL panel

        numbers = [roundtrip.number for roundtrip in instrument_roundtrips]
        pnls = [roundtrip.pnl / SCALE_FACTOR for roundtrip in instrument_roundtrips]
        net_pnls = [
            roundtrip.net_pnl / SCALE_FACTOR for roundtrip in instrument_roundtrips
        ]
        cumulative_net_pnls = list(accumulate(net_pnls))

        pnl_axes.plot(
            numbers,
            cumulative_net_pnls,
            color="black",
            lw=1.2,
            marker="o",
            ms=3,
            label="Net",
        )
        pnl_axes.plot(
            numbers, list(accumulate(pnls)), color="gray", lw=1, ls="--", label="Gross"
        )
        pnl_axes.axhline(y=0, color="gray", lw=0.5)

        # ——————————————————————————————————————————————————————————————————————————————
        # Draw the journeys onto the journey panel

        # Bar widths range from 0.2 (no bars held) to 0.9 (longest holding period)
        longest_holding_period = max(
            roundtrip.holding_period_in_bars for roundtrip in instrument_roundtrips
        )
        widths = {
            roundtrip: 0.2
            + 0.7 * roundtrip.holding_period_in_bars / (longest_holding_period or 1)
            for roundtrip in instrument_roundtrips
        }

        for group, color, label in (
            (winners, "green", "Winners"),
            (losers, "red", "Losers"),
        ):
            journey_axes.bar(
                [roundtrip.number for roundtrip in group],
                [(roundtrip.mfe - roundtrip.mae) / SCALE_FACTOR for roundtrip in group],
                bottom=[roundtrip.mae / SCALE_FACTOR for roundtrip in group],
                width=[widths[roundtrip] for roundtrip in group],
                color=color,
                alpha=0.7,
                label=label,
            )

        journey_axes.hlines(
            pnls,
            [
                roundtrip.number - widths[roundtrip] / 2
                for roundtrip in instrument_roundtrips
            ],
            [
                roundtrip.number + widths[roundtrip] / 2
                for roundtrip in instrument_roundtrips
            ],
            colors="black",
            lw=1.5,
            zorder=5,
            label="PnL",
        )
        winner_pnls = [roundtrip.pnl / SCALE_FACTOR for roundtrip in winners]
        loser_pnls = [roundtrip.pnl / SCALE_FACTOR for roundtrip in losers]
        if winner_pnls:
            journey_axes.axhline(
                y=mean(winner_pnls),
                color="darkgreen",
                ls="--",
                lw=1.2,
                label="Average winner",
            )
        if loser_pnls:
            journey_axes.axhline(
                y=mean(loser_pnls),
                color="darkred",
                ls="--",
                lw=1.2,
                label="Average loser",
            )
        journey_axes.axhline(y=0, color="gray", lw=0.5)

        # ——————————————————————————————————————————————————————————————————————————————
        # Draw the holding periods onto the holding period panel

        holding_axes.bar(
            numbers,
            [roundtrip.holding_period_in_bars for roundtrip in instrument_roundtrips],
            width=0.8,
            color="black",
            alpha=0.5,
        )

        # ——————————————————————————————————————————————————————————————————————————————
        # Write the summary statistics into an info box on each panel

        equity = [0.0, *cumulative_net_pnls]
        max_drawdown = max(
            peak - value for peak, value in zip(accumulate(equity, max), equity)
        )
        total_costs = (
            sum(roundtrip.costs for roundtrip in instrument_roundtrips) / SCALE_FACTOR
        )
        win_rate = len(winners) / len(instrument_roundtrips)
        winner_bars = [roundtrip.holding_period_in_bars for roundtrip in winners]
        loser_bars = [roundtrip.holding_period_in_bars for roundtrip in losers]
        mfes = [roundtrip.mfe / SCALE_FACTOR for roundtrip in instrument_roundtrips]
        maes = [roundtrip.mae / SCALE_FACTOR for roundtrip in instrument_roundtrips]

        pnl_info = "\n".join(
            [
                f"Net total     {sum(net_pnls):+,.2f}",
                f"Costs         {total_costs:,.2f}",
                f"Gross total   {sum(pnls):+,.2f}",
                f"Avg net       {mean(net_pnls):+,.2f}",
                f"Max drawdown  {max_drawdown:,.2f}",
            ]
        )
        journey_info = "\n".join(
            [
                f"Roundtrips    {len(instrument_roundtrips)}",
                f"Winners       {len(winners)} ({win_rate:.1%})",
                f"Losers        {len(losers)}",
                (
                    f"Avg winner    {mean(winner_pnls):+,.2f}"
                    if winner_pnls
                    else "Avg winner    n/a"
                ),
                (
                    f"Avg loser     {mean(loser_pnls):+,.2f}"
                    if loser_pnls
                    else "Avg loser     n/a"
                ),
                f"Best          {max(pnls):+,.2f}",
                f"Worst         {min(pnls):+,.2f}",
                f"Avg MFE       {mean(mfes):+,.2f}",
                f"Highest MFE   {max(mfes):+,.2f}",
                f"Avg MAE       {mean(maes):+,.2f}",
                f"Lowest MAE    {min(maes):+,.2f}",
            ]
        )
        holding_info = "\n".join(
            [
                (
                    f"Winners  avg {mean(winner_bars):.1f}, max {max(winner_bars)}"
                    if winners
                    else "Winners  n/a"
                ),
                (
                    f"Losers   avg {mean(loser_bars):.1f}, max {max(loser_bars)}"
                    if losers
                    else "Losers   n/a"
                ),
            ]
        )

        # Each info box is the title of the panel's legend (which has no entries on the
        # holding period panel), so matplotlib places it where it covers the least data
        for panel_axes, info in (
            (pnl_axes, pnl_info),
            (journey_axes, journey_info),
            (holding_axes, holding_info),
        ):
            handles, labels = panel_axes.get_legend_handles_labels()
            panel_axes.legend(
                handles,
                labels,
                title=info,
                loc="best",
                alignment="left",
                fontsize=8,
                title_fontproperties={"family": "monospace", "size": 8},
            )

        # ——————————————————————————————————————————————————————————————————————————————
        # Style the figure (axis labels, integer roundtrip numbers, title, spacing)

        pnl_axes.set_ylabel(f"Cumulative PnL ({instrument.currency})")
        journey_axes.set_ylabel(f"Gross PnL ({instrument.currency})")
        holding_axes.set_ylabel("Bars")
        holding_axes.set_xlabel("Roundtrip")
        holding_axes.xaxis.set_major_locator(MaxNLocator(integer=True))
        # A fixed margin beyond the widest bar keeps the axis from reaching back to a
        # roundtrip 0, which does not exist
        holding_axes.set_xlim(numbers[0] - 0.75, numbers[-1] + 0.75)
        for panel_axes in (pnl_axes, journey_axes, holding_axes):
            panel_axes.grid(True, axis="y", alpha=0.3)

        figure.suptitle(f"{instrument.ticker}  roundtrip journeys", fontsize=10)

        # Tighten the panel spacing and margins, leaving 0.2 inches for the title
        figure.tight_layout(rect=(0, 0, 1, 1 - 0.2 / figure.get_figheight()))

        figures[instrument] = figure

    return figures
