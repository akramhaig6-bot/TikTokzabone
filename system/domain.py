import json, secrets
from decimal import Decimal, ROUND_HALF_UP
from urllib.parse import urlsplit
from .store import *


def target_valid(target, kind="any"):
    try:
        u = urlsplit(target)
        host = (u.hostname or "").lower()
        if (
            u.scheme != "https"
            or u.username
            or u.password
            or u.port not in (None, 443)
            or len(target) > 2048
            or any(ch.isspace() for ch in target)
        ):
            return False
        if host not in (
            "tiktok.com",
            "www.tiktok.com",
            "m.tiktok.com",
            "vm.tiktok.com",
            "vt.tiktok.com",
        ):
            return False
        if not u.path.strip("/"):
            return False
        if host in ("vm.tiktok.com", "vt.tiktok.com"):
            return kind == "any"
        if not u.path.startswith("/@"):
            return False
        return (
            kind == "any"
            or (kind == "profile" and "/video/" not in u.path)
            or (kind == "video" and "/video/" in u.path)
        )
    except ValueError:
        return False


def quote(c, sid, target, qty):
    s = one(c, "services", sid)
    if not s["enabled"] or s["deleted"]:
        raise ValueError("⚠️ الخدمة غير متاحة حاليًا.")
    if not target_valid(target, s["target_type"]):
        raise ValueError("❌ رابط تيك توك غير صالح أو غير مناسب للخدمة.")
    if isinstance(qty, bool) or not str(qty).isdigit():
        raise ValueError("الكمية يجب أن تكون عددًا صحيحًا موجبًا.")
    qty = int(qty)
    if not s["min_qty"] <= qty <= s["max_qty"]:
        raise ValueError(f"الكمية يجب أن تكون بين {s['min_qty']} و{s['max_qty']}")
    price = int(
        (Decimal(qty) * s["price"] / 1000).quantize(
            Decimal("1"), rounding=ROUND_HALF_UP
        )
    )
    if not setting(c, "order_min") <= price <= setting(c, "order_max"):
        raise ValueError("قيمة الطلب خارج الحدود المالية المسموح بها.")
    return s, qty, price


def maintenance_exempt(c, uid):
    if not setting(c, "maintenance_staff", True):
        return False
    if uid == setting(c, "owner_telegram_id", 0) and uid:
        return True
    return (
        c.execute(
            "SELECT 1 FROM staff WHERE telegram_id=? AND enabled=1", (uid,)
        ).fetchone()
        is not None
    )


def order_create(c, uid, d):
    old = c.execute(
        "SELECT id FROM orders WHERE request_key=? AND user_id=?", (d["key"], uid)
    ).fetchone()
    if old:
        return old[0]
    u = one(c, "users", uid)
    if u["status"] == "blocked":
        raise ValueError("🚫 الحساب محظور. تواصل مع الدعم.")
    if setting(c, "maintenance") in ("all", "orders") and not maintenance_exempt(
        c, uid
    ):
        raise ValueError("🛠 الطلبات متوقفة مؤقتًا للصيانة.")
    s, qty, price = quote(c, d["service_id"], d["target"], d["quantity"])
    if price != d["price"]:
        raise ValueError(
            "تغير السعر. عد لتعديل الكمية ومراجعة السعر الحالي قبل التأكيد."
        )
    if u["balance"] < price:
        raise ValueError(
            f"رصيدك غير كافٍ. المطلوب إضافته: ${money(price-u['balance'])}. طلبك محفوظ."
        )
    cur = c.execute(
        "INSERT INTO orders(user_id,service_id,service_name,target,quantity,price,cost,request_key,created,updated) VALUES(?,?,?,?,?,?,?,?,?,?)",
        (
            uid,
            s["id"],
            s["name"],
            d["target"],
            qty,
            price,
            round(qty * s["cost"] / 1000),
            d["key"],
            now(),
            now(),
        ),
    )
    oid = cur.lastrowid
    lid = ledger(c, uid, -price, f"طلب TK-{oid:05d}", uid, "order:" + d["key"], oid)
    c.execute("UPDATE orders SET debit_id=? WHERE id=?", (lid, oid))
    audit(c, uid, "order.created", oid, {"status": "pending", "price": price})
    staff_notify(
        c,
        "orders",
        f'📦 طلب جديد TK-{oid:05d}\nالمستخدم: {uid}\n{s["name"]}\n{qty} — ${money(price)}',
    )
    c.execute("DELETE FROM drafts WHERE user_id=?", (uid,))
    return oid


def order_status(c, oid, status, actor, customer=False, note=""):
    o = one(c, "orders", oid)
    if customer and (o["user_id"] != actor or o["status"] != "pending"):
        raise ValueError("لا يمكن إلغاء هذا الطلب تلقائيًا. تواصل مع الدعم.")
    allowed = {
        "pending": {"processing", "cancelled", "refunded"},
        "processing": {"completed", "cancelled", "refunded"},
        "completed": {"refunded"},
        "cancelled": set(),
        "refunded": set(),
    }
    if status == o["status"]:
        return o
    if status not in allowed.get(o["status"], set()):
        raise ValueError("انتقال حالة غير مسموح. لا يمكن إعادة فتح طلب نهائي.")
    refund_id = o["refund_id"]
    if status in ("cancelled", "refunded") and not o["refunded"]:
        refund_id = ledger(
            c,
            o["user_id"],
            o["price"],
            f"استرداد TK-{oid:05d}",
            actor,
            f"refund:{oid}",
            oid,
        )
    c.execute(
        "UPDATE orders SET status=?,refunded=?,refund_id=?,note=?,updated=?,completed=? WHERE id=?",
        (
            status,
            int(status in ("cancelled", "refunded")),
            refund_id,
            note or o["note"],
            now(),
            now() if status == "completed" else o["completed"],
            oid,
        ),
    )
    audit(
        c,
        actor,
        "order.status",
        oid,
        {"before": o["status"], "after": status, "note": note},
    )
    notify(
        c,
        o["user_id"],
        render(
            c,
            "notification_order",
            "📦 تحديث TK-{id}\nالحالة: {status}\n{note}",
            {"id": f"{oid:05d}", "status": state_label(c, status), "note": note},
        ),
    )
    return one(c, "orders", oid)


def topup_create(c, uid, amount, method):
    u = one(c, "users", uid)
    if u["status"] == "blocked":
        raise ValueError("حسابك محظور")
    if setting(c, "maintenance") in ("all", "topups") and not maintenance_exempt(
        c, uid
    ):
        raise ValueError("الشحن متوقف للصيانة")
    if method not in ("manual", "stars") or not setting(c, method + "_enabled"):
        raise ValueError("طريقة الشحن غير متاحة")
    if not setting(c, "topup_min") <= amount <= setting(c, "topup_max"):
        raise ValueError("المبلغ خارج حدود الشحن")
    payload = secrets.token_urlsafe(24) if method == "stars" else None
    stars = (
        max(1, round(amount * setting(c, "stars_rate") / 100))
        if method == "stars"
        else None
    )
    cur = c.execute(
        "INSERT INTO topups(user_id,amount,method,status,payload,stars,created,updated) VALUES(?,?,?,?,?,?,?,?)",
        (
            uid,
            amount,
            method,
            "awaiting_payment" if method == "stars" else "awaiting_proof",
            payload,
            stars,
            now(),
            now(),
        ),
    )
    return one(c, "topups", cur.lastrowid)


def topup_review(c, tid, accept, reason, actor):
    t = one(c, "topups", tid)
    if t["status"] in ("approved", "rejected"):
        raise ValueError("تمت معالجة الطلب مسبقًا؛ لن تتكرر العملية.")
    if t["method"] != "manual" or t["status"] != "review" or not t["proof"]:
        raise ValueError("يجب استلام إثبات الدفع أولًا.")
    if not accept and not reason.strip():
        raise ValueError("سبب الرفض مطلوب")
    if accept:
        ledger(
            c, t["user_id"], t["amount"], f"شحن TOP-{tid:05d}", actor, f"topup:{tid}"
        )
    status = "approved" if accept else "rejected"
    c.execute(
        "UPDATE topups SET status=?,reason=?,updated=? WHERE id=?",
        (status, reason, now(), tid),
    )
    audit(c, actor, "topup." + status, tid, {"reason": reason})
    notify(
        c,
        t["user_id"],
        render(
            c,
            "notification_topup",
            "🧾 TOP-{id}\nالحالة: {status}\n{reason}",
            {"id": f"{tid:05d}", "status": state_label(c, status), "reason": reason},
        ),
    )


def invoice_validate(c, uid, p):
    r = c.execute(
        "SELECT * FROM topups WHERE payload=?", (p.get("invoice_payload"),)
    ).fetchone()
    if (
        not r
        or r["user_id"] != uid
        or r["method"] != "stars"
        or r["status"] != "awaiting_payment"
        or p.get("currency") != "XTR"
        or p.get("total_amount") != r["stars"]
    ):
        raise ValueError("بيانات الدفع لا تطابق الفاتورة")
    return dict(r)


def payment(c, uid, p):
    charge = p.get("telegram_payment_charge_id")
    if not charge:
        raise ValueError("معرف الدفع مفقود")
    if c.execute("SELECT 1 FROM payments WHERE charge_id=?", (charge,)).fetchone():
        return
    t = invoice_validate(c, uid, p)
    cur = c.execute(
        "INSERT INTO payments(charge_id,topup_id,user_id,amount,currency,created) VALUES(?,?,?,?,?,?)",
        (charge, t["id"], uid, t["amount"], "XTR", now()),
    )
    ledger(
        c,
        uid,
        t["amount"],
        "Telegram Stars",
        uid,
        "payment:" + charge,
        payment_id=cur.lastrowid,
    )
    c.execute(
        "UPDATE topups SET status='approved',updated=? WHERE id=?", (now(), t["id"])
    )
    notify(
        c,
        uid,
        render(
            c,
            "notification_stars_success",
            "✅ تم استلام الدفع بنجاح\n⭐ Telegram Stars\nالمبلغ: ${amount}\nالرصيد الجديد: ${balance}\n🧾 PAY-{id}",
            {
                "amount": money(t["amount"]),
                "balance": money(one(c, "users", uid)["balance"]),
                "id": f"{cur.lastrowid:05d}",
            },
        ),
    )
    audit(
        c,
        "system",
        "payment.verified",
        cur.lastrowid,
        {"topup": t["id"], "stars": t["stars"]},
    )


def ticket_message(c, tid, actor, body, staff=False, attachment=""):
    t = one(c, "tickets", tid)
    if not staff and t["user_id"] != actor:
        raise ValueError("غير مصرح")
    if t["status"] == "closed":
        raise ValueError("التذكرة مغلقة. أعد فتحها أولًا.")
    if not body.strip() and not attachment:
        raise ValueError("الرسالة فارغة")
    c.execute(
        "INSERT INTO messages(ticket_id,actor,body,attachment,created) VALUES(?,?,?,?,?)",
        (tid, str(actor), body, attachment, now()),
    )
    c.execute(
        "UPDATE tickets SET updated=?,status=? WHERE id=?",
        (now(), "processing" if staff else t["status"], tid),
    )
    if staff:
        notify(
            c,
            t["user_id"],
            render(
                c,
                "notification_support",
                "🎧 رد الدعم SUP-{id}\n{body}",
                {"id": f"{tid:05d}", "body": body},
            ),
        )
    else:
        staff_notify(c, "support", f"🎧 رسالة في SUP-{tid:05d}\n{body}")
    audit(c, actor, "ticket.message", tid, {"staff": staff})


def stats(c, start="", end="9999"):
    totals = {}
    totals["users"] = c.execute(
        "SELECT COUNT(*) FROM users WHERE created>=? AND created<=?", (start, end)
    ).fetchone()[0]
    totals["orders"] = c.execute(
        "SELECT COUNT(*) FROM orders WHERE created>=? AND created<=?", (start, end)
    ).fetchone()[0]
    totals["statuses"] = rows(
        c,
        "SELECT status,COUNT(*) count FROM orders WHERE created>=? AND created<=? GROUP BY status",
        (start, end),
    )
    # Recognize sales at completion, and refunds in the period of the actual refund.
    # A later refund must not erase the original month's completed sale.
    for key, column in (("sales", "price"), ("cost", "cost")):
        totals[key] = c.execute(
            f"SELECT COALESCE(SUM({column}),0) FROM orders WHERE completed IS NOT NULL AND completed>=? AND completed<=?",
            (start, end),
        ).fetchone()[0]
    totals["refunds"] = c.execute(
        "SELECT COALESCE(SUM(l.delta),0) FROM ledger l JOIN orders o ON o.refund_id=l.id WHERE l.created>=? AND l.created<=?",
        (start, end),
    ).fetchone()[0]
    totals["recognized_refunds"] = c.execute(
        "SELECT COALESCE(SUM(l.delta),0) FROM ledger l JOIN orders o ON o.refund_id=l.id WHERE o.completed IS NOT NULL AND l.created>=? AND l.created<=?",
        (start, end),
    ).fetchone()[0]
    totals["net_sales"] = totals["sales"] - totals["recognized_refunds"]
    totals["topups"] = c.execute(
        "SELECT COALESCE(SUM(amount),0) FROM topups WHERE status='approved' AND updated>=? AND updated<=?",
        (start, end),
    ).fetchone()[0]
    for key, kind in (("expenses", "expense"), ("fees", "fee")):
        totals[key] = c.execute(
            "SELECT COALESCE(SUM(amount),0) FROM expenses WHERE kind=? AND occurred_on>=? AND occurred_on<=?",
            (kind, start[:10], end[:10]),
        ).fetchone()[0]
    totals["profit"] = (
        totals["net_sales"] - totals["cost"] - totals["expenses"] - totals["fees"]
    )
    totals["chart"] = rows(
        c,
        "SELECT substr(created,1,10) day,COUNT(*) count, SUM(price) total FROM orders WHERE created>=? AND created<=? GROUP BY day ORDER BY day DESC LIMIT 14",
        (start, end),
    )
    return totals
