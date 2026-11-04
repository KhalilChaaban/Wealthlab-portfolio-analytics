"""Explicit reporting currencies and a fixed USD/AED translation convention.

Yahoo ETF observations remain USD quotes. The holdings engine consumes price
relatives, so capital and cash flows expressed in AED generate AED accounting
without converting or overwriting the vendor's price cache.
"""

import math


AED_PER_USD = 3.6725
FX_SOURCE = "https://centralbank.ae/en/forex-eibor/exchange-rates/"
FX_VERIFIED_DATE = "2026-11-04"


def validate_currency(currency: str) -> None:
    if currency not in {"AED", "USD"}:
        raise ValueError("Supported reporting currencies are AED and USD.")


def conversion_factor(source: str, target: str) -> float:
    """Return a fixed reporting factor, not a live tradable FX quote."""
    validate_currency(source)
    validate_currency(target)
    if source == target:
        return 1.0
    return AED_PER_USD if target == "AED" else 1 / AED_PER_USD


def format_money(value: float, currency: str = "AED", decimals: int = 0) -> str:
    validate_currency(currency)
    if not math.isfinite(value):
        raise ValueError("Monetary values must be finite.")
    return f"{currency} {value:,.{decimals}f}"


def currency_disclosure(currency: str) -> str:
    validate_currency(currency)
    if currency == "USD":
        return "Amounts are in USD; Yahoo ETF source quotes are also in USD."
    return (
        "Amounts are in UAE dirhams (AED). The existing USD case is translated "
        "at a fixed reporting rate of 1 USD = AED 3.6725, verified against CBUAE "
        "on 2026-11-04. Yahoo ETF quotes remain USD source data; portfolio "
        "accounting applies their percentage returns to AED capital. A constant "
        "USD/AED rate is assumed throughout history and planning. FX spreads, "
        "conversion charges, and a change in the peg are not modeled."
    )


def currency_metadata(currency: str) -> dict:
    validate_currency(currency)
    return {
        "reporting_currency": currency,
        "source_quote_currency": "USD",
        "usd_aed_reporting_rate": AED_PER_USD,
        "rate_convention": "fixed reporting assumption; not a live execution quote",
        "rate_source": FX_SOURCE,
        "rate_verified_date": FX_VERIFIED_DATE,
        "note": currency_disclosure(currency),
    }
