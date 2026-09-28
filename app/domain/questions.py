"""从字段状态生成问卷，不依赖 ORM 或 HTTP。"""
from ..dto.requests import DetailFields, MainFields
from ..dto.responses import Question
from . import fields


def build_questions(main: MainFields, details: DetailFields,
                    incomplete: dict[str, str]) -> list[Question]:
    questions: list[Question] = []
    for definition in fields.MAIN_FIELDS:
        if not fields.field_applicable(definition, main):
            continue
        name = definition["name"]
        value = str(main.get(name) or "").strip()
        if value and name not in incomplete:
            continue
        is_incomplete = name in incomplete
        questions.append(Question(
            name=name, label=definition["label"], kind=definition["kind"],
            group=definition["group"], required=definition["required"],
            options=definition["options"], hint=definition.get("hint", ""),
            current_value=value, reason="incomplete" if is_incomplete else "empty",
            reason_text=incomplete.get(name, "尚未填写"),
            section="main", depends_on=definition.get("depends_on"),
        ))
    for definition in fields.DETAILS:
        rows = [
            row for row in details.get(definition["key"], [])
            if any(str(value).strip() for value in row.values())
        ]
        required = definition["key"] != "家庭成员明细"
        max_rows = fields.detail_max(definition)
        if rows:
            reason = "imported"
            reason_text = f"已导入 {len(rows)} 条，可修改或继续补充（最多 {max_rows} 条）"
        elif required:
            reason = "empty"
            reason_text = f"至少填写 1 条{definition['label']}（最多 {max_rows} 条）"
        else:
            reason = "optional"
            reason_text = f"选填，最多 {max_rows} 条"
        questions.append(Question(
            name=definition["key"], label=definition["label"], kind="detail",
            group="明细", required=required, reason=reason, reason_text=reason_text,
            section="detail", rows=rows, max_rows=max_rows,
        ))
    return questions
