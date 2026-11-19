"""STRATLAB Statutory and Brokerage Cost Calculator.

Computes exact regulatory transaction taxes (STT/CTT, Exchange charges, GST,
SEBI turnover fee, Stamp duty) and brokerage for multi-market execution.
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Literal


CostProfile = Literal["india_delivery", "india_intraday", "india_futures", "crypto_futures", "zero_fee"]


@dataclass
class TransactionCosts:
    brokerage: float
    stt: float
    exchange_charges: float
    gst: float
    sebi_charges: float
    stamp_duty: float
    total: float


class CostModel:
    """Calculates fee breakdown for buy and sell transactions."""

    @staticmethod
    def calculate(
        profile: CostProfile,
        side: Literal["BUY", "SELL"],
        price: float,
        quantity: int,
    ) -> TransactionCosts:
        turnover = price * quantity
        if turnover <= 0:
            return TransactionCosts(0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0)

        if profile == "zero_fee":
            return TransactionCosts(0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0)

        if profile == "india_delivery":
            # Delivery: 0.1% STT on both buy and sell; 0.015% stamp on buy only
            brokerage = 0.0
            stt = round(turnover * 0.001)  # 0.1% rounded to nearest rupee per standard exchange rules
            exch = turnover * 0.0000297     # NSE: 0.00297%
            sebi = turnover * 0.000001      # Rs 10 per crore
            stamp = (turnover * 0.00015) if side == "BUY" else 0.0  # 0.015% on buy
            gst = (brokerage + exch + sebi) * 0.18  # 18% GST
            total = brokerage + stt + exch + sebi + stamp + gst
            return TransactionCosts(
                brokerage=round(brokerage, 2),
                stt=round(stt, 2),
                exchange_charges=round(exch, 2),
                gst=round(gst, 2),
                sebi_charges=round(sebi, 2),
                stamp_duty=round(stamp, 2),
                total=round(total, 2),
            )

        elif profile == "india_intraday":
            # Intraday: Rs 20 flat or 0.03% brokerage; 0.025% STT on sell only; 0.003% stamp on buy
            brokerage = min(20.0, turnover * 0.0003)
            stt = round(turnover * 0.00025) if side == "SELL" else 0.0
            exch = turnover * 0.0000297
            sebi = turnover * 0.000001
            stamp = (turnover * 0.00003) if side == "BUY" else 0.0
            gst = (brokerage + exch) * 0.18
            total = brokerage + stt + exch + sebi + stamp + gst
            return TransactionCosts(
                brokerage=round(brokerage, 2),
                stt=round(stt, 2),
                exchange_charges=round(exch, 2),
                gst=round(gst, 2),
                sebi_charges=round(sebi, 2),
                stamp_duty=round(stamp, 2),
                total=round(total, 2),
            )

        elif profile == "india_futures":
            # Futures: Rs 20 flat brokerage; 0.02% STT on sell only; 0.002% stamp on buy
            brokerage = 20.0
            stt = round(turnover * 0.0002) if side == "SELL" else 0.0
            exch = turnover * 0.000019
            sebi = turnover * 0.000001
            stamp = (turnover * 0.00002) if side == "BUY" else 0.0
            gst = (brokerage + exch) * 0.18
            total = brokerage + stt + exch + sebi + stamp + gst
            return TransactionCosts(
                brokerage=round(brokerage, 2),
                stt=round(stt, 2),
                exchange_charges=round(exch, 2),
                gst=round(gst, 2),
                sebi_charges=round(sebi, 2),
                stamp_duty=round(stamp, 2),
                total=round(total, 2),
            )

        elif profile == "crypto_futures":
            # Taker 0.04%, maker 0.02% approximation (taker default)
            brokerage = turnover * 0.0004
            return TransactionCosts(
                brokerage=round(brokerage, 4),
                stt=0.0,
                exchange_charges=0.0,
                gst=0.0,
                sebi_charges=0.0,
                stamp_duty=0.0,
                total=round(brokerage, 4),
            )

        return TransactionCosts(0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0)
