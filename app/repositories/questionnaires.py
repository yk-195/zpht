"""所有 SQL 查询集中在仓储；服务层不拼 SQL。"""
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .models import Event, Questionnaire, Submission


class QuestionnaireRepository:
    def __init__(self, session: Session):
        self.session = session

    def find(self, app_id: str) -> Questionnaire | None:
        return self.session.scalar(select(Questionnaire).where(Questionnaire.app_id == app_id))

    def by_token(self, token: str) -> Questionnaire | None:
        return self.session.scalar(select(Questionnaire).where(Questionnaire.token == token))

    def submission(self, submission_id: str) -> Submission | None:
        return self.session.scalar(select(Submission).where(Submission.submission_id == submission_id))

    def next_sequence(self, app_id: str) -> int:
        latest = self.session.scalar(
            select(func.max(Submission.sequence)).where(Submission.app_id == app_id)
        )
        return (latest or 0) + 1

    def add(self, entity: Questionnaire | Submission | Event) -> None:
        self.session.add(entity)

    def flush(self) -> None:
        self.session.flush()

    def commit(self) -> None:
        self.session.commit()

    def rollback(self) -> None:
        self.session.rollback()
