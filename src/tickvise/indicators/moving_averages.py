"""Module containing moving average indicators."""

# fmt: off
from collections import defaultdict, deque
# fmt: on

from ..domain.events import DomainEvents
from ..domain.instruments import InstrumentBase
from ..domain.types import BarInterval, IndicatorName, IndicatorValue
from .base import IndicatorBase


class SMA(IndicatorBase):
    """
    Simple Moving Average of the source indicator's output values.

    Returns `float("nan")` until enough bars have been received to fill the
    averaging window.

    Example:
        ```python
        sma = SMA(20, Close())
        ```
    """

    def __init__(self, period: int, source: IndicatorBase) -> None:
        """
        Parameters:
            period:
                Number of values to average over. Must be >= 1.
            source:
                The input indicator whose values are averaged. Determines
                `IS_SCALED` — an SMA of prices is scaled, an SMA of volume is not.

        Raises:
            ValueError: If `period` is less than 1.
        """
        if period < 1:
            raise ValueError("period must be positive")
        super().__init__()
        self.IS_SCALED = source.IS_SCALED
        self._period = period
        self._source = self.add_input(source)
        self._sliding_window: defaultdict[
            tuple[InstrumentBase, BarInterval], deque[IndicatorValue]
        ] = defaultdict(lambda: deque(maxlen=self._period))

    @property
    def name(self) -> IndicatorName:
        """
        Returns a unique identifier including the period and source indicator name
        (e.g., `"SMA (20, Close)"`).
        """
        return f"SMA ({self._period}, {self._source.name})"

    def _compute(self, bar: DomainEvents.NewBar) -> IndicatorValue:
        """
        Implementation of the parent class's `_compute` abstract method.

        Appends the source indicator's latest value to the sliding window and
        returns the arithmetic mean once the window is full.

        Parameters:
            bar:
                The completed bar to compute from.

        Returns:
            The arithmetic mean of the last `period` source values, or `float("nan")` if
                the window is not yet full.
        """
        key = (bar.instrument, bar.bar_interval)
        self._sliding_window[key].append(
            self._source[bar.instrument, bar.bar_interval, -1]
        )
        if len(self._sliding_window[key]) < self._period:
            return float("nan")
        return sum(self._sliding_window[key]) / self._period
