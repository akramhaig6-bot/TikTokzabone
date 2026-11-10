"use strict";
const $ = (s) => document.querySelector(s),
  esc = (s) =>
    String(s ?? "").replace(
      /[&<>"']/g,
      (c) =>
        ({
          "&": "&amp;",
          "<": "&lt;",
          ">": "&gt;",
          '"': "&quot;",
          "'": "&#39;",
        })[c],
    );
const labels = {
  workflows: "بناء التدفقات",
  translations: "ترجمات المحتوى",
  locales: "اللغات",
  expenses: "المصروفات والعمولات",
  stats: "نظرة عامة",
  orders: "إدارة الطلبات",
  topups: "طلبات الشحن",
  users: "إدارة المستخدمين",
  balances: "إدارة الأرصدة",
  services: "الخدمات والأسعار",
  inventory: "مخزون الحسابات",
  support: "الدعم الفني",
  tickets: "تذاكر الدعم",
  broadcasts: "الإذاعة",
  menus: "القوائم والرسائل",
  buttons: "الأزرار والإجراءات",
  staff: "الأدمنية والصلاحيات",
  settings: "إعدادات البوت",
  ledger: "السجل المالي",
  audit: "سجل العمليات",
  notifications: "سجل الإشعارات",
  payments: "المدفوعات",
  preview: "معاينة البوت",
  messages: "رسائل التذكرة",
  deliveries: "تقرير تسليم الإذاعة",
};
const icons = {
  workflows: "⇢",
  translations: "文",
  locales: "◎",
  expenses: "◴",
  stats: "◫",
  orders: "▣",
  topups: "▤",
  users: "♧",
  balances: "◉",
  services: "⊞",
  inventory: "▧",
  support: "♧",
  broadcasts: "♬",
  menus: "◈",
  staff: "♙",
  settings: "⚙",
  ledger: "≡",
  audit: "◷",
  notifications: "♧",
  preview: "▯",
};
const fields = {
  layout_key: "تخطيط أزرار الرسالة (اختياري)",
  child_menu: "أزرار فرعية للرسالة (مفتاح قائمة)",
  code: "رمز اللغة",
  locale: "اللغة",
  token: "مفتاح المحتوى: menu:key أو button:id",
  steps: "خطوات التدفق",
  revision: "الإصدار",
  id: "الرقم",
  name: "الاسم",
  username: "اسم المستخدم",
  first_name: "الاسم",
  user_id: "المستخدم",
  telegram_id: "Telegram ID",
  password: "كلمة المرور",
  permissions: "الصلاحيات",
  enabled: "مفعّل",
  price: "السعر لكل 1000 ($)",
  cost: "تكلفة التنفيذ ($)",
  min_qty: "الحد الأدنى للكمية",
  max_qty: "الحد الأعلى للكمية",
  description: "الوصف",
  image: "صورة الخدمة (رفع محلي أو رابط HTTPS)",
  occurred_on: "تاريخ الاستحقاق",
  reversed_from: "الحركة الأصلية المعكوسة",
  target_type: "نوع الرابط المطلوب",
  position: "ترتيب العرض",
  note: "ملاحظة إدارية",
  status: "الحالة",
  created: "تاريخ الإنشاء",
  updated: "آخر تعديل",
  amount: "المبلغ ($)",
  method: "الطريقة",
  proof: "إثبات التحويل",
  reason: "السبب",
  balance: "الرصيد ($)",
  service_name: "الخدمة",
  service_id: "رقم الخدمة",
  target: "الرابط / الوجهة / نص الرسالة",
  quantity: "الكمية",
  refunded: "تم الاسترداد",
  debit_id: "حركة الخصم",
  refund_id: "حركة الاسترداد",
  completed: "تاريخ الإكمال",
  key: "المعرّف البرمجي للقائمة",
  text: "نص الرسالة (يدعم المتغيرات بين { })",
  kind: "النوع",
  menu_id: "رقم القائمة",
  label: "اسم الزر",
  action: "الإجراء",
  row_num: "رقم الصف",
  col_num: "رقم العمود",
  permission: "الصلاحية المطلوبة (فارغ للزبون)",
  body: "محتوى الرسالة",
  media: "رابط الوسائط أو Telegram file_id",
  audience: "المستلمون",
  actor: "المنفّذ",
  delta: "المبلغ",
  before_balance: "الرصيد قبل",
  after_balance: "الرصيد بعد",
  operation_key: "معرف العملية",
  order_id: "الطلب المرتبط",
  payment_id: "الدفع المرتبط",
  subject: "موضوع التذكرة",
  ticket_id: "رقم التذكرة",
  data: "تفاصيل العملية",
  entity: "السجل المرتبط",
  charge_id: "معرف دفعة Telegram",
  currency: "العملة",
  topup_id: "طلب الشحن",
  stars: "عدد Stars",
  last_active: "آخر نشاط",
  added_by: "أضافه",
  updated_by: "عدّله",
  attempts: "المحاولات",
  error: "سبب الفشل",
  payload: "بيانات الإرسال",
  report: "تقرير التسليم",
  order_count: "عدد الطلبات",
  completed_orders: "الطلبات المكتملة",
  pending_orders: "الطلبات المعلقة",
  total_topups: "إجمالي الشحن",
  role: "الدور",
  deleted: "محذوف",
  attachment: "المرفق",
};
const names = {
  expense: "مصروف",
  fee: "عمولة",
  pending: "قيد المراجعة",
  review: "قيد المراجعة",
  processing: "قيد التنفيذ",
  completed: "مكتمل",
  cancelled: "ملغي",
  refunded: "مسترد",
  approved: "مقبول",
  rejected: "مرفوض",
  awaiting_payment: "بانتظار الدفع",
  awaiting_proof: "بانتظار الإثبات",
  active: "نشط",
  blocked: "محظور",
  available: "متاح",
  reserved: "محجوز",
  used: "مستخدم",
  unavailable: "غير متاح",
  open: "مفتوحة",
  closed: "مغلقة",
  draft: "مسودة",
  running: "جارٍ الإرسال",
  paused: "متوقفة مؤقتًا",
  stopped: "متوقفة",
  sent: "تم الإرسال",
  failed: "فشل",
  unknown: "غير مؤكد",
  manual: "يدوي",
  stars: "Telegram Stars",
  all: "الكل",
  balance: "لديهم رصيد",
  orders: "لديهم طلبات",
  text: "نص",
  photo: "صورة",
  video: "فيديو",
  document: "ملف",
  inline: "Inline Keyboard",
  reply: "Reply Keyboard",
  multilevel: "متعددة المستويات",
  workflow: "تشغيل تدفق مخصص",
  language: "اختيار اللغة",
  callback: "Callback",
  url: "رابط",
  webapp: "Web App",
  any: "حساب أو منشور",
  profile: "رابط حساب",
  services: "قائمة الخدمات",
  topup: "شحن الرصيد",
  myorders: "طلبات الزبون",
  account: "حساب الزبون",
  support: "الدعم الفني",
  menu: "فتح قائمة",
  message: "إرسال رسالة",
  order: "بدء طلب (رقم الخدمة في الوجهة)",
  ledger: "سجل الرصيد",
  tickets: "تذاكر الزبون",
  topups: "طلبات شحن الزبون",
  admin: "فتح الإدارة (يتطلب صلاحية)",
  none: "الرئيسية",
};
const currencyFields = [
  "price",
  "cost",
  "balance",
  "amount",
  "delta",
  "before_balance",
  "after_balance",
  "total_topups",
];
let expenseStart = "",
  expenseEnd = "";
let csrf = "",
  boot = null,
  current = "stats",
  page = 1,
  query = "",
  filter = "",
  items = [],
  setup = false,
  activeRecord = null,
  timer,
  requestSeq = 0;
function can(p) {
  if (["workflows", "translations"].includes(p)) p = "menus";
  if (p === "locales") p = "settings";
  return (
    boot?.actor.role === "owner" ||
    JSON.parse(boot?.actor.permissions || "[]").includes(p)
  );
}
function toast(t) {
  $("#toast").textContent = t;
  $("#toast").classList.add("show");
  clearTimeout(timer);
  timer = setTimeout(() => $("#toast").classList.remove("show"), 4200);
}
async function api(path, data) {
  const r = await fetch("/api/" + path, {
    method: data === undefined ? "GET" : "POST",
    headers: { "Content-Type": "application/json", "X-CSRF-Token": csrf },
    body: data === undefined ? undefined : JSON.stringify(data),
  });
  let out;
  try {
    out = await r.json();
  } catch {
    throw Error("تعذر قراءة استجابة الخادم");
  }
  if (!r.ok) throw Error(out.error || "تعذر تنفيذ العملية");
  return out;
}
function badge(v) {
  return `<span class="badge ${esc(v)}">${esc(names[v] || v)}</span>`;
}
function dollars(v) {
  return "$" + (Number(v || 0) / 100).toFixed(2);
}
function fmt(k, v) {
  if (currencyFields.includes(k)) return `<span dir="ltr">${dollars(v)}</span>`;
  if (k === "status") return badge(v);
  if (["kind", "method"].includes(k)) return esc(names[v] || v);
  if (k === "permissions") {
    try {
      return JSON.parse(v)
        .map((p) => labels[p] || p)
        .join("، ");
    } catch {
      return esc(v);
    }
  }
  if (typeof v === "object") return esc(JSON.stringify(v));
  if (k === "enabled" || k === "refunded") return v ? "نعم" : "لا";
  if (["created", "updated", "last_active", "completed"].includes(k))
    return esc(v ? String(v).slice(0, 16).replace("T", " ") : "—");
  return esc(v ?? "—");
}
function btn(text, act, extra = "", cls = "secondary") {
  return `<button type="button" class="${cls}" data-action="${act}" ${extra}>${text}</button>`;
}
async function start() {
  try {
    const s = await api("session");
    csrf = s.csrf;
    setup = s.setup;
    if (!s.actor) {
      $("#auth").classList.remove("hidden");
      $("#shell").classList.add("hidden");
      $("#auth-title").textContent = setup
        ? "أنشئ مساحة عملك ✦"
        : "مرحبًا بعودتك 👋";
      $("#auth-sub").textContent = setup
        ? "أنشئ حساب المالك مرة واحدة لبدء إدارة النظام."
        : "سجّل الدخول إلى مساحة الإدارة الخاصة بك.";
      $("#setup-secret").classList.toggle("hidden", !setup);
      return;
    }
    boot = await api("bootstrap");
    $("#auth").classList.add("hidden");
    $("#shell").classList.remove("hidden");
    $("#actor-name").textContent = boot.actor.username;
    $("#actor-role").textContent =
      boot.actor.role === "owner" ? "مالك النظام" : "أدمن • صلاحيات مخصصة";
    $("#avatar").textContent = boot.actor.username[0];
    $("#workspace-name").textContent = boot.settings.brand || "مساحة العمل";
    const nav = [
      "stats",
      "orders",
      "topups",
      "users",
      "balances",
      "services",
      "inventory",
      "support",
      "broadcasts",
      "menus",
      "workflows",
      "staff",
      "ledger",
      "expenses",
      "audit",
      "settings",
    ];
    $("#nav").innerHTML = nav
      .filter(can)
      .map(
        (k) =>
          `<button data-nav="${k}"><span class="nav-icon">${icons[k]}</span>${labels[k]}</button>`,
      )
      .join("");
    if (!can(current)) current = nav.find(can) || "preview";
    connection();
    await navigate(current);
  } catch (e) {
    toast(e.message);
  }
}
function connection() {
  const connected = boot.runtime.status === "connected";
  $("#connection").classList.toggle("online", connected);
  $("#connection").textContent = connected
    ? "● البوت متصل"
    : boot.connected
      ? "● " +
        ({ error: "خطأ اتصال", connecting: "جارٍ الاتصال" }[
          boot.runtime.status
        ] || "بانتظار الاتصال")
      : "● البوت غير مربوط";
}
async function navigate(k) {
  current = k;
  page = 1;
  query = "";
  filter = "";
  expenseStart = "";
  expenseEnd = "";
  $("#sidebar").classList.remove("open");
  document
    .querySelectorAll("[data-nav]")
    .forEach((n) => n.classList.toggle("active", n.dataset.nav === k));
  const title = labels[k] || k;
  $("#breadcrumb").textContent = title;
  $("#page-heading").innerHTML =
    `<div><div class="eyebrow">WORKSPACE / ${esc(k.toUpperCase())}</div><h1>${title}${k === "stats" ? " ✦" : ""}</h1><p>${k === "stats" ? "أهلاً بك، إليك نظرة شاملة على نشاط منصتك اليوم." : "أدِر " + title + " من مكان واحد، والتغييرات تتزامن مع بوت الزبون."}</p></div><div class="actions" id="heading-actions"></div>`;
  if (k === "stats") await dashboard();
  else if (k === "settings") settings();
  else if (k === "balances") balanceView();
  else if (k === "preview") await previewView();
  else await listView();
}
function tableName() {
  return current === "support" ? "tickets" : current;
}
async function dashboard() {
  const s = await api("stats");
  if (current !== "stats") return;
  $("#heading-actions").innerHTML =
    '<input type="date" id="start-date" title="بداية الفترة"><input type="date" id="end-date" title="نهاية الفترة">' +
    btn("تطبيق", "stats-filter") +
    btn("↓ تصدير", "export");
  renderDashboard(s);
}
function renderDashboard(s) {
  if (current !== "stats") return;
  const completed =
    s.statuses.find((x) => x.status === "completed")?.count || 0;
  const statusCount = (x) => s.statuses.find((i) => i.status === x)?.count || 0;
  let chart = s.chart.slice().reverse();
  if (!chart.length)
    chart = Array.from({ length: 7 }, (_, i) => ({
      day: new Date(Date.now() - (6 - i) * 86400000).toISOString().slice(0, 10),
      total: 0,
      count: 0,
    }));
  const max = Math.max(...chart.map((r) => r.total), 1);
  $("#view").innerHTML =
    `${!boot.connected ? `<div class="banner"><div class="banner-icon">↗</div><div><h3>ابدأ رحلتك، اربط بوت تيليجرام الخاص بك</h3><p>أدخل التوكن مرة واحدة، وأدِر كل التفاصيل من هنا دون تعديل الكود.</p></div>${can("settings") ? btn("ربط البوت ←", "go-settings", "", "primary") : ""}</div>` : `<div class="banner"><div class="banner-icon">✦</div><div><h3>مساحة واحدة لكل عملياتك</h3><p>الخدمات والمحتوى والطلبات ترتبط بقاعدة بيانات موحّدة في الوقت الفعلي.</p></div>${btn("معاينة البوت ←", "go-preview")}</div>`}<div class="stats-grid">${[
      [s.users, "إجمالي المستخدمين", "♧", "مستخدم مسجل"],
      [s.orders, "إجمالي الطلبات", "▣", "طلب في الفترة المحددة"],
      [dollars(s.topups), "إجمالي الشحن", "◉", "عمليات شحن مؤكدة"],
      [
        dollars(s.profit),
        "صافي الربح المحسوب",
        "↗",
        "بعد تكاليف التنفيذ والمصروفات",
      ],
    ]
      .map(
        ([v, l, i, t]) =>
          `<div class="stat"><div class="stat-top"><span>${l}</span><span class="stat-icon">${i}</span></div><strong>${v}</strong><small><em>●</em>${t}</small></div>`,
      )
      .join(
        "",
      )}</div><div class="grid-two"><div class="card"><div class="card-head"><h3>نظرة على نشاط الطلبات</h3><small>قيمة الطلبات • حسب اليوم</small></div><div class="card-body"><div class="chart">${chart.map((r) => `<div class="bar-group" title="${r.count} طلب — ${dollars(r.total)}"><div class="bar" style="height:${Math.max(2, (r.total / max) * 135)}px"></div><span>${esc(r.day.slice(5))}</span></div>`).join("")}</div><div class="chart-caption"><i></i>إجمالي قيمة الطلبات</div></div></div><div class="card"><div class="card-head"><h3>حالات الطلبات</h3><small>توزيع العمليات</small></div><div class="donut-wrap"><div class="donut" style="background:conic-gradient(#a283d6 0 ${s.orders ? (completed / s.orders) * 100 : 0}%,#eee8f7 0 100%)"><div><b>${s.orders}</b><small>إجمالي الطلبات</small></div></div><div class="legend">${["completed", "processing", "pending", "cancelled", "refunded"].map((x) => `<p><i></i>${names[x]}<b>${statusCount(x)}</b></p>`).join("")}</div></div></div></div><div class="card"><div class="card-head"><h3>الوصول السريع</h3><small>إدارة عملياتك اليومية</small></div><div class="card-body quick-links">${[
      "orders",
      "services",
      "topups",
      "support",
    ]
      .filter(can)
      .map(
        (k) =>
          `<button data-nav="${k}"><span>${icons[k]}</span>${labels[k]} ←</button>`,
      )
      .join(
        "",
      )}</div></div><div class="card"><div class="card-head"><h3>الملخص المالي</h3><small>اعتراف بالمبيعات عند الإكمال والاسترداد في تاريخ حدوثه</small></div><div class="table-scroll"><table><thead><tr><th>المبيعات عند الإكمال</th><th>تكلفة التنفيذ</th><th>استردادات المبيعات المكتملة</th><th>المصروفات والعمولات</th></tr></thead><tbody><tr><td>${dollars(s.sales)}</td><td>${dollars(s.cost)}</td><td>${dollars(s.recognized_refunds)}</td><td>${dollars(s.expenses + s.fees)}</td></tr></tbody></table></div></div>`;
}
const columns = {
  workflows: ["id", "name", "enabled", "revision", "updated"],
  translations: ["id", "locale", "token", "text"],
  locales: ["id", "code", "name", "enabled"],
  expenses: ["id", "kind", "amount", "reason", "occurred_on", "reversed_from"],
  orders: [
    "id",
    "service_name",
    "user_id",
    "quantity",
    "price",
    "status",
    "created",
  ],
  topups: ["id", "user_id", "amount", "method", "status", "created"],
  users: ["id", "first_name", "username", "balance", "status", "created"],
  services: ["id", "name", "price", "min_qty", "max_qty", "enabled"],
  inventory: ["id", "username", "status", "note", "updated"],
  tickets: ["id", "subject", "user_id", "status", "updated"],
  staff: ["id", "username", "telegram_id", "permissions", "enabled"],
  menus: ["id", "name", "key", "kind"],
  buttons: ["id", "label", "menu_id", "action", "row_num", "col_num"],
  ledger: ["id", "user_id", "delta", "reason", "after_balance", "created"],
  audit: ["id", "actor", "action", "entity", "created"],
  broadcasts: ["id", "body", "audience", "status", "created"],
  notifications: ["id", "status", "attempts", "error", "created"],
  messages: ["id", "actor", "body", "created"],
  payments: ["id", "user_id", "amount", "currency", "created"],
};
async function listView() {
  const table = tableName(),
    seq = ++requestSeq;
  let url = `data/${table}?page=${page}&q=${encodeURIComponent(query)}&status=${encodeURIComponent(filter)}`;
  if (table === "expenses")
    url +=
      "&start=" +
      encodeURIComponent(expenseStart) +
      "&end=" +
      encodeURIComponent(expenseEnd);
  const r = await api(url);
  if (seq !== requestSeq || table !== tableName()) return;
  items = r.items;
  const create =
    boot.schemas[table] || ["staff", "expenses", "workflows"].includes(table);
  $("#heading-actions").innerHTML =
    (create
      ? btn(
          "＋ إضافة " +
            ({
              workflows: "تدفق",
              locales: "لغة",
              translations: "ترجمة",
              expenses: "مصروف / عمولة",
              services: "خدمة",
              inventory: "حساب",
              menus: "قائمة",
              buttons: "زر",
              staff: "أدمن",
              broadcasts: "إذاعة",
            }[table] || "جديد"),
          "create",
          "",
          "primary",
        )
      : "") +
    (table === "menus"
      ? btn("الأزرار", "go-buttons") +
        btn("ترجمات المحتوى", "go-translations") +
        btn("معاينة", "go-preview")
      : "") +
    (table === "topups" && can("ledger")
      ? btn("المدفوعات", "go-payments")
      : "") +
    (table === "audit" ? btn("الإشعارات", "go-notifications") : "");
  const states =
    {
      orders: ["pending", "processing", "completed", "cancelled", "refunded"],
      topups: [
        "awaiting_payment",
        "awaiting_proof",
        "review",
        "approved",
        "rejected",
        "cancelled",
      ],
      users: ["active", "blocked"],
      inventory: ["available", "reserved", "used", "unavailable"],
      tickets: ["open", "processing", "closed"],
      broadcasts: ["draft", "running", "paused", "completed", "stopped"],
      notifications: ["pending", "sent", "failed"],
    }[table] || [];
  const cols = columns[table] || ["id"];
  $("#view").innerHTML =
    `<div class="card"><form id="search" class="toolbar"><input name="q" placeholder="⌕  ابحث برقم السجل أو الاسم أو أي بيانات…" value="${esc(query)}">${states.length ? `<select name="status" aria-label="تصفية الحالة"><option value="">جميع الحالات</option>${states.map((s) => `<option value="${s}" ${filter === s ? "selected" : ""}>${names[s]}</option>`).join("")}</select>` : ""}${table === "expenses" ? `<label>من<input type="date" name="start" value="${esc(expenseStart)}"></label><label>إلى<input type="date" name="end" value="${esc(expenseEnd)}"></label>` : ""}<button class="secondary" type="submit">بحث وتصفية</button><span class="count">${r.total} سجل</span></form><div class="table-scroll"><table><thead><tr>${cols.map((c) => `<th>${fields[c] || c}</th>`).join("")}<th>الإجراءات</th></tr></thead><tbody>${items.map((row, i) => `<tr>${cols.map((c) => `<td>${c === "id" ? `<span class="code">${esc(({ orders: "TK-", topups: "TOP-", tickets: "SUP-", inventory: "ACC-", ledger: "LED-" }[table] || "#") + String(row.id).padStart(5, "0"))}</span>` : c === "name" || c === "service_name" ? "<strong>" + fmt(c, row[c]) + "</strong>" : fmt(c, typeof row[c] === "string" && row[c].length > 65 && c !== "permissions" ? row[c].slice(0, 65) + "…" : row[c])}</td>`).join("")}<td>${btn("فتح ←", "detail", `data-index="${i}"`, "link-btn")}</td></tr>`).join("")}</tbody></table></div>${!items.length ? '<div class="empty"><span class="empty-icon">▧</span>لا توجد سجلات بعد<br><small>ستظهر البيانات الفعلية هنا عند بدء استخدام النظام.</small></div>' : ""}<div class="pager"><span>صفحة ${r.page} من ${r.pages} · ${r.total} سجل</span><div class="actions">${btn("السابق", "prev", page === 1 ? "disabled" : "")}${btn("التالي", "next", page >= r.pages ? "disabled" : "")}</div></div></div>${table === "menus" ? '<div class="notice">يمكنك تعديل جميع النصوص والقوائم هنا. قوالب شاشات التدفقات مجهّزة مسبقًا وقابلة للتعديل. احتفظ بأسماء المتغيرات بين الأقواس. الأزرار ثابتة الهوية وقابلة لتغيير النص والترتيب والوجهة من إدارة الأزرار.</div>' : ""}`;
  $("#search select")?.classList.add("search-select");
}
function modal(title, body) {
  $("#modal-title").textContent = title;
  $("#modal-body").innerHTML = body;
  if (!$("#modal").open) $("#modal").showModal();
}
function inputField(k, typ, val, full = false) {
  let html;
  let value = val ?? (typ === "bool" ? true : "");
  if (typ === "money" && val !== undefined) value = Number(val) / 100;
  if (typ === "bool")
    return `<label class="check"><input type="checkbox" name="${k}" ${value ? "checked" : ""}>${fields[k] || k}</label>`;
  if (["layout_key", "child_menu"].includes(k))
    html = `<select name="${k}"><option value="">افتراضي / دون تخصيص</option>${(boot.menus || []).map((m) => `<option value="${esc(m.key)}" ${value === m.key ? "selected" : ""}>${esc(m.name)} — ${esc(m.key)}</option>`).join("")}</select>`;
  else if (k === "language")
    html = `<select name="language">${(boot.locales || [])
      .filter((l) => l.enabled)
      .map(
        (l) =>
          `<option value="${esc(l.code)}" ${value === l.code ? "selected" : ""}>${esc(l.name)}</option>`,
      )
      .join("")}</select>`;
  else if (k === "locale")
    html = `<select name="locale">${(boot.locales || []).map((l) => `<option value="${esc(l.code)}" ${value === l.code ? "selected" : ""}>${esc(l.name)}</option>`).join("")}</select>`;
  else if (typ.includes("|"))
    html = `<select name="${k}">${typ
      .split("|")
      .map(
        (o) =>
          `<option value="${o}" ${value === o ? "selected" : ""}>${esc(names[o] || o)}</option>`,
      )
      .join("")}</select>`;
  else if (
    ["text", "description", "note", "body", "transfer_instructions"].includes(k)
  )
    html = `<textarea name="${k}">${esc(value)}</textarea>`;
  else
    html = `<input name="${k}" type="${typ === "money" || typ === "int" ? "number" : k === "password" ? "password" : "text"}" ${typ === "money" ? 'step="0.01"' : typ === "int" ? 'step="1"' : ""} value="${esc(value)}" ${["name", "username", "key", "label"].includes(k) ? "required" : ""}>`;
  return `<label class="${full ? "full" : ""}">${fields[k] || k}${html}</label>`;
}
function editor(record = {}) {
  const t = tableName();
  if (!record.id)
    record = {
      ...({
        services: {
          price: 100,
          cost: 0,
          min_qty: 100,
          max_qty: 100000,
          enabled: 1,
          target_type: "any",
          position: 0,
        },
        buttons: {
          row_num: 0,
          col_num: 0,
          enabled: 1,
          action: "message",
          kind: "callback",
        },
        menus: { kind: "inline" },
        inventory: { status: "available" },
        broadcasts: { kind: "text", audience: "all" },
        staff: { enabled: 1 },
      }[t] || {}),
      ...record,
    };
  const schema =
    t === "staff"
      ? {
          username: "text",
          password: "text",
          telegram_id: "int",
          enabled: "bool",
        }
      : boot.schemas[t];
  activeRecord = record;
  let body = `<form id="editor" data-table="${t}"><div class="form-grid">${Object.entries(
    schema,
  )
    .map(([k, typ]) =>
      inputField(
        k,
        typ,
        record[k],
        ["text", "body", "description", "target", "note"].includes(k),
      ),
    )
    .join("")}`;
  if (t === "staff") {
    let selected = [];
    try {
      selected = JSON.parse(record.permissions || "[]");
    } catch {}
    body += `<div class="full"><p>حدد صلاحيات هذا الأدمن بصورة مستقلة:</p><div class="form-grid">${boot.permissions
      .filter((p) => can(p))
      .map(
        (p) =>
          `<label class="check"><input type="checkbox" name="perm" value="${p}" ${selected.includes(p) ? "checked" : ""}>${labels[p] || p}</label>`,
      )
      .join("")}</div></div>`;
  }
  if (t === "services" || t === "broadcasts") {
    const field = t === "services" ? "image" : "media";
    const existing = record[field] || "";
    body += `<div class="full upload-card"><label>رفع ${t === "services" ? "صورة الخدمة" : "وسائط الإذاعة"} من جهازك<input type="file" data-upload-field="${field}" data-purpose="${t}" accept="${t === "services" ? ".jpg,.jpeg,.png,.webp" : ".jpg,.jpeg,.png,.webp,.mp4,.pdf,.txt"}"></label><small class="hint">صور حتى 10 ميجابايت؛ فيديو وملفات حتى 20 ميجابايت. الملفات محفوظة في مساحة خاصة ولا تُعرض للعموم.</small><div id="upload-status" role="status">${existing.startsWith("upload:") ? uploadPreview(existing, record.kind || "photo") : ""}</div></div>`;
  }
  body += `</div>${t === "inventory" ? '<p class="notice">سجلات أسماء الحسابات فقط. لا تُدخل كلمات مرور أو رموز تحقق أو بيانات دخول.</p>' : ""}${t === "buttons" ? '<p class="hint">الإجراء callback هو مسار نظامي قائم. لإنشاء محتوى جديد استخدم «إرسال رسالة» أو «فتح قائمة» مع معرّف القائمة في الوجهة.</p>' : ""}<div class="form-actions">${btn("إلغاء", "close")}<button class="primary" type="submit">حفظ التغييرات ←</button></div></form>`;
  modal(record.id ? "تعديل السجل #" + record.id : "إضافة " + labels[t], body);
}
async function detail(i) {
  const r = items[i],
    t = tableName();
  activeRecord = r;
  const readable = Object.keys(r).filter(
    (k) => !["password", "request_key", "payload"].includes(k),
  );
  let body = `<div class="detail-grid">${readable.map((k) => `<div class="detail-item"><small>${fields[k] || k}</small><div>${fmt(k, r[k])}</div></div>`).join("")}</div><div class="detail-actions">`;
  if (boot.schemas[t] || t === "staff" || t === "workflows")
    body += btn("✎ تعديل", "edit");
  if (t === "workflows") body += btn("اختبار التدفق", "simulate-workflow");
  if (t === "menus")
    body +=
      btn("نسخ القائمة", "clone-menu") + btn("اختبار القائمة", "simulate-menu");
  if (t === "buttons")
    body += ["up", "down", "left", "right"]
      .map((d) =>
        btn(
          { up: "↑", down: "↓", left: "←", right: "→" }[d],
          "move-button",
          `data-direction="${d}"`,
        ),
      )
      .join("");
  if (["services", "inventory", "menus", "buttons", "staff"].includes(t))
    body += btn("حذف / أرشفة", "delete", "", "danger");
  if (t === "expenses" && r.amount > 0 && !r.reversed_from)
    body += btn("عكس هذه الحركة", "expense-reverse", "", "danger");
  if (t === "orders") {
    if (can("orders"))
      body +=
        ["processing", "completed", "cancelled", "refunded"]
          .map((s) => btn(names[s], "order-state", `data-state="${s}"`))
          .join("") + btn("ملاحظة وتكلفة فعلية", "order-note");
    body += btn("سجل الطلب", "related-audit");
  }
  if (t === "topups") {
    if (can("topups_approve") && r.status === "review")
      body +=
        btn("قبول وإضافة الرصيد", "topup-accept", "", "primary") +
        btn("رفض الطلب", "topup-reject", "", "danger");
    body += btn("عرض الإثبات", "proof");
  }
  if (t === "users") {
    if (can("users_manage"))
      body +=
        btn(
          r.status === "blocked" ? "إلغاء الحظر" : "حظر المستخدم",
          "user-status",
          "",
          "danger",
        ) + btn("ملاحظة إدارية", "user-note");
    if (can("balances")) body += btn("تعديل الرصيد", "user-balance");
    if (can("orders")) body += btn("طلبات المستخدم", "user-orders");
    if (can("ledger")) body += btn("الحركات المالية", "user-ledger");
  }
  if (t === "inventory" || t === "staff")
    body += btn("سجل التعديلات", "related-audit");
  if (t === "tickets")
    body +=
      btn("إرسال رد", "ticket-reply", "", "primary") +
      ["open", "processing", "closed"]
        .map((s) => btn(names[s], "ticket-state", `data-state="${s}"`))
        .join("");
  if (t === "broadcasts") body += btn("تقرير المستلمين", "broadcast-report");
  if (t === "broadcasts")
    body += (
      {
        draft: ["running", "stopped"],
        running: ["paused", "stopped"],
        paused: ["running", "stopped"],
      }[r.status] || []
    )
      .map((s) =>
        btn(
          {
            running: "بدء / استكمال",
            paused: "إيقاف مؤقت",
            stopped: "إيقاف نهائي",
          }[s],
          "broadcast-state",
          `data-state="${s}"`,
          s === "running" ? "primary" : "secondary",
        ),
      )
      .join("");
  if (t === "notifications" && r.status === "failed")
    body += btn("إعادة محاولة", "notification-retry");
  body += "</div>";
  if (t === "tickets") {
    const m = await api("data/messages?ticket_id=" + r.id);
    body += `<h3>المحادثة</h3>${
      m.items
        .reverse()
        .map(
          (x) =>
            `<div class="message"><small>${esc(x.actor)} · ${fmt("created", x.created)}</small>${esc(x.body)}</div>`,
        )
        .join("") || '<p class="hint">لا رسائل</p>'
    }`;
  }
  modal(labels[t] + " #" + r.id, body);
}
function balanceView(uid = "") {
  $("#heading-actions").innerHTML = "";
  $("#view").innerHTML =
    `<div class="card"><div class="card-head"><h3>إضافة أو خصم رصيد</h3><small>عملية ذرية وقابلة للتدقيق</small></div><div class="card-body"><div class="notice">استخدم مبلغًا موجبًا للإضافة وسالبًا للخصم. لا يمكن أن يصبح الرصيد سالبًا. ستظهر مراجعة قبل التنفيذ ويصل إشعار إلى الزبون.</div><form id="balance-form"><div class="form-grid"><label>Telegram ID<input type="number" name="user_id" required value="${esc(uid)}"></label><label>المبلغ بالدولار<input name="amount" type="number" step="0.01" required></label><label class="full">سبب العملية<textarea name="reason" required></textarea></label></div><div class="form-actions"><button type="submit" class="primary">مراجعة وتنفيذ ←</button></div></form></div></div>`;
}
function settings() {
  const s = boot.settings;
  $("#heading-actions").innerHTML = btn("معاينة البوت", "go-preview");
  const monetary = [
    "topup_min",
    "topup_max",
    "order_min",
    "order_max",
    "expenses",
    "fees",
  ];
  const settingFields = {
    brand: "اسم المنصة",
    owner_telegram_id: "Telegram ID للمالك (للإشعارات)",
    maintenance: "وضع الصيانة",
    maintenance_staff: "السماح للمالك والأدمن أثناء الصيانة",
    manual_enabled: "تفعيل الشحن اليدوي",
    stars_enabled: "تفعيل Telegram Stars",
    topup_min: "الحد الأدنى للشحن ($)",
    topup_max: "الحد الأعلى للشحن ($)",
    order_min: "الحد الأدنى لقيمة الطلب ($)",
    order_max: "الحد الأعلى لقيمة الطلب ($)",
    stars_rate: "عدد Stars لكل دولار",
    transfer_instructions: "تعليمات وبيانات التحويل",
    session_minutes: "مدة الجلسة بالدقائق",
    expenses: "المصروفات للفترة المحاسبية ($)",
    fees: "العمولات للفترة المحاسبية ($)",
    language: "اللغة",
    notifications_enabled: "إشعارات الإدارة",
    web_url: "رابط لوحة الإدارة (HTTPS)",
    support_enabled: "تفعيل الدعم",
    customer_cancel_pending: "السماح للزبون بإلغاء الطلب المعلق",
  };
  Object.assign(fields, settingFields);
  $("#view").innerHTML =
    `<div class="card"><div class="card-head"><h3>↗ ربط بوت تيليجرام</h3>${badge(boot.connected ? "active" : "pending")}</div><div class="card-body"><p class="hint">أدخل توكن البوت الصادر من BotFather. سيتم التحقق منه، ضبط أوامر البدء، وإطلاق الاتصال التلقائي. لا تُشارك التوكن مع أي شخص.</p><form id="connect" class="form-grid"><label class="full">توكن Telegram<input name="token" type="password" required autocomplete="off" placeholder="123456789:AA…" dir="ltr"></label><div class="full actions"><button class="primary" type="submit">${boot.connected ? "تحديث الربط" : "ربط وتشغيل البوت"} ←</button><span class="hint">التوكن مشفّر ولا يُعرض بعد الحفظ</span></div></form><p class="hint">${esc(boot.runtime.error || "يعتمد التشغيل على وصول الخادم إلى api.telegram.org. شغّل نسخة واحدة فقط.")}</p></div></div><form id="settings-form"><div class="settings-grid">${[
      [
        "الإعدادات العامة",
        [
          "brand",
          "owner_telegram_id",
          "session_minutes",
          "web_url",
          "language",
        ],
      ],
      [
        "الصيانة والتحكم",
        ["maintenance", "maintenance_staff", "notifications_enabled"],
      ],
      [
        "الشحن والمدفوعات",
        [
          "manual_enabled",
          "stars_enabled",
          "topup_min",
          "topup_max",
          "stars_rate",
        ],
      ],
      ["التحويل اليدوي", ["transfer_instructions"]],
      [
        "الطلبات والدعم",
        [
          "order_min",
          "order_max",
          "support_enabled",
          "customer_cancel_pending",
        ],
      ],
    ]
      .map(
        ([title, keys]) =>
          `<div class="card"><div class="card-head"><h3>${title}</h3></div><div class="card-body form-grid">${keys
            .map((k) => {
              if (k === "owner_telegram_id" && boot.actor.role !== "owner")
                return "";
              if (k === "maintenance")
                return `<label class="full">وضع الصيانة<select name="maintenance">${[
                  ["off", "متوقف — النظام يعمل"],
                  ["orders", "إيقاف الطلبات"],
                  ["topups", "إيقاف الشحن"],
                  ["all", "إيقاف خدمات الزبائن"],
                ]
                  .map(
                    ([v, l]) =>
                      `<option value="${v}" ${s[k] === v ? "selected" : ""}>${l}</option>`,
                  )
                  .join("")}</select></label>`;
              return inputField(
                k,
                typeof s[k] === "boolean"
                  ? "bool"
                  : monetary.includes(k)
                    ? "money"
                    : typeof s[k] === "number"
                      ? "int"
                      : "text",
                s[k],
                k === "transfer_instructions",
              );
            })
            .join("")}</div></div>`,
      )
      .join(
        "",
      )}</div><div class="form-actions"><button class="primary" type="submit">حفظ الإعدادات وتطبيقها ←</button></div></form>`;
}
async function previewView() {
  const m = await api("data/menus?page=1&q=");
  for (let p = 2; p <= m.pages; p++) {
    const next = await api("data/menus?page=" + p);
    m.items.push(...next.items);
  }
  if (current !== "preview") return;
  m.items.sort((a, b) => (a.key === "home" ? -1 : b.key === "home" ? 1 : 0));
  $("#heading-actions").innerHTML = can("menus")
    ? btn("إدارة القوائم", "go-menus")
    : "";
  $("#view").innerHTML =
    `<div class="grid-two"><div class="card"><div class="card-head"><h3>معاينة المحتوى</h3></div><div class="card-body"><label>اختر القائمة<select id="preview-menu">${m.items.map((x) => `<option value="${x.id}">${esc(x.name)} (${esc(x.key)})</option>`).join("")}</select></label><p class="hint">هذه معاينة مرئية للمحتوى المحفوظ وليست محاكاة لعمليات الدفع. اختبر التدفقات الحقيقية من البوت بعد الربط. المتغيرات تستبدل بقيم الزبون أثناء الاستخدام.</p><div class="notice">التغييرات تظهر عند الرسالة أو التفاعل التالي. الرسائل القديمة المرسلة في محادثات الزبائن لا تُعدّل تلقائيًا.</div></div></div><div id="phone-area"></div></div>`;
  window.previewMenus = m.items;
  await drawPreview();
}
async function drawPreview() {
  const id = $("#preview-menu").value,
    m = window.previewMenus.find((x) => String(x.id) === id);
  if (!m) return;
  let all = [],
    p = 1;
  while (true) {
    const r = await api("data/buttons?menu_id=" + id + "&page=" + p);
    all.push(...r.items);
    if (p >= r.pages) break;
    p++;
  }
  all = all
    .filter((b) => b.enabled)
    .sort((a, b) => a.row_num - b.row_num || a.col_num - b.col_num);
  const rows = {};
  all.forEach((b) => (rows[b.row_num] ??= []).push(b));
  $("#phone-area").innerHTML =
    `<div class="phone"><div class="phone-top">♪ ${esc(boot.settings.brand || "TikTok Services")}<small class="muted"> • bot</small></div><div class="phone-content"><div class="bubble">${esc(m.text)}</div><div class="phone-buttons">${Object.values(
      rows,
    )
      .map(
        (r) =>
          `<div class="phone-row">${r.map((b) => `<button title="${esc(b.action + ": " + b.target)}" data-action="preview-button" data-button-id="${b.id}">${esc(b.label)}</button>`).join("")}</div>`,
      )
      .join("")}</div></div></div>`;
  window.previewButtons = all;
}
async function related(table, key, id) {
  const r = await api(`data/${table}?${key}=${encodeURIComponent(id)}`);
  modal(
    labels[table],
    `<div class="hint">أحدث ${r.items.length} من ${r.total} سجل</div>${
      r.items
        .map(
          (x) =>
            `<div class="message">${Object.entries(x)
              .filter(([k]) => k !== "payload")
              .map(([k, v]) => `<small>${fields[k] || k}</small>${fmt(k, v)}`)
              .join("<br>")}</div>`,
        )
        .join("") || '<div class="empty">لا بيانات</div>'
    }`,
  );
}
async function perform(action, d) {
  await api("action/" + action, d);
  toast("تم تنفيذ العملية وحفظ السجل بنجاح");
  $("#modal").close();
  await listView();
}
document.addEventListener("click", async (e) => {
  const nav = e.target.closest("[data-nav]");
  if (nav) {
    try {
      await navigate(nav.dataset.nav);
    } catch (e) {
      toast(e.message);
    }
    return;
  }
  const el = e.target.closest("[data-action]");
  if (!el) return;
  const a = el.dataset.action;
  try {
    if (a === "profile") {
      modal(
        "أمان حسابك",
        `<form id="password-form"><label>كلمة المرور الحالية<input type="password" name="current" required autocomplete="current-password"></label><label>كلمة المرور الجديدة<input type="password" name="new" required minlength="12" autocomplete="new-password"></label><div class="form-actions"><button class="primary" type="submit">تغيير كلمة المرور</button></div></form>`,
      );
      return;
    }
    if (a === "broadcast-report")
      return await related("deliveries", "broadcast_id", activeRecord.id);
    if (a.startsWith("go-")) return await navigate(a.slice(3));
    if (a === "close") return $("#modal").close();
    if (a === "expense-reverse") return expenseEditor(activeRecord);
    if (a === "simulate-workflow")
      return await simulateBot("workflow:" + activeRecord.id);
    if (a === "simulate-menu")
      return await simulateBot("openmenu:" + activeRecord.key);
    if (a === "clone-menu") {
      const key = prompt("المعرّف الجديد للقائمة (حروف إنجليزية وأرقام)");
      if (!key) return;
      await api("studio/clone-menu", { id: activeRecord.id, key });
      $("#modal").close();
      boot = await api("bootstrap");
      await listView();
      toast("تم نسخ القائمة وأزرارها");
      return;
    }
    if (a === "move-button") {
      await api("studio/move-button", {
        id: activeRecord.id,
        direction: el.dataset.direction,
      });
      $("#modal").close();
      await listView();
      return;
    }
    if (a === "create")
      return current === "workflows"
        ? workflowEditor()
        : current === "expenses"
          ? expenseEditor()
          : editor();
    if (a === "edit")
      return current === "workflows"
        ? workflowEditor(activeRecord)
        : editor(activeRecord);
    if (a === "detail") return await detail(Number(el.dataset.index));
    if (a === "prev" || a === "next") {
      page += a === "next" ? 1 : -1;
      return await listView();
    }
    if (a === "export") {
      const qs = new URLSearchParams({
        format: "csv",
        start: $("#start-date")?.value || "",
        end: $("#end-date")?.value ? $("#end-date").value : "9999",
      });
      return window.open("/api/stats?" + qs, "_blank", "noopener");
    }
    if (a === "stats-filter") {
      const s = await api(
        "stats?start=" +
          ($("#start-date").value || "") +
          "&end=" +
          ($("#end-date").value ? $("#end-date").value : "9999"),
      );
      return renderDashboard(s);
    }
    const r = activeRecord;
    if (a === "delete") {
      if (
        confirm(
          "تأكيد حذف / أرشفة هذا السجل؟ سيتم الاحتفاظ بالسجلات التاريخية.",
        )
      ) {
        await api(`delete/${tableName()}/${r.id}`, {});
        $("#modal").close();
        await listView();
        toast("تم الحذف / الأرشفة");
      }
      return;
    }
    if (a === "order-state") {
      if (
        confirm(
          "تأكيد تغيير حالة الطلب إلى " +
            names[el.dataset.state] +
            "؟" +
            (["cancelled", "refunded"].includes(el.dataset.state)
              ? " سيتم استرداد المبلغ مرة واحدة فقط."
              : ""),
        )
      )
        await perform("order", { id: r.id, status: el.dataset.state });
      return;
    }
    if (a === "order-note") {
      const note = prompt("الملاحظة الإدارية", r.note);
      if (note === null) return;
      const cost = prompt(
        "تكلفة التنفيذ الفعلية بالدولار",
        (r.cost / 100).toFixed(2),
      );
      if (cost !== null) await perform("order", { id: r.id, note, cost });
      return;
    }
    if (a === "topup-accept") {
      if (
        confirm(
          "قبول الإثبات وإضافة " +
            dollars(r.amount) +
            " إلى رصيد المستخدم " +
            r.user_id +
            "؟",
        )
      )
        await perform("topup", { id: r.id, accept: true });
      return;
    }
    if (a === "topup-reject") {
      const reason = prompt("سبب الرفض");
      if (reason && confirm("تأكيد رفض الشحن بسبب: " + reason))
        await perform("topup", { id: r.id, accept: false, reason });
      return;
    }
    if (a === "proof") {
      let proof;
      try {
        proof = JSON.parse(r.proof);
      } catch {
        proof = { type: "text", value: r.proof };
      }
      if (proof.type === "photo") {
        modal(
          "إثبات الشحن TOP-" + r.id,
          `<p class="hint">يُحمّل الإثبات عبر الخادم دون كشف التوكن. هذه المعاينة لا تعني قبول الدفع.</p><img class="proof-image" data-proof-image src="/api/topups/${r.id}/proof" alt="إثبات التحويل"><p id="proof-error" class="error"></p><a class="secondary" href="/api/topups/${r.id}/proof" target="_blank" rel="noopener">فتح الإثبات في صفحة مستقلة ↗</a>`,
        );
        $("[data-proof-image]").addEventListener("error", () => {
          $("#proof-error").textContent =
            "تعذر عرض الإثبات. تأكد من ربط البوت والاتصال بتيليجرام، أو افتح الرابط لقراءة سبب الخطأ.";
        });
      } else if (proof.type === "document")
        modal(
          "ملف إثبات الشحن",
          `<p class="notice">الملف مرفق من الزبون؛ لا تفتح مرفقات غير موثوقة. يتم التنزيل من الخادم دون كشف التوكن.</p><a class="primary" href="/api/topups/${r.id}/proof" target="_blank" rel="noopener">تنزيل إثبات التحويل ↓</a>`,
        );
      else {
        const result = await api("topups/" + r.id + "/proof");
        modal(
          "إثبات التحويل",
          `<div class="message">${esc(result.text || "لا يوجد إثبات")}</div>`,
        );
      }
      return;
    }
    if (a === "user-status") {
      if (confirm("تأكيد تغيير حالة هذا المستخدم؟"))
        await perform("user", {
          id: r.id,
          status: r.status === "blocked" ? "active" : "blocked",
        });
      return;
    }
    if (a === "user-note") {
      const note = prompt("ملاحظة إدارية", r.note);
      if (note !== null) await perform("user", { id: r.id, note });
      return;
    }
    if (a === "user-balance") {
      $("#modal").close();
      await navigate("balances");
      return balanceView(r.id);
    }
    if (a === "user-orders" || a === "user-ledger")
      return await related(
        a === "user-orders" ? "orders" : "ledger",
        "user_id",
        r.id,
      );
    if (a === "related-audit") return await related("audit", "entity", r.id);
    if (a === "ticket-reply") {
      modal(
        "الرد على التذكرة SUP-" + r.id,
        `<form id="reply-form"><label>نص الرد<textarea name="body" required></textarea></label><div class="form-actions"><button class="primary">إرسال الرد</button></div></form>`,
      );
      return;
    }
    if (a === "ticket-state") {
      if (confirm("تأكيد تغيير حالة التذكرة؟"))
        await perform("ticket", { id: r.id, status: el.dataset.state });
      return;
    }
    if (a === "broadcast-state") {
      if (
        confirm(
          "تأكيد " +
            (el.dataset.state === "running"
              ? "بدء الإرسال إلى الفئة المحددة"
              : "تغيير حالة الإذاعة") +
            "؟",
        )
      )
        await perform("broadcast", { id: r.id, status: el.dataset.state });
      return;
    }
    if (a === "notification-retry")
      return await perform("retry_notification", { id: r.id });
    if (a === "preview-button") {
      const b = window.previewButtons.find(
        (b) => b.id === Number(el.dataset.buttonId),
      );
      if (b.action === "menu") {
        const target = window.previewMenus.find((m) => m.key === b.target);
        if (target) {
          $("#preview-menu").value = target.id;
          await drawPreview();
          return;
        }
      }
      toast("الإجراء: " + (names[b.action] || b.action) + " — " + b.target);
      return;
    }
  } catch (e) {
    toast(e.message);
  }
});
document.addEventListener("submit", async (e) => {
  e.preventDefault();
  const form = e.target,
    fd = new FormData(form),
    d = Object.fromEntries(fd);
  const submit = form.querySelector("[type=submit],button:not([type])");
  if (submit) submit.disabled = true;
  try {
    if (form.id === "workflow-editor") {
      await saveFlowForm(form);
    } else if (form.id === "simulation-input") {
      simulationInputs.push(d.value);
      try {
        await simulateBot(simulationRoute, false);
      } catch (e) {
        simulationInputs.pop();
        throw e;
      }
    } else if (form.id === "password-form") {
      await api("password", d);
      $("#modal").close();
      toast("تم تغيير كلمة المرور");
    } else if (form.id === "login") {
      const r = await api("auth/" + (setup ? "setup" : "login"), d);
      csrf = r.csrf;
      await start();
    } else if (form.id === "search") {
      query = d.q;
      filter = d.status || "";
      expenseStart = d.start || "";
      expenseEnd = d.end || "";
      page = 1;
      await listView();
    } else if (form.id === "expense-form") {
      const original = form.dataset.reverse;
      const path = original ? "expenses/" + original + "/reverse" : "expenses";
      if (
        confirm(
          original
            ? "تأكيد عكس الحركة بإضافة قيد معاكس دون حذف الأصل؟"
            : "تأكيد حفظ القيد المالي بالتاريخ المحدد؟",
        )
      ) {
        await api(path, { ...d, key: form.dataset.operationKey });
        $("#modal").close();
        toast("تم حفظ القيد المالي دون تعديل الرصيد أو السجلات السابقة");
        await listView();
      }
    } else if (form.id === "editor") {
      if (form.dataset.uploading === "true")
        throw Error("انتظر اكتمال رفع الملف أولًا.");
      const t = form.dataset.table,
        schema =
          t === "staff"
            ? {
                username: "text",
                password: "text",
                telegram_id: "int",
                enabled: "bool",
              }
            : boot.schemas[t];
      for (const [k, typ] of Object.entries(schema)) {
        if (typ === "bool") d[k] = fd.has(k);
        if (typ === "int")
          d[k] = d[k] === "" && k === "telegram_id" ? "" : Number(d[k]);
      }
      if (activeRecord.id) d.id = activeRecord.id;
      if (t === "staff") {
        d.permissions = fd.getAll("perm");
        delete d.perm;
      }
      if (confirm("حفظ التغييرات وتطبيقها على النظام والبوت؟")) {
        await api("data/" + t, d);
        boot = await api("bootstrap");
        $("#modal").close();
        toast("تم الحفظ. يُستخدم التعديل في التفاعل التالي مع البوت.");
        await listView();
      }
    } else if (form.id === "balance-form") {
      const u = (
        await api("data/users?q=" + encodeURIComponent(d.user_id))
      ).items.find((u) => String(u.id) === d.user_id);
      if (!u) throw Error("المستخدم غير موجود. عليه بدء البوت أولًا.");
      const delta = Math.round(Number(d.amount) * 100);
      if (
        confirm(
          `مراجعة الحركة\nالمستخدم: ${u.id}\nالرصيد الحالي: ${dollars(u.balance)}\nالتغيير: ${dollars(delta)}\nالرصيد بعد: ${dollars(u.balance + delta)}\nالسبب: ${d.reason}\nهل تؤكد التنفيذ؟`,
        )
      ) {
        await api("action/balance", {
          ...d,
          user_id: Number(d.user_id),
          key: (form.dataset.operationKey ||= crypto.randomUUID()),
        });
        form.reset();
        delete form.dataset.operationKey;
        toast("تم تحديث الرصيد وإرسال الإشعار");
      }
    } else if (form.id === "settings-form") {
      const monetary = [
        "topup_min",
        "topup_max",
        "order_min",
        "order_max",
        "expenses",
        "fees",
      ];
      for (const k of Object.keys(d)) {
        if (monetary.includes(k)) d[k] = Math.round(Number(d[k]) * 100);
        else if (typeof boot.settings[k] === "number") d[k] = Number(d[k]);
      }
      for (const k of [
        "maintenance_staff",
        "manual_enabled",
        "stars_enabled",
        "notifications_enabled",
        "support_enabled",
        "customer_cancel_pending",
      ])
        d[k] = fd.has(k);
      if (confirm("حفظ وتطبيق إعدادات النظام؟")) {
        await api("settings", d);
        boot = await api("bootstrap");
        toast("تم تطبيق الإعدادات");
        settings();
      }
    } else if (form.id === "connect") {
      await api("connect", d);
      form.reset();
      boot = await api("bootstrap");
      connection();
      settings();
      toast("تم التحقق من البوت وحفظ الربط");
    } else if (form.id === "reply-form") {
      await perform("reply", { id: activeRecord.id, body: d.body });
    }
  } catch (e) {
    if (form.id === "login") $("#auth-error").textContent = e.message;
    else toast(e.message);
  } finally {
    if (submit) submit.disabled = false;
  }
});
$("#close-modal").onclick = () => $("#modal").close();
$("#mobile-menu").onclick = () => $("#sidebar").classList.toggle("open");
$("#logout").onclick = async () => {
  await api("auth/logout", {});
  boot = null;
  await start();
};
$("#refresh").onclick = async () => {
  try {
    boot = await api("bootstrap");
    connection();
    await navigate(current);
    toast("تم التحديث");
  } catch (e) {
    toast(e.message);
  }
};
document.addEventListener("change", (e) => {
  if (e.target.id === "preview-menu")
    drawPreview().catch((e) => toast(e.message));
});
setInterval(async () => {
  if (!boot || $("#modal").open) return;
  try {
    const b = await api("bootstrap");
    boot = b;
    connection();
    if (!document.querySelector("input:focus,textarea:focus,select:focus")) {
      if (current === "stats") {
        const s = await api(
          "stats?start=" +
            ($("#start-date")?.value || "") +
            "&end=" +
            ($("#end-date")?.value ? $("#end-date").value : "9999"),
        );
        renderDashboard(s);
      } else if (!["settings", "balances", "preview"].includes(current))
        await listView();
    }
  } catch {}
}, 10000);
start();

function uploadPreview(ref, kind) {
  const id = ref.match(/^upload:(\d+)$/)?.[1];
  if (!id) return "";
  return kind === "photo"
    ? `<img class="upload-preview" src="/api/media/${id}" alt="معاينة الصورة المرفوعة">`
    : `<a class="secondary" href="/api/media/${id}" target="_blank" rel="noopener">تنزيل الملف المرفوع ↗</a>`;
}
function expenseEditor(original = null) {
  const today = new Date().toISOString().slice(0, 10);
  const body = `<form id="expense-form" data-operation-key="${crypto.randomUUID()}" ${original ? `data-reverse="${original.id}"` : ""}><div class="notice">${original ? "سيبقى القيد الأصلي محفوظًا. يُضاف قيد سالب في تاريخ العكس المختار مرة واحدة فقط." : "القيد لا يخصم من محفظة أي زبون. يُحتسب في الأرباح ضمن تاريخ الاستحقاق، ولا يمكن تعديله أو حذفه بعد التأكيد."}</div><div class="form-grid">${original ? `<div class="detail-item full">عكس ${esc(names[original.kind])} #${original.id} بقيمة ${dollars(original.amount)}</div>` : `<label>النوع<select name="kind"><option value="expense">مصروف</option><option value="fee">عمولة</option></select></label><label>المبلغ بالدولار<input name="amount" type="number" min="0.01" step="0.01" required></label>`}<label>تاريخ ${original ? "العكس" : "الاستحقاق"} (UTC)<input name="occurred_on" type="date" value="${today}" required></label><label class="full">سبب ${original ? "العكس" : "المصروف"}<textarea name="reason" maxlength="2000" required></textarea></label></div><div class="form-actions">${btn("إلغاء", "close")}<button class="primary" type="submit">مراجعة وتأكيد</button></div></form>`;
  modal(original ? "عكس حركة مالية" : "إضافة مصروف / عمولة", body);
}
document.addEventListener("change", async (e) => {
  const input = e.target.closest("[data-upload-field]");
  if (!input || !input.files?.length) return;
  const form = input.closest("form"),
    status = form.querySelector("#upload-status"),
    submit = form.querySelector("[type=submit]");
  const file = input.files[0];
  if (file.size > 20 * 1024 * 1024) {
    toast("الملف يتجاوز 20 ميجابايت");
    input.value = "";
    return;
  }
  const data = new FormData();
  data.append("file", file);
  data.append("purpose", input.dataset.purpose);
  form.dataset.uploading = "true";
  input.disabled = true;
  if (submit) submit.disabled = true;
  status.textContent = "جارٍ التحقق من الملف ورفعه…";
  try {
    const response = await fetch("/api/media", {
      method: "POST",
      headers: { "X-CSRF-Token": csrf },
      body: data,
    });
    const result = await response.json();
    if (!response.ok) throw Error(result.error || "فشل رفع الملف");
    const target = form.querySelector(`[name="${input.dataset.uploadField}"]`);
    target.value = result.ref;
    if (input.dataset.purpose === "broadcasts")
      form.querySelector("[name=kind]").value = result.kind;
    status.innerHTML =
      `<p class="hint">تم حفظ ${esc(result.name)} • ${(result.size / 1024).toFixed(1)} KB</p>` +
      uploadPreview(result.ref, result.kind);
    toast("تم رفع الملف. احفظ السجل لربطه بالخدمة أو الإذاعة.");
  } catch (error) {
    status.textContent = error.message;
    toast(error.message);
  } finally {
    delete form.dataset.uploading;
    input.disabled = false;
    if (submit) submit.disabled = false;
    input.value = "";
  }
});
