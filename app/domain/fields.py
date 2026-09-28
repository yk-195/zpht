"""字段契约、校验、标准化与合并规则；不访问数据库。"""

from __future__ import annotations

import datetime as _dt
import re
from typing import Any

from ..core.config import settings as _settings

CONTRACT_VERSION = "1.0"


def family_relation_options() -> list[str]:
    return _settings.family_relation_list


def health_options() -> list[str]:
    return _settings.health_option_list


# ---------------------------------------------------------------- 字段契约

# kind: text / textarea / date / enum / int / phone / idcard / money / zip
# required 依据 `03` §2.1「必填」列；选填共 6 项（民族、政治面貌、现居住邮编、户籍邮编、子女数目×2）。
_MAIN_BASE = [
    ("姓名", "姓名", "text", True),
    ("应聘职位", "应聘职位", "text", False, None, "不确定可留空，由 HR 确认"),
    ("性别", "性别", "enum", True, ["男", "女"]),
    ("出生日期", "出生日期", "date", True, None, "只需年月也可以，但会被视为不完整"),
    ("民族", "民族", "text", False),
    ("毕业院校", "毕业院校", "text", True),
    ("毕业时间", "毕业时间", "date", True),
    ("最高学历", "最高学历", "enum", True, ["博士", "硕士", "本科", "大专", "中专", "高中及以下"]),
    ("专业", "专业", "text", True),
    ("政治面貌", "政治面貌", "enum", False,
     ["中共党员", "中共预备党员", "共青团员", "民主党派", "群众"]),
    ("身份证号", "身份证号", "idcard", True, None, "18 位；用于核对身份，请如实填写"),
    ("手机号码", "手机号码", "phone", True),
    ("现居住详细地址", "现居住详细地址", "textarea", True, None, "需到门牌号；只到城市会被视为不完整"),
    ("现居住邮政编码", "现居住邮政编码", "zip", False),
    ("户籍详细地址", "户籍详细地址", "textarea", True),
    ("户籍邮政编码", "户籍邮政编码", "zip", False),
    ("可到职日期", "可到职日期", "date", True, "不早于今天"),
    ("希望待遇_税前", "希望待遇（税前，元/月）", "money", True, None,
     "含基本工资及津贴；请填具体数字，不要填区间或年薪"),
    ("健康状况", "健康状况", "enum", True, health_options(), "下拉选择；选项见 .env 的 HEALTH_OPTIONS"),
    ("离职前12个月平均薪资_税前", "离职前 12 个月平均薪资（税前，元/月）", "money", True, None,
     "敏感信息，仅招聘流程相关人员可见"),
    ("婚姻状况", "婚姻状况", "enum", True, ["未婚", "已婚", "离异", "丧偶"]),
    ("子女数目_子", "子女数目（子）", "int", False),
    ("子女数目_女", "子女数目（女）", "int", False),
]

_EMERGENCY = [
    ("紧急联系人姓名", "紧急联系人姓名", "text", True),
    ("紧急联系人关系", "紧急联系人关系", "text", True),
    ("紧急联系人电话", "紧急联系人电话", "phone", True),
]

# 声明：4 组，每组「选项 + 说明」。说明仅在选「是/有」时需要。
_DECLARATIONS = [
    ("犯罪记录情况", "本人曾经", "enum", ["从未有犯罪记录", "有犯罪记录"],
     "犯罪记录说明", "请说明（仅存档，不作为筛选依据）"),
    ("是否受过行政处分", "是否受过行政处分", "enum", ["否", "是"],
     "行政处分说明", "请说明"),
    ("亲属朋友是否在本公司任职", "亲属朋友是否在本公司任职", "enum", ["否", "是"],
     "任职亲属说明", "请说明姓名与关系"),
    ("是否有妨碍工作的身体障碍", "是否有妨碍工作的身体障碍", "enum", ["否", "是"],
     "身体障碍说明", "请说明"),
]


# 明细区：行数与原表一致（学历 2 / 资历 2 / 工作 4 组）；
# 家庭成员实际上限由 `.env` 的 FAMILY_MAX_ROWS 决定（默认 5，纸表 ZMF-HR-WI-BG-004 只有 4 行）
# 明细字段元组： (字段名, 类型, 是否必填[, 枚举选项])
DETAILS: list[dict[str, Any]] = [
    {"key": "家庭成员明细", "label": "家庭成员", "prefix": "家庭", "max": 5,
     "fields": [("姓名", "text", True), ("关系", "enum", True, family_relation_options()),
                ("年龄", "int", False), ("联系电话", "phone", False), ("职业工作单位", "text", False)]},
    {"key": "学历培训明细", "label": "学历 / 培训", "prefix": "学历", "max": 2,
     "fields": [("起始日期", "date", False), ("结束日期", "date", False), ("学校", "text", True),
                ("专业", "text", False), ("证书学位级别", "text", False)]},
    {"key": "资历专业资格明细", "label": "资历及专业资格", "prefix": "资格", "max": 2,
     "fields": [("资格名称", "text", True), ("颁发机构", "text", False), ("颁发日期", "date", False)]},
    {"key": "工作经验明细", "label": "工作经验", "prefix": "工作", "max": 4,
     "fields": [("公司名称", "text", True), ("业务性质", "text", False), ("入职日期", "date", False),
                ("入职职位", "text", False), ("开始薪资", "money", False), ("离职日期", "date", False),
                ("离职职位", "text", False), ("最后薪资", "money", False), ("职务简介", "textarea", False),
                ("离职原因", "text", False), ("单位电话", "phone", False)]},
]

DETAIL_KEYS = [d["key"] for d in DETAILS]


def detail_max(detail: dict) -> int:
    if detail["key"] == "家庭成员明细":
        return _settings.family_max_rows
    return int(detail["max"])


def _field_dict(t: tuple) -> dict:
    """明细字段元组 → 字典（可选第 4 位是枚举选项）。"""
    options = list(t[3]) if len(t) > 3 and t[3] else None
    return {"name": t[0], "kind": t[1], "required": bool(t[2]), "options": options}



# 主表字段全集（用于算"仍缺"）：26 纸表 + 8 声明
# 元组尾部的可选位既可能是 options（list），也可能是 hint（str），按类型认领，
# 避免「只写了 hint、没写 options」的那几项把提示语当成枚举选项。
MAIN_FIELDS: list[dict] = []
for _n, _l, _k, _r, *_rest in _MAIN_BASE + _EMERGENCY:
    _o = next((x for x in _rest if isinstance(x, (list, tuple))), None)
    _h = next((x for x in _rest if isinstance(x, str) and x), "")
    MAIN_FIELDS.append({"name": _n, "label": _l, "kind": _k, "required": _r,
                        "options": list(_o) if _o else None, "hint": _h,
                        "group": "紧急联系人" if _n.startswith("紧急") else "基本信息"})
for _opt, _lab, _k, _opts, _note, _hint in _DECLARATIONS:
    MAIN_FIELDS.append({"name": _opt, "label": _lab, "kind": _k, "required": True,
                        "options": _opts, "hint": "", "group": "声明"})
    MAIN_FIELDS.append({"name": _note, "label": _note, "kind": "textarea", "required": False,
                        "options": None, "hint": _hint, "group": "声明",
                        "depends_on": (_opt, [o for o in _opts if o in ("是", "有犯罪记录")])})

FIELD_BY_NAME = {f["name"]: f for f in MAIN_FIELDS}
MAIN_FIELD_NAMES = [f["name"] for f in MAIN_FIELDS]

# 简历里通常没有、必然要候选人提供的字段（`03` §4.5 / §8）
NEVER_FROM_RESUME = [
    "民族", "身份证号", "现居住邮政编码", "户籍详细地址", "户籍邮政编码", "希望待遇_税前",
    "健康状况", "离职前12个月平均薪资_税前", "紧急联系人姓名", "紧急联系人关系", "紧急联系人电话",
    "婚姻状况", "子女数目_子", "子女数目_女",
    "犯罪记录情况", "犯罪记录说明", "是否受过行政处分", "行政处分说明",
    "亲属朋友是否在本公司任职", "任职亲属说明", "是否有妨碍工作的身体障碍", "身体障碍说明",
]

# 明细内的字段契约（供 /fields 与前端渲染）；枚举字段带 options，页面据此渲染成选择框
DETAIL_FIELDS: dict[str, list[dict]] = {
    d["key"]: [_field_dict(t) for t in d["fields"]] for d in DETAILS
}


def field_contract() -> dict[str, Any]:
    """整份字段契约（给前端/问卷生成器读）。"""
    return {
        "contract_version": CONTRACT_VERSION,
        "main_fields": MAIN_FIELDS,
        "details": [
            {"key": d["key"], "label": d["label"], "max": detail_max(d), "fields": DETAIL_FIELDS[d["key"]]}
            for d in DETAILS
        ],
        "required_main_fields": [f["name"] for f in MAIN_FIELDS if f["required"]],
        "optional_main_fields": [f["name"] for f in MAIN_FIELDS if not f["required"]],
        "never_from_resume": NEVER_FROM_RESUME,
        "counts": {
            "main_total": len(MAIN_FIELDS),
            "main_required": sum(1 for f in MAIN_FIELDS if f["required"]),
            "detail_sections": len(DETAILS),
            "detail_rows_total": sum(detail_max(d) for d in DETAILS),
        },
    }


# ---------------------------------------------------------------- 校验

_PHONE = re.compile(r"^1[3-9]\d{9}$")
_TEL = re.compile(r"^0\d{2,3}-?\d{7,8}$")
_ZIP = re.compile(r"^\d{6}$")
_ID = re.compile(r"^\d{17}[\dXx]$")
_ID_W = [7, 9, 10, 5, 8, 4, 2, 1, 6, 3, 7, 9, 10, 5, 8, 4, 2]
_ID_C = "10X98765432"


def check_idcard(v: str) -> tuple[bool, str]:
    """18 位 + ISO 7064 MOD 11-2 校验位 + 出生段合法性。"""
    v = (v or "").strip().upper()
    if not _ID.match(v):
        return False, "身份证号应为 18 位（末位可为 X）"
    s = sum(int(v[i]) * _ID_W[i] for i in range(17))
    if _ID_C[s % 11] != v[17]:
        return False, "身份证号校验位不正确，请核对"
    y, m, d = int(v[6:10]), int(v[10:12]), int(v[12:14])
    try:
        birth = _dt.date(y, m, d)
    except ValueError:
        return False, "身份证号中的出生日期不合法"
    if birth > _dt.date.today():
        return False, "身份证号中的出生日期晚于今天，请核对"
    if y < 1900:
        return False, "身份证号中的出生年份不合理"
    return True, ""


def derive_from_idcard(v: str) -> dict:
    """派生字段：出生日期、性别由身份证号确定性推出。"""
    v = (v or "").strip().upper()
    if not _ID.match(v):
        return {}
    try:
        birth = _dt.date(int(v[6:10]), int(v[10:12]), int(v[12:14]))
    except ValueError:
        return {}
    return {"出生日期": birth.isoformat(), "性别": "男" if int(v[16]) % 2 else "女"}


def _to_date(v):
    v = str(v).strip()
    if not v:
        return None
    v = v.replace("年", "-").replace("月", "-").replace("日", "").replace("/", "-").replace(".", "-")
    if re.fullmatch(r"\d{8}", v):
        v = f"{v[:4]}-{v[4:6]}-{v[6:]}"
    m = re.match(r"^(\d{4})-(\d{1,2})(?:-(\d{1,2}))?$", v)
    if not m:
        return None
    y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3) or 1)
    try:
        return _dt.date(y, mo, d)
    except ValueError:
        return None


def validate(name: str, value) -> tuple[bool, str, str]:
    """返回 (是否通过, 规范化值, 错误提示)。空值一律通过（必填性由 missing 统一判）。

    主表字段按契约严格校验；明细区字段同样校验，但**允许只填年份**
    （简历里的任职/入学时间经常只有年份，不能因此拒收）。
    """
    f = FIELD_BY_NAME.get(name)
    is_detail = False
    if f is None:
        f = _detail_field(name)
        is_detail = f is not None
    kind = f["kind"] if f else "text"
    v = "" if value is None else str(value).strip()
    if v == "":
        return True, "", ""
    if kind == "enum":
        opts = f.get("options") or []
        if is_detail:
            # 明细区的选项（如家庭成员「关系」）是**给页面渲染下拉用的候选值**，
            # 不硬拦导入/历史数据里的其他写法——纸表该列本来就是自由填写，
            # 拦下来只会让整条记录写不进去（页面会把非清单值也列进下拉，不丢数据）。
            if "其他" in opts and v == "其他":
                # 但「其他」本身必须补充具体内容，否则等于没填
                return False, "", "选择「其他」时请补充具体内容，例如：其他（岳父）"
            return True, v, ""
        if not opts:
            return True, v, ""
        return (True, v, "") if v in opts else (False, "", f"请选择：{' / '.join(opts)}")
    if kind == "date":
        d = _to_date(v)
        if not d:
            if is_detail and re.fullmatch(r"\d{4}", v):
                return True, v, ""        # 明细区允许只填年份，原样保留
            return False, "", "日期格式不正确（可填 2024-06 或 2024-06-01）"
        return True, d.isoformat(), ""
    if kind == "int":
        return (True, str(int(v)), "") if re.fullmatch(r"\d+", v) else (False, "", "请填整数")
    if kind == "money":
        if re.fullmatch(r"\d+(\.\d+)?", v):
            return True, str(int(float(v))), ""
        # 区间/年薪/税后等禁止换算，原样保留交 HR 判断（`03` §4.3）
        return True, v, ""
    if kind == "phone":
        if _PHONE.match(v):
            return True, v, ""
        if _TEL.match(v):
            return True, v, ""
        return False, "", "手机号应为 11 位（1 开头）或 座机格式如 010-88886666"
    if kind == "zip":
        return (True, v, "") if _ZIP.match(v) else (False, "", "邮政编码应为 6 位数字")
    if kind == "idcard":
        ok, msg = check_idcard(v)
        return (True, v.upper(), "") if ok else (False, "", msg)
    return True, v, ""


def _detail_field(name: str) -> dict | None:
    for fields in DETAIL_FIELDS.values():
        for f in fields:
            if f["name"] == name:
                return f
    return None


def validate_all(main: dict, details: dict) -> list[str]:
    """校验主表 + 明细，返回错误列表（空即通过）。非契约字段一律忽略（防注入脏字段）。"""
    errors: list[str] = []
    for k, v in (main or {}).items():
        if k in FIELD_BY_NAME:
            ok, _, msg = validate(k, v)
            if not ok:
                errors.append(f"{FIELD_BY_NAME[k]['label']}：{msg}")
    for d in DETAILS:
        rows = (details or {}).get(d["key"]) or []
        if not isinstance(rows, list):
            errors.append(f"{d['label']}：应为数组")
            continue
        if len(rows) > detail_max(d):
            errors.append(f"{d['label']}：最多 {detail_max(d)} 行")
        for i, row in enumerate(rows, 1):
            row = row or {}
            for f in DETAIL_FIELDS[d["key"]]:
                fname, req = f["name"], f["required"]
                v = row.get(fname, "")
                if req and not str(v).strip() and any(str(x).strip() for x in row.values()):
                    errors.append(f"{d['label']}第 {i} 行「{fname}」为必填")
                if str(v).strip():
                    ok, _, msg = validate(fname, v)
                    if not ok:
                        errors.append(f"{d['label']}第 {i} 行「{fname}」：{msg}")
    return errors


def normalize_values(main: dict, details: dict) -> tuple[dict, dict]:
    """规范化：枚举/日期/金额/整数，并按身份证派生 出生日期、性别；白名单过滤字段名。"""
    out: dict[str, Any] = {}
    for k, v in (main or {}).items():
        if k in FIELD_BY_NAME:
            _ok, nv, _msg = validate(k, v)
            out[k] = nv
    if out.get("身份证号"):
        for k, dv in derive_from_idcard(out["身份证号"]).items():
            if not str(out.get(k) or "").strip():
                out[k] = dv
    det: dict[str, list] = {}
    for d in DETAILS:
        rows = []
        for row in ((details or {}).get(d["key"]) or []):
            row = row or {}
            if not any(str(x).strip() for x in row.values()):
                continue
            nr = {}
            for f in DETAIL_FIELDS[d["key"]]:
                _ok, nv, _msg = validate(f["name"], row.get(f["name"], ""))
                nr[f["name"]] = nv
            rows.append(nr)
        for i, r in enumerate(rows, 1):
            r["序号"] = i
        det[d["key"]] = rows[: detail_max(d)]
    return out, det


# ---------------------------------------------------------------- 合并 / 缺字段


def incomplete_of(raw: dict) -> dict:
    """判定「不完整」字段（`03` §4.4）：值非空但未达门槛 → 仍写入，但要进问卷并回显已有值。

    必须在**规范化之前**调用（规范化会把 1995-03 补成 1995-03-01，信息就丢了）。
    """
    out: dict[str, str] = {}
    for k, v in (raw or {}).items():
        s = str(v if v is not None else "").strip()
        if not s or k not in FIELD_BY_NAME:
            continue
        kind = FIELD_BY_NAME[k]["kind"]
        if kind == "date":
            only_ym = bool(re.fullmatch(r"\d{4}[-/.年]\d{1,2}月?", s))
            if only_ym:
                out[k] = "简历中只有年月，请补全到具体日期"
        elif "地址" in k:
            if len(s) < 12 and not re.search(r"[区县市旗].{0,12}[路街道镇乡号幢栋室]", s):
                out[k] = "简历中只到城市/区，请补全到门牌号"
    return out


def field_applicable(f: dict, main: dict) -> bool:
    """条件字段是否"该问"：声明的说明字段只有在选了「是/有…」时才需要。

    `f["depends_on"]` 形如 `("犯罪记录情况", ["有犯罪记录"])`；没有依赖的字段恒为适用。
    """
    dep = f.get("depends_on")
    if not dep:
        return True
    option_field, triggers = dep[0], list(dep[1] or [])
    return str((main or {}).get(option_field) or "").strip() in triggers


def normalize_declarations(main: dict) -> dict:
    """选项回落到「否 / 从未有…」时，把对应的说明字段清空——**无则不需要额外说明**。

    只清已有值，不往 `main` 里塞空键（否则每次写入都会多出 4 个空字段）。
    """
    out = dict(main or {})
    for f in MAIN_FIELDS:
        if f.get("depends_on") and not field_applicable(f, out) and str(out.get(f["name"]) or "").strip():
            out[f["name"]] = ""
    return out


def conditional_errors(main: dict) -> list[str]:
    """条件字段的必填校验：选了「是 / 有…」就必须写说明（仅提交环节用，导入不拦）。"""
    errors: list[str] = []
    for f in MAIN_FIELDS:
        if not f.get("depends_on"):
            continue
        option_field = f["depends_on"][0]
        if field_applicable(f, main) and not str((main or {}).get(f["name"]) or "").strip():
            errors.append(f"{f['label']}：选了「{main.get(option_field)}」需要填写说明")
    return errors


def compute_missing(main: dict, details: dict) -> list[str]:
    """未填字段 = 纳管全集 − 有值字段；条件字段（选「否」时的说明）不计入。"""
    miss = [f["name"] for f in MAIN_FIELDS
            if field_applicable(f, main) and not str((main or {}).get(f["name"]) or "").strip()]
    for d in DETAILS:
        rows = [r for r in ((details or {}).get(d["key"]) or []) if any(str(v).strip() for v in r.values())]
        need = 0 if d["key"] == "家庭成员明细" else 1   # 家庭成员允许整块为空
        if len(rows) < need:
            miss.append(f"{d['label']}（至少 {need} 条）")
    return miss


def completion_stats(main: dict, details: dict) -> dict:
    """填写进度（给 HR / 前端做进度条）。

    分母只算"该问的字段"：选「否」时不需要的声明说明不计入，
    否则永远到不了 100%（例如从无犯罪记录的人永远填不了「犯罪记录说明」）。
    """
    applicable = [f for f in MAIN_FIELDS if field_applicable(f, main)]
    filled = sum(1 for f in applicable if str((main or {}).get(f["name"]) or "").strip())
    required = [f for f in applicable if f["required"]]
    required_filled = sum(1 for f in required if str((main or {}).get(f["name"]) or "").strip())
    total = len(applicable)
    return {
        "total_fields": total,
        "filled_fields": filled,
        "missing_fields": total - filled,
        "required_total": len(required),
        "required_filled": required_filled,
        "completion_rate": round(filled / total * 100, 2) if total else 0.0,
    }


def merge(旧主表: dict, 旧明细: dict, 新主表: dict, 新明细: dict) -> dict:
    """合并规则：候选人填的非空值优先；空值保留旧值；改动进 changed。"""
    合并主表 = dict(旧主表 or {})
    changed = []
    for k, v in (新主表 or {}).items():
        nv = "" if v is None else str(v).strip()
        if not nv:
            continue
        old = str(合并主表.get(k) or "").strip()
        if old and old != nv:
            changed.append({"字段": k, "原值": old, "新值": nv})
        合并主表[k] = nv
    合并明细 = {}
    for d in DETAILS:
        rows = [r for r in ((新明细 or {}).get(d["key"]) or []) if any(str(x).strip() for x in r.values())]
        for i, r in enumerate(rows, 1):
            r["序号"] = i
        合并明细[d["key"]] = rows or ((旧明细 or {}).get(d["key"]) or [])
    return {"main": 合并主表, "details": 合并明细, "changed": changed}


def empty_details() -> dict[str, list]:
    return {d["key"]: [] for d in DETAILS}
