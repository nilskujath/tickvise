"""
Base class for datafeed connector components.
"""

from ..domain.events import EventMessageBase
from ..domain.instruments import InstrumentBase
from ..domain.types import BarInterval
from ..messaging.eventbus import EventBus
from ..messaging.subscriber import ConnectableSubscriberBase


class DatafeedConnectorBase(ConnectableSubscriberBase):
    """
    Abstract base class for components that connect to an external market data source
    and emit `NewBar` events onto the event bus.

    Datafeed connectors only emit events and do not consume any domain events.
    The only event they process is `SystemEvents.ShutdownDecision`, which triggers
    disconnection and shutdown.

    Parameters:
        event_bus:
            Event bus instance to publish market data events through.
        data_subscriptions:
            Set of instrument and bar interval pairs to subscribe to for market data.
    """

    def __init__(
        self,
        event_bus: EventBus,
        data_subscriptions: set[tuple[InstrumentBase, BarInterval]],
    ) -> None:
        self._data_subscriptions = data_subscriptions
        super().__init__(event_bus)

    def _on_event(self, event_message: EventMessageBase) -> None:
        """
        No-op.
        Datafeed connectors only emit events, they do not consume any domain events.
        `SystemEvents.ShutdownDecision` is handled by the parent class event loop.
        """
        pass
