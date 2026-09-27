"""
Base class for implementing technical analysis indicators.
"""

# fmt: off
from abc            import ABC, abstractmethod
from collections    import defaultdict, deque
from copy           import deepcopy
# fmt: on

from ..domain.events import DomainEvents
from ..domain.instruments import InstrumentBase
from ..domain.types import BarInterval, IndicatorValue, IndicatorName

type MaxHistory = int
"""
Maximum number of indicator readings to retain for each observed (instrument, 
bar interval) pair.
"""

type DequeIndex = int
"""
Index used to access a Python `deque` (e.g., `-1` for the most recent value).
"""


class IndicatorBase(ABC):
    """
    Abstract base class for technical indicators.

    An indicator instance applies a single scalar computation to every `NewBar` event
    it receives.
    The computed values are stored in a rolling history keyed by
    `(instrument, bar_interval)`, so one indicator instance automatically tracks
    multiple instruments and timeframes independently.

    Because each indicator produces exactly one scalar value per bar, composite
    indicators like Bollinger Bands are expressed as multiple `IndicatorBase`
    subclasses (e.g., `BollingerUpper`, `BollingerLower`).

    Indicators can reference other indicators as inputs via `add_input`.

    Subclasses must implement the `name` (a unique string identifying the indicator and
    its configuration) and `_compute` (the actual calculation logic) abstract methods.

    Indicator values are accessed via bracket notation::

    Example:
        ```python
        value = my_sma[instrument, BarInterval(TimeUnit.MINUTE, 5), -1]
        ```

    Missing or insufficient data (e.g., during warmup) returns `float("nan")`.
    """

    IS_SCALED: bool = True
    """
    `True` if the indicator's output is in the same scale as the price data (e.g., SMA),
    `False` if it is in an independent scale (e.g., RSI).
    """

    def __init__(self, max_history: MaxHistory = 100) -> None:
        """
        The indicator's history is keyed by `(instrument, bar_interval)` so that a
        single indicator instance can track multiple instruments and the same
        instrument across multiple timeframes independently.

        Warning:
            `max_history` applies only to this indicator's own history. Input
            indicators retain their own independently configured `max_history`.
            If this indicator's `_compute` accesses an input indicator at an index
            deeper than that input's `max_history`, it will return `NaN`.

        Parameters:
            max_history:
                Maximum number of indicator readings to retain for each observed
                (instrument, bar interval) pair. Must be >= 1.

        Raises:
            ValueError: If `max_history` is less than 1.
        """
        if max_history < 1:
            raise ValueError(f"max_history must be >= 1, got {max_history}")
        self._max_history = max_history

        self._history: defaultdict[
            tuple[InstrumentBase, BarInterval], deque[IndicatorValue]
        ] = defaultdict(lambda: deque(maxlen=self._max_history))

        self._input_indicators: dict[IndicatorName, "IndicatorBase"] = {}

    def __getitem__(
        self, key: tuple[InstrumentBase, BarInterval, DequeIndex]
    ) -> IndicatorValue:
        """
        Retrieve a historical indicator value.

        Returns `float("nan")` if the index is out of range (e.g., the indicator
        has not yet received enough bars).

        Parameters:
            key:
                Tuple of `(instrument, bar_interval, deque_index)`. Negative indices
                are supported (e.g., `-1` for the most recent value).

        Returns:
            The indicator value at the given index, or `float("nan")` if unavailable.
        """
        instrument, bar_interval, deque_index = key
        try:
            return self._history[(instrument, bar_interval)][deque_index]
        except IndexError:
            return float("nan")

    @property
    @abstractmethod
    def name(self) -> IndicatorName:
        """
        Abstract property that must be implemented by subclasses.

        Must return a string that uniquely identifies this indicator instance.
        The name is used as a dictionary key for indicator registration and for
        duplicate detection in `add_input`, so two instances with different
        configurations must return different names.

        A recommended pattern is to include the configuration parameters in the
        name via an f-string referencing the `__init__` parameters:

        Example:
            ```python
            @property
            def name(self) -> IndicatorName:
                return f"SMA({self._period})"
            ```
        """
        ...

    def add_input(self, indicator: "IndicatorBase") -> "IndicatorBase":
        """
        Register another indicator as an input to this indicator.

        The input indicator is deep-copied so that the same indicator instance can
        safely be used as input to multiple parent indicators.
        Without the copy, each parent would call `update` on the shared instance, which
        would cause the same bar to be appended to its history multiple times.

        Duplicate input indicator names are rejected because the second registration
        would shadow the first in the internal dictionary, which would leave the caller
        with a stale reference that silently stops receiving updates.

        Input indicators are updated automatically before this indicator computes
        (see `.update`).

        The deep-copied instance is returned so that the caller can hold a reference
        to the copy that actually receives updates.
        Holding a reference to the original instead of the copy would be a bug since
        the original never gets updated and always would return `NaN`.
        This also allows an easy way to add input indicators in the parent indicator's
        `__init__` method:

        ```
        self._sma = self.add_input(SMA(<period>))
        ```

        Parameters:
            indicator:
                The indicator to register as an input.

        Returns:
            The deep-copied indicator instance that was actually registered.

        Raises:
            ValueError: If an input indicator with the same name has already been
                registered.
        """
        indicator = deepcopy(indicator)

        if indicator.name in self._input_indicators:
            raise ValueError(f"duplicate input indicator {indicator.name!r}")
        self._input_indicators[indicator.name] = indicator

        return indicator

    def update(self, bar: DomainEvents.NewBar) -> None:
        """
        Process a new bar of market data by first updating all input indicators and then
        computing and storing the newly calculated indicator value.

        Parameters:
            bar:
                The completed bar to compute from.
        """
        for indicator in self._input_indicators.values():
            indicator.update(bar)
        self._history[(bar.instrument, bar.bar_interval)].append(self._compute(bar))

    @abstractmethod
    def _compute(self, bar: DomainEvents.NewBar) -> IndicatorValue:
        """
        Abstract method that must be implemented by subclasses to compute the
        indicator's value from a new bar.
        This is where the actual indicator logic lives.

        Input indicators have already been updated when this is called, so their latest
        values are available for use in the computation.

        Parameters:
            bar:
                The completed bar to compute from.

        Returns:
            The computed indicator value.
        """
        ...
