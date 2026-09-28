"""业务异常与统一错误码（配合 dto.common.ErrorEnvelope）。"""

from __future__ import annotations

from typing import Any


class ServiceError(Exception):
    """业务异常基类：抛出后由 main.py 的异常处理器转成统一错误信封。"""

    code = "ERROR"
    status_code = 400

    def __init__(self, message: str, *, code: str | None = None,
                 status_code: int | None = None, details: list[dict[str, Any]] | None = None):
        super().__init__(message)
        self.message = message
        if code:
            self.code = code
        if status_code:
            self.status_code = status_code
        self.details = details


class NotFound(ServiceError):
    code = "NOT_FOUND"
    status_code = 404

    def __init__(self, message: str = "未找到该申请记录", **kw):
        super().__init__(message, **kw)


class ValidationFailed(ServiceError):
    """字段校验不通过（身份证校验位、枚举取值、日期格式…）。"""

    code = "VALIDATION_FAILED"
    status_code = 422

    def __init__(self, message: str = "提交的数据未通过校验", errors: list[str] | None = None):
        details = [{"field": "", "message": e} for e in (errors or [])]
        super().__init__(message, details=details)
        self.errors = errors or []


class Unauthorized(ServiceError):
    code = "UNAUTHORIZED"
    status_code = 401


class Forbidden(ServiceError):
    code = "FORBIDDEN"
    status_code = 403


class Conflict(ServiceError):
    code = "CONFLICT"
    status_code = 409


class LinkExpired(ServiceError):
    code = "LINK_EXPIRED"
    status_code = 410
