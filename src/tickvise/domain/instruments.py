"""
Data structures for specifying tradable instruments.

An instrument specification carries enough information to uniquely identify a security
or derivative contract.
"""

from dataclasses import dataclass

from .enums import OptionRight
from .types import (
    Ticker,
    Exchange,
    Currency,
    Multiplier,
    StrikePrice,
    ExpirationDate,
)


@dataclass(frozen=True, kw_only=True)
class InstrumentBase:
    """
    Base class for all data structures used to specify tradable instruments.

    Parameters:
        ticker:
            Exchange-assigned short code for the instrument.
        exchange:
            Exchange or trading venue the instrument is listed on.
        currency:
            Currency the instrument is denominated in.
    """

    # fmt: off
    ticker:     Ticker
    exchange:   Exchange
    currency:   Currency
    # fmt: on


class Instrument:
    """
    Namespace class for concrete instrument types.
    """

    @dataclass(frozen=True, kw_only=True)
    class Equity(InstrumentBase):
        """
        An equity instrument (e.g., common stock, preferred stock, ETFs, ADRs, REITs,
        et cetera).

        Parameters:
            ticker:
                Exchange-assigned short code for the equity security.
            exchange:
                Exchange the equity security is listed on.
            currency:
                Currency the equity security is denominated in.
        """

        pass

    @dataclass(frozen=True, kw_only=True)
    class Future(InstrumentBase):
        """
        A futures contract.

        Parameters:
            ticker:
                Exchange-assigned short code for the futures contract.
            exchange:
                Exchange the futures contract is listed on.
            currency:
                Currency the futures contract is denominated in.
            expiry:
                The futures contract's expiration date.
            multiplier:
                The futures contract's point multiplier (e.g., 2 for MNQ, 50 for ES).
                Represents how much one point of price movement is worth in the
                denominated currency.
        """

        # fmt: off
        expiry:     ExpirationDate
        multiplier: Multiplier
        # fmt: on

    @dataclass(frozen=True, kw_only=True)
    class Option(InstrumentBase):
        """
        An option on an equity or index.

        Parameters:
            ticker:
                Exchange-assigned short code for the underlying.
            exchange:
                Exchange the option is listed on.
            currency:
                Currency the option is denominated in.
            expiry:
                Contract expiration date.
            strike:
                Strike price of the option.
            right:
                Call or put.
            multiplier:
                Number of units of the underlying that one option contract controls
                (e.g., 100 for standard US equity options).
        """

        # fmt: off
        expiry:     ExpirationDate
        strike:     StrikePrice
        right:      OptionRight
        multiplier: Multiplier
        # fmt: on

    @dataclass(frozen=True, kw_only=True)
    class FuturesOption(InstrumentBase):
        """
        An option on a futures contract.

        Parameters:
            ticker:
                Exchange-assigned short code for the underlying future.
            exchange:
                Exchange the option is listed on.
            currency:
                Currency the option is denominated in.
            expiry:
                Contract expiration date.
            strike:
                Strike price of the option.
            right:
                Call or put.
            multiplier:
                Contract point multiplier of the underlying future.
                Represents how much one point of price movement is worth in the
                denominated currency.
        """

        # fmt: off
        expiry:     ExpirationDate
        strike:     StrikePrice
        right:      OptionRight
        multiplier: Multiplier
        # fmt: on
