"""VISA FX Rate Scraper

Endpoint: https://www.visa.com.tw/cmsapi/fx/rates
Query direction: fromCurr=TWD → fxRateVisa matches calculator UI
"""

from __future__ import annotations

from typing import Any

from .base import BaseScraper


class VisaScraper(BaseScraper):
    source_name = "VISA"
    base_url = "https://www.visa.com.tw/cmsapi/fx/rates"
    referer = (
        "https://www.visa.com.tw/support/consumer/travel-support/exchange-rate-calculator.html"
    )

    def _build_params(self, currency: str, date_str: str) -> dict[str, str]:
        # fromCurr=TWD 才能拿到與計算機 UI 一致的 fxRateVisa
        return {
            "amount": "1",
            "fee": "0",
            "utcConvertedDate": date_str,
            "exchangedate": date_str,
            "fromCurr": "TWD",
            "toCurr": currency,
        }

    def _parse_response(self, data: dict[str, Any]) -> dict[str, float]:
        if data.get("status") != "success":
            raise ValueError(f"API non-success: {data.get('status')}")

        # fxRateVisa  = 1 foreign = X TWD (10 decimal precision)
        # reverseAmount = 1 TWD = X foreign
        return {
            "rate": float(data["originalValues"]["fxRateVisa"]),
            "reverse": float(data["reverseAmount"]),
        }
