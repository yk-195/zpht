"""候选人链接入口：复用生成问卷与接收字段用例，令牌作为凭证。"""
from fastapi import APIRouter, Request

from ..core.security import base_url_of
from ..dto.common import Envelope
from ..dto.requests import SubmitFieldsRequest
from ..dto.responses import QuestionnaireResponse, SubmitFieldsResponse
from .dependencies import Service

router = APIRouter(prefix="/public/questionnaires", tags=["候选人填写"])


@router.get("/{token}", response_model=Envelope[QuestionnaireResponse], summary="读取候选人问卷")
def read_questionnaire(token: str, request: Request, service: Service) -> Envelope[QuestionnaireResponse]:
    return Envelope(data=service.get_public_questionnaire(token, base_url_of(request)))


@router.post("/{token}/answers", response_model=Envelope[SubmitFieldsResponse], summary="提交候选人字段")
def submit_fields(token: str, payload: SubmitFieldsRequest, request: Request,
                  service: Service) -> Envelope[SubmitFieldsResponse]:
    return Envelope(data=service.receive_public_fields(
        token, payload, client_ip=request.client.host if request.client else "",
        user_agent=request.headers.get("user-agent", ""),
    ))
