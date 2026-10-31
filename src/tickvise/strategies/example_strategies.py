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
    Holds a single contract at a time and trades with limit orders at the triggering
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

        Skips bars where either SMA has not yet accumulated enough data, or where both
        are equal.
        Otherwise, the target position is one contract long while the fast SMA is above
        the slow SMA, and one contract short while it is below, and a single order
        covers the difference between the target and the current position.
        An order that has not filled within the bar after its submission is cancelled,
        and no new order is submitted before the broker has confirmed the cancellation:
        until then, the order could still fill, and a new order on top of it could
        overshoot the target position.

        Parameters:
            event:
                The completed bar event.
        """
        fast = self._fast_sma[event.instrument, event.bar_interval, -1]
        slow = self._slow_sma[event.instrument, event.bar_interval, -1]

        if isnan(fast) or isnan(slow) or fast == slow:
            return

        if self.pending_orders() or self.active_orders():
            cancelling = {cancel.order_id for cancel in self.pending_cancels()}
            for order in self.active_orders():
                if order.order_id not in cancelling:
                    self.submit_cancel(order.order_id)
            return

        target_position = 1 if fast > slow else -1
        position = self.position()
        if position < target_position:
            self.submit_order(TradeSide.BUY, target_position - position, event.close)
        elif position > target_position:
            self.submit_order(TradeSide.SELL, position - target_position, event.close)
