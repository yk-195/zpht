"""请求级应用服务装配。"""
from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from ..repositories.database import get_db
from ..repositories.questionnaires import QuestionnaireRepository
from ..services.questionnaires import QuestionnaireService


def questionnaire_service(session: Annotated[Session, Depends(get_db)]) -> QuestionnaireService:
    return QuestionnaireService(QuestionnaireRepository(session))


Service = Annotated[QuestionnaireService, Depends(questionnaire_service)]
