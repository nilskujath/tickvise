from collections.abc import Callable

from ..domain.constants import SCALE_FACTOR
from ..domain.instruments import InstrumentBase
from ..domain.types import Quantity, ScaledMonetaryAmount, ScaledPrice

type CommissionModel = Callable[
    [InstrumentBase, Quantity, ScaledPrice], ScaledMonetaryAmount
]
"""
Signature shared by all commission models: a callable that returns the costs
(commissions and fees) of a fill in the currency of the instrument, given the
instrument, the quantity filled, and the fill price.

Every model receives all three, so that the simulated broker can call any model the
same way; a model ignores the ones it does not need (e.g., a flat fee per contract needs
only the quantity, while a fee per share capped at a percentage of the trade value also
needs the price).
"""


def ib_micro_emini(
    _instrument: InstrumentBase,
    qty: Quantity,
    _price: ScaledPrice,
) -> ScaledMonetaryAmount:
    """
    IB Fixed-pricing all-in commission for a fill of CME Micro E-Mini futures as of Q3
    2026, in USD.

    A flat fee per contract, so only the quantity is used.

    Per contract per side

    - IB commission:    $0.25
    - CME exchange fee: $0.353
    - NFA regulatory:   $0.011
    - Total:            $0.614
    """
    return round(0.614 * SCALE_FACTOR) * qty
