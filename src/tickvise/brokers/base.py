"""
Base class for broker connector components.
"""

from abc import abstractmethod

from ..domain.events import (
    EventMessageBase,
    InstrumentRelated,
    DomainEvents,
)
from ..domain.instruments import InstrumentBase
from ..messaging.eventbus import EventBus
from ..messaging.subscriber import ConnectableSubscriberBase


class BrokerConnectorBase(ConnectableSubscriberBase):
    """
    Abstract base class for components that connect to an external broker API (or a
    simulated external broker API for backtesting purposes) and handle order
    submission, cancellation, and fill reporting.

    A broker connector subscribes to `OrderRequest` and `CancellationRequest`
    events and emits order lifecycle events (`OrderSubmitted`, `OrderRejected`,
    `OrderCancelled`, `CancellationRejected`, `Fill`, `OrderExpired`) in response.

    On initialization (after connecting), `_emit_account_state` is called to emit
    synthetic events that restore the system's view of existing positions and working
    orders at the broker.

    Danger:
        Strategies must be constructed before broker connectors so that they
        are already subscribed to the event bus when `_emit_account_state`
        emits synthetic events during initialization. Otherwise, strategies
        will miss the initial position and working order state.

    Warning:
        Broker connectors filter events by instrument, which allows multiple broker
        connectors on the same event bus, each responsible for a different set of
        instruments (multi-broker trading).
        However, two connectors must not manage the same instrument: both would
        independently process the same order requests, and the resulting duplicate
        fill events would corrupt the subscribing strategy's position state.

    Parameters:
        event_bus:
            Event bus instance to subscribe to and publish through.
        instruments:
            Set of instruments managed by this broker connector.
    """

    SUBSCRIBE_TO = (
        DomainEvents.OrderRequest,
        DomainEvents.CancellationRequest,
    )
    """
    All broker connectors subscribe to `OrderRequest` and `CancellationRequest` events.
    """

    def __init__(self, event_bus: EventBus, instruments: set[InstrumentBase]) -> None:
        """
        Set up the broker connector with its managed instruments, connect to the
        broker, and emit the current account state.

        This necessitates that strategies must be constructed before broker connectors
        so that they are already subscribed to the event bus when `_emit_account_state`
        emits synthetic events during initialization. Otherwise, strategies will miss
        the initial position and working order state.

        Parameters:
            event_bus:
                Event bus instance to subscribe to and publish through.
            instruments:
                Set of instruments managed by this broker connector.
        """
        # `_instruments` must be set before `super().__init__` because
        # `super().__init__` calls `_connect()`, which may use them.
        self._instruments = instruments
        super().__init__(event_bus)
        # `_emit_account_state()` must be called after `super().__init__`
        # because it emits events, which requires the event bus set up by `super()`.
        self._emit_account_state()

    @abstractmethod
    def _emit_account_state(self) -> None:
        """
        Abstract method that must be implemented by subclasses to emit synthetic events
        that restore the system's view of the broker account.

        Called once during initialization, after connecting. Should emit a synthetic
        `Fill` for each open position and a synthetic `OrderSubmitted` for each working
        order to restore each strategy's internal position, cost basis, and active
        order state.
        """
        ...

    def _on_event(self, event_message: EventMessageBase) -> None:
        """
        Implementation of the parent class's `_on_event` abstract method.

        Routes incoming event messages to the appropriate handler after filtering
        out events for instruments not managed by this connector.
        """
        if (
            isinstance(event_message, InstrumentRelated)
            and event_message.instrument not in self._instruments
        ):
            return

        match event_message:
            case DomainEvents.OrderRequest():
                self._on_order_request(event_message)
            case DomainEvents.CancellationRequest():
                self._on_cancellation_request(event_message)

    @abstractmethod
    def _on_order_request(self, event_message: DomainEvents.OrderRequest) -> None:
        """
        Abstract method that must be implemented by subclasses to handle an incoming
        order request.

        The implementation should submit the order through the broker's API and emit
        the appropriate order lifecycle events (`OrderSubmitted`, `OrderRejected`,
        `Fill`, `OrderExpired`) as they occur.

        Parameters:
            event_message:
                The order request to process.
        """
        ...

    @abstractmethod
    def _on_cancellation_request(
        self, event_message: DomainEvents.CancellationRequest
    ) -> None:
        """
        Abstract method that must be implemented by subclasses to handle an incoming
        cancellation request.

        The implementation should submit the cancellation through the broker's API
        and emit the appropriate event (`OrderCancelled` or `CancellationRejected`)
        as the broker responds.

        Parameters:
            event_message:
                The cancellation request to process.
        """
        ...
