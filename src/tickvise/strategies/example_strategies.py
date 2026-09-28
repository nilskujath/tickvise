"""
Example strategy implementations that demonstrate how to subclass `StrategyBase`.

These are educational references and/or dummy strategies to test the system, not
production-ready strategies.
"""

from math import isnan

from ..domain.enums import TradeSide
from ..domain.events import DomainEvents
from ..domain.instruments import InstrumentBase

from ..indicators.bar_fields import Close
from ..indicators.moving_averages import SMA

from ..messaging.eventbus import EventBus

from .base import StrategyBase


class SMACrossover(StrategyBase):
    """
    A simple moving average crossover strategy.

    Goes long when the fast SMA crosses above the slow SMA, and goes short when the
    fast SMA crosses below the slow SMA.
    Trades a single contract at a time with limit orders at the triggering bar's close
    price level.

    Parameters:
        event_bus:
            Event bus instance this component subscribes to and publishes through.
        instruments:
            Set of instruments this strategy trades.
        fast_period:
            Period for the fast SMA.
        slow_period:
            Period for the slow SMA.
    """

    def __init__(
        self,
        event_bus: EventBus,
        instruments: set[InstrumentBase],
        fast_period: int = 10,
        slow_period: int = 20,
    ) -> None:
        """
        Initialize the strategy with its event bus, instruments, and SMA periods.

        Registers a fast and slow SMA indicator, both computed from the triggering
        bar's close price level.

        Parameters:
            event_bus:
                Event bus instance this component subscribes to and publishes through.
            instruments:
                Set of instruments this strategy trades.
            fast_period:
                Period for the fast SMA.
            slow_period:
                Period for the slow SMA.
        """
        super().__init__(event_bus, instruments)
        self._fast_sma = self.register_indicator(SMA(fast_period, Close()))
        self._slow_sma = self.register_indicator(SMA(slow_period, Close()))

    def on_bar(self, event: DomainEvents.NewBar) -> None:
        """
        Implement the abstract `on_bar` method with the crossover logic.

        Skips bars where either SMA has not yet accumulated enough data.
        When the fast SMA crosses above the slow SMA, any short position is flattened
        and a long position is entered.
        When the fast SMA crosses below the slow SMA, any long position is flattened
        and a short position is entered.

        Parameters:
            event:
                The completed bar event.
        """
        fast = self._fast_sma[event.instrument, event.bar_interval, -1]
        slow = self._slow_sma[event.instrument, event.bar_interval, -1]

        if isnan(fast) or isnan(slow):
            return

        pos = self.position()

        if fast > slow and pos <= 0:
            if pos < 0:
                self.submit_order(TradeSide.BUY, 1, event.close)
            self.submit_order(TradeSide.BUY, 1, event.close)

        elif fast < slow and pos >= 0:
            if pos > 0:
                self.submit_order(TradeSide.SELL, 1, event.close)
            self.submit_order(TradeSide.SELL, 1, event.close)
