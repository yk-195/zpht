"""测试环境准备：必须在导入 app 之前设置环境变量。

用的是一份临时 SQLite 库，不碰 `data/service.db`。
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

_TMP = Path(tempfile.mkdtemp(prefix="qsvc-test-"))

# 环境变量优先级高于 .env，因此这些值会覆盖 service/.env
os.environ.update({
    "DATABASE_URL": f"sqlite:///{(_TMP / 'test.db').as_posix()}",
    "DATA_DIR": str(_TMP),
    "SERVICE_API_KEY": "",              # 默认不鉴权，鉴权用例里单独改
    "UI_ENABLED": "true",               # 生产 .env 里可能关掉控制台，但测试要覆盖页面本身
    "PUBLIC_BASE_URL": "http://testserver",
    "QUESTIONNAIRE_PATH": "/q",
    "TOKEN_TTL_DAYS": "7",
    "DB_CREATE_TABLES": "true",
    "DEBUG": "false",
    "ENV": "test",
    "API_PREFIX": "/api/v1",
    "ALLOW_RESUBMIT": "true",
    "AUTO_COMPLETE_ON_SUBMIT": "true",
    "FAMILY_MAX_ROWS": "5",
    "LOG_LEVEL": "WARNING",
})

import pytest                                   # noqa: E402
from fastapi.testclient import TestClient       # noqa: E402

from app.core.config import settings                # noqa: E402
from app.main import app                       # noqa: E402


@pytest.fixture(scope="session")
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture
def api():
    """返回 (client, 前缀) 便于拼路径。"""
    from app.core.config import settings as s

    with TestClient(app) as c:
        yield c, s.api_prefix


@pytest.fixture
def no_auth():
    """临时关闭鉴权。"""
    old = settings.service_api_key
    settings.service_api_key = ""
    yield
    settings.service_api_key = old
