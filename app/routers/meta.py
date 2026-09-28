"""最小健康检查；不返回配置、数据库 URL 或底层错误。"""
from fastapi import APIRouter, Response
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from ..dto.common import Envelope, HealthResponse
from ..repositories.database import engine

router = APIRouter(tags=["health"])


@router.get("/health", response_model=Envelope[HealthResponse])
def health(response: Response) -> Envelope[HealthResponse]:
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except SQLAlchemyError:
        response.status_code = 503
        return Envelope(data=HealthResponse(status="degraded"))
    return Envelope(data=HealthResponse(status="up"))
