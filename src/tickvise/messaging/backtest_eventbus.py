"""
Event bus that should be used for backtesting instead of the regular event bus.

In live trading, orders get executed as the current period for the observed bar
aggregation period unfolds.
Because of this, a `NewBar` event message for that bar will be received only after the
fills that happened during this bar have been received.

Backtesting and live trading are treated the same wrt. the way strategy implementations
work, as they simply receive the new bar of market data and do what they have to do in
terms of sending or cancelling orders with the broker.
The difference lies within the simulated broker connection.
Since we need to evaluate resting orders against the same `NewBar` event before
strategies see it, we need a mechanism that allows the simulated broker component to
first process the received market data and only then (after fills have been propagated)
the strategy (and other interested components) should see the new bar.

This is why we need a `BacktestEventBus` that implements this two-phased delivery.
"""

from ..brokers.base import BrokerConnectorBase
from ..domain.events import DomainEvents, EventMessageBase, SystemEvents
from .eventbus import EventBus, SubscriberLike


class BacktestEventBus(EventBus):
    """
    Event bus subclass that implements two-phase `NewBar` delivery for backtesting.

    `NewBar` events are first delivered to broker connectors (to evaluate fills against
    the bar), then to all remaining subscribers (e.g., strategies, recorders, etc.)
    after the system has fully drained.

    All non-`NewBar` events are delivered normally via the parent class's non-phased
    delivery mechanism.
    """

    def __init__(self) -> None:
        """
        Initialize the backtest event bus.

        After a `ShutdownDecision` is published, subscriber threads exit and may leave
        unprocessed messages in their queues.
        Waiting for those queues to drain would block forever.

        The `_shutting_down` flag lets `wait_until_system_idle` detect this situation
        and return immediately instead of blocking.
        """
        super().__init__()
        self._shutting_down = False

    def publish(self, event_message: EventMessageBase) -> None:
        """
        Override the parent's `publish` to implement two-phase `NewBar` delivery.

        A `ShutdownDecision` event sets a flag so `wait_until_system_idle` exits
        immediately instead of blocking indefinitely on a queue whose consumer thread
        has already exited.

        Warning:
            The caller must not be publishing from inside its own `_on_event`.
            The idle drain would wait on the caller's own queue, which cannot
            become idle until `_on_event` returns, causing a deadlock.

        Warning:
            An order submitted in reaction to a fill during Phase 1 will not be
            evaluated against the same bar.
            In live trading, such an order would be live for the remainder of the bar
            and could be filled within it.
            Our bar-based simulation architecture cannot model this since the intra-bar
            price sequence is unknown.
            These kinds of strategies would need to be tested on sub-bar market data.

        Warning:
            The Phase 2 drain ensures that orders submitted by strategies in response
            to the bar are resting at the broker before the next bar arrives in the
            next Phase 1.
            This is the closest approximation to live trading given bar-level
            granularity, but may be optimistic for orders intended to fill at the open,
            where real-world calculation and submission latency could cause the
            strategy to miss the opening price.

        Parameters:
            event_message:
                Event message instance to deliver.
        """
        if isinstance(event_message, SystemEvents.ShutdownDecision):
            self._shutting_down = True

        # Regular delivery for all non-`NewBar` event messages
        if not isinstance(event_message, DomainEvents.NewBar):
            super().publish(event_message)
            return

        # For `NewBar` event messages:
        # Phase 1: broker connectors evaluate fills against the bar.
        for subscriber in list(self._per_eventtype_subscriptions[type(event_message)]):
            if isinstance(subscriber, BrokerConnectorBase):
                subscriber.receive(event_message)
        self.wait_until_system_idle()

        # Phase 2: strategies and recorders see the bar with fills already applied.
        for subscriber in list(self._per_eventtype_subscriptions[type(event_message)]):
            if not isinstance(subscriber, BrokerConnectorBase):
                subscriber.receive(event_message)

        # Drain orders strategies submit in response to this bar so they are resting at
        # the broker before the next bar arrives in Phase 1.
        self.wait_until_system_idle()

    def wait_until_system_idle(self) -> None:
        """
        Block until every subscriber in the system is idle.

        Processing events in one component may enqueue new events in others, so this
        loops until all components are simultaneously idle.
        The `_shutting_down` flag causes the loop to exit immediately instead of
        blocking indefinitely on a queue whose consumer thread has already exited.
        """
        while not self._shutting_down:
            all_subscribers: set[SubscriberLike] = set().union(
                *self._per_eventtype_subscriptions.values()
            )
            for subscriber in all_subscribers:
                subscriber.wait_until_idle()
            if all(subscriber.is_idle for subscriber in all_subscribers):
                break
