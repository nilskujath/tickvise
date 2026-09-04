"""
Base class for components that record event data to external sinks (files, databases,
charts).
"""

from abc import ABC

from ..messaging.subscriber import SubscriberBase


class RecorderBase(SubscriberBase, ABC):
    """
    Base class for components that record event data to external sinks (files,
    databases, charts).

    Exists to establish recorders as a recognized architectural role.
    No additional behavior over `SubscriberBase`.
    """

    pass
