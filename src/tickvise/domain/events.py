# fmt: off
from dataclasses import dataclass, field
from time        import time_ns
# fmt: on


# fmt: off
from .types import UnixNs, Reason
# fmt: on


@dataclass(frozen=True, kw_only=True)
class EventMessageBase:
    """
    Base class for all event messages.

    Parameters:
        timestamp: Timestamp of event creation.
    """

    timestamp: UnixNs = field(default_factory=time_ns)


class DomainEvents:
    """
    Namespace class for domain-related event messages.
    """


class SystemEvents:
    """
    Namespace class for system-level event messages.
    """

    @dataclass(frozen=True, kw_only=True)
    class ShutdownDecision(EventMessageBase):
        """
        Represents that the decision that the system should shut down.

        Parameters:
            timestamp: Timestamp of event creation.
            reason: Why the system is shutting down.
        """

        reason: Reason
