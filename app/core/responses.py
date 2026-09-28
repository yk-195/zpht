"""统一响应类。

响应里大量中文字段名，必须显式声明 `charset=utf-8`：
不带 charset 时，Windows PowerShell 的 `Invoke-RestMethod` 之类客户端会按 Latin-1 解码，
中文全变乱码（本项目的运维/联调脚本基本都在 Windows 上跑）。
"""

from __future__ import annotations

from fastapi.responses import JSONResponse


class UTF8JSONResponse(JSONResponse):
    media_type = "application/json"

    def init_headers(self, headers=None) -> None:
        super().init_headers(headers)
        self.headers["content-type"] = "application/json; charset=utf-8"
