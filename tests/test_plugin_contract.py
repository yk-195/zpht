"""插件契约与当前服务同步，并按插件定义完成四步流程。"""
import json
from pathlib import Path

import pytest
from openapi_schema_validator import OAS30Validator
from openapi_spec_validator import OpenAPIV30SpecValidator

from app.main import app


PLUGIN_PATH = Path(__file__).resolve().parents[1] / "Questionnaire_Service-20260922-112320.json"
PLUGIN = json.loads(PLUGIN_PATH.read_text(encoding="utf-8"))


def schema_nodes(value, path="#"):
    if isinstance(value, dict):
        yield path, value
        for key, item in value.items():
            yield from schema_nodes(item, f"{path}/{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            yield from schema_nodes(item, f"{path}/{index}")


def test_plugin_arrays_always_define_items():
    for path, schema in schema_nodes(PLUGIN):
        if schema.get("type") == "array":
            assert isinstance(schema.get("items"), dict) and schema["items"], path


def test_plugin_is_valid_openapi_30():
    assert PLUGIN["openapi"] == "3.0.3"
    OpenAPIV30SpecValidator(PLUGIN).validate()
    for path, schema in schema_nodes(PLUGIN):
        assert not {"prefixItems", "const"} & schema.keys(), path
        assert schema.get("type") != "null", path
        if schema.get("nullable"):
            assert "type" in schema, path


def resolve_references(value, document):
    if isinstance(value, list):
        return [resolve_references(item, document) for item in value]
    if not isinstance(value, dict):
        return value
    if "$ref" in value:
        target = document
        assert value["$ref"].startswith("#/")
        for part in value["$ref"][2:].split("/"):
            target = target[part.replace("~1", "/").replace("~0", "~")]
        return resolve_references(target, document)
    return {key: resolve_references(item, document) for key, item in value.items()}


def union_branches(branches):
    """规范化 anyOf 的嵌套与顺序，nullable 分支与显式 null 等价。"""
    flattened = []
    for branch in branches:
        flattened.extend(branch["anyOf"] if set(branch) == {"anyOf"} else [branch])
    unique = {json.dumps(branch, sort_keys=True): branch for branch in flattened}
    return [unique[key] for key in sorted(unique)]


def contract_shape(value, document):
    """比较 3.0/3.1 的等价约束；仅允许响应元组放宽为定长联合类型数组。"""
    if isinstance(value, list):
        return [contract_shape(item, document) for item in value]
    if not isinstance(value, dict):
        return value
    if "$ref" in value:
        return contract_shape(resolve_references(value, document), document)
    shape = {
        key: contract_shape(item, document)
        for key, item in value.items()
        if key not in {"title", "description", "example", "examples", "x-visible"}
    }
    if "allOf" in shape and len(shape["allOf"]) == 1:
        branch = shape.pop("allOf")[0]
        assert not branch.keys() & shape.keys()
        shape = {**branch, **shape}
    if "prefixItems" in shape:
        # OpenAPI 3.0 不支持按数组位置描述元组；限于这两种 depends_on 响应。
        assert shape["type"] == "array" and shape["minItems"] == shape["maxItems"] == 2
        assert shape["prefixItems"] == [
            {"type": "string"}, {"type": "array", "items": {"type": "string"}},
        ]
        shape["items"] = {"anyOf": union_branches(shape.pop("prefixItems"))}
    if "const" in shape:
        shape["enum"] = [shape.pop("const")]
    if shape.pop("nullable", False):
        shape = {"anyOf": [shape, {"type": "null"}]}
    if "anyOf" in shape:
        shape["anyOf"] = union_branches(shape["anyOf"])
    return shape


def tools_by_name():
    return {
        operation["operationId"]: (method.upper(), path, operation)
        for path, methods in PLUGIN["paths"].items()
        for method, operation in methods.items()
    }


def test_plugin_responses_are_inline_and_explicitly_typed():
    for _, _, operation in tools_by_name().values():
        for code, response in operation["responses"].items():
            schema = response["content"]["application/json"]["schema"]
            assert schema["type"] == "object"
            field = "data" if code == "200" else "error"
            assert schema["properties"][field]["type"] == "object"
            assert schema["properties"][field]["properties"]
            for path, node in schema_nodes(schema):
                assert not {"$ref", "allOf"} & node.keys(), path
                if "properties" in node:
                    assert node["type"] == "object", path


@pytest.mark.parametrize("value,valid", [
    (None, True), ("文本", True), (0, True), (12.5, True),
    (True, False), ({"嵌套": "对象"}, False), ([], False),
])
def test_plugin_field_values_preserve_null_and_type_restrictions(value, valid):
    for name in ("write_initial_fields", "submit_fields"):
        operation = tools_by_name()[name][2]
        schema = operation["requestBody"]["content"]["application/json"]["schema"]
        body = {"main": {"姓名": value}, "details": {"家庭成员明细": [{"姓名": value}]}}
        assert OAS30Validator(schema).is_valid(body) is valid


@pytest.mark.parametrize("schema_name", ["Question", "FieldDefinition"])
def test_plugin_dependency_arrays_preserve_response_values(schema_name):
    operation = tools_by_name()["generate_questionnaire"][2]
    response = operation["responses"]["200"]["content"]["application/json"]["schema"]
    properties = response["properties"]["data"]["properties"]
    model = properties["questions"]["items"] if schema_name == "Question" else (
        properties["contract"]["properties"]["main_fields"]["items"]
    )
    schema = model["properties"]["depends_on"]
    validator = OAS30Validator(schema)
    for value in (None, ["是否受过行政处分", ["是"]]):
        validator.validate(value)
    for value in ([], ["少一项"], ["字段", ["是"], "多一项"], ["字段", [1]], [1, ["是"]]):
        assert not validator.is_valid(value)


def test_plugin_matches_current_service_contract():
    live = app.openapi()
    tools = tools_by_name()
    assert set(tools) == {
        "write_initial_fields", "generate_questionnaire", "submit_fields", "get_all_fields",
    }
    assert PLUGIN["security"] == [{"apiKey": []}]
    scheme = PLUGIN["components"]["securitySchemes"]["apiKey"]
    assert (scheme["type"], scheme["in"], scheme["name"]) == ("apiKey", "header", "X-API-Key")
    assert "value" not in scheme
    assert PLUGIN["servers"][0]["url"].startswith("https://")
    assert "X-API-Key" not in PLUGIN["servers"][0]["x-plugin-headers"]
    for method, path, operation in tools.values():
        current = live["paths"][path][method.lower()]
        assert bool(operation.get("requestBody")) == bool(current.get("requestBody"))
        if "requestBody" in operation:
            body = operation["requestBody"]
            assert body["required"] is True
            schema = body["content"]["application/json"]["schema"]
            current_schema = current["requestBody"]["content"]["application/json"]["schema"]
            assert contract_shape(schema, PLUGIN) == contract_shape(current_schema, live)
            assert all(prop["x-visible"] for prop in schema["properties"].values())
        expected_parameters = [parameter for parameter in current.get("parameters", [])
                               if parameter["in"] == "path"]
        assert contract_shape(operation.get("parameters", []), PLUGIN) == contract_shape(expected_parameters, live)
        assert all(parameter["required"] for parameter in operation.get("parameters", []))
        for code, response in operation["responses"].items():
            assert response["description"]
            schema = response["content"]["application/json"]["schema"]
            current_schema = current["responses"][code]["content"]["application/json"]["schema"]
            assert contract_shape(schema, PLUGIN) == contract_shape(current_schema, live)


def test_plugin_four_tool_flow(api):
    client, _ = api
    tools = tools_by_name()

    def invoke(name, app_id=None, body=None):
        method, path, operation = tools[name]
        if app_id:
            path = path.replace("{app_id}", app_id)
        if body is not None:
            request_schema = operation["requestBody"]["content"]["application/json"]["schema"]
            OAS30Validator(resolve_references(request_schema, PLUGIN)).validate(body)
        response = client.request(method, path, json=body) if body is not None else client.request(method, path)
        assert response.status_code == 200, response.text
        envelope = response.json()
        schema = operation["responses"]["200"]["content"]["application/json"]["schema"]
        validator = OAS30Validator(schema)
        validator.validate(envelope)
        # data 必须是对象，不能为迎合平台旧出参定义而将后端响应字符串化。
        assert not validator.is_valid({**envelope, "data": json.dumps(envelope["data"])})
        return envelope["data"]

    write_example = tools["write_initial_fields"][2]["requestBody"]["content"]["application/json"]["example"]
    written = invoke("write_initial_fields", body=write_example)
    app_id = written["app_id"]
    questionnaire = invoke("generate_questionnaire", app_id)
    assert questionnaire["fill_url"].startswith("http://testserver/q/")
    assert questionnaire["questions"] and questionnaire["contract"]
    submission_example = tools["submit_fields"][2]["requestBody"]["content"]["application/json"]["example"]
    submitted = invoke("submit_fields", app_id, submission_example)
    assert submitted["main"]["应聘职位"] == "软件开发"
    final = invoke("get_all_fields", app_id)
    assert final["main"]["姓名"] == write_example["main"]["姓名"]
    assert final["main"]["应聘职位"] == "软件开发"


@pytest.mark.parametrize("payload", [
    {"name": "测试候选人", "手机号码": "13800000001"},
    {"main": '{"姓名":"测试候选人"}'},
    {},
    {"app_id": "", "main": {"姓名": "测试候选人"}},
], ids=["flat-fields", "stringified-main", "empty-fields", "empty-id"])
def test_plugin_invalid_inputs_return_error_not_success_data(api, payload):
    client, _ = api
    app_id = "APP-INVALID-PLUGIN-REQUEST"
    method, path, operation = tools_by_name()["write_initial_fields"]
    response = client.request(method, path, json={"app_id": app_id, **payload})
    assert response.status_code == 422
    body = response.json()
    assert body["ok"] is False and "data" not in body
    assert body["error"]["code"] == "VALIDATION_FAILED"
    assert body["error"]["details"]
    schema = operation["responses"]["422"]["content"]["application/json"]["schema"]
    OAS30Validator(schema).validate(body)
    method, path, _ = tools_by_name()["get_all_fields"]
    assert client.request(method, path.replace("{app_id}", app_id)).status_code == 404
