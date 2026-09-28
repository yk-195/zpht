"""业务响应 DTO；动态中文字段为业务数据，外层结构固定且可校验。"""
from typing import Any, Literal

from pydantic import Field, computed_field, field_validator

from .common import DTO
from .requests import MainFields, DetailFields


class Progress(DTO):
    total_fields: int
    filled_fields: int
    missing_fields: int
    required_total: int
    required_filled: int
    completion_rate: float


class Question(DTO):
    """问卷里的一道题（未填 / 不完整）。"""

    name: str
    label: str
    kind: str
    group: str = "基本信息"
    required: bool = False
    options: list[str] | None = None
    hint: str = ""
    current_value: str = ""
    reason: str = ""            # 为什么进问卷：empty / incomplete / imported / optional
    reason_text: str = ""
    section: str = "main"       # main / detail
    rows: list[MainFields] | None = Field(
        default=None, description="明细区题目：已导入的行（原样回显，供修改与继续补充）")
    max_rows: int | None = Field(default=None, description="明细区题目：最多几行")
    depends_on: tuple[str, list[str]] | None = Field(
        default=None, description="声明类说明字段的依赖：[选项字段, [触发的取值…]]")

    @field_validator("options", mode="before")
    @classmethod
    def _options_only_for_enum(cls, v: Any) -> Any:
        """非枚举字段即使契约里带了文本提示，也不当作选项输出。"""
        if isinstance(v, str):
            return None
        return v



class FieldDefinition(DTO):
    name: str
    label: str = ""
    kind: str
    required: bool = False
    group: str = ""
    options: list[str] | str | None = None
    hint: str = ""
    depends_on: tuple[str, list[str]] | None = None


class DetailDefinition(DTO):
    key: str
    label: str
    max: int
    fields: list[FieldDefinition]


class ContractCounts(DTO):
    main_total: int
    main_required: int
    detail_sections: int
    detail_rows_total: int


class FieldContract(DTO):
    contract_version: str
    main_fields: list[FieldDefinition]
    details: list[DetailDefinition]
    required_main_fields: list[str]
    optional_main_fields: list[str]
    never_from_resume: list[str]
    counts: ContractCounts


class FieldChange(DTO):
    field: str = Field(validation_alias="字段")
    original: str = Field(validation_alias="原值")
    updated: str = Field(validation_alias="新值")


class FieldsResponse(DTO):
    app_id: str
    name: str
    status: Literal["pending", "submitted", "completed", "void"]
    version: int
    main: MainFields
    details: DetailFields
    missing_fields: list[str]
    incomplete_fields: dict[str, str]
    progress: Progress
    created_at: str | None
    updated_at: str | None
    submitted_at: str | None

    @computed_field
    @property
    def missing_count(self) -> int:
        return len(self.missing_fields)

    @computed_field
    @property
    def incomplete_count(self) -> int:
        return len(self.incomplete_fields)


class WriteFieldsResponse(FieldsResponse):
    created: bool


class QuestionnaireResponse(DTO):
    app_id: str
    name: str
    status: str
    questions: list[Question]
    contract: FieldContract
    recognized: MainFields
    missing_fields: list[str]
    required_missing: list[str]
    incomplete_fields: dict[str, str]
    progress: Progress
    fill_url: str
    expires_at: str | None
    allow_resubmit: bool

    @computed_field
    @property
    def question_count(self) -> int:
        return len(self.questions)

    @computed_field
    @property
    def missing_count(self) -> int:
        return len(self.missing_fields)

    @computed_field
    @property
    def incomplete_count(self) -> int:
        return len(self.incomplete_fields)


class SubmitFieldsResponse(FieldsResponse):
    submission_id: str
    sequence: int
    changed_fields: list[FieldChange]

    @computed_field
    @property
    def changed_count(self) -> int:
        return len(self.changed_fields)
