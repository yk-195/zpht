"use strict";

const config = JSON.parse(document.getElementById("client-config").textContent);
const PREFIX = config.apiPrefix;
const QPATH = config.questionnairePath;
const $ = id => document.getElementById(id);
const el = (tag, cls, text) => {
  const node = document.createElement(tag);
  if (cls) node.className = cls;
  if (text != null) node.textContent = text;
  return node;
};
const tokenPath = location.pathname.startsWith(QPATH + "/") ? location.pathname.slice(QPATH.length + 1) : "";
const FILL_TOKEN = tokenPath ? decodeURIComponent(tokenPath) : "";
const CANDIDATE = Boolean(FILL_TOKEN);
// 密钥与候选人数据只保留在当前页面内存，不写入 localStorage。
const S = { appId: "", contract: null, detailDefs: {}, submission: null };
const SAMPLE = { main: { "姓名": "张伟", "手机号码": "13800000001" }, details: {} };

function toast(message) {
  $("toast").textContent = message;
  $("toast").classList.add("show");
  setTimeout(() => $("toast").classList.remove("show"), 3000);
}

async function request(method, path, body) {
  const headers = { Accept: "application/json" };
  if (!CANDIDATE && $("apiKey").value.trim()) headers["X-API-Key"] = $("apiKey").value.trim();
  if (body !== undefined) headers["Content-Type"] = "application/json";
  const response = await fetch(PREFIX + path, {
    method, headers, body: body === undefined ? undefined : JSON.stringify(body),
    cache: "no-store", referrerPolicy: "no-referrer",
  });
  const envelope = await response.json();
  if (!response.ok || !envelope.ok) {
    const error = envelope.error || {};
    throw new Error([error.message || "请求失败", ...(error.details || []).map(item => item.message)].join("；"));
  }
  return envelope.data;
}

function bindAction(id, action, target) {
  $(id).onclick = async () => {
    $(id).disabled = true;
    try { await action(); }
    catch (error) {
      if (target) $(target).replaceChildren(el("div", "card", error.message));
      toast(error.message);
    } finally { $(id).disabled = false; }
  };
}

function applicationId() {
  const id = (CANDIDATE ? S.appId : $("appId").value).trim();
  if (!id) throw new Error("请先写入初始字段或填写申请编号");
  return encodeURIComponent(id);
}

function showTab(tab) {
  for (const button of $("tabs").children) button.classList.toggle("active", button.dataset.tab === tab);
  for (const name of ["write", "missing", "info"]) $("tab-" + name).classList.toggle("active", name === tab);
}
$("tabs").onclick = event => {
  const button = event.target.closest("button[data-tab]");
  if (button) showTab(button.dataset.tab);
};

const _now = new Date();
const TODAY = _now.getFullYear() + "-" + String(_now.getMonth()+1).padStart(2,"0") + "-" + String(_now.getDate()).padStart(2,"0");

/* 把库里的值转成 <input type="date"> 认得的 YYYY-MM-DD；转不了就返回空串 */
function toDateValue(v){
  const s = String(v==null ? "" : v).trim();
  if (/^\d{4}-\d{2}-\d{2}$/.test(s)) return s;
  if (/^\d{8}$/.test(s)) return s.slice(0,4) + "-" + s.slice(4,6) + "-" + s.slice(6);
  const m = s.match(/^(\d{4})[-/.年](\d{1,2})月?$/);            // 只有年月 → 当月 1 日
  if (m) return m[1] + "-" + m[2].padStart(2,"0") + "-01";
  return "";
}

/* 造一个日期选择器：type=date，带业务约束（出生日期不选未来 / 可到职日期不早于今天） */
function dateInput(raw, name){
  const ctl = el("input");
  ctl.type = "date";                       // ← 原生日历选择器
  ctl.style.maxWidth = "200px";
  const val = toDateValue(raw);
  if (val) ctl.value = val;
  if (name === "出生日期") ctl.max = TODAY;
  if (name === "可到职日期") ctl.min = TODAY;
  if (raw && !val) ctl.title = "原值：" + raw + "（无法直接放进日期选择器，请重新选择）";
  return ctl;
}


function selectFor(options, current, placeholder){
  const ctl = el("select");
  ctl.append(new Option(placeholder || "请选择…", ""));
  const opts = (options || []).slice();
  if (current && opts.indexOf(current) === -1) opts.push(current);   // 库里/导入的取值也要能选中，别丢
  opts.forEach(o=>{ const op = new Option(o, o); if (o === current) op.selected = true; ctl.append(op); });
  return ctl;
}

/* ---- 日期控件：一律用原生日期选择器（点日历直接选，不用手打） ---- */
function inputFor(q){
  const wrap = el("div","ctl");
  const v = q.current_value || "";
  let ctl;
  if (q.kind === "enum"){
    ctl = selectFor(q.options, v);
  } else if (q.kind === "textarea"){
    ctl = el("textarea"); ctl.style.minHeight="60px"; ctl.value = v;
  } else if (q.kind === "date"){
    ctl = dateInput(v, q.name);
  } else {
    ctl = el("input"); ctl.type = "text"; ctl.value = v;
    ctl.placeholder = {phone:"11 位手机号或 010-88886666", idcard:"18 位身份证号",
                       money:"数字，不要填区间/年薪", zip:"6 位邮编", int:"整数"}[q.kind] || "";
  }
  ctl.dataset.field = q.name;
  ctl.setAttribute("aria-label", q.label);
  if (q.section === "main") ctl.dataset.main = "1";
  wrap.append(ctl);
  return wrap;
}

/* 明细区：已导入的行原样回显；没有数据时**只显示一条**，用「+ 再加一行」逐条添加（有上限） */
function detailBlock(key, imported, maxRows){
  const def = S.detailDefs[key];
  const rows = el("div");
  const cap = Number(maxRows) || (def ? def.max : 1);
  const addRow = (idx, preset) => {
    const r = el("div","card");
    r.append(el("div","small muted", (def ? def.label : key) + " 第 " + (idx+1) + " 行"));
    (def ? def.fields : []).forEach(f=>{
      const line = el("div","row"); line.style.marginTop="6px";
      line.append(el("span","small muted", f.name + (f.required?" *":"")));
      const v = preset ? String(preset[f.name]==null ? "" : preset[f.name]) : "";
      let ctl;
      if (f.kind === "enum"){
        // 例如家庭成员「关系」：下拉选择而不是输入；选「其他」时要补充具体内容
        const m = /^其他[（(](.+)[）)]$/.exec(v);          // 让已有的「其他（岳父）」能回显成 其他 + 补充
        ctl = selectFor(f.options, m ? "其他" : v);
        ctl.setAttribute("aria-label", key + " 第 " + (idx + 1) + " 行 " + f.name);
        ctl.style.maxWidth = "200px";
        line.append(ctl);
        if ((f.options||[]).indexOf("其他") !== -1){
          const extra = el("input");
          extra.type = "text"; extra.style.maxWidth = "220px";
          extra.placeholder = "请补充具体" + f.name;        // 请补充具体关系
          extra.value = m ? m[1] : "";
          extra.dataset.detail = key; extra.dataset.row = String(idx);
          extra.dataset.supplementFor = f.name;
          line.append(extra);
          const sync = () => { extra.style.display = (ctl.value === "其他") ? "inline-block" : "none"; };
          ctl.addEventListener("change", sync);
          sync();
        }
        ctl.dataset.detail = key; ctl.dataset.row = String(idx); ctl.dataset.field = f.name;
        r.append(line);
        return;
      }
      if (f.kind === "date"){
        ctl = dateInput(v, f.name);              // 明细区的日期同样用选择器
      } else {
        ctl = el("input"); ctl.type = "text"; ctl.style.maxWidth = "320px"; ctl.value = v;
      }
      ctl.dataset.detail = key; ctl.dataset.row = String(idx); ctl.dataset.field = f.name;
      ctl.setAttribute("aria-label", key + " 第 " + (idx + 1) + " 行 " + f.name);
      line.append(ctl);
      r.append(line);
    });
    rows.append(r);
    updateBar();
  };
  const bar = el("div","row"); bar.style.marginTop="8px";
  const count = el("span","small muted");
  const more = el("button","ghost","+ 再加一行");
  more.onclick = () => {
    const n = rows.children.length;
    if (n >= cap) return toast((def ? def.label : key) + "最多 " + cap + " 条");
    addRow(n);
  };
  function updateBar(){
    const n = rows.children.length;
    count.textContent = `已填 ${n} / 最多 ${cap} 条`;
    more.disabled = n >= cap;
    more.textContent = n >= cap ? `已达上限（${cap} 条）` : "+ 再加一行";
  }
  bar.append(more, count);

  const list = (imported || []).filter(r => r && Object.keys(r).length);
  if (list.length){
    list.slice(0, cap).forEach((preset, i) => addRow(i, preset));   // 导入的行全部回显
  } else {
    addRow(0);                                                      // 空的时候开始只显示一条
  }
  return [rows, bar];
}

function renderQuestions(questions){
  const box = $("qform"); box.innerHTML = "";
  if (!questions.length){
    box.append(el("div","card","🎉 没有未填字段了：这条记录已完整。"));
    $("submitBox").style.display = "none";
    return;
  }
  const mainQs = questions.filter(q => q.section !== "detail");
  const needDetail = questions.some(q => q.kind === "detail" && q.reason === "empty");
  if (!mainQs.length){
    box.append(el("div","card", needDetail
      ? "✅ 主表字段已填齐；明细区还有必填项没填。"
      : "🎉 主表字段已填齐；下面是明细区，可按需核对、修改或补充。"));
  }
  const groups = {};
  questions.forEach(q => { const g = q.section==="detail" ? "明细区" : (q.group||"基本信息");
                           (groups[g] = groups[g] || []).push(q); });
  const presentNames = new Set(questions.map(q => q.name));
  Object.keys(groups).forEach(g=>{
    const h = el("h3", null, g + "（" + groups[g].length + "）");
    box.append(h);
    groups[g].forEach(q=>{
      if (q.kind === "detail"){
        const [rows, bar] = detailBlock(q.name, q.rows, q.max_rows);
        const card = el("div","q" + (q.reason==="imported" ? " inc" : ""));
        const lab = el("div","lab", q.label + (q.required ? " *" : "") );
        if (!q.required) lab.append(el("span","chip grey","选填"));
        if (q.reason === "imported") lab.append(el("span","chip","已导入 " + (q.rows||[]).length + " 条"));
        card.append(lab, el("div","small muted", q.reason_text||""));
        card.append(rows, bar);
        box.append(card);
        return;
      }
      const card = el("div","q" + (q.reason==="incomplete" ? " inc" : ""));
      const lab = el("div","lab", q.label + (q.required ? " *" : ""));
      card.append(lab);
      const meta = [];
      if (q.reason === "incomplete") meta.push("⚠ " + (q.reason_text||"已识别但不完整，请补全"));
      if (q.options) meta.push("可选：" + q.options.join(" / "));
      else if (q.hint) meta.push(q.hint);
      if (q.kind === "date"){
        if (q.current_value && !toDateValue(q.current_value))
          meta.push("原值：" + q.current_value + "（放不进日期选择器，请重新选择）");
        meta.push("点日历图标直接选日期");
      }
      if (meta.length) card.append(el("div","small muted", meta.join("　")));
      card.append(inputFor(q));
      renderDependents(card, q, presentNames);      // 选「是 / 有…」时才追问说明
      box.append(card);
    });
  });
  $("submitBox").style.display = "block";
}

/* 声明类说明字段：只有选中触发值（是 / 有犯罪记录）才显示并提交 */
function dependentFields(optionName){
  return ((S.contract && S.contract.main_fields) || []).filter(
    f => Array.isArray(f.depends_on) && f.depends_on[0] === optionName);
}

function renderDependents(card, q, presentNames){
  if (q.kind !== "enum") return;
  // 已经作为独立题目问到的说明字段，不再重复渲染（否则同名输入框会出现两个）
  const deps = dependentFields(q.name).filter(f => !presentNames.has(f.name));
  if (!deps.length) return;
  const ctl = card.querySelector("[data-field]");
  if (!ctl) return;
  const box = el("div");
  deps.forEach(f=>{
    const line = el("div","row"); line.style.marginTop="6px";
    line.append(el("span","small muted", f.label + (f.required ? " *" : "")));
    const ta = el("textarea"); ta.style.minHeight="56px"; ta.dataset.field = f.name;
    ta.setAttribute("aria-label", f.label);
    line.append(ta);
    box.append(line);
  });
  box.style.display = "none";
  card.append(box);
  const triggers = (deps[0].depends_on[1] || []);
  const sync = () => { box.style.display = triggers.indexOf(ctl.value) !== -1 ? "block" : "none"; };
  ctl.addEventListener("change", sync);
  sync();
}

function collectAnswers(){
  const main = {}, details = {};
  // 明细区选了「其他」的枚举：把补充内容并进取值，例如 关系 = 其他（岳父）
  const composed = new Map();
  document.querySelectorAll("#qform [data-supplement-for]").forEach(inp=>{
    if (inp.style.display === "none") return;
    const sel = inp.parentElement.querySelector("select[data-field]");
    const txt = (inp.value||"").trim();
    if (sel && sel.value === "其他" && txt) composed.set(sel, `其他（${txt}）`);
  });
  document.querySelectorAll("#qform [data-field]").forEach(ctl=>{
    if (ctl.closest("[hidden]") || ctl.getClientRects().length === 0) return;
    const v = (composed.get(ctl) || ctl.value || "").trim(); if (!v) return;
    if (ctl.dataset.detail){
      const k = ctl.dataset.detail, i = Number(ctl.dataset.row);
      details[k] = details[k] || []; details[k][i] = details[k][i] || {};
      details[k][i][ctl.dataset.field] = v;
    } else { main[ctl.dataset.field] = v; }
  });
  Object.keys(details).forEach(k=>{ details[k] = details[k].filter(r=>r && Object.keys(r).length); });
  return { main, details };
}

/* 提交前的本地校验：选「其他」必须补充具体内容 */
function unfilledOther(){
  const bad = [];
  document.querySelectorAll("#qform select[data-field]").forEach(sel=>{
    if (sel.value !== "其他") return;
    const inp = sel.parentElement.querySelector("[data-supplement-for]");
    if (inp && !(inp.value||"").trim()){
      const card = sel.closest(".q");
      const label = card ? (card.querySelector(".lab")||{}).textContent : sel.dataset.field;
      bad.push(label || sel.dataset.field);
    }
  });
  return bad;
}



async function loadQuestionnaire() {
  $("submitBox").style.display = "none";
  $("qform").replaceChildren();
  $("recognized").replaceChildren();
  $("fillLink").replaceChildren();
  let data;
  if (CANDIDATE) {
    data = await request("GET", "/public/questionnaires/" + encodeURIComponent(FILL_TOKEN));
  } else {
    // 生成问卷接口只回填写链接与进度；题目、字段契约、已识别值改从公开接口按令牌取。
    const link = await request("POST", "/questionnaires/" + applicationId() + "/questionnaire");
    const token = link.fill_url.split("/").filter(Boolean).pop();
    data = await request("GET", "/public/questionnaires/" + encodeURIComponent(token));
  }
  S.appId = data.app_id;
  S.contract = data.contract;
  S.detailDefs = Object.fromEntries(data.contract.details.map(definition => [definition.key, definition]));
  if (!CANDIDATE) {
    const link = el("a", "", "打开候选人填写链接");
    link.href = data.fill_url;
    link.target = "_blank";
    link.rel = "noopener noreferrer";
    $("fillLink").append(el("div", "card", "将此链接发送给候选人："), link);
  }
  const recognized = el("div", "card");
  recognized.append(el("h3", "", "已识别字段"));
  const values = el("div", "kv");
  for (const [name, value] of Object.entries(data.recognized)) {
    values.append(el("div", "", name), el("div", "", value));
  }
  recognized.append(values);
  $("recognized").append(recognized);
  $("missingSummary").replaceChildren(el("div", "card",
    "待补充 " + data.missing_count + " 项 · 完成度 " + data.progress.completion_rate + "%"));
  renderQuestions(data.questions);
  if (CANDIDATE) $("missingTitle").textContent = (data.name ? data.name + "，" : "") + "请核对并补充信息";
}

bindAction("btnWrite", async () => {
  const body = JSON.parse($("writeBody").value);
  if ($("appId").value.trim()) body.app_id = $("appId").value.trim();
  const data = await request("POST", "/questionnaires", body);
  S.appId = data.app_id;
  $("appId").value = data.app_id;
  $("writeResult").replaceChildren(el("div", "card", "已保存：" + data.app_id + "。请进入第 2 步生成问卷。"));
}, "writeResult");

bindAction("btnMissing", loadQuestionnaire, "missingSummary");

bindAction("btnSubmit", async () => {
  if (!$("confirmCheck").checked) throw new Error("请先勾选核对确认");
  const missing = unfilledOther();
  if (missing.length) throw new Error("请补充具体内容：" + missing.join("、"));
  const body = { ...collectAnswers(), confirmed: true };
  const path = CANDIDATE
    ? "/public/questionnaires/" + encodeURIComponent(FILL_TOKEN) + "/answers"
    : "/questionnaires/" + applicationId() + "/answers";
  const fingerprint = JSON.stringify({ path, body });
  // 网络重试保留同一提交 ID，字段变更才产生新的 ID。
  if (!S.submission || S.submission.fingerprint !== fingerprint) {
    const bytes = crypto.getRandomValues(new Uint8Array(16));
    const id = "SUB-" + Array.from(bytes, byte => byte.toString(16).padStart(2, "0")).join("");
    S.submission = { fingerprint, id };
  }
  const data = await request("POST", path, { ...body, submission_id: S.submission.id });
  S.submission = null;
  $("submitResult").replaceChildren(el("div", "card", "提交成功，待补充 " + data.missing_count + " 项。"));
  try { await loadQuestionnaire(); }
  catch (error) { toast("提交已保存，问卷刷新失败：" + error.message); }
}, "submitResult");

bindAction("btnInfo", async () => {
  const data = await request("GET", "/questionnaires/" + applicationId());
  $("infoView").replaceChildren(el("pre", "", JSON.stringify(data, null, 2)));
}, "infoView");

$("writeBody").value = JSON.stringify(SAMPLE, null, 2);
if (CANDIDATE) {
  document.body.classList.add("candidate");
  $("consoleBar").style.display = "none";
  showTab("missing");
  loadQuestionnaire().catch(error => {
    $("missingSummary").replaceChildren(el("div", "card", error.message));
  });
}
