"""四个业务流程的入参；不再支持顶层平铺字段或客户端 IP。"""
from typing import Annotated

from pydantic import Field, StrictFloat, StrictInt, StrictStr

from .common import DTO

FieldValue = StrictStr | StrictInt | StrictFloat | None
MainFields = dict[str, FieldValue]
DetailFields = dict[str, list[dict[str, FieldValue]]]
Identifier = Annotated[str, Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")]


class WriteFieldsRequest(DTO):
    app_id: Identifier | None = None
    main: MainFields = Field(default_factory=dict)
    details: DetailFields = Field(default_factory=dict)


class SubmitFieldsRequest(DTO):
    submission_id: Identifier | None = None
    main: MainFields = Field(default_factory=dict)
    details: DetailFields = Field(default_factory=dict)
    confirmed: bool = False
