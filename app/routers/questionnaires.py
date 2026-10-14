"""四个业务端点；仅解析 HTTP 参数并返回响应 DTO。"""
from fastapi import APIRouter, Depends, Request

from ..core.security import base_url_of, require_api_key
from ..dto.common import Envelope
from ..dto.requests import SubmitFieldsRequest, WriteFieldsRequest
from ..dto.responses import (
    FieldsResponse, QuestionnaireLinkResponse, SubmitFieldsResponse, WriteFieldsResponse,
)
from .dependencies import Service

router = APIRouter(
    prefix="/questionnaires", tags=["问卷业务"], dependencies=[Depends(require_api_key)],
)


@router.post("", response_model=Envelope[WriteFieldsResponse], summary="1. 写入初始字段")
def write_fields(payload: WriteFieldsRequest, service: Service) -> Envelope[WriteFieldsResponse]:
    return Envelope(data=service.write_initial_fields(payload))


@router.post("/{app_id}/questionnaire", response_model=Envelope[QuestionnaireLinkResponse],
             summary="2. 生成问卷并返回填写链接")
def generate_questionnaire(app_id: str, request: Request, service: Service) -> Envelope[QuestionnaireLinkResponse]:
    return Envelope(data=service.generate_questionnaire(app_id, base_url_of(request)))


@router.post("/{app_id}/answers", response_model=Envelope[SubmitFieldsResponse], summary="3. 接收返回字段")
def receive_fields(app_id: str, payload: SubmitFieldsRequest, request: Request,
                   service: Service) -> Envelope[SubmitFieldsResponse]:
    return Envelope(data=service.receive_fields(
        app_id, payload, client_ip=request.client.host if request.client else "",
        user_agent=request.headers.get("user-agent", ""),
    ))


@router.get("/{app_id}", response_model=Envelope[FieldsResponse], summary="4. 返回所有字段")
def get_fields(app_id: str, service: Service) -> Envelope[FieldsResponse]:
    return Envelope(data=service.get_all_fields(app_id))
