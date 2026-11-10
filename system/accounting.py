"""Append-only dated expenses and reversals, independent of customer wallets."""

from datetime import date
from .store import *


def expense_add(c, kind, amount, reason, occurred_on, actor, key, reversed_from=None):
    if (
        kind not in ("expense", "fee")
        or not isinstance(amount, int)
        or isinstance(amount, bool)
        or not amount
    ):
        raise ValueError("نوع المصروف أو المبلغ غير صالح")
    if (amount < 0) != bool(reversed_from):
        raise ValueError(
            "المبلغ يجب أن يكون موجبًا؛ استخدم عكس الحركة لتصحيح مصروف سابق"
        )
    if (
        not isinstance(reason, str)
        or not reason.strip()
        or len(reason) > 2000
        or not isinstance(key, str)
        or not 1 <= len(key) <= 150
    ):
        raise ValueError("السبب ومعرف العملية مطلوبان")
    reason = reason.strip()
    try:
        if date.fromisoformat(occurred_on).isoformat() != occurred_on:
            raise ValueError()
    except (ValueError, TypeError):
        raise ValueError("تاريخ الاستحقاق غير صالح؛ استخدم YYYY-MM-DD") from None
    previous = c.execute(
        "SELECT * FROM expenses WHERE operation_key=?", (key,)
    ).fetchone()
    if previous:
        if any(
            previous[k] != v
            for k, v in {
                "kind": kind,
                "amount": amount,
                "reason": reason,
                "occurred_on": occurred_on,
                "reversed_from": reversed_from,
            }.items()
        ):
            raise ValueError("معرف العملية مرتبط ببيانات مختلفة")
        return previous["id"]
    if reversed_from:
        original = one(c, "expenses", reversed_from)
        if (
            original["reversed_from"]
            or original["amount"] <= 0
            or original["amount"] != -amount
            or original["kind"] != kind
        ):
            raise ValueError("الحركة لا تقبل العكس")
        if c.execute(
            "SELECT 1 FROM expenses WHERE reversed_from=?", (reversed_from,)
        ).fetchone():
            raise ValueError("تم عكس المصروف مسبقًا؛ لن يتم عكسه مرتين")
    eid = c.execute(
        "INSERT INTO expenses(kind,amount,reason,occurred_on,actor,operation_key,reversed_from,created) VALUES(?,?,?,?,?,?,?,?)",
        (
            kind,
            amount,
            reason.strip(),
            occurred_on,
            str(actor),
            key,
            reversed_from,
            now(),
        ),
    ).lastrowid
    audit(
        c,
        actor,
        "expense.reversed" if reversed_from else "expense.created",
        eid,
        {
            "amount": amount,
            "kind": kind,
            "reason": reason,
            "occurred_on": occurred_on,
            "reversed_from": reversed_from,
        },
    )
    return eid
