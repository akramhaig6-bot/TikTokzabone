const { JSDOM, VirtualConsole, CookieJar } = require("jsdom");
const base = process.env.TEST_BASE_URL || "http://127.0.0.1:8001";
const jar = new CookieJar();
const errors = [];
const vc = new VirtualConsole();
vc.on("jsdomError", (e) => errors.push(e.message));
vc.on("error", (e) => errors.push(e));
const wait = async (fn) => {
  for (let i = 0; i < 100; i++) {
    if (fn()) return;
    await new Promise((r) => setTimeout(r, 80));
  }
  throw Error("Timed out " + fn.toString());
};
(async () => {
  const state = await (await fetch(base + "/api/session")).json();
  if (!state.setup)
    throw Error(
      "UI smoke test requires a NEW disposable DATA_DIR, never run against a real installation",
    );
  const dom = await JSDOM.fromURL(base, {
    resources: "usable",
    runScripts: "dangerously",
    pretendToBeVisual: true,
    cookieJar: jar,
    virtualConsole: vc,
    beforeParse(w) {
      w.fetch = async (path, opts = {}) => {
        if (opts.body instanceof w.FormData) {
          const body = new FormData();
          for (const [key, value] of opts.body) {
            if (typeof value === "string") body.append(key, value);
            else {
              const bytes = await new Promise((resolve, reject) => {
                const reader = new w.FileReader();
                reader.onload = () => resolve(reader.result);
                reader.onerror = reject;
                reader.readAsArrayBuffer(value);
              });
              body.append(
                key,
                new Blob([bytes], { type: value.type }),
                value.name,
              );
            }
          }
          opts = { ...opts, body };
        }
        const res = await fetch(new URL(path, base), {
          ...opts,
          headers: { ...opts.headers, Cookie: jar.getCookieStringSync(base) },
        });
        const cookie = res.headers.get("set-cookie");
        if (cookie) jar.setCookieSync(cookie, base);
        return res;
      };
      w.confirm = () => true;
      w.HTMLDialogElement.prototype.showModal = function () {
        this.open = true;
      };
      w.HTMLDialogElement.prototype.close = function () {
        this.open = false;
      };
    },
  });
  const w = dom.window,
    d = w.document;
  const click = (selector) => {
    const e = d.querySelector(selector);
    if (!e) throw Error("Missing " + selector);
    e.click();
  };
  await wait(() => !d.querySelector("#auth").classList.contains("hidden"));
  d.querySelector("#login [name=username]").value = "owner";
  d.querySelector("#login [name=password]").value = "browser-password-123";
  d.querySelector("#login").dispatchEvent(
    new w.Event("submit", { bubbles: true, cancelable: true }),
  );
  await wait(() => d.querySelector(".stats-grid"));
  for (const route of [
    "orders",
    "topups",
    "users",
    "balances",
    "services",
    "inventory",
    "support",
    "broadcasts",
    "menus",
    "staff",
    "ledger",
    "expenses",
    "audit",
    "settings",
  ]) {
    click("#nav [data-nav=" + route + "]");
    await new Promise((r) => setTimeout(r, 120));
    if (!d.querySelector("#view").textContent.trim())
      throw Error("Empty " + route);
  }
  click("#nav [data-nav=menus]");
  await wait(() => d.querySelector("#heading-actions [data-action=go-buttons]"));
  if (!d.querySelector("#view").textContent.includes("محرر البوت المربوط"))
    throw Error("Missing connected-bot editor section");
  click("#heading-actions [data-action=go-buttons]");
  await wait(
    () => d.querySelector("#page-heading h1").textContent === "الأزرار والإجراءات",
  );
  await wait(() =>
    [...d.querySelectorAll("#view thead th")].some(
      (th) => th.textContent === "لون الزر في Telegram",
    ),
  );
  click("#view [data-action=detail]");
  await wait(() => d.querySelector("#modal [data-action=edit]"));
  click("#modal [data-action=edit]");
  await wait(() => d.querySelector('#editor [name="style"]'));
  if (!d.querySelector("#modal-title").textContent.startsWith("تعديل السجل #"))
    throw Error("Button editor did not open an existing button record");
  const buttonStyle = d.querySelector('#editor [name="style"]');
  buttonStyle.value = "primary";
  d.querySelector("#editor").dispatchEvent(
    new w.Event("submit", { bubbles: true, cancelable: true }),
  );
  await wait(() => d.querySelector("#toast").textContent);
  if (!d.querySelector("#toast").textContent.includes("تم الحفظ"))
    throw Error("Button style save failed: " + d.querySelector("#toast").textContent);
  click("#heading-actions [data-action=create]");
  await wait(() => d.querySelector('#editor [name="style"]'));
  d.querySelector('#editor [name="label"]').value = "زر اختبار لون جديد";
  d.querySelector('#editor [name="action"]').value = "callback";
  d.querySelector('#editor [name="target"]').value = "home";
  d.querySelector('#editor [name="style"]').value = "danger";
  const beforeNewButtonToast = d.querySelector("#toast").textContent;
  d.querySelector("#editor").dispatchEvent(
    new w.Event("submit", { bubbles: true, cancelable: true }),
  );
  await wait(
    () =>
      !d.querySelector("#modal").open ||
      d.querySelector("#toast").textContent !== beforeNewButtonToast,
  );
  if (
    d.querySelector("#modal").open ||
    !d.querySelector("#toast").textContent.includes("تم الحفظ")
  )
    throw Error("New button style save failed: " + d.querySelector("#toast").textContent);

  click("#nav [data-nav=workflows]");
  await wait(() => d.querySelector("[data-action=create]"));
  click("[data-action=create]");
  await wait(() => d.querySelector("#workflow-editor [data-step-field=validator]"));
  const validator = d.querySelector(
    "#workflow-editor [data-step-field=validator]",
  );
  validator.value = "choice";
  validator.dispatchEvent(new w.Event("change", { bubbles: true }));
  const choices = d.querySelector(
    '#workflow-editor [data-step-field="choices"]',
  );
  choices.value = "موافق|غير موافق";
  choices.dispatchEvent(new w.Event("change", { bubbles: true }));
  await wait(
    () =>
      d.querySelectorAll("#workflow-editor [data-choice-style]").length === 2,
  );
  d.querySelectorAll("#workflow-editor [data-choice-style]")[0].value =
    "success";
  d.querySelectorAll("#workflow-editor [data-choice-style]")[1].value =
    "danger";
  d.querySelector('#workflow-editor [name="name"]').value =
    "تدفق اختبار الألوان";
  const previousToast = d.querySelector("#toast").textContent;
  d.querySelector("#workflow-editor").dispatchEvent(
    new w.Event("submit", { bubbles: true, cancelable: true }),
  );
  await wait(() => d.querySelector("#toast").textContent !== previousToast);
  if (!d.querySelector("#toast").textContent.includes("تم حفظ التدفق"))
    throw Error("Flow button style save failed: " + d.querySelector("#toast").textContent);

  click("#nav [data-nav=settings]");
  await wait(() => d.querySelector("#settings-form"));
  d.querySelector("#settings-form").dispatchEvent(
    new w.Event("submit", { bubbles: true, cancelable: true }),
  );
  await wait(
    () => d.querySelector("#toast").textContent === "تم تطبيق الإعدادات",
  );
  click("#nav [data-nav=services]");
  await wait(() => d.querySelector("[data-action=create]"));
  click("[data-action=create]");
  d.querySelector("#editor [name=name]").value = "خدمة اختبار DOM";
  d.querySelector("#editor [name=price]").value = "1.50";
  const chooser = d.querySelector("[data-upload-field=image]");
  const png = Buffer.from(
    "iVBORw0KGgoAAAANSUhEUgAAAAIAAAACCAIAAAD91JpzAAAAFklEQVR4nGP8z8DAwMDAxMDAwMDAAAANHQEDasKb6QAAAABJRU5ErkJggg==",
    "base64",
  );
  Object.defineProperty(chooser, "files", {
    value: [new w.File([png], "tiny.png", { type: "image/png" })],
  });
  chooser.dispatchEvent(new w.Event("change", { bubbles: true }));
  await wait(() =>
    d.querySelector("#editor [name=image]").value.startsWith("upload:"),
  );
  d.querySelector("#editor").dispatchEvent(
    new w.Event("submit", { bubbles: true, cancelable: true }),
  );
  await wait(() =>
    d.querySelector("#view").textContent.includes("خدمة اختبار DOM"),
  );
  click("#nav [data-nav=expenses]");
  await wait(() =>
    d.querySelector("#heading-actions").textContent.includes("مصروف"),
  );
  click("[data-action=create]");
  d.querySelector("#expense-form [name=amount]").value = "3.50";
  d.querySelector("#expense-form [name=reason]").value = "مصروف اختبار واجهة";
  d.querySelector("#expense-form").dispatchEvent(
    new w.Event("submit", { bubbles: true, cancelable: true }),
  );
  await wait(() =>
    d.querySelector("#view").textContent.includes("مصروف اختبار واجهة"),
  );
  click("#view [data-action=detail]");
  await wait(() => d.querySelector("[data-action=expense-reverse]"));
  click("[data-action=expense-reverse]");
  d.querySelector("#expense-form [name=reason]").value = "عكس مصروف الاختبار";
  d.querySelector("#expense-form").dispatchEvent(
    new w.Event("submit", { bubbles: true, cancelable: true }),
  );
  await wait(() =>
    d.querySelector("#view").textContent.includes("عكس مصروف الاختبار"),
  );
  click("#nav [data-nav=menus]");
  await wait(() => d.querySelector("[data-action=go-preview]"));
  click("[data-action=go-preview]");
  await wait(() => d.querySelector(".phone"));
  console.log(
    JSON.stringify(
      {
        passed: true,
        routes: 14,
        serviceCreated: true,
        mediaUploaded: true,
        expenseCreated: true,
        expenseReversed: true,
        preview: true,
        errors,
      },
      null,
      2,
    ),
  );
  dom.window.close();
  if (errors.length) process.exit(1);
})();
