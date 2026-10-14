"""围绕四个用例、DTO 边界、事务与私有配置的集成测试。"""
import datetime as dt
import json
from urllib.parse import urlsplit

import pytest
from sqlalchemy import func, select

from app.core.config import settings
from app.repositories.database import SessionLocal
from app.repositories.models import Event, Questionnaire, Submission, utcnow


def create(client, prefix, **overrides):
    body = {"main": {"姓名": "张伟", "手机号码": "13800000001"},
            "details": {"家庭成员明细": [{"姓名": "张一", "关系": "父亲"}]}}
    body.update(overrides)
    response = client.post(f"{prefix}/questionnaires", json=body)
    assert response.status_code == 200, response.text
    return response.json()["data"]


def generate(client, prefix, app_id):
    """生成问卷：只返回填写链接与进度，不返回题目本身。"""
    response = client.post(f"{prefix}/questionnaires/{app_id}/questionnaire")
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    # 题目、字段契约、已识别值都不该出现在生成接口的返回里。
    assert {"questions", "contract", "recognized"}.isdisjoint(data)
    return data


def public_questionnaire(client, prefix, app_id):
    """签发链接后，按令牌从公开接口取完整问卷（题目在候选人侧）。"""
    token = generate(client, prefix, app_id)["fill_url"].rsplit("/", 1)[1]
    response = client.get(f"{prefix}/public/questionnaires/{token}")
    assert response.status_code == 200, response.text
    return response.json()["data"]


def test_four_step_flow(api):
    client, prefix = api
    written = create(client, prefix)
    app_id = written["app_id"]
    assert written["created"] is True
    assert written["main"]["姓名"] == "张伟"
    link = generate(client, prefix, app_id)
    assert link["fill_url"].startswith("http")
    assert link["question_count"] > 0
    token = link["fill_url"].rsplit("/", 1)[1]
    assert client.get(urlsplit(link["fill_url"]).path).status_code == 200
    public = client.get(f"{prefix}/public/questionnaires/{token}")
    assert public.status_code == 200
    questionnaire = public.json()["data"]
    assert questionnaire["question_count"] == len(questionnaire["questions"])
    assert questionnaire["contract"]["counts"]["main_total"] == 34
    family = next(q for q in questionnaire["questions"] if q["name"] == "家庭成员明细")
    assert family["rows"][0]["姓名"] == "张一"
    assert family["max_rows"] == 5
    marriage = next(q for q in questionnaire["questions"] if q["name"] == "婚姻状况")
    assert marriage["options"] == ["未婚", "已婚", "离异", "丧偶"]
    submitted = client.post(f"{prefix}/public/questionnaires/{token}/answers",
                            json={"main": {"婚姻状况": "未婚"}, "confirmed": True})
    assert submitted.status_code == 200, submitted.text
    result = client.get(f"{prefix}/questionnaires/{app_id}").json()["data"]
    assert result["main"]["姓名"] == "张伟"
    assert result["main"]["婚姻状况"] == "未婚"
    assert result["details"]["家庭成员明细"][0]["姓名"] == "张一"
    assert "婚姻状况" not in result["missing_fields"]
    assert result["status"] == "submitted"
    assert {"token", "resume_main", "events", "database_url"}.isdisjoint(result)


def test_write_merges_without_changing_valid_link(api):
    client, prefix = api
    first = create(client, prefix)
    link = generate(client, prefix, first["app_id"])["fill_url"]
    second = create(client, prefix, app_id=first["app_id"], main={"专业": "计算机"}, details={})
    assert not second["created"]
    assert second["main"]["姓名"] == first["main"]["姓名"]
    assert second["main"]["专业"] == "计算机"
    assert generate(client, prefix, first["app_id"])["fill_url"] == link


@pytest.mark.parametrize("body", [
    {"姓名": "不再支持平铺"},
    {"main": {"姓名": "张伟"}, "overwrite": True},
    {"main": {"姓名": "张伟"}, "client_ip": "伪造"},
    {"main": {"未知字段": "值"}},
    {"details": {"未知明细": []}},
    {"details": {"家庭成员明细": [{"姓名": "甲", "关系": "父亲", "秘密": "值"}]}},
    {"main": {"姓名": {"nested": "object"}}},
    {"main": {"性别": "男性"}},
    {"main": {"身份证号": "310101199503121231"}},
    {"main": {"出生日期": "1995/13/45"}},
    {"app_id": "../escape", "main": {"姓名": "张伟"}},
    {},
])
def test_request_contract_rejects_invalid_input(api, body):
    client, prefix = api
    response = client.post(f"{prefix}/questionnaires", json=body)
    assert response.status_code == 422, response.text
    assert response.json()["error"]["code"] == "VALIDATION_FAILED"


def test_idcard_derivation_and_incomplete_dates(api):
    client, prefix = api
    result = create(client, prefix, main={"姓名": "张伟", "身份证号": "310101199503121230"})
    assert result["main"]["出生日期"] == "1995-03-12"
    assert result["main"]["性别"] == "男"
    partial = create(client, prefix, main={"姓名": "张伟", "出生日期": "1995-03"})
    question = public_questionnaire(client, prefix, partial["app_id"])
    birthday = next(q for q in question["questions"] if q["name"] == "出生日期")
    assert birthday["reason"] == "incomplete"
    response = client.post(f"{prefix}/questionnaires/{partial['app_id']}/answers",
                           json={"main": {"出生日期": "1995-03-12"}})
    assert response.status_code == 200
    assert "出生日期" not in response.json()["data"]["incomplete_fields"]


def test_zero_is_a_valid_initial_value(api):
    client, prefix = api
    result = create(client, prefix, main={"子女数目_子": 0}, details={})
    assert result["main"]["子女数目_子"] == "0"


def test_field_changes_have_explicit_dto_keys(api):
    client, prefix = api
    record = create(client, prefix)
    response = client.post(f"{prefix}/questionnaires/{record['app_id']}/answers",
                           json={"main": {"姓名": "更新姓名"}})
    assert response.status_code == 200
    assert response.json()["data"]["changed_fields"] == [
        {"field": "姓名", "original": "张伟", "updated": "更新姓名"}]


def test_detail_row_limit(api):
    client, prefix = api
    body = {"main": {"姓名": "张伟"}, "details": {
        "家庭成员明细": [{"姓名": str(i), "关系": "兄"} for i in range(6)]}}
    assert client.post(f"{prefix}/questionnaires", json=body).status_code == 422


def test_family_and_work_experience_are_optional(api):
    """家庭成员与工作经验为非必填：整块为空不算未填，题目标记「选填」。"""
    client, prefix = api
    record = create(client, prefix, details={})
    missing = record["missing_fields"]
    assert not [item for item in missing if item.startswith("家庭成员")]
    assert not [item for item in missing if item.startswith("工作经验")]
    # 另外两个明细区仍然必填，没被一起放开
    assert [item for item in missing if item.startswith("学历 / 培训")]
    assert [item for item in missing if item.startswith("资历及专业资格")]

    questions = public_questionnaire(client, prefix, record["app_id"])["questions"]
    details = {q["name"]: q for q in questions if q["kind"] == "detail"}
    for name in ("家庭成员明细", "工作经验明细"):
        assert details[name]["required"] is False, name
        assert details[name]["reason"] == "optional", name
        assert "选填" in details[name]["reason_text"], name
    for name in ("学历培训明细", "资历专业资格明细"):
        assert details[name]["required"] is True, name
        assert details[name]["reason"] == "empty", name


def test_optional_sections_do_not_block_progress(api):
    """没填家庭成员与工作经验时，明细区不应再产生「至少 1 条」的未填项。"""
    client, prefix = api
    record = create(client, prefix, details={})
    response = client.post(f"{prefix}/questionnaires/{record['app_id']}/answers",
                           json={"details": {"学历培训明细": [{"学校": "清华大学"}],
                                             "资历专业资格明细": [{"资格名称": "系统架构设计师"}]},
                                 "confirmed": True})
    assert response.status_code == 200, response.text
    still_missing = response.json()["data"]["missing_fields"]
    assert not [item for item in still_missing if "（至少" in item], still_missing
    assert response.json()["data"]["incomplete_fields"] == {}


def test_condition_validation_rolls_back(api):
    client, prefix = api
    original = create(client, prefix)
    path = f"{prefix}/questionnaires/{original['app_id']}"
    response = client.post(path + "/answers", json={"main": {"犯罪记录情况": "有犯罪记录"}})
    assert response.status_code == 422
    current = client.get(path).json()["data"]
    assert current == original_without_created(original)
    with SessionLocal() as session:
        count = session.scalar(select(func.count()).select_from(Submission)
                               .where(Submission.app_id == original["app_id"]))
        assert count == 0
    valid = client.post(path + "/answers", json={
        "main": {"犯罪记录情况": "有犯罪记录", "犯罪记录说明": "说明"}})
    assert valid.status_code == 200
    cleared = client.post(path + "/answers", json={"main": {"犯罪记录情况": "从未有犯罪记录"}})
    assert cleared.status_code == 200, cleared.text
    assert cleared.json()["data"]["main"]["犯罪记录说明"] == ""


def original_without_created(data):
    return {key: value for key, value in data.items() if key != "created"}


def test_idempotency_replay_and_cross_application_isolation(api, monkeypatch):
    client, prefix = api
    first = create(client, prefix)
    second = create(client, prefix)
    path = f"{prefix}/questionnaires/{first['app_id']}/answers"
    body = {"submission_id": "SUB-isolation", "main": {"婚姻状况": "未婚"}, "confirmed": True}
    submitted = client.post(path, json=body)
    assert submitted.status_code == 200
    monkeypatch.setattr(settings, "allow_resubmit", False)
    replay = client.post(path, json=body)
    assert replay.status_code == 200
    assert replay.json() == submitted.json()
    cross = client.post(f"{prefix}/questionnaires/{second['app_id']}/answers", json=body)
    assert cross.status_code == 409
    changed = client.post(path, json={**body, "main": {"婚姻状况": "已婚"}})
    assert changed.status_code == 409
    assert client.post(path, json={"main": {"婚姻状况": "已婚"}}).status_code == 409
    with SessionLocal() as session:
        assert session.scalar(select(func.count()).select_from(Submission)
                              .where(Submission.submission_id == body["submission_id"])) == 1


def test_expired_token_is_replaced_during_generation(api):
    client, prefix = api
    data = create(client, prefix)
    old = generate(client, prefix, data["app_id"])["fill_url"].rsplit("/", 1)[1]
    with SessionLocal() as session:
        entity = session.scalar(select(Questionnaire).where(Questionnaire.app_id == data["app_id"]))
        entity.token_expires_at = utcnow() - dt.timedelta(seconds=1)
        session.commit()
    assert client.get(f"{prefix}/public/questionnaires/{old}").status_code == 410
    assert client.post(f"{prefix}/public/questionnaires/{old}/answers", json={}).status_code == 410
    new = generate(client, prefix, data["app_id"])["fill_url"].rsplit("/", 1)[1]
    assert new != old
    assert client.get(f"{prefix}/public/questionnaires/{new}").status_code == 200
    assert client.get(f"{prefix}/public/questionnaires/{old}").status_code == 410


def test_void_record_cannot_generate_submit_or_open(api):
    client, prefix = api
    data = create(client, prefix)
    token = generate(client, prefix, data["app_id"])["fill_url"].rsplit("/", 1)[1]
    with SessionLocal() as session:
        entity = session.scalar(select(Questionnaire).where(Questionnaire.app_id == data["app_id"]))
        entity.status = "void"
        session.commit()
    assert client.post(f"{prefix}/questionnaires/{data['app_id']}/questionnaire").status_code == 409
    assert client.post(f"{prefix}/questionnaires/{data['app_id']}/answers", json={}).status_code == 409
    assert client.get(f"{prefix}/public/questionnaires/{token}").status_code == 410


def test_auth_and_public_boundary(api, monkeypatch):
    client, prefix = api
    data = create(client, prefix)
    token = generate(client, prefix, data["app_id"])["fill_url"].rsplit("/", 1)[1]
    monkeypatch.setattr(settings, "service_api_key", "test-private-key")
    assert client.get(f"{prefix}/questionnaires/{data['app_id']}").status_code == 401
    assert client.post(f"{prefix}/questionnaires", json={"main": {"姓名": "甲"}}).status_code == 401
    assert client.post(f"{prefix}/questionnaires/{data['app_id']}/questionnaire").status_code == 401
    assert client.post(f"{prefix}/questionnaires/{data['app_id']}/answers", json={}).status_code == 401
    assert client.get(f"{prefix}/questionnaires/{data['app_id']}",
                      headers={"Authorization": "Bearer test-private-key"}).status_code == 200
    assert client.get(f"{prefix}/public/questionnaires/{token}").status_code == 200
    assert client.post(f"{prefix}/public/questionnaires/{token}/answers",
                       json={"main": {"婚姻状况": "未婚"}}).status_code == 200


@pytest.mark.parametrize("path", ["/.env", "/static/.env", "/static/../.env",
                                "/static/%2e%2e/.env", "/static/config.py", "/app/core/config.py"])
def test_private_files_not_served(api, path):
    client, _ = api
    assert client.get(path).status_code == 404


def test_health_has_no_configuration(api, monkeypatch):
    client, _ = api
    monkeypatch.setattr(settings, "service_api_key", "secret-marker")
    monkeypatch.setattr(settings, "database_url", "secret-database-url")
    response = client.get("/health")
    assert response.json() == {"ok": True, "data": {"status": "up"}}
    assert "secret-marker" not in client.get("/ui").text
    assert "secret-marker" not in repr(settings)
    assert "service_api_key" not in settings.model_dump()
    assert "database_url" not in settings.model_dump()


def test_response_and_openapi_contract(api):
    client, prefix = api
    schema = client.get("/openapi.json").json()
    business = {path: set(value) for path, value in schema["paths"].items()
                if path.startswith(prefix + "/questionnaires")}
    assert business == {
        prefix + "/questionnaires": {"post"},
        prefix + "/questionnaires/{app_id}/questionnaire": {"post"},
        prefix + "/questionnaires/{app_id}/answers": {"post"},
        prefix + "/questionnaires/{app_id}": {"get"},
    }
    for path, methods in business.items():
        for method in methods:
            assert "$ref" in schema["paths"][path][method]["responses"]["200"]["content"]["application/json"]["schema"]
    for old in ("/fields", "/questionnaires/missing/qrcode", "/questionnaires/missing/token"):
        assert client.get(prefix + old).status_code in (404, 405)


def test_frontend_resources_and_private_headers(api, monkeypatch):
    client, _ = api
    for path in ("/ui", "/static/test-console.html", "/static/app.js", "/static/app.css"):
        response = client.get(path)
        assert response.status_code == 200
        assert response.headers["cache-control"] == "no-store"
        assert response.headers["referrer-policy"] == "no-referrer"
    html = client.get("/ui").text
    assert "{{client_config}}" not in html
    assert "apiPrefix" in html
    monkeypatch.setattr(settings, "ui_enabled", False)
    assert client.get("/ui").status_code == 404
    assert client.get("/static/test-console.html").status_code == 404
    assert client.get("/q/any-token").status_code == 200


def test_audit_does_not_store_field_values(api):
    client, prefix = api
    data = create(client, prefix)
    with SessionLocal() as session:
        entries = session.scalars(select(Event).where(Event.app_id == data["app_id"])).all()
        assert entries
        assert all("张伟" not in json.dumps(entry.detail, ensure_ascii=False) for entry in entries)


def test_unknown_record_and_error_envelope(api):
    client, prefix = api
    response = client.get(f"{prefix}/questionnaires/not-found")
    assert response.status_code == 404
    assert response.json()["ok"] is False
    assert response.json()["error"]["code"] == "NOT_FOUND"


def test_concurrent_update_does_not_overwrite_another_writer(api):
    from app.core.errors import Conflict
    from app.dto.requests import WriteFieldsRequest
    from app.repositories.questionnaires import QuestionnaireRepository
    from app.services.questionnaires import QuestionnaireService

    client, prefix = api
    record = create(client, prefix)
    with SessionLocal() as first, SessionLocal() as second:
        first_repository = QuestionnaireRepository(first)
        second_repository = QuestionnaireRepository(second)
        first_entity = first_repository.find(record["app_id"])
        second_entity = second_repository.find(record["app_id"])
        assert first_entity.version == second_entity.version
        QuestionnaireService(first_repository).write_initial_fields(WriteFieldsRequest(
            app_id=record["app_id"], main={"专业": "计算机"}))
        with pytest.raises(Conflict):
            QuestionnaireService(second_repository).write_initial_fields(WriteFieldsRequest(
                app_id=record["app_id"], main={"专业": "自动化"}))
    current = client.get(f"{prefix}/questionnaires/{record['app_id']}").json()["data"]
    assert current["main"]["专业"] == "计算机"


def test_health_failure_hides_database_exception(api, monkeypatch):
    from sqlalchemy.exc import OperationalError
    from app.routers.meta import engine

    def fail_connect():
        raise OperationalError("secret-connection-string", {}, Exception("secret-password"))

    monkeypatch.setattr(engine, "connect", fail_connect)
    client, _ = api
    response = client.get("/health")
    assert response.status_code == 503
    assert response.json() == {"ok": True, "data": {"status": "degraded"}}


def test_production_does_not_publish_openapi(api, monkeypatch):
    from fastapi.testclient import TestClient
    from app.main import create_app

    monkeypatch.setattr(settings, "env", "prod")
    monkeypatch.setattr(settings, "debug", False)
    with TestClient(create_app()) as client:
        for path in ("/docs", "/redoc", "/openapi.json"):
            assert client.get(path).status_code == 404
