/* No-code workflow editor. Stored steps are data, never evaluated as browser/server code. */
let flowDraft = [],
  flowRecord = {},
  simulationRoute = "",
  simulationInputs = [];
const stepNames = {
  message: "إرسال رسالة",
  input: "طلب إدخال والتحقق منه",
  menu: "فتح قائمة",
  action: "تشغيل وظيفة نظامية",
  condition: "شرط وتفرّع",
  end: "إنهاء التدفق",
};
function readFlowSteps() {
  return [...document.querySelectorAll(".flow-step")].map((el) => {
    const d = {};
    el.querySelectorAll("[data-step-field]").forEach((input) => {
      d[input.dataset.stepField] =
        input.type === "number" &&
        ["yes", "no"].includes(input.dataset.stepField)
          ? Number(input.value)
          : input.value;
    });
    return d;
  });
}
function workflowEditor(record = {}) {
  flowRecord = record;
  flowDraft = record.steps
    ? JSON.parse(record.steps)
    : [
        {
          type: "input",
          text: "مرحبًا، ما اسمك؟",
          variable: "name",
          validator: "text",
        },
        {
          type: "message",
          text: "أهلًا {name}، اختر الخدمات من القائمة الرئيسية.",
        },
        { type: "end" },
      ];
  drawFlowEditor();
}
function drawFlowEditor() {
  const options = (values, current) =>
    Object.entries(values)
      .map(
        ([v, n]) =>
          `<option value="${esc(v)}" ${v === current ? "selected" : ""}>${esc(n)}</option>`,
      )
      .join("");
  const routes = {
    home: "الرئيسية",
    services: "الخدمات",
    topup: "شحن الرصيد",
    account: "حساب الزبون",
    myorders: "طلباتي",
    ledger: "سجل الرصيد",
    support: "الدعم",
    tickets: "تذاكري",
    topups: "طلبات الشحن",
    resume: "استكمال الطلب",
    language: "اختيار اللغة",
  };
  for (const s of boot.services || [])
    routes["service:" + s.id] = "بدء طلب: " + s.name;
  const rows = flowDraft
    .map((s, i) => {
      let body = "";
      if (["message", "input"].includes(s.type))
        body += `<label class="full">نص الرسالة / سؤال الإدخال<textarea data-step-field="text">${esc(s.text || "")}</textarea></label>`;
      if (s.type === "input")
        body += `<label>اسم المتغير<input data-step-field="variable" value="${esc(s.variable || "answer")}" pattern="[A-Za-z][A-Za-z0-9_]*" required></label><label>التحقق<select data-step-field="validator">${options({ text: "نص غير فارغ", integer: "عدد صحيح", decimal: "عدد عشري", tiktok: "رابط تيك توك", choice: "اختيار من قائمة" }, s.validator || "text")}</select></label><label>الحد الأدنى (للعدد)<input data-step-field="min" type="number" step="any" value="${esc(s.min ?? "")}"></label><label>الحد الأعلى (للعدد)<input data-step-field="max" type="number" step="any" value="${esc(s.max ?? "")}"></label><label class="full">الخيارات (افصل بينها بالعلامة |)<input data-step-field="choices" value="${esc(s.choices || "")}"></label>`;
      if (s.type === "menu")
        body += `<label class="full">القائمة<select data-step-field="target">${options(Object.fromEntries((boot.menus || []).map((m) => [m.key, m.name + " — " + m.key])), s.target)}</select></label>`;
      if (s.type === "action")
        body += `<label class="full">الوظيفة<select data-step-field="target">${options(routes, s.target || "home")}</select></label>`;
      if (s.type === "condition")
        body += `<label>اسم المتغير<input data-step-field="variable" value="${esc(s.variable || "answer")}"></label><label>يساوي<input data-step-field="equals" value="${esc(s.equals || "")}"></label><label>إذا تحقق → الخطوة<select data-step-field="yes">${options(Object.fromEntries(flowDraft.map((_, n) => [String(n), "الخطوة " + (n + 1)])), String(s.yes ?? i + 1))}</select></label><label>إذا لم يتحقق → الخطوة<select data-step-field="no">${options(Object.fromEntries(flowDraft.map((_, n) => [String(n), "الخطوة " + (n + 1)])), String(s.no ?? i + 1))}</select></label>`;
      return `<section class="flow-step" data-index="${i}"><div class="flow-step-head"><b>الخطوة ${i + 1}</b><select data-step-field="type" data-flow-type>${options(stepNames, s.type)}</select><button type="button" class="icon-btn" data-flow-op="up" data-index="${i}" title="أعلى">↑</button><button type="button" class="icon-btn" data-flow-op="down" data-index="${i}" title="أسفل">↓</button><button type="button" class="icon-btn" data-flow-op="remove" data-index="${i}" title="حذف">×</button></div><div class="form-grid">${body}</div></section>`;
    })
    .join("");
  modal(
    flowRecord.id ? "تحرير التدفق #" + flowRecord.id : "إنشاء تدفق دون كود",
    `<form id="workflow-editor"><div class="form-grid"><label>اسم التدفق<input name="name" value="${esc(flowRecord.name || "")}" required></label><label class="check"><input name="enabled" type="checkbox" ${flowRecord.enabled !== 0 ? "checked" : ""}>التدفق متاح</label></div><p class="notice">استخدم متغيرات مثل {name} داخل النصوص. وظائف الطلب والشحن تمر بتحققات النظام؛ هذا المحرر لا يسمح بتشغيل كود أو تجاوز الرصيد والصلاحيات.</p><div id="flow-steps">${rows}</div><button type="button" class="secondary" data-flow-op="add">＋ إضافة خطوة</button><div class="form-actions">${btn("إلغاء", "close")}<button class="primary" type="submit">حفظ وتطبيق التدفق</button></div></form>`,
  );
}
async function saveFlowForm(form) {
  if (
    !confirm(
      "حفظ هذا التدفق؟ الجلسات التي بدأت بإصدار أقدم ستحتاج بدء التدفق من جديد.",
    )
  )
    return;
  await api("workflows", {
    id: flowRecord.id,
    name: form.elements.name.value,
    enabled: form.elements.enabled.checked,
    steps: readFlowSteps(),
  });
  $("#modal").close();
  boot = await api("bootstrap");
  await listView();
  toast("تم حفظ التدفق؛ اربطه بزر من محرر القوائم.");
}
async function simulateBot(route, reset = true) {
  if (reset) {
    simulationRoute = route;
    simulationInputs = [];
  }
  const result = await api("simulate", {
    route: simulationRoute,
    inputs: simulationInputs,
  });
  modal(
    "محاكاة آمنة — لا إرسال ولا خصم حقيقي",
    `<p class="notice">رصيد افتراضي $100. تُعاد جميع تغييرات المحاكاة داخل قاعدة البيانات ولا تصل إشعارات إلى Telegram. هذه ليست شهادة اتصال حي.</p><div class="simulation">${result.messages.map((p) => `<div class="message"><small>${esc(p.method)}</small>${esc(p.data.text || p.data.caption || p.data.title || "وسائط")}</div>`).join("")}</div><p class="hint">الحالة: ${esc(result.state || "القائمة")}</p><form id="simulation-input"><label>الإدخال التالي<input name="value" required></label><div class="form-actions"><button class="primary" type="submit">إرسال للمعاينة</button></div></form>`,
  );
}
document.addEventListener("click", (e) => {
  const button = e.target.closest("[data-flow-op]");
  if (!button) return;
  flowDraft = readFlowSteps();
  const name = $("#workflow-editor [name=name]").value,
    enabled = $("#workflow-editor [name=enabled]").checked;
  flowRecord = { ...flowRecord, name, enabled: enabled ? 1 : 0 };
  const i = Number(button.dataset.index);
  if (button.dataset.flowOp === "add")
    flowDraft.push({ type: "message", text: "" });
  if (button.dataset.flowOp === "remove") flowDraft.splice(i, 1);
  if (button.dataset.flowOp === "up" && i > 0)
    [flowDraft[i - 1], flowDraft[i]] = [flowDraft[i], flowDraft[i - 1]];
  if (button.dataset.flowOp === "down" && i < flowDraft.length - 1)
    [flowDraft[i + 1], flowDraft[i]] = [flowDraft[i], flowDraft[i + 1]];
  drawFlowEditor();
});
document.addEventListener("change", (e) => {
  if (e.target.matches("[data-flow-type]")) {
    flowDraft = readFlowSteps();
    flowRecord = {
      ...flowRecord,
      name: $("#workflow-editor [name=name]").value,
      enabled: $("#workflow-editor [name=enabled]").checked ? 1 : 0,
    };
    drawFlowEditor();
  }
});
