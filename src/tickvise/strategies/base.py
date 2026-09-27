"""
Base class for trading strategy components.
"""

from abc import abstractmethod
from collections.abc import Generator
from contextlib import contextmanager
from uuid import uuid4


from ..domain.enums import TradeSide
from ..domain.events import DomainEvents, EventMessageBase, SystemEvents
from ..domain.instruments import InstrumentBase
from ..domain.types import (
    IndicatorName,
    Position,
    SignedPositionSize,
    IndicatorReading,
    OrderId,
    Quantity,
    ScaledPrice,
)

from ..indicators.base import IndicatorBase

from ..messaging.eventbus import EventBus
from ..messaging.subscriber import SubscriberBase


class StrategyBase(SubscriberBase):
    """
    Abstract base class for trading strategies.

    A trading strategy component executes the trading logic based on incoming market
    data and order/fill status information from the broker.
    The following event messages are observed: `NewBar`, `OrderSubmitted`,
    `OrderRejected`, `OrderCancelled`, `CancellationRejected`, `Fill`, `OrderExpired`.

    Subclasses must implement the `.on_bar` abstract method to define the core trading
    logic.
    """

    SUBSCRIBE_TO: tuple[type[EventMessageBase], ...] = (
        DomainEvents.NewBar,
        DomainEvents.OrderSubmitted,
        DomainEvents.OrderRejected,
        DomainEvents.OrderCancelled,
        DomainEvents.CancellationRejected,
        DomainEvents.Fill,
        DomainEvents.OrderExpired,
    )

    def __init__(self, event_bus: EventBus, instruments: set[InstrumentBase]) -> None:
        """
        Initialize the strategy with its event bus and the set of instruments it trades.

        Sets up internal tracking structures for indicators, orders at each lifecycle
        stage, and positions.

        Parameters:
            event_bus:
                Event bus instance this component subscribes to and publishes through.
            instruments:
                Set of instruments this strategy is allowed to trade; events for
                    instruments outside this set are discarded by `_on_event`.
        """
        # fmt: off
        self._instruments:      set[InstrumentBase] = instruments
        self._indicators:       dict[IndicatorName, IndicatorBase] = {}
        self._pending_orders:   dict[OrderId, DomainEvents.OrderRequest] = {}
        self._active_orders:    dict[OrderId, DomainEvents.OrderRequest] = {}
        self._pending_cancels:  dict[OrderId, DomainEvents.CancellationRequest] = {}
        self._positions:        dict[InstrumentBase, Position] = {}
        # fmt: on
        super().__init__(event_bus)

    @contextmanager
    def _bar_context(self, instrument: InstrumentBase) -> Generator[None, None, None]:
        """
        Context manager that temporarily binds `_current_instrument` to the given
        instrument for the duration of the `with` block.

        This allows query methods like `position()` and `active_orders()` to default to
        the instrument currently being processed instead of requiring an explicit
        argument.

        The attribute is deleted on exit (including on exception) so that any access
        outside a `with` block raises `AttributeError` rather than silently returning
        stale state.

        Parameters:
            instrument:
                The instrument to bind as the current instrument.
        """
        self._current_instrument = instrument
        try:
            yield
        finally:
            del self._current_instrument

    def position(self, instrument: InstrumentBase | None = None) -> SignedPositionSize:
        """
        Return the signed position size for the given instrument.

        Positive values indicate a long position, negative values a short position, and
        zero means flat.

        Parameters:
            instrument:
                Instrument to query; defaults to `_current_instrument` when called
                    inside a `_bar_context`.

        Returns:
            The net signed position size, or ``0`` if no position is held.
        """
        held_position = self._positions.get(instrument or self._current_instrument)
        return held_position.size if held_position is not None else 0

    def cost_basis(
        self, instrument: InstrumentBase | None = None
    ) -> ScaledPrice | None:
        """
        Return the cost basis of the current position for the given instrument.

        Parameters:
            instrument:
                Instrument to query; defaults to `_current_instrument` when called
                    inside a `_bar_context`.

        Returns:
            The cost basis as a `ScaledPrice`, or `None` if no position is held.
        """
        held_position = self._positions.get(instrument or self._current_instrument)
        return held_position.cost_basis if held_position is not None else None

    def active_orders(
        self, instrument: InstrumentBase | None = None
    ) -> list[DomainEvents.OrderRequest]:
        """
        Return all orders that have been confirmed by the broker and are currently live
        on the market for the given instrument.

        Parameters:
            instrument:
                Instrument to query; defaults to `_current_instrument` when called
                    inside a `_bar_context`.

        Returns:
            List of active `OrderRequest` events.
        """
        instrument = instrument or self._current_instrument
        return [o for o in self._active_orders.values() if o.instrument == instrument]

    def pending_orders(
        self, instrument: InstrumentBase | None = None
    ) -> list[DomainEvents.OrderRequest]:
        """
        Return all orders that have been submitted to the broker but are not yet
        confirmed or rejected by the broker for the given instrument.

        Parameters:
            instrument:
                Instrument to query; defaults to `_current_instrument` when called
                    inside a `_bar_context`.

        Returns:
            List of pending `OrderRequest` events.
        """
        instrument = instrument or self._current_instrument
        return [o for o in self._pending_orders.values() if o.instrument == instrument]

    def pending_cancels(
        self, instrument: InstrumentBase | None = None
    ) -> list[DomainEvents.CancellationRequest]:
        """
        Return all cancellation requests that have been submitted to but are not yet
        confirmed or rejected by the broker for the given instrument.

        Parameters:
            instrument:
                Instrument to query; defaults to `_current_instrument` when called
                    inside a `_bar_context`

        Returns:
            List of pending `CancellationRequest` events.
        """
        instrument = instrument or self._current_instrument
        return [c for c in self._pending_cancels.values() if c.instrument == instrument]

    def submit_order(
        self,
        trade_side: TradeSide,
        qty: Quantity,
        limit_price: ScaledPrice,
        stop_price: ScaledPrice | None = None,
        instrument: InstrumentBase | None = None,
    ) -> OrderId:
        """
        Submit an order for the given instrument and track it as pending.

        Constructs an `OrderRequest` event, records it in `_pending_orders`, and emits
        it on the event bus.
        The order moves from `_pending_orders` to `_active_orders` once the broker
        confirms it via a `OrderSubmitted` message received by the strategy component.

        Parameters:
            trade_side:
                Direction of the order (buy or sell).
            qty:
                Number of contracts or shares to trade.
            limit_price:
                Limit price for the order.
            stop_price:
                If set, the order becomes a stop-limit order that activates at this
                    price.
            instrument:
                Instrument to submit the order for; defaults to `_current_instrument`
                    when called inside `on_bar`.

        Returns:
            The generated order ID, which can be used to track and cancel the order.
        """
        event = DomainEvents.OrderRequest(
            instrument=instrument or self._current_instrument,
            order_id=(order_id := uuid4()),
            trade_side=trade_side,
            qty=qty,
            limit_price=limit_price,
            stop_price=stop_price,
        )

        self._pending_orders[order_id] = event
        self.emit(event)
        return order_id

    def submit_cancel(self, order_id: OrderId) -> None:
        """
        Request cancellation of an active order.

        Constructs a `CancellationRequest` event, records it in `_pending_cancels`, and
        emits it on the event bus.

        The instrument is looked up from `_active_orders` because only broker-confirmed
        orders can be cancelled.

        Parameters:
            order_id:
                The order ID returned by `submit_order`.

        Raises:
            KeyError: If `order_id` is not in `_active_orders`.
        """
        event = DomainEvents.CancellationRequest(
            instrument=self._active_orders[order_id].instrument,
            order_id=order_id,
        )
        self._pending_cancels[order_id] = event
        self.emit(event)

    @abstractmethod
    def on_bar(self, event: DomainEvents.NewBar) -> None:
        """
        Called when a new completed bar is received for an instrument this strategy
        trades.

        Subclasses implement their trading logic here.
        Query methods like `position()`, `active_orders()`, etc. default to the bar's
        instrument and only require an explicit instrument argument when querying an
        instrument other than the one currently being processed.

        Parameters:
            event:
                The completed bar event.
        """
        ...

    def register_indicator(self, indicator: IndicatorBase) -> IndicatorBase:
        """
        Register an indicator to be updated automatically on each new bar.

        Called during `__init__` of the subclass.
        Duplicate indicator names are rejected because the second registration would
        shadow the first in the internal dictionary.

        Parameters:
            indicator:
                The indicator instance to register.

        Returns:
            The same indicator instance, for convenient assignment in `__init__` via:
                `self._sma = self.register_indicator(SMA(20))`.

        Raises:
            ValueError: If an indicator with the same `name` is already registered.
        """
        if indicator.name in self._indicators:
            self.emit(
                SystemEvents.ShutdownDecision(
                    reason=f"duplicate indicator {indicator.name!r}."
                )
            )
            raise ValueError(f"duplicate indicator {indicator.name!r}.")

        self._indicators[indicator.name] = indicator
        return indicator

    def _update_indicators(self, event: DomainEvents.NewBar) -> None:
        """
        Update all registered indicators with the new bar and emit an `IndicatorUpdate`
        event with the computed readings.

        Called before the trading logic so that indicator values are current
        when `on_bar` runs.

        Parameters:
            event:
                The completed bar event to feed into each indicator.
        """
        readings: dict[IndicatorName, IndicatorReading] = {}
        for indicator in self._indicators.values():
            indicator.update(event)
            readings[indicator.name] = IndicatorReading(
                indicator[event.instrument, event.bar_interval, -1],
                indicator.IS_SCALED,
            )
        self.emit(SystemEvents.IndicatorUpdate(source_bar=event, readings=readings))

    def _on_event(self, event_message: EventMessageBase) -> None:
        """
        Route an incoming event message to the appropriate handler method.

        Events that carry an `instrument` attribute are silently discarded if that
        instrument is not in this strategy's instrument set.
        This is necessary because two strategies on the same event bus must not trade
        the same instrument: they would receive each other's fills and order lifecycle
        events, causing conflicting state transitions.

        Parameters:
            event_message:
                Event message to process.
        """

        if (
            instrument := getattr(event_message, "instrument", None)
        ) is not None and instrument not in self._instruments:
            return

        match event_message:
            case DomainEvents.NewBar():
                self._on_new_bar(event_message)
            case DomainEvents.OrderSubmitted():
                self._on_order_submitted(event_message)
            case DomainEvents.OrderRejected():
                self._on_order_rejected(event_message)
            case DomainEvents.OrderCancelled():
                self._on_order_cancelled(event_message)
            case DomainEvents.CancellationRejected():
                self._on_cancellation_rejected(event_message)
            case DomainEvents.Fill():
                self._on_fill(event_message)
            case DomainEvents.OrderExpired():
                self._on_order_expired(event_message)

    def _on_new_bar(self, event: DomainEvents.NewBar) -> None:
        """
        Handle a `NewBar` event by entering the bar context, updating the associated
        indicators and running the strategy logic implemented via `.on_bar`.

        Historical bars update indicators but do not trigger trading logic, which
        allows indicators to warm up without generating trades.

        Parameters:
            event:
                The completed bar event.
        """
        with self._bar_context(event.instrument):
            self._update_indicators(event)
            if event.is_historical:
                return
            self.on_bar(event)

    def _on_order_submitted(self, event: DomainEvents.OrderSubmitted) -> None:
        """
        Handle an `OrderSubmitted` event by promoting the order from `_pending_orders`
        to `_active_orders`.

        Synthetic events (emitted on reconnect to restore broker state) store the
        `source_request` directly since no prior `OrderRequest` was submitted during
        this run.

        Parameters:
            event:
                The order submission confirmation from the broker.
        """
        if event.synthetic:
            self._active_orders[event.order_id] = event.source_request
            return
        self._active_orders[event.order_id] = self._pending_orders.pop(event.order_id)

    def _on_order_rejected(self, event: DomainEvents.OrderRejected) -> None:
        """
        Handle an `OrderRejected` event by removing the order from `_pending_orders`.

        Parameters:
            event:
                The order rejection from the broker.
        """
        self._pending_orders.pop(event.order_id)

    def _on_order_cancelled(self, event: DomainEvents.OrderCancelled) -> None:
        """
        Handle an `OrderCancelled` event by removing the order from
        `_pending_cancels` and `_active_orders`.

        Uses a defensive pop on `_pending_cancels` because a fill processed before this
        event may have already cleared the entry.

        Parameters:
            event:
                The cancellation confirmation from the broker.
        """
        self._pending_cancels.pop(event.order_id, None)
        self._active_orders.pop(event.order_id)

    def _on_cancellation_rejected(
        self, event: DomainEvents.CancellationRejected
    ) -> None:
        """
        Handle a `CancellationRejected` event by removing the cancellation request from
        `_pending_cancels`.

        Uses a defensive pop (default `None`) because a fill or expiration may have
        already cleared the entry in `_pending_cancels` before this event was processed.

        Parameters:
            event:
                The cancellation rejection from the broker.
        """
        self._pending_cancels.pop(event.order_id, None)

    def _on_fill(self, event: DomainEvents.Fill) -> None:
        """
        Handle a `Fill` event by updating position state and order tracking.

        Synthetic fills (emitted on reconnect) restore the position from broker state
        without touching order tracking, since no orders were submitted during this run.

        For real fills, any in-flight cancellation request for the order is cleared,
        the order is removed from `_active_orders` if fully filled, and the position is
        updated or removed based on the post-fill state reported by the broker.

        Parameters:
            event:
                The fill confirmation from the broker.
        """
        if event.synthetic:
            assert event.position_cost_basis is not None
            self._positions[event.instrument] = Position(
                event.signed_position_size, event.position_cost_basis
            )
            return

        self._pending_cancels.pop(event.order_id, None)

        if event.remaining_qty == 0:
            self._active_orders.pop(event.order_id)

        if event.signed_position_size == 0:
            self._positions.pop(event.instrument)

        else:
            assert event.position_cost_basis is not None
            self._positions[event.instrument] = Position(
                event.signed_position_size, event.position_cost_basis
            )

    def _on_order_expired(self, event: DomainEvents.OrderExpired) -> None:
        """
        Handle an `OrderExpired` event by removing the order from `_active_orders`.

        Defensively pops from `_pending_cancels` because a cancellation request may
        have been in flight when the order expired.

        Parameters:
            event:
                The order expiration notification from the broker.
        """
        self._active_orders.pop(event.order_id)
        self._pending_cancels.pop(event.order_id, None)
