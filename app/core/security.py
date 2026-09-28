"""FastAPI 依赖：接口鉴权 + 对外地址推导。"""

from __future__ import annotations

import secrets

from fastapi import Header, Request

from .config import settings
from .errors import Unauthorized


def require_api_key(
    x_api_key: str | None = Header(default=None, alias="X-API-Key",
                                  description="接口密钥；也支持 Authorization: Bearer <key>"),
    authorization: str | None = Header(default=None),
) -> None:
    """`SERVICE_API_KEY` 留空时不校验（仅限本机联调），填了就强制校验。"""
    if not settings.auth_enabled:
        return
    key = (x_api_key or "").strip()
    if not key and authorization and authorization.lower().startswith("bearer "):
        key = authorization[7:].strip()
    if not key or not secrets.compare_digest(key, settings.service_api_key.strip()):
        raise Unauthorized("接口密钥无效或缺失：请在请求头带 X-API-Key 或 Authorization: Bearer <key>")


def base_url_of(request: Request) -> str:
    """请求自身的对外地址，用于 `PUBLIC_BASE_URL` 留空时兜底。"""
    return str(request.base_url).rstrip("/")
