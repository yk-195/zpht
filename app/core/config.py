"""配置中心：所有可配置项都从 .env 读取，代码里不出现魔法值。

优先级：进程环境变量 > `.env` 文件 > 本文件默认值。
`.env` 路径固定指向 service 根目录，因此从任何工作目录启动都能读到同一份配置。
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# service/ 根目录（config.py 在 service/app/core/ 下）
ROOT_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(ROOT_DIR / ".env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ------------------------------------------------------------ 1. 服务基础
    service_name: str = "求职申请表·问卷调查服务"
    service_version: str = "0.1.0"
    env: str = "dev"
    debug: bool = True
    service_host: str = "127.0.0.1"
    service_port: int = 8000
    api_prefix: str = "/api/v1"
    public_base_url: str = "http://127.0.0.1:8000"
    questionnaire_path: str = "/q"
    cors_origins: str = "*"
    log_level: str = "INFO"
    ui_enabled: bool = True

    # ------------------------------------------------------------ 2. 数据库
    database_url: str = Field(default="sqlite:///./data/service.db", repr=False, exclude=True)
    db_echo: bool = False
    db_create_tables: bool = True
    data_dir: str = "./data"

    # ------------------------------------------------------------ 3. 接口鉴权
    service_api_key: str = Field(default="", repr=False, exclude=True)

    # ------------------------------------------------------------ 4. 链接与令牌
    token_ttl_days: int = Field(default=7, ge=1, le=365)
    token_bytes: int = Field(default=32, ge=32, le=64)
    allow_resubmit: bool = True
    auto_complete_on_submit: bool = True

    # 家庭成员明细最多几行（纸表 ZMF-HR-WI-BG-004 只有 4 行；要严格对齐成稿模板就改回 4）
    family_max_rows: int = Field(default=5, ge=1, le=20)
    # 家庭成员「关系」的下拉选项（逗号分隔，页面渲染成选择框而不是输入框）
    family_relation_options: str = "父亲,母亲,配偶,子,女,兄,弟,姐,妹,其他"
    # 「健康状况」的下拉选项（逗号分隔）
    health_options: str = "良好,一般,较差"

    # ------------------------------------------------------------ 派生属性
    @property
    def cors_origin_list(self) -> list[str]:
        """CORS_ORIGINS 支持 `*` 或逗号分隔的多个来源。"""
        raw = (self.cors_origins or "").strip()
        if not raw or raw == "*":
            return ["*"]
        return [x.strip() for x in raw.split(",") if x.strip()]

    @property
    def docs_url(self) -> str | None:
        return "/docs" if self.debug or self.env != "prod" else None

    @property
    def redoc_url(self) -> str | None:
        return "/redoc" if self.debug or self.env != "prod" else None

    @property
    def auth_enabled(self) -> bool:
        return bool(self.service_api_key.strip())

    @property
    def family_relation_list(self) -> list[str]:
        """家庭成员「关系」可选值；留空时退回默认列表。"""
        items = [x.strip() for x in (self.family_relation_options or "").split(",") if x.strip()]
        return items or ["父亲", "母亲", "配偶", "子", "女", "兄", "弟", "姐", "妹", "其他"]

    @property
    def health_option_list(self) -> list[str]:
        """「健康状况」可选值；留空时退回默认列表。"""
        items = [x.strip() for x in (self.health_options or "").split(",") if x.strip()]
        return items or ["良好", "一般", "较差"]

    def path(self, value: str) -> Path:
        """把配置里的相对路径解析成绝对路径（相对 service/ 根目录）。"""
        p = Path(value)
        return p if p.is_absolute() else (ROOT_DIR / p).resolve()

    @property
    def data_path(self) -> Path:
        return self.path(self.data_dir)

    @property
    def static_path(self) -> Path:
        source = ROOT_DIR / "static"
        return source if source.is_dir() else Path(__file__).resolve().parents[1] / "web"

    @property
    def questionnaire_prefix(self) -> str:
        p = self.questionnaire_path.strip() or "/q"
        return p if p.startswith("/") else "/" + p

    def public_url(self, path: str, fallback_base: str | None = None) -> str:
        """拼对外地址；PUBLIC_BASE_URL 留空时用请求自身的 base_url 兜底。"""
        base = (self.public_base_url or "").strip().rstrip("/") or (fallback_base or "").rstrip("/")
        p = path if path.startswith("/") else "/" + path
        return f"{base}{p}"

    def ensure_dirs(self) -> None:
        self.data_path.mkdir(parents=True, exist_ok=True)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """单例；测试里可用 `get_settings.cache_clear()` 重载。"""
    return Settings()


settings = get_settings()
