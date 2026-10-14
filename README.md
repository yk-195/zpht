# 问卷服务

围绕四个流程提供 API：写入初始字段、生成问卷、接收补充字段、返回所有字段。
FastAPI + Pydantic DTO + SQLAlchemy；前端位于 `static/`。

## 代码结构

```text
app/
  routers/          HTTP 路由、依赖装配、固定页面与资源入口
  dto/              requests.py 入参、responses.py 出参、common.py 响应信封
  services/         四个业务用例、事务边界、提交幂等
  repositories/     ORM 模型、数据库会话、SQL 查询
  domain/           字段契约、校验、标准化、合并、问卷题目生成
  mappers/          ORM 实体到响应 DTO 的显式映射
  core/             私有配置、鉴权、异常、JSON 响应
  main.py           应用装配与启动
static/
  test-console.html 页面结构
  app.js            同源 API 调用、表单控件与交互
  app.css           页面样式
tests/              业务闭环、字段校验、隔离、事务、配置保护
```

采用 DTO 分层：路由 → 服务 → 仓储。路由不执行 SQL，服务不拼 HTTP 响应，
映射器只输出 DTO 中明确声明的字段，不直接返回 ORM 对象。
主表中文字段和动态明细保留为字典值，外层请求、响应和嵌套问卷契约均由 Pydantic 定义。

## 启动

```powershell
uv sync
# 仅首次创建本地配置；已有 .env 不要覆盖
Copy-Item .env.example .env
uv run python -m app
```

访问 [前端](http://127.0.0.1:8000/ui) 或
[静态页面入口](http://127.0.0.1:8000/static/test-console.html)。
页面由后端注入 API 前缀，请通过 HTTP 打开。已有服务需要重启后加载新代码。

`.env` 是本地私有文件，不是接口、前端或发布产物；不要提交或分享。
`.env.example` 仅包含无密钥模板。设置 `SERVICE_API_KEY` 后，在前端输入密钥，
或在内部接口请求中提供 `X-API-Key` / `Authorization: Bearer <key>`。
前端不持久化密钥。候选人通过填写链接中的令牌访问，不需要内部密钥。

## 四个接口

默认前缀 `/api/v1`；下列四个业务接口均受 API Key 配置控制。

| 步骤 | 方法及路径 | 请求 DTO | 响应 DTO |
| --- | --- | --- | --- |
| 写入初始字段 | POST /questionnaires | WriteFieldsRequest | WriteFieldsResponse |
| 生成问卷（只回链接） | POST /questionnaires/{app_id}/questionnaire | 无请求体 | QuestionnaireLinkResponse |
| 接收返回字段 | POST /questionnaires/{app_id}/answers | SubmitFieldsRequest | SubmitFieldsResponse |
| 返回所有字段 | GET /questionnaires/{app_id} | 无请求体 | FieldsResponse |

写入示例：

```json
{
  "main": {"姓名": "张伟", "手机号码": "13800000001"},
  "details": {"家庭成员明细": [{"姓名": "张一", "关系": "父亲"}]}
}
```

不传 `app_id` 时生成 UUID 申请编号；传已有编号时按非空值合并，保留已有字段。
未知顶层参数、未知业务字段和对象类型的字段值返回 422。
不再支持顶层平铺字段、整体覆盖、客户端指定 IP 等旧参数。

使用返回的 `app_id` 生成问卷。该接口**只返回填写链接与进度**——`fill_url`、
`expires_at`、`allow_resubmit`、`question_count`、`missing_count`、`incomplete_count`、
`progress`——**不返回 `questions` / `contract` / `recognized`**：调用方拿到链接转发给候选人即可，
题目与字段契约由候选人页面自己按令牌从公开接口取。
有效链接重复生成保持不变，过期后重新签发。
题目包括未填、不完整字段与可编辑的明细区；条件说明随声明选项生成。
四个明细区**都会出题**，但整块是否必填不同：**家庭成员与工作经验为非必填**
（应届生可以没有工作经历，家庭成员也可能不便提供），标记为「选填」；
学历 / 培训与资历及专业资格仍要求至少 1 条。
非必填明细区整块为空时**不计入 `missing_fields`**，也不会挡住状态走到 `completed`；
一旦填了行，行内的必填字段（如家庭成员「姓名 / 关系」、工作经验「公司名称」）仍会校验。
注意 `missing_fields` 是写入时算好并**存下来**的，改动这类规则后**已有记录会保留旧值**，
直到它下一次被写入或提交才会刷新。

提交示例：

```json
{
  "submission_id": "SUB-client-unique-id",
  "main": {"婚姻状况": "未婚"},
  "details": {},
  "confirmed": true
}
```

`submission_id` 可省略；传入后用于网络重试。相同申请、相同 ID、相同标准化内容
不重复写入；跨申请或更换内容复用 ID 返回 409。重试返回该提交的序号及问卷当前字段状态。
问卷、提交记录及审计摘要在同一事务保存；失败回滚。版本检查避免并发覆盖，
冲突返回 409 后应重新读取并重试。

所有业务 JSON 响应为 `{"ok": true, "data": ...}`；
失败为 `{"ok": false, "error": {"code": "...", "message": "...", "details": [...]}}`。
计数由 DTO 根据集合计算。全部字段接口返回当前主表、明细、状态、进度与时间，
不返回内部令牌、原始快照、IP、审计流水或数据库配置。

## 插件导入

将 `Questionnaire_Service-20260922-112320.json` 重新导入插件平台，并在平台鉴权配置中
设置 `X-API-Key`，不要将密钥写进 JSON。文件仅公开上述四个业务工具。
响应 Schema 完全内联，不依赖 `$ref` / `allOf` 展开；成功响应的 `data` 和失败响应的
`error` 均显式声明为 `object`。重新导入后确认平台「输出参数配置」中的 `data` 为
Object，而不是 String；旧工具若保留了手工出参配置，需要同步更新或重新创建工具。
不要将后端对象响应字符串化。未提供申请编号时省略 `app_id` 或传 `null`，不能传空字符串。
`servers[0].url` 必须指向平台可访问的服务地址；临时隧道重建后需同步更新这个地址
及本地私有配置中的 `PUBLIC_BASE_URL`。

插件使用 OpenAPI 3.0.3 兼容格式，后端 OpenAPI 仍为 3.1：空值使用 `nullable`，
常量使用单值 `enum`，所有数组明确声明 `items`。`questions`、`contract`、`recognized`
（以及其中的 `depends_on`、`options`）**只出现在候选人公开接口的返回里，不在插件中**——
生成问卷工具回的是精简的 `QuestionnaireLinkResponse`。若将来要把它们放回插件，注意
3.0 无法精确声明数组位置类型，`depends_on` 只能写成长度为 2 的联合类型数组，
位置约束由后端 DTO 保证。不要直接用后端 3.1 Schema 覆盖插件定义；
测试包含独立格式校验及请求、响应数据校验。

## 候选人页面

`/q/{token}` 使用相同页面，仅展示候选人问卷。它复用两个公开入口：

- GET /api/v1/public/questionnaires/{token}
- POST /api/v1/public/questionnaires/{token}/answers

**这两个公开接口是唯一返回完整问卷（`questions` + `contract` + `recognized`）的地方**；
内部生成接口只给链接。控制台页面在非候选人模式下也走这条路：先调生成接口拿 `fill_url`，
再从链接里取令牌调公开接口渲染题目。

无效、过期和作废链接统一返回 410。前端和 API 响应禁止缓存，并设置
`Referrer-Policy: no-referrer`。`uv run python -m app` 默认关闭访问日志，避免记录 URL 令牌；
若通过独立 uvicorn 或反向代理部署，应同样避免将候选人 URL 写入访问日志。

## 配置与验证

`UI_ENABLED` 只控制管理页面；候选人页面始终可加载，但数据需要有效令牌。
`PUBLIC_BASE_URL` 设置为候选人可访问的地址；留空使用当前请求的来源。
`ENV=prod` 且 `DEBUG=false` 时关闭交互文档及 OpenAPI。
`GET /health` 仅返回状态，数据库不可用时返回 503，不回显异常或连接信息。
静态资源仅允许已知 HTML、JS、CSS，不挂载项目根目录。

```powershell
uv run pytest
```

测试使用临时数据库，不操作 `data/service.db`。
数据库表结构与旧版兼容；保留旧表列供现有数据继续使用，无需清库。
初始化建表不负责数据库结构迁移。

## 本次精简

移除二维码、文档渲染、平台插件生成、问卷列表、独立字段契约接口和独立令牌轮换接口。
旧 `GET /questionnaires/{id}/missing-fields` 改为
`POST /questionnaires/{id}/questionnaire`；该接口**只返回填写链接与进度**，
字段契约与题目改由候选人公开接口返回（见上）。
前端已使用新接口。旧插件和外部调用方需按上表调整，已保存申请编号继续有效。
历史产物与本地私有配置未删除；不再使用的旧配置项会被忽略。
