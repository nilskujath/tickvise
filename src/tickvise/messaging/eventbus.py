# fmt: off
from typing         import Protocol
from collections    import defaultdict
# fmt: on


# fmt: off
from ..domain.events    import EventMessageBase
# fmt: on


class SubscriberLike(Protocol):
    """
    Protocol class that must be satisfied by those system components that are designed
    around reacting to events.

    Receiving an event message notifies such a system component that an event of a
    certain type has occurred and also carries the details specific to the occurrence
    of the represented event type (e.g., an event message that notifies about the event
    that an order has been filled should carry details like the filled quantity and
    price point at which the fill occurred).
    """

    def receive(self, event_message: EventMessageBase) -> None:
        """
        Protocol method. Once implemented, this method should allow external callers
        to deliver event messages to this system component.

        Caller-blocking should be kept to a minimum, e.g., by enqueuing the event
        message and leaving the actual processing to the system component's own thread.

        Parameters:
            event_message:
                Event message representing the occurrence of a certain type of event.
        """
        ...


class EventBus:
    """
    Dispatch mechanism for event messages.
    """

    def __init__(self) -> None:
        self._per_eventtype_subscriptions: defaultdict[
            type[EventMessageBase], set[SubscriberLike]
        ] = defaultdict(set)

    def subscribe(
        self, subscriber: SubscriberLike, *event_types: type[EventMessageBase]
    ) -> None:
        """
        Register a system component to receive event messages of the specified types.

        Parameters:
            subscriber:
                System component that satisfies the `SubscriberLike` protocol.
            *event_types:
                One or more event message types (classes, not instances) the subscriber
                wants to be notified about. No-op if none provided.
        """
        for event_type in event_types:
            self._per_eventtype_subscriptions[event_type].add(subscriber)

    def publish(self, event_message: EventMessageBase) -> None:
        """
        Deliver an event message to all subscribers registered for its type by calling
        their respective `.receive` methods.

        Parameters:
            event_message:
                Event message instance to deliver.

        Implementation Note:
            The subscriber set is snapshotted before iteration since a system component
            may subscribe to an event type while another is publishing an event message
            of that type, and modifying a set while it is being iterated over would
            raise a `RuntimeError`.
        """
        for subscriber in list(self._per_eventtype_subscriptions[type(event_message)]):
            subscriber.receive(event_message)
