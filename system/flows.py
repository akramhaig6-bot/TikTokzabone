"""No-code customer flows. Only registered bot routes, never arbitrary code or HTTP."""

import json
import re
from decimal import Decimal, InvalidOperation
from .store import *

KINDS = ("message", "input", "menu", "action", "condition", "end")
VALIDATORS = ("text", "integer", "decimal", "tiktok", "choice")


def validate_steps(steps):
    if not isinstance(steps, list) or not 1 <= len(steps) <= 100:
        raise ValueError("التدفق يتضمن من 1 إلى 100 خطوة")
    for step in steps:
        if not isinstance(step, dict) or step.get("type") not in KINDS:
            raise ValueError("نوع خطوة غير صالح")
        if set(step) - {
            "type",
            "text",
            "target",
            "variable",
            "validator",
            "min",
            "max",
            "choices",
            "choice_styles",
            "equals",
            "yes",
            "no",
        }:
            raise ValueError("خاصية خطوة غير معروفة")
        for key in ("text", "target", "variable", "validator", "choices", "equals"):
            if key in step and (
                not isinstance(step[key], str) or len(step[key]) > 4000
            ):
                raise ValueError("محتوى خطوة غير صالح")
        if "choice_styles" in step:
            styles = step["choice_styles"]
            choices = step.get("choices", "").split("|")
            if (
                step["type"] != "input"
                or step.get("validator") != "choice"
                or not isinstance(styles, list)
                or len(styles) > len(choices)
                or any(
                    style not in ("default", "primary", "success", "danger")
                    for style in styles
                )
            ):
                raise ValueError("ألوان أزرار التدفق غير صالحة")
        if step["type"] == "input":
            if not re.fullmatch(
                r"[A-Za-z][A-Za-z0-9_]{0,39}", step.get("variable", "")
            ):
                raise ValueError("اسم المتغير حروف إنجليزية وأرقام ويبدأ بحرف")
            if step.get("validator", "text") not in VALIDATORS:
                raise ValueError("نوع التحقق غير صالح")
            for k in ("min", "max"):
                if step.get(k, "") != "":
                    try:
                        if not Decimal(str(step[k])).is_finite():
                            raise ValueError()
                    except (ValueError, InvalidOperation):
                        raise ValueError("حد إدخال غير صالح")
        if step["type"] == "condition":
            for k in ("yes", "no"):
                if not isinstance(step.get(k), int) or not 0 <= step[k] < len(steps):
                    raise ValueError("وجهة الشرط خارج التدفق")
    return steps


def fill(text, variables):
    return re.sub(
        r"\{([A-Za-z][A-Za-z0-9_]*)\}",
        lambda m: str(variables.get(m[1], m[0])),
        str(text),
    )


def start(c, uid, fid):
    from .telegram import state

    flow = one(c, "workflows", fid)
    if not flow["enabled"]:
        raise ValueError("هذا التدفق غير متاح حاليًا")
    run = c.execute(
        "INSERT INTO flow_runs(user_id,workflow_id,step,variables,status,updated,revision) VALUES(?,?,0,?,'active',?,?)",
        (uid, fid, json.dumps({"user_id": uid}), now(), flow["revision"]),
    ).lastrowid
    state(c, uid, "workflow", {"run_id": run})
    advance(c, uid, run)


def advance(c, uid, rid, value=None):
    from .telegram import state, action, say, keyboard, button_style

    run = one(c, "flow_runs", rid)
    if run["user_id"] != uid or run["status"] != "active":
        raise ValueError("هذا التدفق منتهٍ أو لا يخصك")
    flow = one(c, "workflows", run["workflow_id"])
    if not flow["enabled"] or flow["revision"] != run["revision"]:
        # Runs snapshot their revision; a changed definition must be restarted, not reinterpreted.
        raise ValueError("تغير التدفق من الإدارة. ابدأه من جديد.")
    steps = json.loads(flow["steps"])
    variables = json.loads(run["variables"])
    index = run["step"]
    if value is not None:
        step = steps[index]
        if step["type"] != "input":
            raise ValueError("التدفق لا ينتظر إدخالًا")
        validator = step.get("validator", "text")
        value = value.strip()
        if not value:
            raise ValueError("الإدخال مطلوب")
        if validator in ("integer", "decimal"):
            try:
                number = Decimal(value)
                if not number.is_finite() or (
                    validator == "integer" and number != number.to_integral_value()
                ):
                    raise ValueError()
                if step.get("min", "") != "" and number < Decimal(str(step["min"])):
                    raise ValueError()
                if step.get("max", "") != "" and number > Decimal(str(step["max"])):
                    raise ValueError()
            except (ValueError, InvalidOperation):
                raise ValueError("العدد غير صالح أو خارج الحدود المحددة")
        if validator == "tiktok":
            from .domain import target_valid

            if not target_valid(value):
                raise ValueError("رابط تيك توك غير صالح")
        if validator == "choice" and value not in step.get("choices", "").split("|"):
            raise ValueError("اختر أحد الخيارات المعروضة")
        variables[step["variable"]] = value
        index += 1
    for _ in range(100):
        if index >= len(steps):
            break
        step = steps[index]
        kind = step["type"]
        if kind == "end":
            break
        if kind == "input":
            c.execute(
                "UPDATE flow_runs SET step=?,variables=?,updated=? WHERE id=?",
                (index, json.dumps(variables), now(), rid),
            )
            state(c, uid, "workflow", {"run_id": rid})
            buttons = []
            if step.get("validator") == "choice":
                styles = step.get("choice_styles", [])
                buttons = [
                    [
                        button_style(
                            {
                                "text": choice,
                                "callback_data": f"flow_choice:{rid}:{i}",
                            },
                            styles[i] if i < len(styles) else "default",
                        )
                    ]
                    for i, choice in enumerate(step.get("choices", "").split("|"))
                ]
            buttons += [
                [
                    {"text": "❌ إلغاء التدفق", "callback_data": f"flow_cancel:{rid}"},
                    {"text": "🏠 الرئيسية", "callback_data": "home"},
                ]
            ]
            notify(
                c,
                uid,
                fill(step.get("text", "أرسل البيانات"), variables),
                extra={"reply_markup": {"inline_keyboard": buttons}},
            )
            return
        if kind == "message":
            notify(c, uid, fill(step.get("text", ""), variables))
        elif kind == "menu":
            key = fill(step.get("target", ""), variables)
            menu = c.execute("SELECT * FROM menus WHERE key=?", (key,)).fetchone()
            if not menu:
                raise ValueError("القائمة المرتبطة بالتدفق غير موجودة")
            notify(
                c,
                uid,
                fill(menu["text"], variables),
                extra={
                    "reply_markup": keyboard(c, uid, key, values=variables)
                    or {"remove_keyboard": True}
                },
            )
        elif kind == "action":
            route = fill(step.get("target", ""), variables)
            # Flow entrypoints cannot recursively invoke other flows in a single update.
            if route.split(":")[0] in (
                "workflow",
                "flow_choice",
                "flow_cancel",
                "button",
            ):
                raise ValueError("إجراء يسبب استدعاء تدفق متكرر")
            action(c, uid, route)
            current = c.execute(
                "SELECT state,data FROM sessions WHERE user_id=?", (uid,)
            ).fetchone()
            if current and (
                current["state"] != "workflow"
                or json.loads(current["data"]).get("run_id") != rid
            ):
                c.execute(
                    "UPDATE flow_runs SET status='handed_off',updated=? WHERE id=?",
                    (now(), rid),
                )
                return
        elif kind == "condition":
            index = (
                step["yes"]
                if str(variables.get(step.get("variable", ""), ""))
                == step.get("equals", "")
                else step["no"]
            )
            continue
        index += 1
    else:
        raise ValueError("التدفق يحتوي حلقة دون إدخال؛ صحح فروع الشرط من الويب")
    c.execute(
        "UPDATE flow_runs SET status='completed',variables=?,updated=? WHERE id=?",
        (json.dumps(variables), now(), rid),
    )
    c.execute("DELETE FROM sessions WHERE user_id=? AND state='workflow'", (uid,))
    audit(c, uid, "workflow.completed", rid, {"workflow": flow["id"]})
