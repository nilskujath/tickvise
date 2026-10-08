"""
Utilities for working with Databento data.
"""

import csv
import pickle
from pathlib import Path

from ..domain.enums import TimeUnit
from ..domain.events import DomainEvents
from ..domain.instruments import InstrumentBase
from ..domain.types import BarInterval

type DatabentoRtype = int


def databento_csv_to_pkl(
    csv_path: Path,
    output_path: Path,
    instruments: set[InstrumentBase],
) -> None:
    """
    Converts a Databento-format CSV export of aggregated bars (OHLCV schema) into a
    pickle file of serialized `DomainEvents.NewBar` event messages for replay by
    `SimulatedDatafeedConnector`.

    Each row whose `rtype` maps to a known `BarInterval` and whose `symbol` appears in
    `instruments` produces one serialized `DomainEvents.NewBar` event.
    Rows that match neither are silently skipped.

    Parameters:
        csv_path:
            Path to the Databento-format CSV file.
        output_path:
            Path for the output `.pkl` file (created or overwritten).
        instruments:
            Set of `InstrumentBase` instances whose tickers should be matched
            against the CSV `symbol` column.
    """
    rtype_to_barinterval: dict[DatabentoRtype, BarInterval] = {
        32: BarInterval(TimeUnit.SECOND),
        33: BarInterval(TimeUnit.MINUTE),
        34: BarInterval(TimeUnit.HOUR),
        35: BarInterval(TimeUnit.DAY),
    }
    ticker_to_instrument = {i.ticker: i for i in instruments}

    with open(csv_path, newline="") as f_in, open(output_path, "wb") as f_out:
        reader = csv.reader(f_in)
        header = next(reader)
        col = {name: i for i, name in enumerate(header)}

        # resolve column indices once
        c_rtype = col["rtype"]
        c_symbol = col["symbol"]
        c_ts = col["ts_event"]
        c_open = col["open"]
        c_high = col["high"]
        c_low = col["low"]
        c_close = col["close"]
        c_vol = col["volume"]

        for row in reader:
            interval = rtype_to_barinterval.get(int(row[c_rtype]))
            if interval is None:
                continue

            instrument = ticker_to_instrument.get(row[c_symbol])
            if instrument is None:
                continue

            pickle.dump(
                DomainEvents.NewBar(
                    instrument=instrument,
                    period_start=int(row[c_ts]),
                    bar_interval=interval,
                    open=int(row[c_open]),
                    high=int(row[c_high]),
                    low=int(row[c_low]),
                    close=int(row[c_close]),
                    volume=int(row[c_vol]),
                    data_source="Databento",
                    is_historical=True,
                ),
                f_out,
            )
