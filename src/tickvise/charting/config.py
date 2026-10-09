"""
Configuration types for the charting module.
"""

from dataclasses import dataclass, field
from enum import Enum, auto

from ..domain.types import IndicatorName

type PlotGroup = int | None
"""
Panel assignment for an indicator plot.

None excludes the indicator from the chart.
0 overlays the indicator on the price panel.
Positive integers (1, 2, ...) place the indicator on separate panels below the
price panel.
Negative integers (-1, -2, ...) place the indicator on separate panels above the
price panel.
Indicators sharing the same integer are drawn on the same panel.
"""


type HexColor = str
"""
Hex color string (e.g., "#FF6600").
"""


class BarStyle(Enum):
    """
    Bar rendering style for OHLCV price data.
    """

    CANDLESTICK = auto()
    BAR = auto()
    CBAR = auto()
    OCBAR = auto()


class PlotStyle(Enum):
    """
    Line style for indicator plots.
    """

    SOLID = auto()
    DASHED = auto()
    DOTTED = auto()
    DASHDOT = auto()
    HISTOGRAM = auto()


class Color(Enum):
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

    Parameters:
        plot_group:
            Panel assignment for the indicator.
            None suppresses the indicator from the chart entirely.
            0 overlays the indicator on the price panel.
            Positive integers (1, 2, ...) place the indicator on separate panels
                below the price panel.
                Indicators sharing the same positive integer are drawn on the same
                sub-panel.
            Negative integers (-1, -2, ...) place the indicator on separate panels
                above the price panel.
                Indicators sharing the same negative integer are drawn on the same
                sub-panel.
        style:
            Rendering style for the indicator line.
        color:
            Explicit color override. Accepts a Color enum member or a hex color
                string.
            None defers to the renderer's automatic palette assignment.
    """

    plot_group: PlotGroup | None = 0
    style: PlotStyle = PlotStyle.SOLID
    color: Color | HexColor | None = None


@dataclass(frozen=True, kw_only=True)
class ChartConfig:
    """
    Complete chart configuration.

    Example:
        ```python
        config = ChartConfig(
            bar_style=BarStyle.BAR,
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
