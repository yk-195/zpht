"""统一响应信封；所有公开 JSON 响应都有明确 DTO。"""
from typing import Generic, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T")


class DTO(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Envelope(DTO, Generic[T]):
    ok: Literal[True] = True
    data: T


class ErrorDetail(DTO):
    field: str = ""
    message: str


class ErrorBody(DTO):
    code: str
    message: str
    details: list[ErrorDetail] = Field(default_factory=list)


class ErrorEnvelope(DTO):
    ok: Literal[False] = False
    error: ErrorBody


class HealthResponse(DTO):
    status: Literal["up", "degraded"]
