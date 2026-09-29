"""
Simulated broker connector for backtesting.

In backtesting, there is no external broker API to submit orders to and receive fills
from.
The `SimulatedBrokerConnector` fills this role by evaluating resting orders against
incoming bar data and emitting (approximately) the same order lifecycle events that a
live broker connector would produce.
"""

from typing import Callable

from ..domain.enums import TradeSide
from ..domain.events import DomainEvents, EventMessageBase
from ..domain.instruments import InstrumentBase
from ..domain.types import (
    OrderId,
    Position,
    ScaledPrice,
    SignedPositionSize,
)
from ..messaging.backtest_eventbus import BacktestEventBus
from .base import BrokerConnectorBase


class SimulatedBrokerConnector(BrokerConnectorBase):
    """
    Broker connector that simulates order execution against bar data for backtesting.

    Resting orders are evaluated against each incoming `NewBar` event. Position state
    is tracked internally using weighted average cost basis accounting.

    Warning:
        All fills are modeled as complete.
        Partial fills are not simulated.
        Orders are treated as GTC (good-till-cancelled) with no expiration.
        Limit fills use strict inequality against the bar's extreme: an order whose
        limit price is merely touched but not penetrated is not filled.

    Parameters:
        event_bus:
            Must be a `BacktestEventBus` instance to ensure two-phase `NewBar` delivery.
        instruments:
            Set of instruments managed by this broker connector.
    """

    SUBSCRIBE_TO = BrokerConnectorBase.SUBSCRIBE_TO + (DomainEvents.NewBar,)
    """
    Extends the parent's subscriptions with `NewBar` so that resting orders can be
    evaluated against incoming bar data.
    """

    def __init__(
        self,
        event_bus: BacktestEventBus,
        instruments: set[InstrumentBase],
        commission_model: (
            Callable[[InstrumentBase, int, ScaledPrice], ScaledPrice] | None
        ) = None,
    ) -> None:
        """
        Initialize the simulated broker connector.

        State must be initialized before `super().__init__` because the parent's
        constructor calls `_connect()` and `_emit_account_state()`, which may access it.

        Parameters:
            event_bus:
                Must be a `BacktestEventBus` instance; a `TypeError` is raised
                    otherwise.
            instruments:
                Set of instruments managed by this broker connector.
            commission_model:
                Optional callable that computes the per-contract commission for a
                fill, given the instrument, quantity, and fill price.
                The returned value is in `ScaledPrice` units and is folded into the
                position's cost basis: added for buys, subtracted for sells.
                Defaults to zero commission if not provided.
        """
        if not isinstance(event_bus, BacktestEventBus):
            raise TypeError(
                f"SimulatedBrokerConnector requires a BacktestEventBus instance, "
                f"got {type(event_bus).__name__}"
            )

        # fmt: off
        self._commission_model = commission_model or (lambda inst, qty, price: 0)
        self._working_orders:   dict[OrderId, DomainEvents.OrderRequest] = {}
        self._position:         dict[InstrumentBase, SignedPositionSize]  = {}
        self._cost_basis:       dict[InstrumentBase, ScaledPrice]         = {}
        # fmt: on

        super().__init__(event_bus, instruments)

    def _connect(self) -> None:
        """No-op. There is no external broker to connect to."""
        pass

    def _disconnect(self) -> None:
        """No-op. There is no external broker to disconnect from."""
        pass

    def _emit_account_state(self) -> None:
        """
        No-op. A backtest starts with a clean slate: no existing positions and no
        working orders to restore.
        """
        pass

    def _on_event(self, event_message: EventMessageBase) -> None:
        """
        Route incoming events to the appropriate handler.

        `NewBar` events are routed to `_on_bar` for fill evaluation.
        All other events are delegated to the parent's `_on_event` routing,
        which handles `OrderRequest` and `CancellationRequest`.

        Parameters:
            event_message:
                The incoming event message.
        """
        match event_message:
            case DomainEvents.NewBar():
                self._on_bar(event_message)
            case _:
                super()._on_event(event_message)

    def _on_order_request(self, event_message: DomainEvents.OrderRequest) -> None:
        """
        Implementation of `BrokerConnectorBase._on_order_request`.

        Accept an order request by storing it as a working order and emitting an
        `OrderSubmitted` event.

        Orders are treated as GTC (good-till-cancelled) with no expiration.

        Parameters:
            event_message:
                The order request to accept.
        """
        self._working_orders[event_message.order_id] = event_message
        self.emit(
            DomainEvents.OrderSubmitted(
                instrument=event_message.instrument,
                order_id=event_message.order_id,
                source_request=event_message,
            )
        )

    def _on_cancellation_request(
        self, event_message: DomainEvents.CancellationRequest
    ) -> None:
        """
        Implementation of `BrokerConnectorBase._on_cancellation_request`.

        Cancel a working order and emit an `OrderCancelled` event.

        The order is hard-deleted from `_working_orders`.
        A `KeyError` here means the strategy tried to cancel an order that does not
        exist (already filled or never submitted), which is a bug in the strategy.
        Two-phase bar delivery guarantees that the strategy has seen all fills before
        it can issue a cancel, so this should never happen with a correctly implemented
        strategy.

        Parameters:
            event_message:
                The cancellation request to process.
        """
        del self._working_orders[event_message.order_id]
        self.emit(
            DomainEvents.OrderCancelled(
                instrument=event_message.instrument,
                order_id=event_message.order_id,
            )
        )

    def _on_bar(self, bar: DomainEvents.NewBar) -> None:
        """
        Evaluate all resting orders for the bar's instrument against the bar's OHLC
        data.

        Stop-limit orders are checked for stop trigger first.
        If triggered, the stop component is removed and the order becomes a plain limit
        order that may fill immediately or rest for the next bar.
        Plain limit orders are evaluated for fill directly.

        Parameters:
            bar:
                The new bar to evaluate resting orders against.
        """
        for order in list(self._working_orders.values()):
            if order.instrument != bar.instrument:
                continue
            if order.stop_price is not None:
                self._try_trigger_stop(order, bar)
            else:
                self._try_fill_limit(order, bar)

    def _try_fill_limit(
        self, order: DomainEvents.OrderRequest, bar: DomainEvents.NewBar
    ) -> None:
        """
        Attempt to fill a limit order against the bar.

        A buy limit fills when the bar's low is strictly below the limit price.
        A sell limit fills when the bar's high is strictly above the limit price.
        Strict inequality is used conservatively: a limit price that is merely touched
        but not penetrated does not fill.

        The fill price is the better of the limit price and the bar's open.
        This handles the gap-through case where the market opens beyond the limit and
        the order would have filled at the (better) opening price.

        Parameters:
            order:
                The limit order to evaluate.
            bar:
                The bar to evaluate the order against.
        """
        if order.trade_side is TradeSide.BUY and bar.low < order.limit_price:
            self._fill(order=order, fill_price=min(order.limit_price, bar.open))
        elif order.trade_side is TradeSide.SELL and bar.high > order.limit_price:
            self._fill(order=order, fill_price=max(order.limit_price, bar.open))

    def _try_trigger_stop(
        self, order: DomainEvents.OrderRequest, bar: DomainEvents.NewBar
    ) -> None:
        """
        Check whether a stop-limit order's stop component triggers against the bar,
        and if so, handle the resulting limit order.

        A buy stop triggers when the bar's high reaches or exceeds the stop price.
        A sell stop triggers when the bar's low reaches or drops below the stop price.

        Once triggered, the stop component is removed and the order becomes a plain
        limit order stored in `_working_orders`.
        Whether this limit order fills immediately depends on the relationship between
        the limit price and the stop price:

        A stop-limit order's limit price either serves as slippage protection beyond
        the stop level or fishes for a pullback after the breakout.

        Slippage protection orders fill at the worse of the stop price and the bar's
        open, which accounts for gap-through without being pessimistic.
        If the gap is large enough to open past the limit price, the order rests as a
        plain limit and is evaluated on the next bar by `_try_fill_limit`.

        Pullback orders are deferred to the next bar since bar data cannot confirm
        the retracement occurred after the stop triggered.

        Parameters:
            order:
                The stop-limit order to evaluate.
            bar:
                The bar to evaluate the order against.
        """
        assert order.stop_price is not None

        stop_triggered = (
            order.trade_side is TradeSide.BUY and bar.high >= order.stop_price
        ) or (order.trade_side is TradeSide.SELL and bar.low <= order.stop_price)

        if not stop_triggered:
            return

        limit_order = DomainEvents.OrderRequest(
            instrument=order.instrument,
            order_id=order.order_id,
            trade_side=order.trade_side,
            qty=order.qty,
            limit_price=order.limit_price,
            stop_price=None,
        )
        self._working_orders[order.order_id] = limit_order

        if order.trade_side is TradeSide.BUY and order.limit_price >= order.stop_price:
            fill_price = max(order.stop_price, bar.open)
            if fill_price <= order.limit_price:
                self._fill(order=limit_order, fill_price=fill_price)

        elif (
            order.trade_side is TradeSide.SELL and order.limit_price <= order.stop_price
        ):
            fill_price = min(order.stop_price, bar.open)
            if fill_price >= order.limit_price:
                self._fill(order=limit_order, fill_price=fill_price)

    def _fill(self, order: DomainEvents.OrderRequest, fill_price: ScaledPrice) -> None:
        """
        Execute a complete fill for the given order at the given price.

        Commission is computed via the injected commission model and folded into
        the effective price used for cost basis accounting: added for buys,
        subtracted for sells.
        This matches Interactive Brokers' `avgCost` behavior, where the position's
        cost basis includes commissions and fees.

        Parameters:
            order:
                The order being filled.
            fill_price:
                The execution price.
        """
        signed_fill_qty = order.qty if order.trade_side is TradeSide.BUY else -order.qty

        commission = self._commission_model(order.instrument, order.qty, fill_price)

        if order.trade_side is TradeSide.BUY:
            effective_price = fill_price + commission
        else:
            effective_price = fill_price - commission

        del self._working_orders[order.order_id]

        held = self._update_position(
            self._position.get(order.instrument, 0),
            self._cost_basis.get(order.instrument),
            signed_fill_qty,
            effective_price,
        )

        self.emit(
            DomainEvents.Fill(
                instrument=order.instrument,
                order_id=order.order_id,
                trade_side=order.trade_side,
                filled_qty=order.qty,
                remaining_qty=0,
                fill_price=fill_price,
                signed_position_size=held.size if held is not None else 0,
                position_cost_basis=held.cost_basis if held is not None else None,
            )
        )

        if held is None:
            self._position.pop(order.instrument)
            self._cost_basis.pop(order.instrument)
        else:
            self._position[order.instrument] = held.size
            self._cost_basis[order.instrument] = held.cost_basis

    @staticmethod
    def _update_position(
        size: SignedPositionSize,
        cost_basis: ScaledPrice | None,
        signed_qty: SignedPositionSize,
        fill_price: ScaledPrice,
    ) -> Position | None:
        """
        Compute the post-fill position state using weighted average cost basis
        accounting.

        Returns the updated `Position`, or `None` if the fill flattens the position.

        Four cases exist:
        (1) Flattens (new size is zero): returns `None`.
        (2) Opens or flips through flat (was flat, or the fill crosses zero): cost
        basis is the fill price.
        (3) Adds to the position (fill in the same direction): cost basis is the
        weighted average of the existing position and the fill.
        (4) Reduces the position (fill in the opposite direction, without crossing
        zero): cost basis is unchanged.

        Parameters:
            size:
                Current signed position size (0 if flat).
            cost_basis:
                Current weighted average entry price, or `None` if flat.
            signed_qty:
                Signed fill quantity (positive for buy, negative for sell).
            fill_price:
                Execution price.
        """
        new_size = size + signed_qty

        if new_size == 0:
            return None

        if size == 0 or size * new_size < 0:
            return Position(new_size, fill_price)

        if size * signed_qty > 0:
            assert cost_basis is not None
            return Position(
                new_size,
                (size * cost_basis + signed_qty * fill_price) // new_size,
            )

        assert cost_basis is not None
        return Position(new_size, cost_basis)
