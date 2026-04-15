"""Pydantic models — source-agnostic, extensible for any card network."""

from __future__ import annotations

from pydantic import BaseModel

# ── Core ───────────────────────────────────────────────────────────────────────


class CurrencyRate(BaseModel):
    rate: float  # 1 foreign = X TWD
    reverse: float  # 1 TWD = X foreign


class RatesMeta(BaseModel):
    base: str
    currencies: list[str]
    last_updated: str


# source-agnostic: {"VISA": {"USD": CurrencyRate(...)}, "Mastercard": {...}}
SourceRates = dict[str, CurrencyRate]
DailyRates = dict[str, SourceRates]


class RatesPayload(BaseModel):
    meta: RatesMeta
    rates: dict[str, DailyRates]  # "2026-04-15" → {"VISA": {"USD": ...}}


# ── Response ───────────────────────────────────────────────────────────────────


class LatestRatesResponse(BaseModel):
    date: str
    source: str
    rates: dict[str, CurrencyRate]


class HistoryPoint(BaseModel):
    date: str
    rate: float
    reverse: float


class HistoryResponse(BaseModel):
    currency: str
    source: str
    data: list[HistoryPoint]
