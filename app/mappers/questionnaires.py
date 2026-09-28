"""显式白名单映射，不返回 ORM 实体、数据库配置或审计日志。"""
from ..core.config import settings
from ..domain import fields
from ..domain.questions import build_questions
from ..dto.responses import (
    FieldChange, FieldContract, FieldsResponse, Progress, QuestionnaireResponse,
    SubmitFieldsResponse, WriteFieldsResponse,
)
from ..repositories.models import Questionnaire, Submission, to_iso


def to_fields(entity: Questionnaire) -> FieldsResponse:
    return FieldsResponse(
        app_id=entity.app_id, name=entity.name, status=entity.status, version=entity.version,
        main=entity.main, details=entity.details, missing_fields=entity.missing_fields,
        incomplete_fields=entity.incomplete_fields,
        progress=Progress.model_validate(fields.completion_stats(entity.main, entity.details)),
        created_at=to_iso(entity.created_at), updated_at=to_iso(entity.updated_at),
        submitted_at=to_iso(entity.submitted_at),
    )


def to_write(entity: Questionnaire, created: bool) -> WriteFieldsResponse:
    return WriteFieldsResponse(**to_fields(entity).model_dump(exclude={"missing_count", "incomplete_count"}), created=created)


def to_questionnaire(entity: Questionnaire, base_url: str) -> QuestionnaireResponse:
    main, details = entity.main, entity.details
    required_missing = [
        definition["name"] for definition in fields.MAIN_FIELDS
        if definition["required"] and fields.field_applicable(definition, main)
        and not str(main.get(definition["name"]) or "").strip()
    ]
    return QuestionnaireResponse(
        app_id=entity.app_id, name=entity.name, status=entity.status,
        questions=build_questions(main, details, entity.incomplete_fields),
        contract=FieldContract.model_validate(fields.field_contract()),
        recognized=main, missing_fields=entity.missing_fields,
        required_missing=required_missing, incomplete_fields=entity.incomplete_fields,
        progress=Progress.model_validate(fields.completion_stats(main, details)),
        fill_url=settings.public_url(f"{settings.questionnaire_prefix}/{entity.token}", base_url),
        expires_at=to_iso(entity.token_expires_at), allow_resubmit=settings.allow_resubmit,
    )


def to_submission(entity: Questionnaire, submission: Submission) -> SubmitFieldsResponse:
    return SubmitFieldsResponse(
        **to_fields(entity).model_dump(exclude={"missing_count", "incomplete_count"}),
        submission_id=submission.submission_id, sequence=submission.sequence,
        changed_fields=[FieldChange.model_validate(change) for change in submission.changed_fields],
    )
