"""ORM 模型：3 张表。

- `questionnaires`  一次申请/一份问卷的当前状态（唯一键 `app_id`）
- `submissions`     候选人每次提交的原始答案（留痕 + 幂等键 `submission_id`）
- `events`          处理流水（写入 / 签发令牌 / 提交 / 状态迁移 / 异常）

时间统一存 **UTC 朴素时间**（SQLite 不保留时区），出参时补 `Z` 后缀，
避免不同数据库/驱动下"带不带时区"的不一致。
"""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

from sqlalchemy import JSON, DateTime, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base

# 状态取值
STATUS_PENDING = "pending"        # 已建档，等候选人补充
STATUS_SUBMITTED = "submitted"    # 候选人已提交，但仍缺必填项
STATUS_COMPLETED = "completed"    # 候选人已提交且无未填字段
STATUS_VOID = "void"              # 作废（链接同时失效）

STATUSES = (STATUS_PENDING, STATUS_SUBMITTED, STATUS_COMPLETED, STATUS_VOID)


def utcnow() -> dt.datetime:
    """UTC 朴素时间（秒级精度足够，微秒留着做排序）。"""
    return dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)


def to_iso(value: dt.datetime | None) -> str | None:
    """UTC 朴素时间 → `2026-09-18T07:30:00Z`。"""
    if value is None:
        return None
    return value.replace(microsecond=0).isoformat() + "Z"


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:16]}"


class Questionnaire(Base):
    """一份问卷（对应一位候选人 / 一个申请编号）。"""

    __tablename__ = "questionnaires"
    __table_args__ = (UniqueConstraint("app_id", name="uq_questionnaires_app_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    app_id: Mapped[str] = mapped_column(String(64), index=True)
    name: Mapped[str] = mapped_column(String(64), default="")
    status: Mapped[str] = mapped_column(String(16), default=STATUS_PENDING, index=True)
    source: Mapped[str] = mapped_column(String(32), default="resume")

    # 业务数据（字段名沿用 `03-字段字典与映射表.md`，是数据不是 key）
    main: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)          # 主表当前值（含合并结果）
    details: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)       # 4 个明细区当前值
    resume_main: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)   # 简历/初次写入的原值（用于对比改动）
    resume_details: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)

    missing_fields: Mapped[list[str]] = mapped_column(JSON, default=list)     # 未填字段（人可读）
    incomplete_fields: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)  # 值非空但未达门槛
    still_missing: Mapped[list[str]] = mapped_column(JSON, default=list)      # 提交后仍缺
    changed_fields: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)  # 候选人改动的已填字段

    # 填写链接令牌（明文仅存本条记录，接口按 app_id 取；可轮换）
    token: Mapped[str] = mapped_column(String(128), index=True, default="")
    token_expires_at: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)
    token_revoked: Mapped[int] = mapped_column(Integer, default=0)

    version: Mapped[int] = mapped_column(Integer, default=1)
    __mapper_args__ = {"version_id_col": version, "version_id_generator": False}
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)
    submitted_at: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)
    last_submission_id: Mapped[str] = mapped_column(String(64), default="")


class Submission(Base):
    """成功提交的原始答案；与问卷状态在同一事务保存。"""

    __tablename__ = "submissions"
    __table_args__ = (UniqueConstraint("submission_id", name="uq_submissions_submission_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    submission_id: Mapped[str] = mapped_column(String(64), index=True)
    app_id: Mapped[str] = mapped_column(String(64), index=True)
    sequence: Mapped[int] = mapped_column(Integer, default=1)     # 第几次提交
    main: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    details: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    changed_fields: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    confirmed: Mapped[int] = mapped_column(Integer, default=0)    # 是否勾选"核对无误"
    client_ip: Mapped[str] = mapped_column(String(64), default="")
    user_agent: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow)


class Event(Base):
    """处理流水：状态迁移、签发链接、提交、异常，带耗时。异常永不写明文敏感项。"""

    __tablename__ = "events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    app_id: Mapped[str] = mapped_column(String(64), index=True, default="")
    event: Mapped[str] = mapped_column(String(48), index=True)
    actor: Mapped[str] = mapped_column(String(32), default="system")
    detail: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    elapsed_ms: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow)


__all__ = [
    "Questionnaire",
    "Submission",
    "Event",
    "utcnow",
    "to_iso",
    "new_id",
    "STATUS_PENDING",
    "STATUS_SUBMITTED",
    "STATUS_COMPLETED",
    "STATUS_VOID",
    "STATUSES",
]
