from ..domain.constants import PRICE_SCALE_FACTOR
from ..domain.instruments import Instrument
from ..domain.types import ScaledPrice


def ib_micro_emini(
    instrument: Instrument.Future,
    qty: int,
    price: ScaledPrice,
) -> ScaledPrice:
    """
    IB Fixed-pricing all-in commission for CME Micro E-Mini futures as of Q3 2026.

    Per contract per side

    - IB commission:    $0.25
    - CME exchange fee: $0.353
    - NFA regulatory:   $0.011
    - Total:            $0.614
    """
    return int(0.614 / instrument.multiplier * PRICE_SCALE_FACTOR)
