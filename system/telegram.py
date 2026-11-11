import hashlib, json, logging, secrets, threading, time, urllib.request, urllib.error
from .store import *
from .domain import *

runtime = {"status": "disconnected", "last_update": None, "error": ""}
log = logging.getLogger(__name__)


def call(token, method, data):
    from .media import multipart

    body, content_type = multipart(data)
    req = urllib.request.Request(
        "https://api.telegram.org/bot" + token + "/" + method,
        data=body,
        headers={"Content-Type": content_type},
    )
    try:
        with urllib.request.urlopen(req, timeout=40) as response:
            result = json.load(response)
    except urllib.error.HTTPError as e:
        if e.code == 401:
            raise RuntimeError("رفض Telegram التوكن (401). تحقق من توكن BotFather.") from None
        if e.code == 409:
            raise RuntimeError("تعارض Telegram (409): أوقف أي نسخة أو webhook آخر للبوت.") from None
        if e.code == 429:
            raise RuntimeError("Telegram يطلب الانتظار قبل إعادة المحاولة (429).") from None
        raise RuntimeError(f"رفض Telegram الطلب (HTTP {e.code}).") from None
    except (urllib.error.URLError, TimeoutError, OSError):
        raise RuntimeError("تعذر الوصول إلى api.telegram.org من الخادم.") from None
    except Exception:
        raise RuntimeError("تعذر قراءة رد Telegram.") from None
    if not isinstance(result, dict) or not result.get("ok"):
        code = result.get("error_code") if isinstance(result, dict) else None
        if code == 401:
            raise RuntimeError("رفض Telegram التوكن (401). تحقق من توكن BotFather.")
        if code == 409:
            raise RuntimeError("تعارض Telegram (409): أوقف أي نسخة أو webhook آخر للبوت.")
        if code == 429:
            raise RuntimeError("Telegram يطلب الانتظار قبل إعادة المحاولة (429).")
        raise RuntimeError(f"رفض Telegram الطلب{f' (رمز {code})' if code else ''}.")
    return result["result"]


def b(label, action):
    return {"text": label, "callback_data": action}

def button_style(button, style="default"):
    if style in ("primary", "success", "danger"):
        button["style"] = style
    return button


HOME = [[b("🏠 الرئيسية", "home")]]


def role(c, uid, permission=None):
    if uid == setting(c, "owner_telegram_id", 0) and uid:
        return True
    a = c.execute(
        "SELECT * FROM staff WHERE telegram_id=? AND enabled=1", (uid,)
    ).fetchone()
    return bool(
        a
        and (
            not permission
            or a["role"] == "owner"
            or permission in json.loads(a["permissions"])
        )
    )


def text(c, key, default, values=None):
    return render(c, key, default, values)


def keyboard(c, uid, key, defaults=None, values=None):
    from .flows import fill

    values = {"user_id": uid, **(values or {})}
    m = c.execute("SELECT * FROM menus WHERE key=?", (key,)).fetchone()
    if not m:
        mid = c.execute(
            "INSERT INTO menus(key,name,text) VALUES(?,?,?)", (key, key, "")
        ).lastrowid
        for ri, row in enumerate(defaults or []):
            for ci, but in enumerate(row):
                c.execute(
                    "INSERT INTO buttons(menu_id,label,action,target,row_num,col_num) VALUES(?,?,?,?,?,?)",
                    (
                        mid,
                        but["text"],
                        "callback",
                        but.get("callback_data", "home"),
                        ri,
                        ci,
                    ),
                )
        m = c.execute("SELECT * FROM menus WHERE id=?", (mid,)).fetchone()
    buttons = rows(
        c,
        "SELECT * FROM buttons WHERE menu_id=? AND enabled=1 ORDER BY row_num,col_num,id",
        (m["id"],),
    )
    grid = {}
    for btn in buttons:
        btn = dict(btn)
        btn["label"] = translate(c, "button:" + str(btn["id"]), btn["label"])
        btn["label"] = fill(btn["label"], values)
        if btn["permission"] and not role(c, uid, btn["permission"]):
            continue
        target = fill(btn["target"], values)
        if "{" in target and btn["action"] != "message":
            continue
        if btn["kind"] == "url" and m["kind"] != "reply":
            item = button_style({"text": btn["label"], "url": target}, btn["style"])
        elif btn["kind"] == "webapp":
            item = button_style(
                {"text": btn["label"], "web_app": {"url": target}}, btn["style"]
            )
        elif m["kind"] == "reply":
            item = button_style({"text": btn["label"]}, btn["style"])
        else:
            if values and any("{" + k + "}" in btn["target"] for k in values):
                code = secrets.token_urlsafe(12)
                c.execute(
                    "INSERT INTO button_context(code,user_id,button_id,data,expires) VALUES(?,?,?,?,?)",
                    (
                        code,
                        uid,
                        btn["id"],
                        json.dumps(values),
                        time.time() + setting(c, "session_minutes", 30) * 60,
                    ),
                )
                item = button_style(b(btn["label"], "context:" + code), btn["style"])
            else:
                item = button_style(
                    b(btn["label"], "button:" + str(btn["id"])), btn["style"]
                )
        grid.setdefault(btn["row_num"], []).append(item)
    if m["kind"] == "text":
        return None
    if m["kind"] == "reply":
        mapping = {}
        for btn in buttons:
            if not btn["permission"] or role(c, uid, btn["permission"]):
                mapping[
                    fill(translate(c, "button:" + str(btn["id"]), btn["label"]), values)
                ] = {"id": btn["id"], "values": values}
        c.execute(
            "INSERT INTO reply_context VALUES(?,?) ON CONFLICT(user_id) DO UPDATE SET buttons=excluded.buttons",
            (uid, json.dumps(mapping)),
        )
        return {"keyboard": list(grid.values()), "resize_keyboard": True}
    return {"inline_keyboard": list(grid.values())}


def say(c, uid, key, default="", values=None, buttons=None, layout=None):
    user = c.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
    values = {
        "user_id": uid,
        "username": user["username"] if user else "",
        "first_name": user["first_name"] if user else "",
        **(values or {}),
    }
    content = text(c, key, default, values)
    if buttons:
        buttons = [[dict(btn) for btn in row] for row in buttons]
        for row in buttons:
            for btn in row:
                label = btn["text"]
                # Entity list titles are derived from editable service/customer records.
                if " — " not in label and not label[:1].isdigit():
                    btn["text"] = text(
                        c,
                        "label_" + hashlib.sha256(label.encode()).hexdigest()[:12],
                        label,
                    )
    bound = c.execute("SELECT layout_key FROM menus WHERE key=?", (key,)).fetchone()
    if bound and bound[0]:
        layout = bound[0]
    markup = (
        keyboard(c, uid, layout, buttons, values)
        if layout
        else ({"inline_keyboard": buttons} if buttons else None)
    )
    if markup:
        notify(c, uid, content, extra={"reply_markup": markup})
    else:
        notify(c, uid, content)


def state(c, uid, name, data):
    if name.startswith("topup_") or name == "awaiting_payment":
        c.execute(
            "INSERT INTO topup_drafts VALUES(?,?,?,?) ON CONFLICT(user_id) DO UPDATE SET state=excluded.state,data=excluded.data,updated=excluded.updated",
            (uid, name, json.dumps(data), now()),
        )
    c.execute(
        "INSERT INTO sessions VALUES(?,?,?,?) ON CONFLICT(user_id) DO UPDATE SET state=excluded.state,data=excluded.data,updated=excluded.updated",
        (uid, name, json.dumps(data), time.time()),
    )


def getstate(c, uid):
    s = c.execute("SELECT * FROM sessions WHERE user_id=?", (uid,)).fetchone()
    if s and time.time() - s["updated"] > setting(c, "session_minutes", 30) * 60:
        c.execute("DELETE FROM sessions WHERE user_id=?", (uid,))
        return "expired", {}
    return (s["state"], json.loads(s["data"])) if s else ("", {})


def draft(c, uid):
    r = c.execute("SELECT data FROM drafts WHERE user_id=?", (uid,)).fetchone()
    return json.loads(r[0]) if r else {}


def savedraft(c, uid, d):
    c.execute(
        "INSERT INTO drafts VALUES(?,?) ON CONFLICT(user_id) DO UPDATE SET data=excluded.data",
        (uid, json.dumps(d)),
    )


def upsert(c, u):
    c.execute(
        "INSERT INTO users(id,username,first_name,created,last_active) VALUES(?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET username=excluded.username,first_name=excluded.first_name,last_active=excluded.last_active",
        (u["id"], u.get("username", ""), u.get("first_name", ""), now(), now()),
    )


def review(c, uid, d):
    if not all(k in d for k in ("service_id", "target", "quantity")):
        raise ValueError("أكمل الرابط والكمية أولًا.")
    s, qty, price = quote(c, d["service_id"], d["target"], d["quantity"])
    d.update(quantity=qty, price=price)
    savedraft(c, uid, d)
    state(c, uid, "order_confirm", d)
    u = one(c, "users", uid)
    say(
        c,
        uid,
        "order_review",
        "📋 مراجعة الطلب\n\n🛒 {service}\n🔗 {target}\n📦 الكمية: {quantity}\n💰 سعر كل 1000: ${unit_price}\n💰 السعر: ${price}\n💳 رصيدك: ${balance}\nالرصيد بعد الطلب: ${after}\n\nهل تريد تأكيد الطلب؟",
        {
            "service": s["name"],
            "target": d["target"],
            "quantity": qty,
            "unit_price": money(s["price"]),
            "price": money(price),
            "balance": money(u["balance"]),
            "after": money(u["balance"] - price),
        },
        [
            [b("✅ تأكيد الطلب", "order_confirm")],
            [b("✏️ تعديل الرابط", "edit_target"), b("✏️ تعديل الكمية", "edit_qty")],
            [b("💳 شحن الرصيد", "topup"), b("❌ إلغاء الطلب", "cancel_order")],
        ],
        "layout_order_review",
    )


def listing(c, uid, kind, page=0, filt=""):
    cfg = {
        "services": ("services", "enabled=1 AND deleted=0", (), "service:", "الخدمات"),
        "myorders": ("orders", "user_id=?", (uid,), "order:", "الطلبات"),
        "topups": ("topups", "user_id=?", (uid,), "topup:", "طلبات الشحن"),
        "tickets": ("tickets", "user_id=?", (uid,), "ticket:", "تذاكر الدعم"),
        "ledger": ("ledger", "user_id=?", (uid,), "ledger:", "سجل الرصيد"),
    }
    table, where, args, prefix, title = cfg[kind]
    if filt and table == "orders":
        where += " AND status=?"
        args += (filt,)
    order_by = "position,id" if table == "services" else "id DESC"
    rr = rows(
        c,
        f"SELECT * FROM {table} WHERE {where} ORDER BY {order_by} LIMIT 9 OFFSET ?",
        args + (page * 8,),
    )
    buttons = []
    for r in rr[:8]:
        if table == "services":
            label = render(
                c,
                "list_service_row",
                "{name} — ${price}/1000",
                {"name": r["name"], "price": money(r["price"])},
            )
        elif table == "ledger":
            label = render(
                c,
                "list_ledger_row",
                "LED-{id} — ${amount} — {reason}",
                {
                    "id": f"{r['id']:05d}",
                    "amount": money(r["delta"]),
                    "reason": r["reason"],
                },
            )
        else:
            code = {"orders": "TK-", "topups": "TOP-", "tickets": "SUP-"}[
                table
            ] + f"{r['id']:05d}"
            label = render(
                c,
                "list_" + table + "_row",
                "{id} — {status}",
                {"id": code, "status": state_label(c, r["status"])},
            )
        buttons.append([b(label, prefix + str(r["id"]))])
    if page:
        buttons.append([b("◀️ السابق", f"page:{kind}:{page-1}:{filt}")])
    if len(rr) > 8:
        buttons.append([b("▶️ التالي", f"page:{kind}:{page+1}:{filt}")])
    if kind == "myorders":
        buttons += [
            [
                b("⏳ المعلقة", "page:myorders:0:pending"),
                b("✅ المكتملة", "page:myorders:0:completed"),
            ],
            [b("❌ الملغاة", "page:myorders:0:cancelled"), b("🔍 بحث", "search_order")],
        ]
    buttons += HOME
    say(
        c,
        uid,
        kind + "_list",
        "{title}\n{empty}",
        {
            "title": render(c, kind + "_title", title),
            "empty": "" if rr else "📭 لا توجد بيانات لعرضها حاليًا.",
        },
        buttons,
    )


def action(c, uid, a, depth=0, context=None):
    from .flows import fill

    if depth > 12:
        raise ValueError("تسلسل قوائم غير صالح")
    parts = a.split(":")
    cmd = parts[0]
    if cmd == "context":
        row = c.execute(
            "SELECT * FROM button_context WHERE code=? AND user_id=? AND expires>?",
            (parts[1], uid, time.time()),
        ).fetchone()
        if not row:
            raise ValueError("⌛ انتهت جلسة الزر. حدّث الشاشة.")
        return action(
            c,
            uid,
            "button:" + str(row["button_id"]),
            depth + 1,
            json.loads(row["data"]),
        )
    if cmd == "button":
        btn = one(c, "buttons", int(parts[1]))
        if not btn["enabled"] or (
            btn["permission"] and not role(c, uid, btn["permission"])
        ):
            raise ValueError("غير مصرح")
        act = btn["action"]
        user = one(c, "users", uid)
        route = btn["target"].split(":")[0] if act == "callback" else act
        if route not in (
            "support",
            "newticket",
            "ticket",
            "tickets",
            "ticket_reply",
            "ticket_status",
            "home",
        ) and not role(c, uid):
            if user["status"] == "blocked":
                raise ValueError("🚫 حسابك محظور؛ تواصل مع الدعم.")
            if setting(c, "maintenance") == "all":
                say(c, uid, "maintenance", buttons=[[b("🎧 الدعم", "support")]])
                return
        user = one(c, "users", uid)
        target = fill(
            btn["target"],
            {
                "user_id": uid,
                "username": user["username"],
                "first_name": user["first_name"],
                **(context or {}),
            },
        )
        if act == "callback":
            return action(c, uid, target, depth + 1)
        if act == "menu":
            m = c.execute("SELECT * FROM menus WHERE key=?", (target,)).fetchone()
            if not m:
                raise ValueError("القائمة غير موجودة")
            say(c, uid, target, m["text"], values=context, layout=target)
            return
        if act == "message":
            # The button's current text is authoritative; do not cache a stale first version.
            layout = btn["child_menu"]
            notify(
                c,
                uid,
                target,
                extra={
                    "reply_markup": (
                        keyboard(c, uid, layout, values=context)
                        if layout
                        else {"inline_keyboard": HOME}
                    )
                },
            )
            return
        if act == "workflow":
            return action(c, uid, "workflow:" + target, depth + 1)
        if btn["kind"] == "url":
            notify(c, uid, target)
            return
        if act == "order":
            return action(c, uid, "service:" + target, depth + 1)
        if act == "none":
            return action(c, uid, "home", depth + 1)
        return action(c, uid, act, depth + 1)
    maint = setting(c, "maintenance")
    staff = role(c, uid) and setting(c, "maintenance_staff")
    if (
        maint == "all"
        and not staff
        and cmd
        not in (
            "support",
            "newticket",
            "tickets",
            "ticket",
            "ticket_reply",
            "ticket_status",
            "home",
        )
    ):
        say(
            c,
            uid,
            "maintenance",
            buttons=[[b("🎧 الدعم", "support"), b("🔄 إعادة المحاولة", "home")]],
        )
        return
    u = one(c, "users", uid)
    if u["status"] == "blocked" and cmd not in (
        "support",
        "newticket",
        "tickets",
        "ticket",
        "ticket_reply",
        "ticket_status",
        "home",
    ):
        raise ValueError("🚫 حسابك محظور؛ تواصل مع الدعم.")
    if cmd == "openmenu":
        key = parts[1]
        m = c.execute("SELECT * FROM menus WHERE key=?", (key,)).fetchone()
        if not m:
            raise ValueError("القائمة غير موجودة")
        say(c, uid, key, m["text"], layout=key)
    elif cmd == "language":
        langs = rows(c, "SELECT * FROM locales WHERE enabled=1 ORDER BY id")
        say(
            c,
            uid,
            "choose_language",
            "🌐 اختر اللغة",
            buttons=[[b(lang["name"], "setlanguage:" + lang["code"])] for lang in langs]
            + HOME,
        )
    elif cmd == "setlanguage":
        if not c.execute(
            "SELECT 1 FROM locales WHERE code=? AND enabled=1", (parts[1],)
        ).fetchone():
            raise ValueError("اللغة غير متاحة")
        c.execute("UPDATE users SET language=? WHERE id=?", (parts[1], uid))
        CURRENT_LANGUAGE.set(parts[1])
        action(c, uid, "home")
    elif cmd == "workflow":
        from .flows import start

        start(c, uid, int(parts[1]))
    elif cmd in ("flow_choice", "flow_cancel"):
        run = one(c, "flow_runs", int(parts[1]))
        if run["user_id"] != uid:
            raise ValueError("غير مصرح")
        if cmd == "flow_cancel":
            c.execute(
                "UPDATE flow_runs SET status='cancelled',updated=? WHERE id=?",
                (now(), run["id"]),
            )
            c.execute(
                "DELETE FROM sessions WHERE user_id=? AND state='workflow'", (uid,)
            )
            action(c, uid, "home")
        else:
            st, info = getstate(c, uid)
            if st != "workflow" or info.get("run_id") != run["id"]:
                raise ValueError("انتهت جلسة التدفق")
            flow = one(c, "workflows", run["workflow_id"])
            step = json.loads(flow["steps"])[run["step"]]
            choices = step.get("choices", "").split("|")
            index = int(parts[2])
            if step.get("validator") != "choice" or not 0 <= index < len(choices):
                raise ValueError("خيار غير صالح")
            from .flows import advance

            advance(c, uid, run["id"], choices[index])
    elif cmd == "resume_topup":
        d = c.execute("SELECT * FROM topup_drafts WHERE user_id=?", (uid,)).fetchone()
        if not d:
            raise ValueError("لا يوجد شحن محفوظ")
        data = json.loads(d["data"])
        if data.get("topup_id"):
            return topup_details(c, uid, data["topup_id"])
        state(c, uid, d["state"], data)
        if d["state"] == "topup_review":
            return handle_input(c, uid, "", {}, resume=True)
        say(
            c,
            uid,
            "topup_amount_resume",
            "أرسل مبلغ الشحن لاستكمال العملية.",
            buttons=HOME,
        )
    elif cmd == "home":
        if u["status"] == "blocked":
            say(
                c,
                uid,
                "blocked",
                "🚫 حسابك غير قادر على استخدام هذه الخدمة. يرجى التواصل مع الدعم.",
                buttons=[[b("🎧 الدعم", "support")]],
            )
            return
        if maint == "all" and not staff:
            say(c, uid, "maintenance", buttons=[[b("🎧 الدعم", "support")]])
            return
        markup = keyboard(c, uid, "home")
        if role(c, uid) and markup and "inline_keyboard" in markup:
            markup["inline_keyboard"].append(
                [
                    b(
                        (
                            "👑 لوحة المالك"
                            if uid == setting(c, "owner_telegram_id")
                            else "⚙️ لوحة الإدارة"
                        ),
                        "admin",
                    )
                ]
            )
        notify(
            c,
            uid,
            text(c, "home", "أهلاً بك"),
            extra={"reply_markup": markup} if markup else {},
        )
        if c.execute("SELECT 1 FROM topup_drafts WHERE user_id=?", (uid,)).fetchone():
            say(
                c,
                uid,
                "resume_topup_draft",
                "💳 لديك شحن غير مكتمل محفوظ.",
                buttons=[[b("▶️ استكمال الشحن", "resume_topup")]],
            )
        if c.execute("SELECT COUNT(*) FROM locales WHERE enabled=1").fetchone()[0] > 1:
            say(c, uid, "language_hint", "🌐", buttons=[[b("🌐 اللغة", "language")]])
        if draft(c, uid):
            say(
                c,
                uid,
                "resume_draft",
                "📋 لديك طلب غير مكتمل محفوظ.",
                buttons=[[b("▶️ استكمال الطلب", "resume")]],
            )
    elif (
        cmd in ("services", "myorders", "topups", "tickets", "ledger")
        and len(parts) == 1
    ):
        listing(c, uid, cmd)
    elif cmd == "page":
        listing(
            c, uid, parts[1], max(0, int(parts[2])), parts[3] if len(parts) > 3 else ""
        )
    elif cmd == "service":
        s = one(c, "services", int(parts[1]))
        if not s["enabled"] or s["deleted"]:
            raise ValueError("الخدمة غير متاحة")
        if maint in ("orders", "all") and not staff:
            raise ValueError("الطلبات متوقفة للصيانة")
        d = {"service_id": s["id"], "key": secrets.token_urlsafe(20)}
        savedraft(c, uid, d)
        state(c, uid, "order_target", d)
        if s["image"].startswith(("https://", "upload:")):
            notify(c, uid, "", method="sendPhoto", extra={"photo": s["image"]})
        say(
            c,
            uid,
            "service_details",
            "🛒 {name}\n{description}\nالسعر لكل 1000: ${price}\nالحد الأدنى: {min}\nالحد الأعلى: {max}\n📌 أرسل رابط تيك توك.",
            {
                "name": s["name"],
                "description": s["description"],
                "price": money(s["price"]),
                "min": s["min_qty"],
                "max": s["max_qty"],
            },
            [[b("↩️ الخدمات", "services")]] + HOME,
            "layout_service_details",
        )
    elif cmd in ("edit_target", "edit_qty", "resume"):
        d = draft(c, uid)
        if not d:
            raise ValueError("لا يوجد طلب محفوظ")
        if cmd == "resume" and "quantity" in d:
            return review(c, uid, d)
        step = "order_quantity" if cmd == "edit_qty" else "order_target"
        state(c, uid, step, d)
        say(
            c,
            uid,
            step + "_prompt",
            "أرسل {input}.",
            {
                "input": (
                    "الكمية كعدد صحيح" if step == "order_quantity" else "رابط تيك توك"
                )
            },
            [[b("❌ إلغاء الطلب", "cancel_order")]] + HOME,
        )
    elif cmd == "qty":
        handle_input(c, uid, parts[1], {})
    elif cmd == "order_confirm":
        d = draft(c, uid)
        if not d:
            raise ValueError("⚠️ تم تنفيذ العملية مسبقًا أو انتهت الجلسة.")
        st, session_data = getstate(c, uid)
        if st != "order_confirm" or session_data.get("key") != d.get("key"):
            raise ValueError(
                "⌛ انتهت جلسة التأكيد. اضغط استكمال الطلب لمراجعته من جديد."
            )
        oid = order_create(c, uid, d)
        c.execute("DELETE FROM sessions WHERE user_id=?", (uid,))
        say(
            c,
            uid,
            "order_created",
            "✅ تم تسجيل الطلب TK-{id}\nالخدمة: {service}\nالكمية: {quantity}\nالحالة: قيد المراجعة\nالسعر: ${price}",
            {
                "id": f"{oid:05d}",
                "price": money(d["price"]),
                "quantity": d["quantity"],
                "service": one(c, "services", d["service_id"])["name"],
            },
            [[b("📋 تفاصيل الطلب", "order:" + str(oid)), b("📋 طلباتي", "myorders")]]
            + HOME,
        )
    elif cmd == "cancel_order":
        c.execute("DELETE FROM drafts WHERE user_id=?", (uid,))
        c.execute("DELETE FROM sessions WHERE user_id=?", (uid,))
        say(
            c,
            uid,
            "order_cancelled",
            "❌ تم إلغاء الطلب. لم يتم خصم أي مبلغ.",
            buttons=HOME,
        )
    elif cmd == "order":
        o = one(c, "orders", int(parts[1]))
        if o["user_id"] != uid:
            raise ValueError("غير مصرح")
        buttons = [
            [b("🔄 تحديث الحالة", a), b("🎧 الدعم", "newticket:طلب:" + str(o["id"]))]
        ]
        if o["status"] in ("pending", "processing"):
            buttons.append([b("❌ طلب إلغاء", "cancel_request:" + str(o["id"]))])
        if o["refund_id"]:
            buttons.append([b("📄 تفاصيل الاسترداد", "ledger:" + str(o["refund_id"]))])
        buttons += [
            [b("📋 سجل الطلب", "order_log:" + str(o["id"])), b("📋 طلباتي", "myorders")]
        ] + HOME
        say(
            c,
            uid,
            "order_details",
            "📋 TK-{id}\nالخدمة: {service}\nالرابط: {target}\nالكمية: {quantity}\nالسعر: ${price}\nالحالة: {status}\nتاريخ الإنشاء: {created}\nملاحظات: {note}\nحركة الخصم: {debit}\nحركة الاسترداد: {refund}",
            {
                "id": f"{o['id']:05d}",
                "service": o["service_name"],
                "target": o["target"],
                "quantity": o["quantity"],
                "price": money(o["price"]),
                "status": state_label(c, o["status"]),
                "created": o["created"],
                "note": o["note"],
                "debit": o["debit_id"],
                "refund": o["refund_id"] or "—",
            },
            buttons,
        )
    elif cmd == "order_log":
        o = one(c, "orders", int(parts[1]))
        if o["user_id"] != uid:
            raise ValueError("غير مصرح")
        history = rows(
            c,
            "SELECT action,data,created FROM audit WHERE entity=? AND action LIKE 'order.%' ORDER BY id",
            (str(o["id"]),),
        )
        say(
            c,
            uid,
            "order_history",
            "📋 سجل الطلب\n{history}",
            {"history": "\n".join(r["created"] + " " + r["data"] for r in history)},
            [[b("↩️ الطلب", "order:" + str(o["id"]))]],
        )
    elif cmd == "cancel_request":
        order = one(c, "orders", int(parts[1]))
        if order["user_id"] != uid:
            raise ValueError("غير مصرح")
        if order["status"] != "pending":
            say(
                c,
                uid,
                "cancel_in_progress",
                "⚠️ لا يمكن إلغاء الطلب تلقائيًا بعد بدء التنفيذ.",
                buttons=[
                    [b("🎧 طلب إلغاء من الدعم", "newticket:طلب:" + parts[1])],
                    [b("↩️ العودة", "order:" + parts[1])],
                ],
            )
            return
        say(
            c,
            uid,
            "cancel_confirmation",
            "⚠️ هل تريد إلغاء الطلب واسترداد المبلغ؟",
            buttons=[
                [
                    b("✅ تأكيد الإلغاء", "cancel_confirm:" + parts[1]),
                    b("↩️ رجوع", "order:" + parts[1]),
                ]
            ],
        )
    elif cmd == "cancel_confirm":
        if not setting(c, "customer_cancel_pending", True):
            raise ValueError("الإلغاء التلقائي متوقف. تواصل مع الدعم.")
        order_status(c, int(parts[1]), "cancelled", uid, True)
        action(c, uid, "order:" + parts[1])
    elif cmd == "search_order":
        state(c, uid, "search_order", {})
        say(c, uid, "search_order_prompt", "أرسل رقم الطلب TK-00001", buttons=HOME)
    elif cmd == "ledger":
        r = one(c, "ledger", int(parts[1]))
        if r["user_id"] != uid:
            raise ValueError("غير مصرح")
        say(
            c,
            uid,
            "ledger_details",
            "💰 LED-{id}\nالمبلغ: ${delta}\nالسبب: {reason}\nقبل: ${before} / بعد: ${after}\nالمنفذ: {actor}\nالتاريخ: {created}",
            {
                "id": f"{r['id']:05d}",
                "delta": money(r["delta"]),
                "reason": r["reason"],
                "before": money(r["before_balance"]),
                "after": money(r["after_balance"]),
                "actor": r["actor"],
                "created": r["created"],
            },
            [[b("↩️ سجل الرصيد", "ledger")]] + HOME,
        )
    elif cmd == "account":
        count = c.execute(
            "SELECT COUNT(*) FROM orders WHERE user_id=?", (uid,)
        ).fetchone()[0]
        say(
            c,
            uid,
            "account_details",
            "👤 حسابك الشخصي\nID: {id}\nUsername: @{username}\nتاريخ الانضمام: {created}\n💳 الرصيد: ${balance}\n📦 عدد الطلبات: {count}",
            {
                "id": uid,
                "username": u["username"],
                "created": u["created"],
                "balance": money(u["balance"]),
                "count": count,
            },
            [
                [b("💳 شحن الرصيد", "topup"), b("📋 طلباتي", "myorders")],
                [b("💰 سجل الرصيد", "ledger"), b("🎧 الدعم", "support")],
            ]
            + HOME,
            "layout_account",
        )
    elif cmd == "topup":
        (
            say(
                c,
                uid,
                "topup",
                buttons=[
                    [
                        b("⭐ Telegram Stars", "newtopup:stars"),
                        b("🧾 شحن يدوي", "newtopup:manual"),
                    ],
                    [b("📋 طلبات الشحن", "topups")],
                ]
                + HOME,
                layout="layout_topup",
            )
            if len(parts) == 1
            else topup_details(c, uid, int(parts[1]))
        )
    elif cmd == "newtopup":
        method = parts[1]
        if method not in ("stars", "manual") or not setting(c, method + "_enabled"):
            raise ValueError("الطريقة معطلة")
        state(c, uid, "topup_amount", {"method": method})
        say(
            c,
            uid,
            "topup_amount",
            "أدخل مبلغ الشحن بالدولار.\nالحد الأدنى: ${min}\nالحد الأعلى: ${max}\nسعر Stars لكل دولار: {rate}",
            {
                "min": money(setting(c, "topup_min")),
                "max": money(setting(c, "topup_max")),
                "rate": setting(c, "stars_rate"),
            },
            [
                [
                    b("$1", "amount:1"),
                    b("$5", "amount:5"),
                    b("$10", "amount:10"),
                    b("$20", "amount:20"),
                ]
            ]
            + HOME,
            "layout_topup_amount",
        )
    elif cmd == "amount":
        handle_input(c, uid, parts[1], {})
    elif cmd == "edit_topup_amount":
        st, d = getstate(c, uid)
        if st != "topup_review":
            raise ValueError("انتهت جلسة الشحن")
        action(c, uid, "newtopup:" + d["method"])
    elif cmd == "topup_go":
        st, d = getstate(c, uid)
        if st != "topup_review":
            raise ValueError("انتهت الجلسة أو تم تنفيذ العملية مسبقًا")
        t = topup_create(c, uid, d["amount"], d["method"])
        if t["method"] == "stars":
            notify(
                c,
                uid,
                "",
                method="sendInvoice",
                extra={
                    "title": text(c, "invoice_title", "شحن رصيد البوت"),
                    "description": text(
                        c,
                        "invoice_description",
                        "إضافة ${amount} إلى رصيدك",
                        {"amount": money(t["amount"])},
                    ),
                    "payload": t["payload"],
                    "provider_token": "",
                    "currency": "XTR",
                    "prices": [{"label": "رصيد", "amount": t["stars"]}],
                },
            )
            state(c, uid, "awaiting_payment", {"topup_id": t["id"]})
            say(
                c,
                uid,
                "invoice_waiting",
                "⭐ تم إنشاء الفاتورة. لم تتم إضافة الرصيد بعد.\nيمكنك مراجعة حالة الشحن أو إلغاء الفاتورة غير المدفوعة.",
                buttons=[
                    [
                        b("📋 حالة الشحن", "topup:" + str(t["id"])),
                        b("❌ إلغاء الدفع", "topup_cancel:" + str(t["id"])),
                    ]
                ]
                + HOME,
            )
        else:
            state(c, uid, "topup_proof", {"topup_id": t["id"]})
            say(
                c,
                uid,
                "transfer_instructions",
                "🧾 TOP-{id}\nالمبلغ: ${amount}\n{instructions}\n\nأرسل صورة أو ملف إثبات أو رقم التحويل وملاحظة.",
                {
                    "id": f"{t['id']:05d}",
                    "amount": money(t["amount"]),
                    "instructions": setting(c, "transfer_instructions"),
                },
                [
                    [
                        b("❌ إلغاء", "topup_cancel:" + str(t["id"])),
                        b("🎧 الدعم", "support"),
                    ]
                ]
                + HOME,
            )
    elif cmd == "cancel_topup_draft":
        c.execute("DELETE FROM topup_drafts WHERE user_id=?", (uid,))
        c.execute("DELETE FROM sessions WHERE user_id=?", (uid,))
        say(
            c,
            uid,
            "topup_draft_cancelled",
            "❌ تم إلغاء عملية الشحن. لم تتم إضافة أي مبلغ إلى رصيدك.",
            buttons=HOME,
        )
    elif cmd == "topup_cancel":
        t = one(c, "topups", int(parts[1]))
        if t.get("checkout_started"):
            raise ValueError(
                "الدفع قيد المعالجة. انتظر تأكيد تيليجرام أو تواصل مع الدعم؛ لا يمكن إلغاء دفعة قيد التنفيذ."
            )
        if t["user_id"] != uid or t["status"] not in (
            "awaiting_proof",
            "awaiting_payment",
        ):
            raise ValueError("لا يمكن إلغاء هذا الطلب")
        c.execute(
            "UPDATE topups SET status='cancelled',updated=? WHERE id=?",
            (now(), t["id"]),
        )
        c.execute("DELETE FROM sessions WHERE user_id=?", (uid,))
        c.execute("DELETE FROM topup_drafts WHERE user_id=?", (uid,))
        action(c, uid, "topups")
    elif cmd == "support":
        if not setting(c, "support_enabled", True):
            raise ValueError("الدعم متوقف مؤقتًا. حاول لاحقًا.")
        say(
            c,
            uid,
            "support",
            buttons=[
                [
                    b("💳 مشكلة شحن", "newticket:شحن"),
                    b("📦 مشكلة طلب", "newticket:طلب"),
                ],
                [
                    b("👤 مشكلة حساب", "newticket:حساب"),
                    b("❓ استفسار", "newticket:عام"),
                ],
                [b("📋 تذاكري", "tickets")],
            ]
            + HOME,
            layout="layout_support",
        )
    elif cmd == "newticket":
        if not setting(c, "support_enabled", True):
            raise ValueError("إنشاء التذاكر متوقف مؤقتًا")
        data = {"subject": parts[1] if len(parts) > 1 else "عام"}
        if len(parts) > 2:
            o = one(c, "orders", int(parts[2]))
            if o["user_id"] != uid:
                raise ValueError("غير مصرح")
            data["order_id"] = o["id"]
        state(c, uid, "ticket_new", data)
        say(c, uid, "ticket_new", "🎧 أرسل وصف المشكلة بالتفصيل.", buttons=HOME)
    elif cmd == "ticket":
        t = one(c, "tickets", int(parts[1]))
        if t["user_id"] != uid:
            raise ValueError("غير مصرح")
        msgpage = max(0, int(parts[2])) if len(parts) > 2 else 0
        messages = rows(
            c,
            "SELECT * FROM messages WHERE ticket_id=? ORDER BY id DESC LIMIT 6 OFFSET ?",
            (t["id"], msgpage * 5),
        )
        more = len(messages) > 5
        messages = messages[:5]
        if msgpage:
            notify(c, uid, render(c, "ticket_previous_page", "📄 صفحة رسائل سابقة"))
        pagebuttons = []
        if msgpage:
            pagebuttons.append(b("◀️ الأحدث", f"ticket:{t['id']}:{msgpage-1}"))
        if more:
            pagebuttons.append(b("▶️ الأقدم", f"ticket:{t['id']}:{msgpage+1}"))
        body = "\n".join(
            ("👤 أنت: " if r["actor"] == str(uid) else "🎧 الدعم: ") + r["body"]
            for r in reversed(messages)
        )
        say(
            c,
            uid,
            "ticket_details",
            "🎫 SUP-{id}\nالموضوع: {subject}\nالحالة: {status}\n\n{messages}",
            {
                "id": f"{t['id']:05d}",
                "subject": t["subject"],
                "status": state_label(c, t["status"]),
                "messages": body,
            },
            ([pagebuttons] if pagebuttons else [])
            + [
                [b("✉️ إرسال رسالة", "ticket_reply:" + str(t["id"]))],
                [
                    b(
                        "🔄 إعادة فتح" if t["status"] == "closed" else "🔒 إغلاق",
                        "ticket_status:"
                        + str(t["id"])
                        + (":open" if t["status"] == "closed" else ":confirm"),
                    )
                ],
                [b("↩️ تذاكري", "tickets")],
            ]
            + HOME,
        )
    elif cmd == "ticket_reply":
        t = one(c, "tickets", int(parts[1]))
        if t["user_id"] != uid or t["status"] == "closed":
            raise ValueError("التذكرة مغلقة أو غير مصرح")
        state(c, uid, "ticket_message", {"ticket_id": t["id"]})
        say(c, uid, "ticket_reply_prompt", "✉️ أرسل رسالتك.", buttons=HOME)
    elif cmd == "ticket_status":
        t = one(c, "tickets", int(parts[1]))
        if t["user_id"] != uid:
            raise ValueError("غير مصرح")
        status = parts[2]
        if status == "confirm":
            say(
                c,
                uid,
                "ticket_close_confirm",
                "هل تريد إغلاق التذكرة؟",
                buttons=[
                    [
                        b("✅ إغلاق", "ticket_status:" + parts[1] + ":closed"),
                        b("❌ إلغاء", "ticket:" + parts[1]),
                    ]
                ],
            )
            return
        if status not in ("closed", "open"):
            raise ValueError("حالة غير صالحة")
        c.execute(
            "UPDATE tickets SET status=?,updated=? WHERE id=?", (status, now(), t["id"])
        )
        audit(c, uid, "ticket.status", t["id"], {"status": status})
        action(c, uid, "ticket:" + parts[1])
    elif cmd == "admin":
        if not role(c, uid):
            raise ValueError("⛔ غير مصرح لك بالدخول")
        say(
            c,
            uid,
            "admin_web",
            "⚙️ تتم إدارة النظام من لوحة الويب. افتح عنوان اللوحة وسجل الدخول بحسابك المخصص.",
            buttons=HOME,
        )
        if setting(c, "web_url"):
            notify(
                c,
                uid,
                render(c, "admin_web_link", "🌐 افتح لوحة التحكم"),
                extra={
                    "reply_markup": {
                        "inline_keyboard": [
                            [
                                {
                                    "text": render(
                                        c, "admin_web_button", "فتح لوحة الويب"
                                    ),
                                    "url": setting(c, "web_url"),
                                }
                            ]
                        ]
                    }
                },
            )
    else:
        raise ValueError("الإجراء غير معروف. افتح القائمة الرئيسية.")


def topup_details(c, uid, tid):
    t = one(c, "topups", tid)
    if t["user_id"] != uid:
        raise ValueError("غير مصرح")
    buttons = [[b("🔄 تحديث", "topup:" + str(tid)), b("🎧 الدعم", "support")]] + HOME
    if t["status"] == "rejected":
        buttons.insert(
            0,
            [
                b("🔄 طلب شحن جديد", "topup"),
                b("🎧 الاعتراض على الرفض", "newticket:اعتراض شحن TOP-" + str(tid)),
            ],
        )
    if t["status"] == "awaiting_proof":
        state(c, uid, "topup_proof", {"topup_id": tid})
        buttons.insert(0, [b("❌ إلغاء", "topup_cancel:" + str(tid))])
    say(
        c,
        uid,
        "topup_details",
        "🧾 TOP-{id}\nالمبلغ: ${amount}\nالطريقة: {method}\nالحالة: {status}\nالتاريخ: {created}\nسبب الرفض: {reason}\n{hint}",
        {
            "id": f"{tid:05d}",
            "amount": money(t["amount"]),
            "method": state_label(c, t["method"]),
            "status": state_label(c, t["status"]),
            "created": t["created"],
            "reason": t["reason"],
            "hint": (
                "أرسل إثبات التحويل هنا." if t["status"] == "awaiting_proof" else ""
            ),
        },
        buttons,
    )


def handle_input(c, uid, value, msg, resume=False):
    st, d = getstate(c, uid)
    user = one(c, "users", uid)
    if user["status"] == "blocked" and st.startswith(("order", "topup")):
        raise ValueError("حسابك محظور. تواصل مع الدعم.")
    if st == "expired":
        say(c, uid, "expired", buttons=HOME)
        return
    if st == "workflow":
        from .flows import advance

        advance(c, uid, d["run_id"], value)
    elif st == "order_target":
        s = one(c, "services", d["service_id"])
        if not s["enabled"] or s["deleted"]:
            raise ValueError("⚠️ الخدمة غير متاحة حاليًا")
        if not target_valid(value, s["target_type"]):
            raise ValueError("❌ رابط غير صالح. مثال: https://www.tiktok.com/@username")
        d["target"] = value
        savedraft(c, uid, d)
        state(c, uid, "order_quantity", d)
        say(
            c,
            uid,
            "quantity_prompt",
            "✅ تم استلام الرابط.\n📦 أرسل الكمية كعدد صحيح.\nالحد الأدنى: {min} / الأعلى: {max}",
            {"min": s["min_qty"], "max": s["max_qty"]},
            [
                [
                    b("100", "qty:100"),
                    b("500", "qty:500"),
                    b("1000", "qty:1000"),
                    b("5000", "qty:5000"),
                ],
                [b("✏️ تعديل الرابط", "edit_target"), b("❌ إلغاء", "cancel_order")],
            ]
            + HOME,
            "layout_quantity",
        )
    elif st == "order_quantity":
        d["quantity"] = value
        review(c, uid, d)
    elif st == "search_order":
        try:
            oid = int(value.upper().replace("TK-", ""))
        except ValueError:
            raise ValueError("رقم طلب غير صالح")
        action(c, uid, "order:" + str(oid))
    elif st == "topup_amount" or (st == "topup_review" and resume):
        amount = d["amount"] if resume else cents(value.replace("$", "").strip())
        if not setting(c, "topup_min") <= amount <= setting(c, "topup_max"):
            raise ValueError("المبلغ خارج حدود الشحن")
        d["amount"] = amount
        state(c, uid, "topup_review", d)
        say(
            c,
            uid,
            "topup_review",
            "🧾 مراجعة الشحن\nالمبلغ: ${amount}\nالطريقة: {method}\nStars: {stars}\nهل تريد المتابعة؟",
            {
                "amount": money(amount),
                "method": state_label(c, d["method"]),
                "stars": (
                    round(amount * setting(c, "stars_rate") / 100)
                    if d["method"] == "stars"
                    else "—"
                ),
            },
            [
                [b("✅ متابعة", "topup_go"), b("✏️ تعديل", "edit_topup_amount")],
                [b("❌ إلغاء", "cancel_topup_draft")],
            ]
            + HOME,
            "layout_topup_review",
        )
    elif st == "topup_proof":
        t = one(c, "topups", d["topup_id"])
        if t["user_id"] != uid or t["status"] != "awaiting_proof":
            raise ValueError("تمت معالجة الطلب أو إلغاؤه")
        typ = "text"
        proof = value
        if msg.get("photo"):
            typ = "photo"
            proof = msg["photo"][-1]["file_id"]
        elif msg.get("document"):
            typ = "document"
            proof = msg["document"]["file_id"]
        if not proof:
            raise ValueError("أرسل صورة أو ملف أو رقم تحويل")
        c.execute(
            "UPDATE topups SET proof=?,note=?,status='review',updated=? WHERE id=?",
            (
                json.dumps({"type": typ, "value": proof}),
                msg.get("caption", ""),
                now(),
                t["id"],
            ),
        )
        c.execute("DELETE FROM sessions WHERE user_id=?", (uid,))
        c.execute("DELETE FROM topup_drafts WHERE user_id=?", (uid,))
        staff_notify(c, "topups", f"🧾 طلب شحن للمراجعة TOP-{t['id']:05d}")
        action(c, uid, "topup:" + str(t["id"]))
    elif st == "ticket_new":
        if not value.strip():
            raise ValueError("أرسل وصف المشكلة")
        tid = c.execute(
            "INSERT INTO tickets(user_id,subject,order_id,created,updated) VALUES(?,?,?,?,?)",
            (uid, d["subject"], d.get("order_id"), now(), now()),
        ).lastrowid
        ticket_message(c, tid, uid, value)
        c.execute("DELETE FROM sessions WHERE user_id=?", (uid,))
        action(c, uid, "ticket:" + str(tid))
    elif st == "ticket_message":
        ticket_message(c, d["ticket_id"], uid, value)
        c.execute("DELETE FROM sessions WHERE user_id=?", (uid,))
        action(c, uid, "ticket:" + str(d["ticket_id"]))
    else:
        action(c, uid, "home")


def process_update(update):
    source = update.get("message") or (update.get("callback_query") or {}).get(
        "message"
    )
    u = (update.get("callback_query") or {}).get("from") or (
        update.get("message") or {}
    ).get("from")
    if not u or (source and source.get("chat", {}).get("type", "private") != "private"):
        return
    uid = u["id"]
    language_token = CURRENT_LANGUAGE.set(None)
    try:
        with db() as c:
            if c.execute(
                "SELECT 1 FROM updates WHERE id=?", (update["update_id"],)
            ).fetchone():
                return
            upsert(c, u)
            CURRENT_LANGUAGE.set(locale_for(c, uid))
            if update.get("callback_query"):
                q = update["callback_query"]
                notify(
                    c,
                    uid,
                    "",
                    method="answerCallbackQuery",
                    extra={"callback_query_id": q["id"]},
                )
                # answerCallbackQuery has no chat_id parameter.
                last = c.execute(
                    "SELECT id,payload FROM notifications ORDER BY id DESC LIMIT 1"
                ).fetchone()
                payload = json.loads(last["payload"])
                payload["data"].pop("chat_id", None)
                c.execute(
                    "UPDATE notifications SET payload=? WHERE id=?",
                    (json.dumps(payload), last["id"]),
                )
                action(c, uid, q["data"])
            else:
                m = update["message"]
                value = m.get("text", "").strip()
                if m.get("successful_payment"):
                    payment(c, uid, m["successful_payment"])
                elif value.startswith("/start"):
                    action(c, uid, "home")
                elif value.startswith("/paysupport"):
                    action(c, uid, "support")
                else:
                    row = c.execute(
                        "SELECT buttons FROM reply_context WHERE user_id=?", (uid,)
                    ).fetchone()
                    mapping = json.loads(row[0]) if row else {}
                    selected = mapping.get(value)
                    if selected:
                        action(
                            c,
                            uid,
                            "button:" + str(selected["id"]),
                            context=selected.get("values"),
                        )
                    else:
                        handle_input(c, uid, value, m)
            c.execute("INSERT INTO updates VALUES(?,?)", (update["update_id"], now()))
    except (ValueError, KeyError, IndexError, TypeError) as e:
        message = (
            str(e)
            if isinstance(e, ValueError)
            else "البيانات غير صحيحة أو انتهت الجلسة. عد إلى القائمة الرئيسية."
        )
        with db() as c:
            upsert(c, u)
            if c.execute(
                "SELECT 1 FROM updates WHERE id=?", (update["update_id"],)
            ).fetchone():
                return
            say(
                c,
                uid,
                "validation_error",
                "⚠️ {error}",
                {"error": message},
                [[b("🔄 استكمال الطلب", "resume"), b("💳 شحن الرصيد", "topup")]] + HOME,
            )
            c.execute("INSERT INTO updates VALUES(?,?)", (update["update_id"], now()))

    finally:
        CURRENT_LANGUAGE.reset(language_token)


def precheckout(token, q):
    try:
        with db() as c:
            invoice = invoice_validate(c, q["from"]["id"], q)
            c.execute(
                "UPDATE topups SET checkout_started=1 WHERE id=?", (invoice["id"],)
            )
        data = {"pre_checkout_query_id": q["id"], "ok": True}
    except ValueError:
        data = {
            "pre_checkout_query_id": q["id"],
            "ok": False,
            "error_message": "الفاتورة غير صالحة أو تمت معالجتها. أنشئ فاتورة جديدة.",
        }
    call(token, "answerPreCheckoutQuery", data)


def dispatch(token):
    # At-least-once transport for notifications; financial mutations are already committed exactly once.
    with db() as c:
        pending = rows(c, "SELECT * FROM notifications WHERE status='pending' LIMIT 12")
    for n in pending:
        p = json.loads(n["payload"])
        try:
            call(token, p["method"], p["data"])
            status = "sent"
            err = ""
        except Exception:
            status = "failed" if n["attempts"] >= 4 else "pending"
            err = "فشل الاتصال أو رفض Telegram الرسالة"
        with db() as c:
            c.execute(
                "UPDATE notifications SET status=?,attempts=attempts+1,error=? WHERE id=?",
                (status, err, n["id"]),
            )


def broadcast_step(token):
    with db() as c:
        d = c.execute(
            "SELECT d.*,b.body,b.kind,b.media FROM deliveries d JOIN broadcasts b ON b.id=d.broadcast_id WHERE d.status='pending' AND b.status='running' ORDER BY d.id LIMIT 1"
        ).fetchone()
        if not d:
            c.execute(
                "UPDATE broadcasts SET status='completed' WHERE status='running' AND NOT EXISTS(SELECT 1 FROM deliveries WHERE broadcast_id=broadcasts.id AND status='pending')"
            )
            return
        d = dict(d)
        c.execute("UPDATE deliveries SET status='sending' WHERE id=?", (d["id"],))
    try:
        if d["kind"] == "text":
            call(token, "sendMessage", {"chat_id": d["user_id"], "text": d["body"]})
        else:
            call(
                token,
                {
                    "photo": "sendPhoto",
                    "video": "sendVideo",
                    "document": "sendDocument",
                }[d["kind"]],
                {"chat_id": d["user_id"], d["kind"]: d["media"], "caption": d["body"]},
            )
        status = "sent"
        err = ""
    except Exception:
        status = "failed"
        err = "تعذر التسليم"
    with db() as c:
        c.execute(
            "UPDATE deliveries SET status=?,error=? WHERE id=?", (status, err, d["id"])
        )
    time.sleep(0.05)


def run(stop):
    from .web import token as readtoken

    with db() as c:
        c.execute(
            "UPDATE deliveries SET status='unknown',error='انقطع التشغيل أثناء التسليم؛ لم تتم الإعادة لتجنب التكرار' WHERE status='sending'"
        )

    def sender():
        while not stop.is_set():
            try:
                with db() as c:
                    t = readtoken(c)
                if t:
                    dispatch(t)
                    for _ in range(15):
                        if stop.is_set():
                            break
                        broadcast_step(t)
            except Exception:
                log.warning("Delivery worker failure (details redacted)")
            stop.wait(1)

    threading.Thread(target=sender, daemon=True).start()
    webhook_cleared_for = None
    while not stop.is_set():
        try:
            with db() as c:
                t = readtoken(c)
                offset = setting(c, "poll_offset", 0)
            if not t:
                runtime.update(status="disconnected")
                webhook_cleared_for = None
                stop.wait(2)
                continue
            if runtime["status"] != "connected":
                runtime.update(status="connecting")
            if webhook_cleared_for != t:
                call(t, "deleteWebhook", {"drop_pending_updates": False})
                webhook_cleared_for = t
            updates = call(
                t,
                "getUpdates",
                {
                    "offset": offset,
                    "timeout": 25,
                    "allowed_updates": [
                        "message",
                        "callback_query",
                        "pre_checkout_query",
                    ],
                },
            )
            with db() as c:
                current_token = readtoken(c)
            if current_token != t:
                continue
            runtime.update(status="connected", error="", last_update=now())
            for update in updates:
                if "pre_checkout_query" in update:
                    precheckout(t, update["pre_checkout_query"])
                else:
                    process_update(update)
                with db() as c:
                    put(c, "poll_offset", update["update_id"] + 1)
        except Exception:
            runtime.update(
                status="error",
                error="تعذر الاتصال بتيليجرام. تحقق من الاتصال ومن عدم تشغيل نسخة أخرى للبوت.",
            )
            stop.wait(4)
