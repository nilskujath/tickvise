"""
Data structures for specifying tradable instruments.

An instrument specification carries enough information to uniquely identify a security
or derivative contract.
"""

from dataclasses import dataclass, field

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
        multiplier:
            How much one point of price movement of one unit of the instrument is
                worth in the instrument's currency.
    """

    # fmt: off
    ticker:     Ticker
    exchange:   Exchange
    currency:   Currency
    multiplier: Multiplier
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
            multiplier:
                How much one point of price movement of one share is worth in its
                    currency.
                Always 1, since the price is quoted per share; not a constructor
                    parameter.
        """

        multiplier: Multiplier = field(default=1, init=False)

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
                How much one point of price movement of one futures contract is worth
                    in its currency.
                Set by the contract specification (e.g., 2 for MNQ, 50 for ES).
        """

        expiry: ExpirationDate

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
                How much one point of price movement of one option contract is worth
                    in its currency.
                Equals the number of units of the underlying that one option contract
                    controls, since the option price is quoted per unit (e.g., 100 for
                    standard US equity options).
        """

        # fmt: off
        expiry:     ExpirationDate
        strike:     StrikePrice
        right:      OptionRight
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
                How much one point of price movement of one option contract is worth
                    in its currency.
                Equals the point multiplier of the underlying futures contract when, as
                    usual, one option contract is exercised into one futures contract
                    and quoted in the same points (e.g., 50 for options on ES futures).
        """

        # fmt: off
        expiry:     ExpirationDate
        strike:     StrikePrice
        right:      OptionRight
        # fmt: on
