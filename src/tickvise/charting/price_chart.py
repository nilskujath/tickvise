"""
Generates price charts from event messages (e.g., as recorded by `PickleRecorder`).
"""

import math

from bisect import bisect_left
from collections import defaultdict
from datetime import datetime, timezone
from itertools import count
from typing import Any

from matplotlib.axes import Axes
import matplotlib.dates as mdates
from matplotlib.figure import Figure
from matplotlib.patches import FancyBboxPatch
from matplotlib.path import Path as MplPath

from ..domain.constants import PRICE_SCALE_FACTOR
from ..domain.enums import TimeUnit, TradeSide
from ..domain.events import (
    DomainEvents,
    EventMessageBase,
    InstrumentRelated,
    SystemEvents,
)
from ..domain.instruments import InstrumentBase
from ..domain.types import IndicatorName
from .config import (
    POSITION_PANEL_PLOT_GROUP,
    BarStyle,
    ChartConfig,
    Color,
    IndicatorPlotConfig,
    PlotStyle,
)

NS_PER_DAY: int = 86_400_000_000_000
"""
Number of nanoseconds in a day.

Used to convert `UnixNs` timestamps to matplotlib dates, which count days since
1970-01-01.
"""

DAYS_PER_TIME_UNIT: dict[TimeUnit, float] = {
    TimeUnit.SECOND: 1 / 86_400,
    TimeUnit.MINUTE: 1 / 1_440,
    TimeUnit.HOUR: 1 / 24,
    TimeUnit.DAY: 1,
}
"""
Length of each time unit in days, the unit of matplotlib's date axis.

Used to convert bar intervals to x-axis widths and offsets.
"""

LINESTYLES: dict[PlotStyle, str] = {
    PlotStyle.SOLID: "-",
    PlotStyle.DASHED: "--",
    PlotStyle.DOTTED: ":",
    PlotStyle.DASHDOT: "-.",
}
"""
Matplotlib line style for each line-based `PlotStyle` (`PlotStyle.HISTOGRAM` is drawn
as bars and has no line style).
"""

PALETTE: list[Color] = list(Color)
"""
Colors assigned to indicators by default, cycled through in the order of the
indicators' readings.
"""

BUY_MARKER: MplPath = MplPath(
    [(0, 0), (-1, -2), (1, -2), (0, 0)],
    [MplPath.MOVETO, MplPath.LINETO, MplPath.LINETO, MplPath.CLOSEPOLY],
)
"""
Upward-pointing triangle marking buy fills.

Its tip is at the origin, which matplotlib anchors to the data point, so the tip
points exactly at the fill price.
"""

SELL_MARKER: MplPath = MplPath(
    [(0, 0), (-1, 2), (1, 2), (0, 0)],
    [MplPath.MOVETO, MplPath.LINETO, MplPath.LINETO, MplPath.CLOSEPOLY],
)
"""
Downward-pointing triangle marking sell fills.

Its tip is at the origin, which matplotlib anchors to the data point, so the tip
points exactly at the fill price.
"""


def generate_price_charts(
    events: list[EventMessageBase],
    config: ChartConfig | None = None,
) -> dict[InstrumentBase, Figure]:
    """
    Generate one price chart per instrument from a list of event messages.

    Events are grouped by the instrument they relate to; events not related to an
    instrument (e.g., `ShutdownDecision`) are ignored.
    Every instrument gets a figure, even one without bars (e.g., with only a fill from
    a position restored on reconnect), so that no instrument activity goes unnoticed.

    Each figure consists of the following panels, from top to bottom: the position
    panel (signed position size), panels for indicators with negative plot groups, the
    price panel (price bars, indicators with plot group 0, fill markers, and profit and
    loss shading around the cost basis while a position is open), and panels for
    indicators with positive plot groups.
    The background of all panels is shaded while a position is open.

    Bars and indicator readings are taken from `IndicatorUpdate` events (every `NewBar`
    produces exactly one); fills and position data are taken from `Fill` events.

    Indicator plot configs are resolved per instrument (because of the possibility of
    multi-strategy runs): by default, scaled indicators are drawn on the price panel
    and unscaled indicators each on their own panel below it, with colors assigned from
    the `Color` palette.
    Fields set in `config` override these defaults; fields left at None keep them.

    Parameters:
        events:
            Event messages to chart (e.g., all events recorded by `PickleRecorder`, or
                a pre-filtered slice of them).
        config:
            Chart configuration. If None, all defaults are used.

    Returns:
        Mapping of each instrument found in `events` to its figure.

    Implementation Note:
        Event timestamps are wall-clock times, not market times: every event's
        `timestamp` is set via `time_ns()` when the event is created, and
        `SimulatedDatafeed` restamps replayed bars the same way.
        In live trading, both are the same.
        In a backtest, they are far apart: a bar from March 2025 replayed in October
        2026 has a `period_start` in March 2025 but a `timestamp` in October 2026.

        The x-axis of the chart is in market time, since bars are drawn at their
        `period_start`.
        Fills carry no market time, only their wall-clock `timestamp`, so drawing a
        fill at its timestamp would place it far away from the bars in a backtest.

        Since all event timestamps come from the same clock and events are created in
        order, the timestamps still reliably order fills relative to bars.
        Each fill is therefore assigned to the bar it happened in (the first bar
        completing at or after the fill) and drawn at that bar's `period_start`.
        Event timestamps decide which bar a fill belongs to, but are never used as
        x-positions.

        The only exception are instruments without bars, which have no market time at
        all.
        Their fills are drawn at their own timestamps, which is consistent within the
        figure since everything in it is on the same clock.

        Figures are created via `Figure` instead of `pyplot`, so they are not kept
        alive in pyplot's global figure registry, which matters when generating many
        charts (e.g., one per roundtrip).
    """

    figures: dict[InstrumentBase, Figure] = {}

    # ——————————————————————————————————————————————————————————————————————————————————
    # Group events by the instrument they are associated to and their type
    events_by_instrument_and_type: dict[InstrumentBase, dict[type, list[Any]]] = (
        defaultdict(lambda: defaultdict(list))
    )

    for event in events:
        if isinstance(event, InstrumentRelated):
            events_by_instrument_and_type[event.instrument][type(event)].append(event)

    # ——————————————————————————————————————————————————————————————————————————————————
    # Construct the figure for each instrument
    for instrument, events_by_type_dict in events_by_instrument_and_type.items():

        # ——————————————————————————————————————————————————————————————————————————————
        # Resolve chart config settings (overwrite default config with user config)

        # Create default chart config as fallback
        example_indicator_readings = (
            events_by_type_dict[SystemEvents.IndicatorUpdate][0].readings
            if events_by_type_dict[SystemEvents.IndicatorUpdate]
            else {}
        )
        auto_plot_groups = count(1)
        default_config = ChartConfig(
            indicators={
                name: IndicatorPlotConfig(
                    plot_group=0 if reading.is_scaled else next(auto_plot_groups),
                    style=PlotStyle.SOLID,
                    color=PALETTE[i % len(PALETTE)],
                )
                for i, (name, reading) in enumerate(example_indicator_readings.items())
            }
        )

        # Overwrite default chart config with user provided chart config (if any);
        # only fields the user set (not None) override the default
        if config is None:
            chart_config = default_config
        else:
            indicators: dict[IndicatorName, IndicatorPlotConfig] = {}
            for name, default in default_config.indicators.items():
                user = config.indicators.get(name, IndicatorPlotConfig())
                indicators[name] = IndicatorPlotConfig(
                    plot_group=(
                        user.plot_group
                        if user.plot_group is not None
                        else default.plot_group
                    ),
                    style=user.style or default.style,
                    color=user.color or default.color,
                    hidden=user.hidden,
                )
            chart_config = ChartConfig(
                bar_style=config.bar_style, indicators=indicators
            )

        # ——————————————————————————————————————————————————————————————————————————————
        # Create an empty figure with the necessary panels (resolved via plot groups)

        # Determine which panels are needed (position panel + price panel + one panel
        # per distinct plot group)
        plot_groups: set[int] = {POSITION_PANEL_PLOT_GROUP, 0}  # always needed plots
        for plot_config in chart_config.indicators.values():
            if not plot_config.hidden:
                plot_groups.add(plot_config.plot_group)
        panel_order: list[int] = sorted(plot_groups)

        # Determine panel heights; height_ratios[i] is the height of panel_order[i]
        height_ratios: list[int] = []
        for plot_group in panel_order:
            if plot_group == POSITION_PANEL_PLOT_GROUP:
                height_ratios.append(2)
            elif plot_group == 0:
                height_ratios.append(9)
            else:
                height_ratios.append(3)

        # Create the figure; axes[i] is the panel of panel_order[i]
        figure: Figure = Figure(figsize=(16, sum(height_ratios)))
        axes = figure.subplots(
            nrows=len(panel_order),
            sharex=True,
            gridspec_kw={"height_ratios": height_ratios},
        )
        axes_by_plot_group: dict[int, Axes] = dict(zip(panel_order, axes))

        # ——————————————————————————————————————————————————————————————————————————————
        # Draw the price bars onto the price panel

        price_axes = axes_by_plot_group[0]

        for indicator_update in events_by_type_dict[SystemEvents.IndicatorUpdate]:
            bar = indicator_update.source_bar

            # Matplotlib dates are days since 1970-01-01, like Unix time
            x = bar.period_start / NS_PER_DAY
            interval_days = (
                DAYS_PER_TIME_UNIT[bar.bar_interval.time_unit]
                * bar.bar_interval.multiplier
            )
            bar_open = bar.open / PRICE_SCALE_FACTOR
            bar_high = bar.high / PRICE_SCALE_FACTOR
            bar_low = bar.low / PRICE_SCALE_FACTOR
            bar_close = bar.close / PRICE_SCALE_FACTOR

            match chart_config.bar_style:
                case BarStyle.CANDLESTICK:
                    candle_width = interval_days * 0.8
                    body_bottom = min(bar_open, bar_close)
                    body_top = max(bar_open, bar_close)
                    price_axes.add_patch(
                        FancyBboxPatch(
                            (x - candle_width / 2, body_bottom),
                            candle_width,
                            (body_top - body_bottom) or (bar_high - bar_low) * 0.01,
                            boxstyle="square,pad=0",
                            facecolor="white" if bar_close > bar_open else "black",
                            edgecolor="black",
                            lw=0.5,
                            alpha=0.7,
                        )
                    )
                    if body_bottom > bar_low:
                        price_axes.plot(
                            [x, x],
                            [bar_low, body_bottom],
                            color="black",
                            lw=0.8,
                            alpha=0.7,
                        )
                    if body_top < bar_high:
                        price_axes.plot(
                            [x, x],
                            [body_top, bar_high],
                            color="black",
                            lw=0.8,
                            alpha=0.7,
                        )

                case BarStyle.HL_BAR:
                    price_axes.plot(
                        [x, x],
                        [bar_low, bar_high],
                        color="black",
                        lw=0.8,
                        alpha=0.7,
                    )

                case BarStyle.HLC_BAR:
                    tick_width = interval_days * 0.3
                    price_axes.plot(
                        [x, x],
                        [bar_low, bar_high],
                        color="black",
                        lw=0.8,
                        alpha=0.7,
                    )
                    price_axes.plot(
                        [x, x + tick_width],
                        [bar_close, bar_close],
                        color="black",
                        lw=0.8,
                        alpha=0.7,
                    )

                case BarStyle.OHLC_BAR:
                    tick_width = interval_days * 0.3
                    price_axes.plot(
                        [x, x],
                        [bar_low, bar_high],
                        color="black",
                        lw=0.8,
                        alpha=0.7,
                    )
                    price_axes.plot(
                        [x - tick_width, x],
                        [bar_open, bar_open],
                        color="black",
                        lw=0.8,
                        alpha=0.7,
                    )
                    price_axes.plot(
                        [x, x + tick_width],
                        [bar_close, bar_close],
                        color="black",
                        lw=0.8,
                        alpha=0.7,
                    )

        # ——————————————————————————————————————————————————————————————————————————————
        # Draw the indicators onto their panels

        for name, plot_config in chart_config.indicators.items():
            if plot_config.hidden:
                continue

            # Collect the indicator's values over time (skipping NaNs from warmup)
            indicator_x: list[float] = []
            indicator_y: list[float] = []
            for indicator_update in events_by_type_dict[SystemEvents.IndicatorUpdate]:
                reading = indicator_update.readings[name]
                if math.isnan(reading.value):
                    continue
                indicator_x.append(
                    indicator_update.source_bar.period_start / NS_PER_DAY
                )
                indicator_y.append(
                    reading.value / PRICE_SCALE_FACTOR
                    if reading.is_scaled
                    else reading.value
                )

            indicator_axes = axes_by_plot_group[plot_config.plot_group]
            color = plot_config.color

            match plot_config.style:
                case PlotStyle.HISTOGRAM:
                    bar_interval = events_by_type_dict[SystemEvents.IndicatorUpdate][
                        0
                    ].source_bar.bar_interval
                    indicator_axes.bar(
                        indicator_x,
                        indicator_y,
                        width=DAYS_PER_TIME_UNIT[bar_interval.time_unit]
                        * bar_interval.multiplier
                        * 0.8,
                        color=color,
                        alpha=0.7,
                        label=name,
                    )
                case _:
                    indicator_axes.plot(
                        indicator_x,
                        indicator_y,
                        lw=1.2,
                        color=color,
                        linestyle=LINESTYLES[plot_config.style],
                        label=name,
                    )

        # Add a legend to every panel that has labeled plots
        for panel_axes in axes_by_plot_group.values():
            if panel_axes.get_legend_handles_labels()[1]:
                panel_axes.legend(loc="upper left", fontsize=8)

        # ——————————————————————————————————————————————————————————————————————————————
        # Draw the fill markers onto the price panel

        # Each fill is drawn on the bar it happened in (the first bar completing at or
        # after the fill); fills after the last bar go one interval past it, and fills
        # of instruments without bars are drawn at their own timestamp
        bar_completion_times: list[int] = [
            u.timestamp for u in events_by_type_dict[SystemEvents.IndicatorUpdate]
        ]
        fill_xs: list[float] = []  # x position of each fill, reused for the cost basis
        for fill in events_by_type_dict[DomainEvents.Fill]:
            k = bisect_left(bar_completion_times, fill.timestamp)
            if k < len(bar_completion_times):
                # Fill happened during the k-th bar
                bar = events_by_type_dict[SystemEvents.IndicatorUpdate][k].source_bar
                x = bar.period_start / NS_PER_DAY
            elif bar_completion_times:
                # Fill happened after the last bar: draw it one interval past it
                bar = events_by_type_dict[SystemEvents.IndicatorUpdate][-1].source_bar
                x = (
                    bar.period_start / NS_PER_DAY
                    + DAYS_PER_TIME_UNIT[bar.bar_interval.time_unit]
                    * bar.bar_interval.multiplier
                )
            else:
                # No bars at all (fills-only instrument): only the fill's own time exists
                x = fill.timestamp / NS_PER_DAY
            fill_xs.append(x)

            is_buy = fill.trade_side is TradeSide.BUY
            price_axes.scatter(
                x,
                fill.fill_price / PRICE_SCALE_FACTOR,
                marker=BUY_MARKER if is_buy else SELL_MARKER,
                color="green" if is_buy else "red",
                edgecolors="green" if is_buy else "red",
                s=80,
                lw=0.5,
                zorder=5,
            )

        # ——————————————————————————————————————————————————————————————————————————————
        # Shade profit and loss zones around the cost basis while a position is open

        # Split the fills into one segment per position (entry to exit, or to a flip
        # between long and short); each segment is a step line of the cost basis
        segments: list[tuple[list[float], list[float], bool]] = []
        segment_x: list[float] = []
        segment_y: list[float] = []
        segment_is_long = True

        for fill, x in zip(events_by_type_dict[DomainEvents.Fill], fill_xs):
            is_flat = fill.position_cost_basis is None
            is_flip = not is_flat and (fill.signed_position_size > 0) != segment_is_long
            if segment_y and (is_flat or is_flip):
                segment_x.append(x)
                segment_y.append(segment_y[-1])
                segments.append((segment_x, segment_y, segment_is_long))
                segment_x, segment_y = [], []
            if not is_flat:
                segment_x.append(x)
                segment_y.append(fill.position_cost_basis / PRICE_SCALE_FACTOR)
                segment_is_long = fill.signed_position_size > 0

        # A position still open at the end of the data runs to the last bar
        if segment_y:
            if events_by_type_dict[SystemEvents.IndicatorUpdate]:
                last_bar = events_by_type_dict[SystemEvents.IndicatorUpdate][
                    -1
                ].source_bar
                segment_x.append(max(last_bar.period_start / NS_PER_DAY, segment_x[-1]))
            else:
                segment_x.append(segment_x[-1])
            segment_y.append(segment_y[-1])
            segments.append((segment_x, segment_y, segment_is_long))

        # Shade above and below each segment (extended by half a bar on both ends);
        # the y-limits are fixed first so the shading doesn't stretch the price axis
        if events_by_type_dict[SystemEvents.IndicatorUpdate]:
            first_bar = events_by_type_dict[SystemEvents.IndicatorUpdate][0].source_bar
            half_bar = (
                DAYS_PER_TIME_UNIT[first_bar.bar_interval.time_unit]
                * first_bar.bar_interval.multiplier
                / 2
            )
        else:
            half_bar = 0
        y_min, y_max = price_axes.get_ylim()

        for segment_x, segment_y, is_long in segments:
            shade_x = (
                [segment_x[0] - half_bar] + segment_x[1:] + [segment_x[-1] + half_bar]
            )
            shade_y = segment_y + [segment_y[-1]]
            price_axes.fill_between(
                shade_x,
                shade_y,
                y_max,
                step="post",
                color="green" if is_long else "red",
                alpha=0.08,
                zorder=0,
            )
            price_axes.fill_between(
                shade_x,
                y_min,
                shade_y,
                step="post",
                color="red" if is_long else "green",
                alpha=0.08,
                zorder=0,
            )
        price_axes.set_ylim(y_min, y_max)

        # ——————————————————————————————————————————————————————————————————————————————
        # Draw the position size onto the position panel

        position_axes = axes_by_plot_group[POSITION_PANEL_PLOT_GROUP]

        # Position after the last fill of each bar, keyed by bar index
        position_after_bar: dict[int, int] = {}
        for fill in events_by_type_dict[DomainEvents.Fill]:
            k = bisect_left(bar_completion_times, fill.timestamp)
            position_after_bar[k] = fill.signed_position_size

        # One position bar per bar interval from the first to the last bar; each shows
        # the larger of the positions before and after it (so entry and exit bars show
        # the position), and gaps without bars carry the position forward
        position_x: list[float] = []
        position_size: list[int] = []
        if events_by_type_dict[SystemEvents.IndicatorUpdate]:
            first_bar = events_by_type_dict[SystemEvents.IndicatorUpdate][0].source_bar
            last_bar = events_by_type_dict[SystemEvents.IndicatorUpdate][-1].source_bar
            interval_days = (
                DAYS_PER_TIME_UNIT[first_bar.bar_interval.time_unit]
                * first_bar.bar_interval.multiplier
            )
            interval_ns = round(interval_days * NS_PER_DAY)
            bar_index_by_period_start: dict[int, int] = {
                u.source_bar.period_start: k
                for k, u in enumerate(events_by_type_dict[SystemEvents.IndicatorUpdate])
            }

            position = 0
            for period_start in range(
                first_bar.period_start, last_bar.period_start + interval_ns, interval_ns
            ):
                k = bar_index_by_period_start.get(period_start)
                if k is None:
                    shown = position
                else:
                    position_before = position
                    position = position_after_bar.get(k, position)
                    shown = (
                        position
                        if abs(position) >= abs(position_before)
                        else position_before
                    )
                if shown != 0:
                    position_x.append(period_start / NS_PER_DAY)
                    position_size.append(shown)

            if position_x:
                position_axes.bar(
                    position_x,
                    position_size,
                    width=interval_days * 0.8,
                    color="black",
                    alpha=0.5,
                    label="Position Size",
                )
                position_axes.legend(loc="upper left", fontsize=8)

        position_axes.axhline(y=0, color="gray", lw=0.5, ls="-")

        # ——————————————————————————————————————————————————————————————————————————————
        # Shade the background of all panels while a position is open

        # One span per position, from its entry bar to its exit bar (both included);
        # flips keep the position open, and a position still open at the end of the
        # data runs to the last bar
        position_spans: list[tuple[float, float]] = []
        entry_x: float | None = None
        for fill, x in zip(events_by_type_dict[DomainEvents.Fill], fill_xs):
            if fill.position_cost_basis is not None and entry_x is None:
                entry_x = x
            elif fill.position_cost_basis is None and entry_x is not None:
                position_spans.append((entry_x, x))
                entry_x = None
        if entry_x is not None:
            if events_by_type_dict[SystemEvents.IndicatorUpdate]:
                last_bar = events_by_type_dict[SystemEvents.IndicatorUpdate][
                    -1
                ].source_bar
                position_spans.append(
                    (entry_x, max(last_bar.period_start / NS_PER_DAY, entry_x))
                )
            else:
                position_spans.append((entry_x, fill_xs[-1]))

        for start_x, end_x in position_spans:
            for panel_axes in axes_by_plot_group.values():
                panel_axes.axvspan(
                    start_x - half_bar,
                    end_x + half_bar,
                    color="lightgray",
                    alpha=0.1,
                    zorder=0,
                )

        # ——————————————————————————————————————————————————————————————————————————————
        # Style the figure (x-range, date axis, title, panel spacing)

        bottom_axes = axes_by_plot_group[panel_order[-1]]

        if events_by_type_dict[SystemEvents.IndicatorUpdate]:
            first_bar = events_by_type_dict[SystemEvents.IndicatorUpdate][0].source_bar
            last_bar = events_by_type_dict[SystemEvents.IndicatorUpdate][-1].source_bar
            bar_interval = first_bar.bar_interval
            interval_days = (
                DAYS_PER_TIME_UNIT[bar_interval.time_unit] * bar_interval.multiplier
            )

            # One bar interval of padding on both sides (on the right, past the last
            # bar or the last fill, whichever is later)
            bottom_axes.set_xlim(
                first_bar.period_start / NS_PER_DAY - interval_days,
                max([last_bar.period_start / NS_PER_DAY, *fill_xs]) + interval_days,
            )

            match bar_interval.time_unit:
                case TimeUnit.SECOND:
                    tick_locator = mdates.SecondLocator(bysecond=range(0, 60, 10))
                case TimeUnit.MINUTE:
                    tick_locator = mdates.MinuteLocator(byminute=range(0, 60, 10))
                case TimeUnit.HOUR:
                    tick_locator = mdates.HourLocator(byhour=range(0, 24, 8))
                case TimeUnit.DAY:
                    tick_locator = mdates.DayLocator(interval=1)
                case _:
                    raise ValueError(f"unsupported time unit: {bar_interval.time_unit}")
            bottom_axes.xaxis.set_major_locator(tick_locator)

            start_ns, end_ns = first_bar.period_start, last_bar.period_start
            interval_text = f"  {bar_interval.multiplier} {bar_interval.time_unit.name}"
        else:
            # No bars: the time range comes from the instrument's own events
            timestamps = [
                e.timestamp for es in events_by_type_dict.values() for e in es
            ]
            start_ns, end_ns = min(timestamps), max(timestamps)
            bottom_axes.set_xlim(
                start_ns / NS_PER_DAY - DAYS_PER_TIME_UNIT[TimeUnit.MINUTE],
                end_ns / NS_PER_DAY + DAYS_PER_TIME_UNIT[TimeUnit.MINUTE],
            )
            interval_text = ""

        bottom_axes.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m-%d %H:%M:%S"))
        bottom_axes.tick_params(axis="x", labelrotation=90, labelsize=8)

        # Title: instrument, bar interval, and time range
        label_parts = [instrument.ticker]
        if (expiry := getattr(instrument, "expiry", None)) is not None:
            label_parts.append(str(expiry))
        strike = getattr(instrument, "strike", None)
        right = getattr(instrument, "right", None)
        if strike is not None and right is not None:
            label_parts.append(f"{right.name[0]}{strike:g}")
        start_text, end_text = (
            datetime.fromtimestamp(ns / 1_000_000_000, tz=timezone.utc).strftime(
                "%Y-%m-%d %H:%M:%S"
            )
            for ns in (start_ns, end_ns)
        )
        figure.suptitle(
            f"{' '.join(label_parts)}{interval_text}  {start_text} to {end_text}",
            fontsize=10,
        )

        # Tighten the panel spacing and margins, leaving 0.2 inches for the title
        figure.tight_layout(rect=(0, 0, 1, 1 - 0.2 / figure.get_figheight()))

        figures[instrument] = figure

    return figures
