"""
Base classes for event-driven system components.
"""

# fmt: off
from abc        import ABC, abstractmethod
from traceback  import format_exc
from queue      import Queue
from threading  import Thread
# fmt: on


# fmt: off
from .eventbus              import EventBus
from ..domain.events        import EventMessageBase, SystemEvents
from ..utils.post_init_hook import HasPostInitHook
# fmt: on


class SubscriberBase(ABC, HasPostInitHook):
    """
    Abstract base class for system components that react to event messages.
    Implementation of the `SubscriberLike` protocol.

    Each component runs its own thread with an event loop that dequeues and processes
    event messages one at a time.
    Incoming event messages are enqueued via `.receive` (which returns immediately) and
    processed on the component's own thread via `._on_event`, which subclasses must
    implement.

    Subclasses must override the `SUBSCRIBE_TO` class variable to declare which event
    message types they want to receive.
    Every component is automatically subscribed to receive
    `SystemEvents.ShutdownDecision` event messages.
    """

    SUBSCRIBE_TO: tuple[type[EventMessageBase], ...] = ()  # override to receive events

    def __init__(self, event_bus: EventBus) -> None:
        """
        Subscribes to the event message types set via `SUBSCRIBE_TO` with the event bus
        instance given as an argument.

        Every component is automatically subscribed to receive
        `SystemEvents.ShutdownDecision` event messages.

        Parameters:
            event_bus:
                Event bus instance this component subscribes to and publishes through.
        """
        self._event_bus: EventBus = event_bus
        self._queue: Queue[EventMessageBase] = Queue()
        self._event_loop_thread = Thread(
            target=self._event_loop, name=type(self).__name__
        )
        self._event_bus.subscribe(
            self, *self.SUBSCRIBE_TO, SystemEvents.ShutdownDecision
        )

    def _post_init_hook(self) -> None:
        """
        Start the event loop thread after the full `__init__` chain has completed.
        """
        self._event_loop_thread.start()

    def receive(self, event_message: EventMessageBase) -> None:
        """
        Allows external callers to deliver event messages to this system component.
        Implementation of the `SubscriberLike` `.receive` protocol method.

        The caller is only blocked for the duration of a `Queue.put` call.
        The actual processing happens on this component's own thread via the
        `._event_loop`.

        Parameters:
            event_message:
                Event message to enqueue for processing.
        """
        self._queue.put(event_message)

    def emit(self, event_message: EventMessageBase) -> None:
        """
        Convenience wrapper for publishing an event message through the same event
        bus instance this component subscribes to for receiving event messages.

        Parameters:
            event_message:
                Event message to publish to the system.
        """
        self._event_bus.publish(event_message)

    def _event_loop(self) -> None:
        """
        Processes received event messages.

        Dequeues received event messages one at a time and tries to process them via
        `._on_event`. An unhandled exception in `._on_event` will cause the system
        to shut down.

        The reception of a `SystemEvents.ShutdownDecision` event message stops the
        component from processing any further events even if they have already been
        received.
        """

        while True:
            event_message = self._queue.get()
            try:
                self._on_event(event_message)
            except Exception:
                self.emit(SystemEvents.ShutdownDecision(reason=format_exc()))
            self._queue.task_done()

            if isinstance(event_message, SystemEvents.ShutdownDecision):
                break

        self._teardown()

    def _teardown(self) -> None:
        """
        Hook for component-specific cleanup after the event loop in the `._event_loop`
        method exits.

        The cleanup behavior defined here will still run on the component's thread.
        Override in subclasses as needed.
        The default implementation is a no-op.
        """
        pass

    @abstractmethod
    def _on_event(self, event_message: EventMessageBase) -> None:
        """
        Called to process a single event message. Subclasses must implement this
        to define their event handling logic.

        The recommended pattern for implementing this method is to use a match-case
        statement that routes each event message type to a dedicated handler method,
        such that this method only serves as a clean dispatch hub to keep code
        maintainable.

        Parameters:
            event_message:
                Event message to process.
        """
        ...


class ConnectableSubscriberBase(ABC, SubscriberBase):
    """
    Abstract base class for system components that react to event messages and
    manage an external connection.

    Connects during initialization (after subscribing to the event bus) and disconnects
    during teardown.
    Subclasses must implement `._connect` and `._disconnect`.
    """

    def __init__(self, event_bus: EventBus) -> None:
        """
        Subscribe to the event bus, then establish the external connection.

        Parameters:
            event_bus:
                Event bus instance this component subscribes to and publishes through.
        """
        super().__init__(event_bus)
        self._connect()

    @abstractmethod
    def _connect(self) -> None:
        """
        Called to establish a connection to an external API.
        Subclasses must implement it.
        """
        ...

    @abstractmethod
    def _disconnect(self) -> None:
        """
        Close the connection to the external API.
        """
        ...

    def _event_loop(self) -> None:
        """
        Wraps the parent event loop in a `try/finally` to guarantee that `._disconnect`
        is called after the event loop exits, even if it terminates due to an unhandled
        exception.
        """
        try:
            super()._event_loop()
        finally:
            self._disconnect()
