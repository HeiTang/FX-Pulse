"""Mastercard Currency Converter scraper."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from .base import BaseScraper


class MastercardScraper(BaseScraper):
    source_name = "Mastercard"
    base_url = (
        "https://www.mastercard.com/marketingservices/public"
        "/mccom-services/currency-conversions/conversion-rates"
    )
    referer = (
        "https://www.mastercard.com/global/en/personal"
        "/get-support/currency-exchange-rate-converter.html"
    )

    def _build_params(self, currency: str, date_str: str) -> dict[str, str]:
        # BaseScraper passes MM/DD/YYYY; Mastercard API expects YYYY-MM-DD
        exchange_date = datetime.strptime(date_str, "%m/%d/%Y").strftime("%Y-%m-%d")
        return {
            "exchange_date": exchange_date,
            "transaction_currency": currency,
            "cardholder_billing_currency": "TWD",
            "bank_fee": "0",
            "transaction_amount": "1",
        }

    def _parse_response(self, data: dict[str, Any]) -> dict[str, float]:
        inner = data.get("data")
        if not inner or "conversionRate" not in inner:
            raise ValueError("Mastercard response missing 'data.conversionRate'")

        rate = float(inner["conversionRate"])
        if rate <= 0:
            raise ValueError(f"Invalid conversionRate: {rate}")

        reverse = 1.0 / rate
        return {"rate": rate, "reverse": reverse}
