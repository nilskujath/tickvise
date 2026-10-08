"""
Simulated datafeed connector for backtesting.

Drip-feeds `DomainEvents.NewBar` event messages into the system one-by-one from a
provided `.pkl` file with serialized bar data  (`DomainEvents.NewBar` event messages).
"""

import pickle
from dataclasses import replace
from pathlib import Path
from time import time_ns

from ..domain.events import SystemEvents
from ..domain.instruments import InstrumentBase
from ..domain.types import BarInterval
from ..messaging.backtest_eventbus import BacktestEventBus
from .base import DatafeedConnectorBase


class SimulatedDatafeedConnector(DatafeedConnectorBase):
    """
    Datafeed connector that replays historical bar data from a pickle file.

    The pickle file must contain a chronological sequence of `DomainEvents.NewBar`
    objects.
    Only bars whose `(instrument, bar_interval)` pair is in the `data_subscriptions`
    set are emitted.

    Warning:
        The pickle file must have been serialized with the same version of the
        `DomainEvents.NewBar` dataclass that is used now to deserialize it.
        If fields have been added, removed, or renamed since the file was written,
        `pickle.load` will raise an error or silently produce corrupt objects.
        Re-export the historical data after schema changes.

    Parameters:
        event_bus:
            Must be a `BacktestEventBus` instance; the simulated datafeed calls
            `wait_until_system_idle` after the last bar to drain all pending processing
            before emitting `ShutdownDecision`.
        data_subscriptions:
            Set of `(instrument, bar_interval)` pairs to replay.
        path_to_pkl:
            Path to the pickle file containing serialized `DomainEvents.NewBar` events.
        max_bars:
            Optional cap on the number of bars to emit; `None` replays all bars in the
            `.pkl` file.
    """

    def __init__(
        self,
        event_bus: BacktestEventBus,
        data_subscriptions: set[tuple[InstrumentBase, BarInterval]],
        path_to_pkl: Path,
        max_bars: int | None = None,
    ) -> None:
        if not isinstance(event_bus, BacktestEventBus):
            raise TypeError(
                f"SimulatedDatafeedConnector requires a BacktestEventBus instance, "
                f"got {type(event_bus).__name__}"
            )

        self._path_to_pkl = path_to_pkl
        self._backtest_bus = event_bus
        self._max_bars = max_bars

        super().__init__(event_bus, data_subscriptions)

    def _connect(self) -> None:
        """
        Replay bars from the pickle file onto the event bus.

        Reads serialized `NewBar` events sequentially, filters by `data_subscriptions`,
        replaces the stale serialization timestamp with the current timestamp, and
        emits each matching bar.

        Each `emit` call blocks until the `BacktestEventBus` has completed its
        two-phase delivery (broker fills, then strategy processing) for that bar.

        After all bars have been emitted (or `max_bars` is reached), it waits for the
        system to fully drain and then emits a `ShutdownDecision` to signal the end of
        the backtest.
        """
        bars_emitted = 0
        with open(self._path_to_pkl, "rb") as f:
            while True:
                try:
                    bar = pickle.load(f)
                except EOFError:
                    break
                if (bar.instrument, bar.bar_interval) in self._data_subscriptions:
                    self.emit(replace(bar, timestamp=time_ns()))
                    bars_emitted += 1
                    if self._max_bars is not None and bars_emitted == self._max_bars:
                        break

        self._backtest_bus.wait_until_system_idle()
        self.emit(
            SystemEvents.ShutdownDecision(
                reason=f"end of historical data ({bars_emitted} bars emitted)"
            )
        )

    def _disconnect(self) -> None:
        """
        No-op since the simulated datafeed has no external connection to close.
        """
        pass
