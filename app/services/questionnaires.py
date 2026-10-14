"""四个用例：写入初始字段、生成问卷、接收字段、读取全部字段。"""
import copy
import datetime as dt
import secrets
import uuid

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm.exc import StaleDataError

from ..core.config import settings
from ..core.errors import Conflict, LinkExpired, NotFound, ValidationFailed
from ..domain import fields
from ..dto.requests import DetailFields, MainFields, SubmitFieldsRequest, WriteFieldsRequest
from ..dto.responses import (
    FieldsResponse, QuestionnaireLinkResponse, QuestionnaireResponse,
    SubmitFieldsResponse, WriteFieldsResponse,
)
from ..mappers.questionnaires import (
    to_fields, to_questionnaire, to_questionnaire_link, to_submission, to_write,
)
from ..repositories.models import (
    STATUS_COMPLETED, STATUS_PENDING, STATUS_SUBMITTED, STATUS_VOID,
    Event, Questionnaire, Submission, utcnow,
)
from ..repositories.questionnaires import QuestionnaireRepository


class QuestionnaireService:
    def __init__(self, repository: QuestionnaireRepository):
        self.repository = repository

    def write_initial_fields(self, request: WriteFieldsRequest) -> WriteFieldsResponse:
        self._validate(request.main, request.details)
        if not any(str(value if value is not None else "").strip() for value in request.main.values()) and not any(request.details.values()):
            raise ValidationFailed("请提供至少一个初始字段",
                                   errors=["main / details：至少要有一个非空字段值"])
        main, details = fields.normalize_values(request.main, request.details)
        entity = self.repository.find(request.app_id) if request.app_id else None
        created = entity is None
        if created:
            entity = Questionnaire(
                app_id=request.app_id or f"APP-{uuid.uuid4().hex}",
                name="", status=STATUS_PENDING, source="resume", version=1,
                main={}, details={}, resume_main={}, resume_details={},
                missing_fields=[], incomplete_fields={}, still_missing=[], changed_fields=[],
            )
            self.repository.add(entity)
        self._ensure_active(entity)
        merged = fields.merge(entity.main, entity.details, main, details)
        entity.main = fields.normalize_declarations(merged["main"])
        entity.details = merged["details"]
        entity.name = str(entity.main.get("姓名") or "")
        entity.resume_main = copy.deepcopy(entity.main)
        entity.resume_details = copy.deepcopy(entity.details)
        self._refresh_missing(entity, request.main)
        if entity.status in (STATUS_SUBMITTED, STATUS_COMPLETED) and (entity.missing_fields or entity.incomplete_fields):
            entity.status = STATUS_PENDING
        if not created:
            entity.version += 1
        entity.updated_at = utcnow()
        self._audit(entity, "write_info", "agent")
        # flush 填充数据库默认时间；DTO 校验成功后才提交事务。
        self._flush()
        result = to_write(entity, created)
        self._commit()
        return result

    def generate_questionnaire(self, app_id: str, base_url: str) -> QuestionnaireLinkResponse:
        """签发/复用填写令牌，只把填写链接与进度交回调用方（不回传题目）。"""
        entity = self._get(app_id)
        self._ensure_active(entity)
        if not self._token_valid(entity):
            entity.token = secrets.token_urlsafe(settings.token_bytes)
            entity.token_expires_at = utcnow() + dt.timedelta(days=settings.token_ttl_days)
            entity.token_revoked = 0
            entity.version += 1
            entity.updated_at = utcnow()
            self._audit(entity, "questionnaire_generated", "agent")
        result = to_questionnaire_link(entity, base_url)
        self._commit()
        return result

    def receive_fields(self, app_id: str, request: SubmitFieldsRequest, *,
                       client_ip: str = "", user_agent: str = "") -> SubmitFieldsResponse:
        return self._submit(self._get(app_id), request, client_ip, user_agent)

    def get_all_fields(self, app_id: str) -> FieldsResponse:
        return to_fields(self._get(app_id))

    def get_public_questionnaire(self, token: str, base_url: str) -> QuestionnaireResponse:
        return to_questionnaire(self._resolve_token(token), base_url)

    def receive_public_fields(self, token: str, request: SubmitFieldsRequest, *,
                              client_ip: str = "", user_agent: str = "") -> SubmitFieldsResponse:
        return self._submit(self._resolve_token(token), request, client_ip, user_agent)

    def _submit(self, entity: Questionnaire, request: SubmitFieldsRequest,
                client_ip: str, user_agent: str) -> SubmitFieldsResponse:
        self._ensure_active(entity)
        self._validate(request.main, request.details)
        main, details = fields.normalize_values(request.main, request.details)
        submission_id = request.submission_id or f"SUB-{uuid.uuid4().hex}"
        previous = self.repository.submission(submission_id)
        if previous is not None:
            # 全局唯一键保留兼容旧库；跨申请或换内容复用都拒绝，绝不回放他人数据。
            if (previous.app_id != entity.app_id or previous.main != main
                    or previous.details != details or bool(previous.confirmed) != request.confirmed):
                raise Conflict("提交 ID 已被使用，请使用新的 submission_id")
            return to_submission(entity, previous)
        if entity.submitted_at and not settings.allow_resubmit:
            raise Conflict("该问卷已提交，不允许重复提交")
        merged = fields.merge(entity.main, entity.details, main, details)
        merged_main = fields.normalize_declarations(merged["main"])
        errors = fields.conditional_errors(merged_main)
        if errors:
            raise ValidationFailed(errors=errors)
        entity.main = merged_main
        entity.details = merged["details"]
        entity.changed_fields = merged["changed"]
        entity.name = str(merged_main.get("姓名") or "")
        self._refresh_missing(entity, request.main)
        entity.status = (
            STATUS_COMPLETED if settings.auto_complete_on_submit and not entity.missing_fields and not entity.incomplete_fields
            else STATUS_SUBMITTED
        )
        submission = Submission(
            submission_id=submission_id, app_id=entity.app_id,
            sequence=self.repository.next_sequence(entity.app_id),
            main=main, details=details, changed_fields=merged["changed"],
            confirmed=int(request.confirmed), client_ip=client_ip[:64], user_agent=user_agent[:2000],
        )
        self.repository.add(submission)
        entity.submitted_at = utcnow()
        entity.updated_at = entity.submitted_at
        entity.last_submission_id = submission_id
        entity.version += 1
        self._audit(entity, "submit_answers", "candidate")
        self._flush()
        result = to_submission(entity, submission)
        self._commit()
        return result

    def _get(self, app_id: str) -> Questionnaire:
        entity = self.repository.find(app_id)
        if entity is None:
            raise NotFound()
        return entity

    def _resolve_token(self, token: str) -> Questionnaire:
        entity = self.repository.by_token(token) if token else None
        if entity is None or entity.status == STATUS_VOID or not self._token_valid(entity):
            raise LinkExpired("链接无效或已过期，请联系 HR 重新获取")
        return entity

    @staticmethod
    def _token_valid(entity: Questionnaire) -> bool:
        return bool(entity.token and not entity.token_revoked and entity.token_expires_at
                    and entity.token_expires_at > utcnow())

    @staticmethod
    def _ensure_active(entity: Questionnaire) -> None:
        if entity.status == STATUS_VOID:
            raise Conflict("该申请已作废")

    @staticmethod
    def _validate(main: MainFields, details: DetailFields) -> None:
        errors = []
        if set(main) - set(fields.FIELD_BY_NAME):
            errors.append("main 包含未定义字段")
        if set(details) - set(fields.DETAIL_KEYS):
            errors.append("details 包含未定义明细区")
        for key, rows in details.items():
            if key not in fields.DETAIL_FIELDS:
                continue
            allowed = {definition["name"] for definition in fields.DETAIL_FIELDS[key]} | {"序号"}
            if any(set(row) - allowed for row in rows):
                errors.append(f"{key}包含未定义字段")
        errors.extend(fields.validate_all(main, details))
        if errors:
            raise ValidationFailed(errors=errors)

    @staticmethod
    def _refresh_missing(entity: Questionnaire, raw_main: MainFields) -> None:
        incomplete = dict(entity.incomplete_fields or {})
        for key, value in raw_main.items():
            if str(value or "").strip():
                incomplete.pop(key, None)
        incomplete.update(fields.incomplete_of(raw_main))
        entity.incomplete_fields = incomplete
        entity.missing_fields = fields.compute_missing(entity.main, entity.details)
        entity.still_missing = list(entity.missing_fields)

    def _audit(self, entity: Questionnaire, event: str, actor: str) -> None:
        self.repository.add(Event(
            app_id=entity.app_id, event=event, actor=actor,
            detail={"missing_count": len(entity.missing_fields)},
        ))

    def _flush(self) -> None:
        try:
            self.repository.flush()
        except (IntegrityError, StaleDataError) as exc:
            self.repository.rollback()
            raise Conflict("记录已被更新或提交 ID 冲突，请刷新后重试") from exc

    def _commit(self) -> None:
        try:
            self.repository.commit()
        except (IntegrityError, StaleDataError) as exc:
            self.repository.rollback()
            raise Conflict("记录已被更新或提交 ID 冲突，请刷新后重试") from exc
