"""
Provides the `Open`, `High`, `Low`, `Close`, and `Volume` indicator classes, each
extracting the corresponding field from a `NewBar` event.
"""

from ..domain.events import DomainEvents
from ..domain.types import IndicatorName, IndicatorValue
from .base import IndicatorBase


class Open(IndicatorBase):
    """The open price of each bar."""

    @property
    def name(self) -> IndicatorName:
        return "Open"

    def _compute(self, bar: DomainEvents.NewBar) -> IndicatorValue:
        return bar.open


class High(IndicatorBase):
    """The high price of each bar."""

    @property
    def name(self) -> IndicatorName:
        return "High"

    def _compute(self, bar: DomainEvents.NewBar) -> IndicatorValue:
        return bar.high


class Low(IndicatorBase):
    """The low price of each bar."""

    @property
    def name(self) -> IndicatorName:
        return "Low"

    def _compute(self, bar: DomainEvents.NewBar) -> IndicatorValue:
        return bar.low


class Close(IndicatorBase):
    """The close price of each bar."""

    @property
    def name(self) -> IndicatorName:
        return "Close"

    def _compute(self, bar: DomainEvents.NewBar) -> IndicatorValue:
        return bar.close


class Volume(IndicatorBase):
    """The volume of each bar."""

    IS_SCALED = False

    @property
    def name(self) -> IndicatorName:
        return "Volume"

    def _compute(self, bar: DomainEvents.NewBar) -> IndicatorValue:
        return bar.volume
