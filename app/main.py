"""FastAPI 应用入口。

启动：
    uv run uvicorn app.main:app --reload        # 开发
    uv run questionnaire-service                # 等价（读 .env 的 host/port）
    uv run python -m app                        # 同上
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from .core.config import settings
from .repositories.database import init_db
from .core.errors import ServiceError
from .core.responses import UTF8JSONResponse
from .dto.common import ErrorBody, ErrorDetail, ErrorEnvelope
from .routers import meta, public, questionnaires, ui

logger = logging.getLogger("questionnaire-service")


def _configure_logging() -> None:
    logging.basicConfig(
        level=getattr(logging, (settings.log_level or "INFO").upper(), logging.INFO),
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    _configure_logging()
    settings.ensure_dirs()
    if settings.db_create_tables:
        init_db()
    if not settings.auth_enabled:
        logger.warning("SERVICE_API_KEY 为空：/api/* 未启用鉴权，仅可用于本机联调；生产请在 .env 里配置。")
    if not settings.public_base_url or "127.0.0.1" in settings.public_base_url or "localhost" in settings.public_base_url:
        logger.warning("问卷链接使用本机地址；部署时请配置候选人可访问的 PUBLIC_BASE_URL。")
    logger.info("%s v%s 已启动", settings.service_name, settings.service_version)
    yield
    logger.info("服务已停止")


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.service_name,
        version=settings.service_version,
        description="写入初始字段 → 生成问卷 → 接收字段 → 返回所有字段。",
        docs_url=settings.docs_url,
        redoc_url=settings.redoc_url,
        openapi_url="/openapi.json" if settings.docs_url else None,
        default_response_class=UTF8JSONResponse,
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=settings.cors_origin_list != ["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # 业务接口（统一挂在 API_PREFIX 下）
    api = APIRouter(responses={
        status: {"model": ErrorEnvelope} for status in (400, 401, 404, 409, 410, 422, 500)
    })
    api.include_router(questionnaires.router)
    api.include_router(public.router)          # 候选人公开接口：令牌即凭证，不要 API Key
    app.include_router(api, prefix=settings.api_prefix)

    # 无前缀的运维/说明/页面路由
    app.include_router(meta.router)
    app.include_router(ui.router)              # /ui 控制台 + {QUESTIONNAIRE_PATH}/{token} 填写页

    @app.middleware("http")
    async def privacy_headers(request: Request, call_next):
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    _register_error_handlers(app)
    return app


def _err(status_code: int, code: str, message: str, details: list | None = None) -> JSONResponse:
    body = ErrorEnvelope(error=ErrorBody(
        code=code, message=message,
        details=[ErrorDetail.model_validate(item) for item in (details or [])],
    ))
    return UTF8JSONResponse(status_code=status_code, content=body.model_dump())


def _register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ServiceError)
    async def _service_error(_request: Request, exc: ServiceError) -> JSONResponse:
        return _err(exc.status_code, exc.code, exc.message, exc.details)

    @app.exception_handler(RequestValidationError)
    async def _validation_error(_request: Request, exc: RequestValidationError) -> JSONResponse:
        details = [
            {"field": ".".join(str(x) for x in e.get("loc", [])), "message": e.get("msg", "")}
            for e in exc.errors()
        ]
        return _err(422, "VALIDATION_FAILED", "请求参数不合法", details)

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(_request: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = {400: "BAD_REQUEST", 401: "UNAUTHORIZED", 403: "FORBIDDEN", 404: "NOT_FOUND",
                405: "METHOD_NOT_ALLOWED", 409: "CONFLICT", 410: "GONE", 422: "VALIDATION_FAILED",
                502: "UPSTREAM_ERROR"}.get(exc.status_code, "HTTP_ERROR")
        return _err(exc.status_code, code, str(exc.detail))

    @app.exception_handler(Exception)
    async def _unhandled(_request: Request, exc: Exception) -> JSONResponse:  # pragma: no cover
        logger.error("未处理异常类型：%s", type(exc).__name__)
        return _err(500, "INTERNAL_ERROR", "服务内部错误，请查看服务端日志")


app = create_app()


def run() -> None:
    import uvicorn

    uvicorn.run(
        "app.main:app", host=settings.service_host, port=settings.service_port,
        reload=settings.debug, log_level=settings.log_level.lower(),
        access_log=False,  # 候选人令牌位于 URL，避免写入访问日志。
    )


if __name__ == "__main__":
    run()
