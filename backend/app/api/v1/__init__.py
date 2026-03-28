from fastapi import APIRouter

from app.api.v1.auth import router as auth_router
from app.api.v1.strategies import router as strategies_router
from app.api.v1.orders import router as orders_router
from app.api.v1.backtest import router as backtest_router
from app.api.v1.portfolio import router as portfolio_router
from app.api.v1.exchange import router as exchange_router

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(auth_router)
api_router.include_router(strategies_router)
api_router.include_router(orders_router)
api_router.include_router(backtest_router)
api_router.include_router(portfolio_router)
api_router.include_router(exchange_router)

__all__ = ["api_router"]
