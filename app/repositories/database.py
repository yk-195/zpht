"""数据库：引擎 / 会话 / 建表。

默认 SQLite（零依赖、单机够用）；把 `.env` 里的 `DATABASE_URL` 换成 PostgreSQL /
MySQL 即可切换，模型层未使用任何 SQLite 专有语法。
"""

from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from ..core.config import settings


class Base(DeclarativeBase):
    pass


def _normalize_url(url: str) -> str:
    """把 sqlite 的相对路径解析成 service 根目录下的绝对路径。

    否则 `sqlite:///./data/service.db` 会跟着"启动时的工作目录"跑，换个目录启动就换了库。
    """
    prefix = "sqlite:///"
    if url.startswith(prefix) and not url.startswith("sqlite:////"):
        raw = url[len(prefix):]
        if raw and not raw.startswith(":"):          # `:memory:` 保持原样
            from pathlib import Path

            p = Path(raw)
            if not p.is_absolute():
                p = (settings.path(raw)).resolve()
            return f"{prefix}{p.as_posix()}"
    return url


DATABASE_URL = _normalize_url(settings.database_url)

_is_sqlite = DATABASE_URL.startswith("sqlite")

engine = create_engine(
    DATABASE_URL,
    echo=settings.db_echo,
    future=True,
    pool_pre_ping=not _is_sqlite,
    connect_args={"check_same_thread": False} if _is_sqlite else {},
)

if _is_sqlite:

    @event.listens_for(engine, "connect")
    def _sqlite_pragmas(dbapi_conn, _record):  # pragma: no cover - 驱动层钩子
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA journal_mode=WAL")       # 读写并发更稳
        cur.execute("PRAGMA foreign_keys=ON")
        cur.close()


SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)


def init_db() -> None:
    """建表（幂等）。"""
    from . import models  # noqa: F401  确保模型已注册到 Base.metadata

    settings.ensure_dirs()
    Base.metadata.create_all(bind=engine)


def get_db() -> Iterator[Session]:
    """FastAPI 依赖：一个请求一个会话；事务由应用服务提交，异常回滚。"""
    db = SessionLocal()
    try:
        yield db
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
