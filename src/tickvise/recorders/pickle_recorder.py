"""
Records all event messages to a pickle file for post-run inspection.
"""

# fmt: off
import pickle

from collections.abc    import Iterator
from io                 import BufferedWriter
from pathlib            import Path
# fmt: on


# fmt: off
from ..domain.events        import EventMessageBase, DomainEvents, SystemEvents
from ..messaging.eventbus   import EventBus
from .base                  import RecorderBase
# fmt: on


class PickleRecorder(RecorderBase):
    """
    Persists all event messages that are published to the event bus to a pickle file as
    native Python objects.
    """

    SUBSCRIBE_TO = tuple(
        member
        for cls in (DomainEvents, SystemEvents)
        for member in vars(cls).values()
        if isinstance(member, type) and issubclass(member, EventMessageBase)
    )
    """
    Subscribe to all existing event messages (that is, all subclasses of the 
    `DomainEvents` and `SystemEvents` namespace classes).
    """

    def __init__(self, event_bus: EventBus, output_path: Path) -> None:
        """
        Parameters:
            event_bus:
                Event bus instance to subscribe to.
            output_path:
                Path to the pickle file. Parent directories are created if missing.
        """
        self._output_path = output_path
        self._output_file: BufferedWriter | None = None

        super().__init__(event_bus)

    def _event_loop(self) -> None:
        """
        Override of `SubscriberBase._event_loop`. Wraps the parent event loop to open
        the output file before processing begins and guarantee it is closed after the
        event loop exits, even on failure.
        """
        self._output_path.parent.mkdir(parents=True, exist_ok=True)
        self._output_file = open(self._output_path, "wb")
        try:
            super()._event_loop()
        finally:
            self._output_file.close()

    def _on_event(self, event_message: EventMessageBase) -> None:
        """
        Implementation of the parent class' `_on_event` abstract method.

        Serialize and write a single event message to the pickle file.
        Flushes after each write to minimize data loss on crash.

        Parameters:
            event_message:
                Event message to serialize and write to the pickle file.

        Implementation Note:
            Flushing after each write minimizes data loss on crash but adds a
            system call per event.
            If this becomes a bottleneck, consider flushing in batches or excluding the
            recorder from any synchronization mechanism that waits for all components to
            finish before advancing to process a new event, should such a mechanism
            exist.
        """
        assert self._output_file is not None
        pickle.dump(event_message, self._output_file)
        self._output_file.flush()

    @staticmethod
    def read(path: Path) -> Iterator[EventMessageBase]:
        """
        Read the event messages from a pickle file written by a `PickleRecorder`, one
        at a time and in recording order.

        Event messages are loaded one at a time as the caller iterates, so a recording
        can be processed without loading all of it into memory at once.

        Example:
            ```python
            for event_message in PickleRecorder.read(Path("recording.pkl")):
                print(event_message)

            # Or collect the entire recording into a list (keeps all of it in memory):
            event_messages = list(PickleRecorder.read(Path("recording.pkl")))
            ```

        Parameters:
            path:
                Path to the pickle file.
        """
        with open(path, "rb") as f:
            while True:
                try:
                    yield pickle.load(f)
                except EOFError:
                    return
