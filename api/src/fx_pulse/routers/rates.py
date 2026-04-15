from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from ..config import settings
from ..models.rate import HistoryResponse, LatestRatesResponse
from ..store import get_store

router = APIRouter(prefix="/rates", tags=["rates"])


@router.get("/latest", response_model=LatestRatesResponse)
def get_latest(source: str = Query("VISA", description="資料來源")) -> LatestRatesResponse:
    """最新一筆匯率（所有幣別）。"""
    result = get_store().get_latest_rates(source)
    if result is None:
        raise HTTPException(status_code=404, detail=f"No data for source '{source}'")

    date_key, rates = result
    return LatestRatesResponse(date=date_key, source=source, rates=rates)


@router.get("/history/{currency}", response_model=HistoryResponse)
def get_history(
    currency: str,
    source: str = Query("VISA", description="資料來源"),
    days: int = Query(30, ge=1, le=365, description="回傳最近 N 天的資料"),
) -> HistoryResponse:
    """指定幣別的歷史匯率，供前端折線圖使用。"""
    currency = currency.upper()
    if currency not in settings.currencies:
        raise HTTPException(
            status_code=404,
            detail=f"Currency '{currency}' not supported. Available: {settings.currencies}",
        )

    points = get_store().get_history(currency, source, days)
    return HistoryResponse(currency=currency, source=source, data=points)
