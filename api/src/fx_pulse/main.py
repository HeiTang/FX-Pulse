from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .routers import rates

app = FastAPI(
    title="FX Pulse API",
    version="0.1.0",
    description="VISA 匯率歷史查詢 API",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["GET"],
    allow_headers=["*"],
)

app.include_router(rates.router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
