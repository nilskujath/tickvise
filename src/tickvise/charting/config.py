"""
Configuration types for the charting module.
"""

from dataclasses import dataclass, field
from enum import Enum, StrEnum, auto

from ..domain.types import IndicatorName

type PlotGroup = int
"""
Panel assignment for an indicator plot.

0 overlays the indicator on the price panel.
Positive integers (1, 2, ...) place the indicator on separate panels below the
price panel.
Negative integers (-1, -2, ...) place the indicator on separate panels above the
price panel.
Indicators sharing the same integer are drawn on the same panel.

Warning:
    -999 is reserved for the position panel (see `POSITION_PANEL_PLOT_GROUP`) and
    must not be used as a plot group for indicators.
"""


POSITION_PANEL_PLOT_GROUP: int = -999
"""
Plot group reserved for the position panel, which is always drawn as the topmost panel 
of each price chart.

Warning:
    Do not assign -999 as the `plot_group` of an indicator. The indicator would be 
    drawn onto the position panel.
"""


type HexColor = str
"""
Hex color string (e.g., "#FF6600").
"""


class BarStyle(Enum):
    """
    Bar rendering style for OHLCV price data.

    `CANDLESTICK` draws a body spanning open to close (white if the close is above
    the open, black otherwise) with wicks extending to the high and low.

    `HL_BAR` draws a vertical line from the low to the high of the bar.

    `HLC_BAR` draws a vertical line from the low to the high of the bar, with a tick
    to the right marking the close.

    `OHLC_BAR` draws a vertical line from the low to the high of the bar, with a
    tick to the left marking the open and a tick to the right marking the close.
    """

    CANDLESTICK = auto()
    HL_BAR = auto()
    HLC_BAR = auto()
    OHLC_BAR = auto()


class PlotStyle(Enum):
    """
    Line style for indicator plots.
    """

    SOLID = auto()
    DASHED = auto()
    DOTTED = auto()
    DASHDOT = auto()
    HISTOGRAM = auto()


class Color(StrEnum):
    """
    Default chart color palette based on matplotlib's tab10 color cycle.
    """

    BLUE = "#1f77b4"
    ORANGE = "#ff7f0e"
    GREEN = "#2ca02c"
    RED = "#d62728"
    PURPLE = "#9467bd"
    BROWN = "#8c564b"
    PINK = "#e377c2"
    GRAY = "#7f7f7f"
    OLIVE = "#bcbd22"
    CYAN = "#17becf"


@dataclass(frozen=True, kw_only=True)
class IndicatorPlotConfig:
    """
    Plot configuration for a single indicator.

    Fields left at None are not overridden and keep the renderer's default.

    Parameters:
        plot_group:
            Panel assignment for the indicator (see `PlotGroup`).
            None keeps the default (scaled indicators on the price panel, unscaled
                indicators on their own panel each).
        style:
            Rendering style for the indicator.
            None keeps the default (`PlotStyle.SOLID`).
        color:
            Color for the indicator. Accepts a Color enum member or a hex color
                string.
            None keeps the default (automatic palette assignment).
        hidden:
            If True, the indicator is excluded from the chart.
    """

    plot_group: PlotGroup | None = None
    style: PlotStyle | None = None
    color: Color | HexColor | None = None
    hidden: bool = False


@dataclass(frozen=True, kw_only=True)
class ChartConfig:
    """
    Complete chart configuration.

    Example:
        ```python
        config = ChartConfig(
            bar_style=BarStyle.HL_BAR,
            indicators={
                "RSI(14)": IndicatorPlotConfig(plot_group=1),
                "MACD(12,26,9)": IndicatorPlotConfig(
                    plot_group=1,
                    style=PlotStyle.HISTOGRAM
                ),
            },
        )
        ```

    Parameters:
        bar_style:
            Rendering style for price bars.
        indicators:
            Per-indicator plot configuration keyed by indicator name.
            Indicators absent from this dict use defaults resolved at render time.
    """

    bar_style: BarStyle = BarStyle.CANDLESTICK
    indicators: dict[IndicatorName, IndicatorPlotConfig] = field(default_factory=dict)
